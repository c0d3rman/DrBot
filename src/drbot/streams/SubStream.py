from __future__ import annotations
from abc import abstractmethod
from typing import TypeVar, Generic
from ..Stream import Stream

T = TypeVar("T")


class SubStream(Stream[T]):
    """A SubStream that filters for only some items from a parent Stream."""

    def __init__(self, parent: Stream[T], name: str | None = None) -> None:
        super().__init__(name)
        self.__parent = parent
        self.__items: list[T] = []
        self.__parent.subscribe(self, self._handle)

    @property
    def parent(self):
        """The parent Stream which this SubStream draws from."""
        return self.__parent

    def _handle(self, item: T) -> None:
        self.__items.append(item)

    def get_items(self) -> list[T]:
        items = self.__items
        self.__items = []
        return items

    def id(self, item: T) -> T:
        return self.__parent.id(item)

    def get_latest_item(self) -> T | None:
        # This may be an irrelevant item, but just as with Stream it's OK,
        # since irrelevant items are still returned by get_item and can be used to know where to start -
        # they're only skipped by skip_item during actual processing.
        return self.__parent.get_latest_item()

    @abstractmethod
    def skip_item(self, item: T) -> bool:
        """Implement this method to tell the SubStream which items from the parent Stream it should reject."""
        pass
