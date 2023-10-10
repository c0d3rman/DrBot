from __future__ import annotations
from abc import abstractmethod
from typing import TypeVar
from datetime import datetime
from praw.models import ModmailConversation, ModmailMessage
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Callable
    from ..DrBot import DrBotRep

T = TypeVar("T")


class SubStream(Stream[T]):
    """A SubStream that filters for only some items from a parent Stream."""

    def __init__(self, parent: Stream[T], name: str | None = None) -> None:
        super().__init__(name or f"{self.__class__.__name__}[{parent.name}]")
        self.__parent = parent
        self.__items: list[T] = []

    def setup(self) -> None:
        self.parent.subscribe(self, self._handle)

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

    def accept_registration(self, DR: DrBotRep) -> None:
        # Make sure parent is registered first, otherwise we'll output its items one polling cycle late
        if not self.parent.is_registered:
            raise RuntimeError(f"SubStream's parent {self.parent} must be registered before it.")
        super().accept_registration(DR)

    @abstractmethod
    def skip_item(self, item: T) -> bool:
        """Implement this method to tell the SubStream which items from the parent Stream it should reject."""
        pass


class UnionStream(Stream[T]):
    """A UnionStream that combines multiple parent Streams.
    Uses the ID of each respective parent Stream for its items,
    so if your ID functions are inconsistent but your streams share items you may reprocess some things."""

    def __init__(self, *streams: Stream[T], name: str | None = None) -> None:
        super().__init__(name or self.__class__.__name__ + "[" + ",".join(s.name for s in streams) + "]")
        assert len(streams) > 0, f"You must provide at least one stream to UnionStream."
        self.__streams = streams
        self.__items: list[T] = []
        self.__ids: dict[Stream[T], set[int]] = {stream: set() for stream in streams}

    def setup(self) -> None:
        for stream in self.streams:
            stream.subscribe(self, self._make_handler(stream), self._make_start_run(stream))

    @property
    def streams(self):
        """The Streams which this UnionStream draws from."""
        return self.__streams

    def _make_handler(self, stream: Stream[T]) -> Callable[[T], None]:
        """Make a handler for a given parent stream."""
        def _handle(item: T) -> None:
            self.__items.append(item)
            self.__ids[stream].add(id(item))  # Save this item's numerical python ID so we can find its parent later
        return _handle

    def _make_start_run(self, stream: Stream[T]) -> Callable[[], None]:
        """Make a start_run function for a given parent stream."""
        def _start_run() -> None:
            # Clear the respective stream's ID dict,
            # since otherwise it will build up indefinitely and run us out of memory over time
            self.__ids[stream].clear()
        return _start_run

    def get_items(self) -> list[T]:
        items = self.sort_items(self.__items)
        self.__items = []
        return items

    def id(self, item: T) -> T:
        """Since this must use the IDs of the parent streams,
        an item's ID is available only until the next run from its associated parent stream
        and only while it's still in memory.
        Failing that, we default to the first parent stream's ID function.
        If all of your streams have the same ID function, this isn't a concern."""
        for stream, ids in self.__ids.items():  # If we can find it, use the relevant parent's ID function
            if id(item) in ids:
                return stream.id(item)  # This will favor earlier parents in ties
        return self.__streams[0].id(item)

    def accept_registration(self, DR: DrBotRep) -> None:
        # Make sure all parents are registered first, otherwise we'll output their items one polling cycle late
        unregistered_parents = [str(parent) for parent in self.streams if not parent.is_registered]
        if len(unregistered_parents) > 0:
            raise RuntimeError("All of UnionStream's parent streams must be registered before it. Unregistered:\n- " + "\n- ".join(unregistered_parents))
        super().accept_registration(DR)

    def sort_items(self, items: list[T]) -> list[T]:
        """You can override this method if you want your UnionStream's output sorted somehow (e.g. by timestamp).
        By default it will be [all items from parent 1, all items from parent 2, etc.]"""
        return items


class ModmailConversationUnionStream(UnionStream[ModmailConversation]):
    def sort_items(self, items: list[ModmailConversation]) -> list[ModmailConversation]:
        return list(sorted(items, key=lambda item: datetime.fromisoformat(item.messages[-1].date)))


class ModmailMessageUnionStream(UnionStream[ModmailMessage]):
    def sort_items(self, items: list[ModmailMessage]) -> list[ModmailMessage]:
        return list(sorted(items, key=lambda item: datetime.fromisoformat(item.date)))
