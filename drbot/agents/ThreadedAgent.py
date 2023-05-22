from __future__ import annotations
from abc import abstractmethod
from drbot.agents import Agent
from threading import Thread
from drbot import log
from drbot.stores import ThreadedDataStore


class ThreadedAgent(Agent):
    def __init__(self, data_store: ThreadedDataStore, name: str | None = None) -> None:
        assert isinstance(data_store, ThreadedDataStore)
        super().__init__(data_store, name)
        self.thread = None

    def run(self) -> None:
        if not self.thread is None and self.thread.is_alive():
            log.info(f"Skipping {self.name} execution because a previous iteration's thread is still running.")
            return

        log.debug(f"Launching thread for {self.name}.")
        self.thread = Thread(target=self._run)
        self.thread.start()

    @abstractmethod
    def _run(self) -> None:
        super().run()
