from __future__ import annotations
import re
from praw.models import ModmailConversation
from drbot import settings, log, reddit
from drbot.handlers import Handler


class ModmailMobileLinkHandler(Handler[ModmailConversation]):
    """Scans modmails for removal messages and adds mobile-compatible links."""

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
        if not re.match(fr"^Your (post|comment) from {settings.subreddit} was removed$", item.subject, re.IGNORECASE):
            log.debug(f"Skipping modmail {item.id} because it has the wrong subject: {item.subject}")
            return

        result = re.search(r"\nOriginal (post|comment): (/r/.+)$", item.messages[0].body_markdown)
        if result is None:
            log.warning(f"Unknown removal message format for modmail {item.id} - this shouldn't happen.")
            return

        log.info(f"Posting mobile link for modmail {item.id}.")
        body = f"Beep boop, I'm a robot. Here's a mobile-compatible [link](https://reddit.com{result.group(2)}) for your removed {result.group(1)}."
        if settings.dry_run:
            log.info(f"""[DRY RUN: would have sent the following reply to modmail {item.id}:
{body}]""")
        else:
            item.reply(author_hidden=True, body=body)
            item.archive()
