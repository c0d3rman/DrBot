from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Optional
from drbot.agents import Agent


T = TypeVar("T")


class Handler(ABC, Generic[T]):
    """For use with Agents.
    Scans incoming items entries one at a time."""

    def __init__(self, name: Optional[str] = None):
        if name is None:  # By default, the name is just the class name
            name = self.__class__.__name__
        self.name = name

    @property
    def data_store(self):
        return self.agent.get_data_store(self)

    def setup(self, agent: Agent[T]) -> None:
        """Called to set up the handler when it is registered."""
        self.agent = agent

    def start_run(self) -> None:
        """Called by the agent when it starts looping through a new batch.
        Can optionally be overriden to do things like invalidating caches."""
        pass

    @abstractmethod
    def handle(self, item: T) -> None:
        """The core handler method. Handle a single item."""
        pass
