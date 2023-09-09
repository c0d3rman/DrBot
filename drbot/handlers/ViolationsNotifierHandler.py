from __future__ import annotations
import re
from praw.models import ModmailConversation
from datetime import datetime, timezone, timedelta
from drbot import settings, log, reddit
from drbot.handlers import Handler, PointsHandler


class ViolationsNotifierHandler(Handler[ModmailConversation]):
    """Scans modmails for ban messages and adds a notice with a summary of the user's violations.
    Relies on a PointHandler to gather said violations."""

    def __init__(self, points_handler: PointsHandler, name: str | None = None):
        self.points_handler = points_handler
        super().__init__(name)

    def handle(self, item: ModmailConversation) -> None:
        if not item.is_auto:
            return
        if item.is_internal:
            return
        if not item.is_repliable:
            return
        if not re.match(fr"^u/[^ ]+ is (?:temporarily|permanently) banned from r/{settings.subreddit}$", item.subject, re.IGNORECASE):
            return

        # Make sure the user isn't muted, since for some reason reddit freaks out if we try to message them
        if len(reddit().request(method="GET", path="/r/DebateReligion/about/muted",
                                params={"user": item.participant})['data']['children']) > 0:
            log.info(f"Couldn't send a violations notice to u/{item.participant} on modmail {item.id} since they are muted and reddit freaks out about that.")
            return

        # Find the ban message's associated ViolationInterval by matching their timestamps.
        # Sadly there's no ID or similar that we can use, but unless you're banning a user multiple times a minute it really shouldn't be an issue.
        ban_date = datetime.fromisoformat(item.messages[0].date)
        violations = self.points_handler.get_violations(item.participant)[:-1]  # Don't include violations after the most recent ban
        interval_distances = [(interval, abs(datetime.fromtimestamp(interval.ban.created_at, timezone.utc) - ban_date)) for interval in violations]
        closest_interval, time_gap = min(interval_distances, key=lambda p: p[1])
        epsilon = timedelta(hours=1)  # The maximum time gap before we consider a ban message not associated with a ban anymore
        if time_gap >= epsilon:  # Technically the ban message should always come after the ban, but who knows what Reddit might do, so we compare the absolute time gap
            log.warning(f"No matching ban could be found for ban message {item.id} of user u/{item.participant}, so no violations notice could be sent.")
            return
        log.debug(f"Found a matching ban {closest_interval.ban.id} within {time_gap} of ban message {item.id}.")

        # Prepare modmail message
        violation_string = closest_interval.to_string(self.points_handler, include_points=False, relevant_only=True)
        if len(violation_string.strip()) == 0:
            log.info(f"Skipping violations notice for banned user u/{item.participant} because they have no relevant violations on record.")
            return
        message = f"Beep boop, I'm a robot. Here's a list of recent violations which contributed to your ban:\n\n"
        message += violation_string

        log.info(f"Sending banned user u/{item.participant} a summary of their violations for ban notice {item.id}.")

        if settings.dry_run:
            log.info(f"""[DRY RUN: would have sent the following reply to modmail {item.id}:
{message}]""")
        else:
            item.reply(author_hidden=True, body=message)
            item.archive()
