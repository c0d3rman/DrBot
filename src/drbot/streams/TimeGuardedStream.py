from __future__ import annotations
from abc import abstractmethod
from typing import TypeVar
from ..log import log
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable
    from datetime import datetime

T = TypeVar("T")


class TimeGuardedStream(Stream[T]):
    """A stream for a Reddit endpoint that doesn't have a functioning `before` parameter.
    Instead, we keep track of a timestamp for each item and sweep the list ourselves."""

    def setup(self) -> None:
        if "last_processed_time" not in self.DR.storage:
            latest = self.get_latest_item()
            self.DR.storage["last_processed_time"] = self.timestamp(latest) if latest else None
            log.debug(f"Initialized last_processed_time for {self} - {self.DR.storage['last_processed_time']}")

    def get_items(self) -> Iterable[T]:
        items: list[T] = []
        last_processed_time: datetime | None = None
        for item in self.get_items_raw():
            # Stop early if we see the last processed ID - this check is repeated in Stream.run() but we want to quit early here if we can to save time
            if self.id(item) == self.DR.storage["last_processed"]:
                break
            d = self.timestamp(item)
            # If we're before our last processed time, stop regardless of whether we've seen the last_processed id (which is the whole point of TimeGuardedStream)
            if self.DR.storage["last_processed_time"] and d < self.DR.storage["last_processed_time"]:
                break
            # We get items from latest to earliest, so only the first item's last_processed_time should be kept
            if not last_processed_time:
                last_processed_time = d
            items.append(item)
        # If we processed at least one thing, update the last processed time
        if last_processed_time:
            self.DR.storage["last_processed_time"] = last_processed_time
        # Return items to be processed from earliest to latest
        return reversed(items)

    @abstractmethod
    def get_items_raw(self) -> Iterable[T]:
        """Return a raw iterator to the relevant reddit endpoint.
        E.g. reddit.sub.comments(limit=None)."""
        pass

    @abstractmethod
    def timestamp(self, item: T) -> datetime:
        """Given an item, return the timestamp associated with it."""
        pass
