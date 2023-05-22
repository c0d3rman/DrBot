from __future__ import annotations
from datetime import datetime
from praw.models import Submission
from drbot import reddit
from drbot.agents import HandlerAgent
# from drbot.agents import ThreadedHandlerAgent


class PostAgent(HandlerAgent[Submission]):
    """Scans incoming posts and runs sub-tools on them."""

    def get_items(self) -> list[Submission]:
        items = []
        for item in reddit().sub.new(limit=None):
            # This assumes we never have a case where:
            #   1. The two newest posts have identical timestamps
            #   2. We only get the first post in one request, then get the second post in the next request
            if self.id(item) <= self.data_store["_meta"]["last_processed"]:
                break
            items.append(item)
        return list(reversed(items))  # Process from earliest to latest

    def id(self, item: Submission) -> str:
        return datetime.fromtimestamp(item.created_utc)

    def get_latest_item(self) -> list[Submission]:
        return next(reddit().sub.new(limit=1))
