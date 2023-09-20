from __future__ import annotations
from abc import abstractmethod
from typing import Generic, TypeVar
from .log import log
from .util import name_of

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Callable, Iterable, Any
    from .storage import DrDict
    from .DrBotling import DrBotling

T = TypeVar("T")


class ObserverBundle(Generic[T]):
    """A class used to hold information about a subscribed observer."""

    def __init__(self, botling: DrBotling, handler: Callable[[T], None], start_run: Callable[[], None] | None = None) -> None:
        self.botling = botling
        self.handler = handler
        self.start_run = start_run

    @property
    def name(self):
        """A helper that gets a human-readable name for the observer (including the Botling name and the function names)."""
        def get_name(func: Callable[[Any], Any]): getattr(func, "__name__", getattr(func, "__qualname__", repr(func)))  # Handle lambdas and such
        return f"{self.botling.name} ({get_name(self.handler)}" + (f", {get_name(self.start_run)}" if self.start_run else "") + ")"


class DrStream(Generic[T]):
    """Scans incoming entries of type T and notifies observers about them."""

    def __init__(self, name: str | None = None) -> None:
        """Each DrStream must have a unique name.
        You can set json_encoder and json_decoder to custom ones in __init__ if you want custom serialization."""
        super().__init__()
        self.__name = name or self.__class__.__name__
        self.json_encoder = self.json_decoder = None
        self.__observers: list[ObserverBundle[T]] = []

    @property
    def name(self) -> str:
        """The DrStream's name. Each DrStream must have a unique name.
        Equal to the class name by default."""
        return self.__name
    
    @property
    def active(self) -> bool:
        """Whether this DrStream wants to poll.
        DrStreams turn themselves off when they have no observers."""
        return len(self.__observers) > 0

    def register_init(self, storage: DrDict):
        """This should only ever be called by DrBot.register_stream(). Do not call it yourself."""
        if hasattr(self, "storage"):
            raise ValueError("A DrStream cannot be registered multiple times.")
        self.storage = storage

        # Initialize last_processed
        latest = self.get_latest_item()
        self.storage["last_processed"] = None if latest is None else self.id(latest)

        log.debug(f"DrStream {name_of(self)} registered.")
        self.setup()

    def subscribe(self, botling: DrBotling, handler: Callable[[T], None], start_run: Callable[[], None] | None = None) -> ObserverBundle[T]:
        """Subscribe an observer with the stream.
        Optionally, you can also pass a start_run function that is run when we get a new batch of items (most useful for invalidating caches).
        Returns an ObserverBundle which you can keep if you want to unsubscribe later."""
        bundle = ObserverBundle(botling, handler, start_run)
        self.__observers.append(bundle)
        log.debug(f"Observer {bundle.name} subscribed to DrStream {self.name}")
        return bundle

    def unsubscribe(self, bundle: ObserverBundle[T]) -> bool:
        """Unsubscribe an observer from the stream. Keep the ObserverBundle that subscribe() returns if you want to use this.
        Returns True if deregistration was successful."""
        if bundle in self.__observers:
            self.__observers.remove(bundle)
            log.debug(f"Observer {bundle.name} unsubscribed from DrStream {self.name}")
            return True
        else:
            log.debug(f"Couldn't unsubscribe observer {bundle.name} from DrStream {self.name} because it's not subscribed")
            return False

    def run(self) -> None:
        """Poll the stream. Looks for new items and notifies observers.
        Handles killing and unsubscribing any observers that error."""

        if not self.storage:
            raise RuntimeError(f"DrStream {self.name} was run before it was registered.")

        items = [item for item in self.get_items() if not self.skip_item(item)]
        if len(items) == 0:
            return
        log.info(f"DrStream {self.name} processing {len(items)} new items.")

        # Let all the handlers know we're starting a new run
        for i in reversed(range(len(self.__observers))):  # Reversed iteration since we may remove some items
            bundle = self.__observers[i]
            if not bundle.botling.is_alive:
                log.debug(f"Unsubscribing observer {bundle.name} from DrStream {self.name} since it is dead")
                del self.__observers[i]
            if bundle.start_run:
                log.debug(f"DrStream {self.name} notifying observer {bundle.name} about the start of a new run")
                try:
                    bundle.start_run()
                except Exception:
                    bundle.botling.die()
                    del self.__observers[i]
                    log.exception(f"Observer {bundle.name} of DrStream {self.name} crashed during start_run.")

        # Process items
        for item in items:
            log.debug(f"DrStream {self.name} handling item {self.id(item)}")
            for i in reversed(range(len(self.__observers))):  # Reversed iteration since we may remove some items
                bundle = self.__observers[i]
                if not bundle.botling.is_alive:
                    log.debug(f"Unsubscribing observer {bundle.name} from DrStream {self.name} since it is dead")
                    del self.__observers[i]
                try:
                    bundle.handler(item)
                except Exception:
                    bundle.botling.die()
                    del self.__observers[i]
                    log.exception(f"Observer {bundle.name} of DrStream {self.name} crashed during handler.")
            self.storage["last_processed"] = self.id(item)

        # Save our storage right now to make sure we don't reprocess any items,
        # even if bad things happen before the next scheduled save.
        self.storage.force_save()

    def setup(self) -> None:
        """Called once a DrStream is registered and has access to its storage.
        This method is meant to be overriden, and you should do most setup here instead of __init__."""
        pass

    @ abstractmethod
    def get_items(self) -> Iterable[T]:
        """Get all new items for the agent to process. E.g. all new modlog entries.
        You can use self.storage["last_processed"] for this purpose."""
        pass

    @ abstractmethod
    def id(self, item: T) -> str:
        """Get a unique ID for a given item. Used for keeping track of last_processed."""
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
