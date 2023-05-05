from __future__ import annotations
from abc import abstractmethod
from typing import Generic, TypeVar
from drbot import log
from drbot.agents import Agent
from drbot.handlers import Handler
from drbot.stores import DataStore


T = TypeVar("T")


class HandlerAgent(Agent, Generic[T]):
    """Scans incoming entries of type T and runs handlers on them.
    Manages storage for the handler."""

    def __init__(self, data_store: DataStore, name: str | None = None) -> None:
        super().__init__(data_store, name)
        self.handlers = {}

        # Initialize last_processed
        latest = self.get_latest_item()
        self._data_store[self.name] = {"_meta": {"last_processed": None if latest is None else self.id(latest)}}

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
        super().run()

        items = [item for item in self.get_items() if not self.skip_item(item)]
        if len(items) == 0:
            return
        log.info(f"{self.name} processing {len(items)} new items.")

        # Let all the handlers know we're starting a new run
        for handler in self.handlers.values():
            handler.start_run()

        # Process items
        for item in items:
            log.debug(f"{self.name} handling item {self.id(item)}")
            for handler in self.handlers.values():
                handler.handle(item)
            self.data_store["_meta"]["last_processed"] = self.id(item)

        # Make a local backup
        self._data_store.save()

    @abstractmethod
    def get_items(self) -> list[T]:
        """Get all new items for the agent to process. E.g. all new modlog entries.
        You can use self.data_store["_meta"]["last_processed"] for this purpose.
        Make sure to return a list, not a generator."""
        pass

    @abstractmethod
    def id(self, item: T) -> str:
        """Get a unique ID for a given item.
        Used for keeping track of last_processed."""
        pass

    def get_latest_item(self) -> T | None:
        """Get the latest item. Used for setting the initial last_processed,
        so you don't process items stretching backwards forever on the first run.
        If you don't return an item (or don't implement this), it will in fact process backwards forever."""
        pass

    def skip_item(self, item: T) -> bool:
        """Optionally, you can override this to skip cetain items.
        mostly useful to avoid updating last_processed with your own modlog entries,
        which can get you stuck in update loops."""
        return False
