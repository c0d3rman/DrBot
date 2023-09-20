from __future__ import annotations
from datetime import datetime
from pytz import UTC
from praw.models import ModmailConversation
from ..log import log
from ..reddit import reddit
from ..DrStream import DrStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from ..storage import DrDict


class ModmailStream(DrStream[ModmailConversation]):
    """A stream of modmail conversations."""

    def __init__(self, name: str | None = None, state: str = "all") -> None:
        super().__init__(name=name)
        self.state = state  # Must happen here since get_latest_item is called before setup

    def setup(self) -> None:
        self.storage["last_processed_time"] = UTC.localize(datetime.min)  # TBD: Still relevant? -> Must happen last so our name is initialized

    def get_items(self) -> list[ModmailConversation]:
        # This endpoint doesn't have a 'before' parameter for some reason, so we do it manually
        items: list[ModmailConversation] = []
        for item in reddit.sub.modmail.conversations(state=self.state, limit=None):
            if self.id(item) == self.storage["last_processed"]:
                break
            # Safety check to make sure we don't go back in time somehow, which happened once.
            d = datetime.fromisoformat(item.messages[0].date)
            if d < self.storage["last_processed_time"]:
                break
            self.storage["last_processed_time"] = d
            items.append(item)

            # TEMP
            if len(items) >= 10:
                break
        return list(reversed(items))  # Process from earliest to latest

    def id(self, item: ModmailConversation) -> str:
        return item.id

    def get_latest_item(self) -> ModmailConversation | None:
        return
        return next(reddit.sub.modmail.conversations(state=self.state, limit=1))

    # def skip_item(self, item: ModmailConversation) -> bool:
    #     # Make sure DrBot's not already in the thread.
    #     me = reddit().user.me().name
    #     return any(me == author.name for author in item.authors)
    # TBD: do we want this? Do we maybe want to skip only ones started by DrBot?
