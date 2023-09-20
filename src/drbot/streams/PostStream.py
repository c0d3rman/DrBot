from __future__ import annotations
from datetime import datetime, timezone
from praw.models import Submission
from ..reddit import reddit
from ..Stream import Stream


class PostStream(Stream[Submission]):
    """A stream of posts."""

    def get_items(self) -> list[Submission]:
        items: list[Submission] = []
        for item in reddit.sub.new(limit=None):
            # This assumes we never have a case where both:
            #   1. The two newest posts have identical timestamps
            #   2. We only get the first post in one request, then get the second post in the next request
            if self.storage["last_processed"] and self.id(item) <= self.storage["last_processed"]:
                break
            items.append(item)
        return list(reversed(items))  # Process from earliest to latest

    def id(self, item: Submission) -> datetime:
        return datetime.fromtimestamp(item.created_utc, timezone.utc)

    def get_latest_item(self) -> Submission | None:
        return next(reddit.sub.new(limit=1), None)
