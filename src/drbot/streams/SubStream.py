from __future__ import annotations
from abc import abstractmethod
from typing import TypeVar
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
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
