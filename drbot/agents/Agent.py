from __future__ import annotations
from abc import ABC, abstractmethod
from drbot import log
from drbot.stores import DataStore


class Agent(ABC):
    """Scans incoming entries of type T and runs handlers on them.
    Manages storage for the handler."""

    @property
    def data_store(self):
        if not self.name in self._data_store:
            self._data_store[self.name] = {}
        return self._data_store[self.name]

    def __init__(self, data_store: DataStore, name: str | None = None) -> None:
        super().__init__()
        if name is None:  # By default, the name is just the class name
            name = self.__class__.__name__
        self.name = name
        self._data_store = data_store

        # Check for DataStore conflicts
        if self.name in self._data_store:
            raise Exception(f'Name "{self.name}" already exists in the DataStore.')

    @abstractmethod
    def run(self) -> None:
        log.debug(f"{self.name} running.")
