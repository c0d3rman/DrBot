from __future__ import annotations
import heapq
from datetime import datetime, timezone
from praw.models import ModmailMessage
from ..reddit import reddit
from .TimeGuardedStream import TimeGuardedStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable


class ModmailMessageStream(TimeGuardedStream[ModmailMessage]):
    """A stream of modmail messages, sorted from oldest to newest without regard for which conversation they're in.
    Doesn't include archived modmails by default - use state="archived" if you need that."""

    def __init__(self, name: str | None = None, state: str = "all") -> None:
        super().__init__(name=name or f"{self.__class__.__name__}[{state}]")
        self.state = state  # Must happen here since get_latest_item is called before setup

    def get_items_raw(self) -> Iterable[ModmailMessage]:
        heap = []
        heapq.heapify(heap)

        conversation_i = 0
        for conversation in reddit.sub.modmail.conversations(state=self.state, limit=None, sort="recent"):
            message_i = 0
            conversation_i += 1

            # Pop from the heap until the next conversation's latest message is newer than anything we've seen
            while len(heap) > 0 and -self.timestamp(conversation.messages[-1]).timestamp() >= heap[0][0]:
                yield heapq.heappop(heap)[3]

            # Ingest all messages into the heap
            for message in conversation.messages:
                message_i += 1
                heapq.heappush(heap, (-self.timestamp(message).timestamp(), conversation_i, -message_i, message))  # Make sure that we tiebreak timestamps and maintain the order reddit gives us - first (newest) conversations first, last (newest) messages first

    def id(self, item: ModmailMessage) -> str:
        return item.id

    def timestamp(self, item: ModmailMessage) -> datetime:
        return datetime.fromisoformat(item.date).astimezone(timezone.utc)

    def get_latest_item(self) -> ModmailMessage | None:
        latest_conversation = next(reddit.sub.modmail.conversations(state=self.state, limit=1, sort="recent"), None)
        if latest_conversation is None:
            return None
        return latest_conversation.messages[-1]
