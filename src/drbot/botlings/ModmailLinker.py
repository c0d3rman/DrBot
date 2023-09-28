from __future__ import annotations
import re
from praw.models import ModmailConversation
from ..util import markdown_comment, get_markdown_comments
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class ModmailLinker(Botling):
    """Scans modmails for removal messages and adds mobile-compatible links."""

    MARKER_COMMENT = "ModmailLinker"

    def setup(self) -> None:
        self.DR.streams.modmail_conversation.subscribe(self, self.handle)

    def handle(self, item: ModmailConversation) -> None:
        if not item.is_auto:
            log.debug(f"Skipping modmail {item.id} because it's manual.")
            return
        if item.is_internal:
            log.debug(f"Skipping modmail {item.id} because it's internal.")
            return
        if not item.is_repliable:
            log.debug(f"Skipping modmail {item.id} because it's non-repliable.")
            return
        if not re.match(fr"^Your (post|comment) from {self.DR.global_settings.subreddit} was removed$", item.subject, re.IGNORECASE):
            log.debug(f"Skipping modmail {item.id} because it has the wrong subject: {item.subject}")
            return

        # Make sure we haven't already linked this conversation
        for message in item.messages[1:]:
            if message.author == reddit.user.me().name and ModmailLinker.MARKER_COMMENT in get_markdown_comments(message.body_markdown):
                log.debug(f"Skipping modmail {item.id} since we've already linked it.")
                return

        result = re.search(r"\nOriginal (post|comment): (/r/.+)$", item.messages[0].body_markdown)
        if result is None:
            log.error(f"Unknown removal message format for modmail {item.id} - this shouldn't happen.")
            return

        log.info(f"Posting mobile link for modmail {item.id}.")
        body = f"""Beep boop, I'm a robot. Here's a mobile-compatible [link](https://reddit.com{result.group(2)}) for your removed {result.group(1)}.

{markdown_comment(ModmailLinker.MARKER_COMMENT)}"""
        if self.DR.global_settings.dry_run:
            log.info(f"""DRY RUN: would have sent the following reply to modmail {item.id} and archived it:
{body}""")
        else:
            item.reply(author_hidden=True, body=body)
            item.archive()
