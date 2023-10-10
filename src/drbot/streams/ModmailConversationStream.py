from __future__ import annotations
from praw.models import ModmailConversation
from ..reddit import reddit
from .BeforelessStream import BeforelessStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Generator


class ModmailConversationStream(BeforelessStream[ModmailConversation]):
    """A stream of modmail conversations.
    Doesn't include archived modmails by default - use state="archived" if you want only those."""

    def __init__(self, name: str | None = None, state: str = "all") -> None:
        super().__init__(name=name or f"{self.__class__.__name__}[{state}]")
        self.state = state  # Must happen here since get_latest_item is called before setup

    def get_raw_stream(self) -> Generator[ModmailConversation, None, None]:
        return reddit.sub.mod.stream.modmail_conversations(state=self.state, pause_after=0)

    def id(self, item: ModmailConversation) -> str:
        return item.id

    def get_latest_item(self) -> ModmailConversation | None:
        return next(reddit.sub.modmail.conversations(state=self.state, limit=1), None)
