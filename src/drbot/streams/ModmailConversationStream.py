from __future__ import annotations
from typing import Iterable
from datetime import datetime, timezone
from praw.models import ModmailConversation
from ..reddit import reddit
from .TimeGuardedStream import TimeGuardedStream


class ModmailConversationStream(TimeGuardedStream[ModmailConversation]):
    """A stream of modmail conversations."""

    def get_items_raw(self) -> Iterable[ModmailConversation]:
        return reddit.sub.modmail.conversations(state=self.state, limit=None)

    def id(self, item: ModmailConversation) -> str:
        return item.id

    def timestamp(self, item: ModmailConversation) -> datetime:
        return datetime.fromisoformat(item.messages[0].date).astimezone(timezone.utc)

    def get_latest_item(self) -> ModmailConversation | None:
        return next(reddit.sub.modmail.conversations(state=self.state, limit=1), None)
