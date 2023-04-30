from abc import ABC, abstractmethod
import praw
from .log import log


class Handler(ABC):
    def init(self, data_store: dict, reddit: praw.Reddit):
        self.data_store = data_store
        self.reddit = reddit

    @abstractmethod
    def handle(self, mod_action: praw.models.ModAction) -> None:
        pass
