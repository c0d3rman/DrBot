from __future__ import annotations
from abc import abstractmethod
from typing import TypeVar
from ..log import log
from ..util import name_of
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
        if not "last_processed_time" in self.DR.storage:
            latest = self.get_latest_item()
            self.DR.storage["last_processed_time"] = self.timestamp(latest) if latest else None
            log.debug(f"Initialized last_processed_time for {self.kind} {name_of(self)} - {self.DR.storage['last_processed_time']}")

    def get_items(self) -> Iterable[T]:
        items: list[T] = []
        for item in self.get_items_raw():
            if self.DR.storage["last_processed"] and self.id(item) == self.DR.storage["last_processed"]:
                break
            # Safety check to make sure we don't go back in time somehow, which happened once.
            d = self.timestamp(item)
            if self.DR.storage["last_processed"] and d < self.DR.storage["last_processed_time"]:
                break
            self.DR.storage["last_processed_time"] = d
            items.append(item)
        return reversed(items)  # Process from earliest to latest

    @abstractmethod
    def get_items_raw(self) -> Iterable[T]:
        """Return a raw iterator to the relevant reddit endpoint.
        E.g. reddit.sub.comments(limit=None)."""
        pass

    @abstractmethod
    def timestamp(self, item: T) -> datetime:
        """Given an item, return the timestamp associated with it."""
        pass
