from abc import ABC, abstractmethod
import praw
from drbot import log


class Handler(ABC):
    """For use with ModlogAgent.
    Scans incoming modlog entries one at a time."""

    def init(self, data_store: dict, reddit: praw.Reddit):
        """Called to set up the handler when it is registered."""
        self.data_store = data_store
        self.reddit = reddit

    def start_run(self):
        """Called by ModlogAgent when it starts looping through a new batch of mod log items.
        Can optionally be overriden to do things like invalidating caches."""
        pass

    @abstractmethod
    def handle(self, mod_action: praw.models.ModAction) -> None:
        """The core handler method. Handle a single mod action."""
        pass
