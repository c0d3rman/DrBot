from __future__ import annotations
import json
from typing import cast
from praw.models import Submission, Comment
from ..Botling import Botling
from ..log import log
from ..reddit import reddit

class ReportReviewBotling(Botling):
    """
    A Botling that periodically checks the mod queue for reported items and uses the LLM to review them.
    It can Approve, Remove, Spam, or Ignore items based on the LLM's decision.
    """
    
    default_settings = {
        "check_interval_minutes": 10,
        "disallow_removal": True,
        "rule_instructions": []
    }

    DEFAULT_INSTRUCTIONS = (
        "You are an AI assistant helping moderators review reported content on Reddit.\n"
        "Your goal is to handle \"low-hanging fruit\"—cases where the violation is obvious or the content is clearly fine.\n"
        "If the decision is ambiguous, difficult, or requires subtle context you don't have, you MUST reply with ACTION: NOT_SURE.\n"
        "Do not attempt to make a decision if you are not 99% sure.\n"
        "\n"
        "Determine if the content violates the subreddit rules.\n"
        "Respond ONLY with JSON in this exact schema:\n"
        "{\n"
        "  \"action\": \"APPROVE\" | \"REMOVE\" | \"SPAM\" | \"NOT_SURE\",\n"
        "  \"reason_id\": <string or null>,\n"
        "  \"reasoning\": \"concise explanation\"\n"
        "}\n"
        "If action is REMOVE or SPAM, reason_id must be the matching removal reason ID from the provided removal reasons list.\n"
        "If action is APPROVE or NOT_SURE, reason_id must be null."
    )

    def setup(self) -> None:
        self.removal_reasons = list(reddit.sub.mod.removal_reasons)
        self.removal_reasons_by_id = {reason.id: reason for reason in self.removal_reasons}
        self.removal_reasons_by_short_id = {
            reason.id.split("-", 1)[0]: reason for reason in self.removal_reasons
        }
        self._processed_in_run = 0
        self.DR.streams.reports.subscribe(self, self.handle_report, self.start_run)

    def validate_settings(self) -> None:
        rule_instructions = self.DR.settings.rule_instructions
        assert isinstance(rule_instructions, list), "rule_instructions must be a list"
        for entry in rule_instructions:
            assert isinstance(entry, dict), "rule_instructions entries must be dicts"
            has_rule_num = "rule_num" in entry
            has_reason_title = "reason_title" in entry
            assert has_rule_num != has_reason_title, "each rule_instructions entry must have exactly one of rule_num or reason_title"
            assert isinstance(entry.get("instruction"), str), "rule_instructions instruction must be a string"
            if has_rule_num:
                assert isinstance(entry["rule_num"], int), "rule_instructions rule_num must be an int"
            else:
                assert isinstance(entry["reason_title"], str), "rule_instructions reason_title must be a string"

    def start_run(self) -> None:
        log.info("Checking reports for review...")
        self._processed_in_run = 0

    def handle_report(self, item: Submission | Comment) -> None:
        # TEMP: testing shim - stop after 3 items
        if self._processed_in_run >= 3:
            return
        self.process_item(item)
        self._processed_in_run += 1

    def process_item(self, item: Submission | Comment) -> None:
        # Start constructing the prompt
        # Extract reports
        # user_reports and mod_reports can have extra fields, so avoid tuple unpacking
        reports_list = []
        for report in item.user_reports:
            reason = report[0] if len(report) > 0 else "[no reason]"
            count = report[1] if len(report) > 1 else 1
            reports_list.append(f"User Report ({count}): {reason}")
        for report in item.mod_reports:
            reason = report[0] if len(report) > 0 else "[no reason]"
            count = report[1] if len(report) > 1 else 1
            reports_list.append(f"Mod Report ({count}): {reason}")
             
        reports_text = "\n".join(reports_list)
        
        # Extract content
        if isinstance(item, Submission):
            content_type = "Submission"
            content_text = f"Title: {item.title}\nBody:\n{item.selftext}"
            author = item.author.name if item.author else "[deleted]"
            context_text = "N/A (Top-level submission)"
        else:
            content_type = "Comment"
            content_text = f"Body:\n{item.body}"
            author = item.author.name if item.author else "[deleted]"
            
            # Fetch Context
            context_text = ""
            try:
                # Submission context
                subm = item.submission
                context_text += f"Submission Title: {subm.title}\n"
                if subm.selftext:
                     # Truncate selftext
                     body_preview = subm.selftext[:500] + "..." if len(subm.selftext) > 500 else subm.selftext
                     context_text += f"Submission Body: {body_preview}\n"

                # Parent context
                parent = item.parent()
                if isinstance(parent, Comment):
                     p_author = parent.author.name if parent.author else '[deleted]'
                     context_text += f"\nParent Comment by u/{p_author}:\n{parent.body}\n"
                elif isinstance(parent, Submission):
                     context_text += "\n(Parent is the submission itself)\n"
            except Exception as e:
                log.warning(f"Failed to fetch context for {item.id}: {e}")
                context_text += f"\n[Error fetching context: {e}]"

        rule_notes_by_num: dict[int, str] = {}
        reason_notes_by_title: dict[str, str] = {}
        for entry in self.DR.settings.rule_instructions:
            if "rule_num" in entry:
                rule_notes_by_num[entry["rule_num"]] = entry["instruction"]
            else:
                reason_notes_by_title[entry["reason_title"]] = entry["instruction"]

        subreddit_rules = []
        for idx, rule in enumerate(reddit.sub.rules, start=1):
            extra = rule_notes_by_num.get(idx)
            if extra:
                subreddit_rules.append(f"{idx}. {rule.short_name}\n{rule.description}\nExtra: {extra}")
            else:
                subreddit_rules.append(f"{idx}. {rule.short_name}\n{rule.description}")
        rules_text = "\n".join(subreddit_rules)

        removal_reasons = []
        for reason in self.removal_reasons:
            extra = reason_notes_by_title.get(reason.title)
            short_id = reason.id.split("-", 1)[0]
            header = f"{short_id}: {reason.title}"
            if extra:
                removal_reasons.append(f"{header}\n{reason.message}\nExtra: {extra}")
            else:
                removal_reasons.append(f"{header}\n{reason.message}")
        removal_reasons_text = "\n".join(removal_reasons)

        system_prompt = (
            self.DEFAULT_INSTRUCTIONS
            + f"\n\nSubreddit rules (for context):\n{rules_text}\n"
            + f"\nRemoval reasons (use reason_id below):\n{removal_reasons_text}\n"
        )

        user_prompt = f"""
Type: {content_type}
Author: {author}
ID: {item.id}

Content:
---
{content_text}
---

Context:
---
{context_text}
---

Reports:
{reports_text}
"""

        log.info(
            "ReportReviewBotling raw prompt:\n"
            f"{system_prompt}\n\n---\n\n{user_prompt}"
        )

        log.debug(f"Requesting LLM review for {item.id}...")
        # response = self.DR.llm.generate(prompt) -> Changed signature
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "report_review_decision",
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string", "enum": ["APPROVE", "REMOVE", "SPAM", "NOT_SURE"]},
                        "reason_id": {"type": ["string", "null"]},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["action", "reason_id", "reasoning"],
                },
                "strict": True,
            },
        }
        response = self.DR.llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            response_format=response_format,
        )
        
        if not response:
            log.warning(f"LLM failed to return a response for {item.id} (capped or error).")
            return
            
        try:
            parsed = json.loads(response)
        except Exception as e:
            log.error(f"Invalid JSON response for {item.id}: {e} | Raw: {response}")
            return

        self.handle_decision(item, parsed)

    def handle_decision(self, item: Submission | Comment, response: dict[str, object]) -> None:
        decision = cast(str, response["action"]).upper()
        reason_id = cast(str | None, response["reason_id"])
        reasoning = cast(str, response["reasoning"])

        log.info(f"LLM reviewed {item.id}. Decision: {decision}. Reasoning: {reasoning[:100]}...")

        if self.DR.global_settings.dry_run:
            if decision in ("REMOVE", "SPAM"):
                reason = self.removal_reasons_by_id[reason_id]
                log.info(f"DRY RUN: Would execute {decision} on {item.id} with reason '{reason.title}'")
            else:
                log.info(f"DRY RUN: Would execute {decision} on {item.id}")
            return

        if decision == "APPROVE":
            item.mod.approve()
            log.info(f"Approved {item.id}")
        elif decision == "REMOVE":
            reason = self.removal_reasons_by_short_id[reason_id]
            if self.DR.settings.get("disallow_removal", True):
                bot_name = reddit.user.me().name
                item.report(f"REMOVE suggested - {reason.title} ({reason.id.split('-', 1)[0]})")
                log.info(f"Reported {item.id} with removal recommendation '{reason.title}'")
            else:
                item.mod.remove(reason_id=reason.id)
                log.info(f"Removed {item.id} with reason '{reason.title}'")
        elif decision == "SPAM":
            reason = self.removal_reasons_by_short_id[reason_id]
            if self.DR.settings.get("disallow_removal", True):
                bot_name = reddit.user.me().name
                item.report(f"DrBot ({bot_name}): SPAM suggested ({reason.title} - {reason.id.split('-', 1)[0]}).")
                log.info(f"Reported {item.id} with spam recommendation '{reason.title}'")
            else:
                item.mod.remove(spam=True, reason_id=reason.id)
                log.info(f"Spammed {item.id} with reason '{reason.title}'")
        elif decision == "NOT_SURE":
            # Punt to human mods, do nothing but log
            log.info(f"Not sure about {item.id} (Ambiguous/Hard)")

