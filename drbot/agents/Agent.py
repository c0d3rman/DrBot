from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Generic, TypeVar, List
from drbot import log
from drbot.handlers import Handler
from drbot.stores import DataStore


T = TypeVar("T")


class Agent(ABC, Generic[T]):
    """Scans incoming entries of type T and runs handlers on them.
    Manages storage for the handler."""

    @property
    def data_store(self):
        return self._data_store[self.name]

    def __init__(self, data_store: DataStore, name: Optional[str] = None) -> None:
        super().__init__()
        if name is None:  # By default, the name is just the class name
            name = self.__class__.__name__
        self.name = name
        self._data_store = data_store
        self.handlers = {}

        # Initialize our slice of the DataStore
        if self.name in self._data_store:
            raise Exception(f'Name "{self.name}" already exists in the DataStore.')
        self._data_store[self.name] = {"_meta": {"last_processed": self.id(self.get_latest_item())}}

    def get_data_store(self, handler: Handler) -> dict:
        """Get a reserved slice of the DataStore for a given handler.
        Creates one if it doesn't already exist."""

        if not handler.name in self.data_store:
            self.data_store[handler.name] = {}
        return self.data_store[handler.name]

    def register(self, handler: Handler[T]) -> None:
        """Register a handler with the agent."""

        if handler.name == "_meta":
            raise Exception("Illegal handler name - cannot be _meta.")
        if handler.name in self.handlers:
            log.error(f"Handler {handler.name} already registered, overwriting.")
        self.handlers[handler.name] = handler
        handler.setup(self)

    def run(self) -> None:
        items = self.get_items()
        if len(items) == 0:
            return
        log.info(f"{self.name} processing {len(items)} new items.")

        # Let all the handlers know we're starting a new run
        for handler in self.handlers.values():
            handler.start_run()

        # Process items
        for item in items:
            for handler in self.handlers.values():
                handler.handle(item)
        self.data_store["_meta"]["last_processed"] = self.id(item)

        # Make a local backup
        self._data_store.save()

    @abstractmethod
    def get_items(self) -> List[T]:
        """Get all new items for the agent to process. E.g. all new modlog entries.
        You can use self.data_store["_meta"]["last_processed"] for this purpose.
        Make sure to return a list, not a generator."""
        pass

    @abstractmethod
    def id(self, item: T) -> str:
        """Get a unique ID for a given item.
        Used for keeping track of last_processed."""
        pass

    def get_latest_item(self) -> Optional[T]:
        """Get the latest item. Used for setting the initial last_processed,
        so you don't process items stretching backwards forever on the first run.
        If you don't return an item (or don't implement this), it will in fact process backwards forever."""
        pass
