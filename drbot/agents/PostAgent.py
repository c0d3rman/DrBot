from __future__ import annotations
from typing import List, Optional
from praw.models import Submission
from drbot import reddit
from drbot.agents import Agent


class PostAgent(Agent[Submission]):
    """Scans incoming posts and runs sub-tools on them."""

    def get_items(self) -> List[Submission]:
        return list(reddit.sub.new(
            limit=None, params={"before": self.data_store["_meta"]["last_processed"]}))

    def id(self, item: Submission) -> str:
        return item.fullname

    def get_latest_item(self) -> Optional[Submission]:
        return next(reddit.sub.new(limit=1))
