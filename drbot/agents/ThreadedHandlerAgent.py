from typing import TypeVar
from drbot.agents import ThreadedAgent, HandlerAgent

T = TypeVar("T")


class ThreadedHandlerAgent(ThreadedAgent, HandlerAgent[T]):
    def _run(self) -> None:
        HandlerAgent.run(self)
