from __future__ import annotations
from typing import Iterable
from datetime import datetime, timezone
from praw.models import ModmailConversation
from praw.models.reddit.modmail import ModmailConversation
from ..reddit import reddit
from .TimeGuardedStream import TimeGuardedStream


class ModmailStream(TimeGuardedStream[ModmailConversation]):
    """A stream of modmail conversations."""

    def __init__(self, name: str | None = None, state: str = "all") -> None:
        super().__init__(name=name)
        self.state = state  # Must happen here since get_latest_item is called before setup
    
    def get_items_raw(self) -> Iterable[ModmailConversation]:
        return reddit.sub.modmail.conversations(state=self.state, limit=None)

    def id(self, item: ModmailConversation) -> str:
        return item.id
    
    def timestamp(self, item: ModmailConversation) -> datetime:
        return datetime.fromisoformat(item.messages[0].date).astimezone(timezone.utc)
    
    def get_latest_item(self) -> ModmailConversation | None:
        return next(reddit.sub.modmail.conversations(state=self.state, limit=1), None)

    # def skip_item(self, item: ModmailConversation) -> bool:
    #     # Make sure DrBot's not already in the thread.
    #     me = reddit().user.me().name
    #     return any(me == author.name for author in item.authors)
    # TBD: do we want this? Do we maybe want to skip only ones started by DrBot?
