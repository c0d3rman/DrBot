from __future__ import annotations
from abc import abstractmethod
from typing import Generic, TypeVar
from .log import log
from .util import name_of
from .Regi import Regi

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Callable, Iterable, Any
    from .storage import StorageDict
    from .Botling import Botling

T = TypeVar("T")


class ObserverBundle(Generic[T]):
    """A class used to hold information about a subscribed observer."""

    def __init__(self, botling: Botling, handler: Callable[[T], None], start_run: Callable[[], None] | None = None) -> None:
        self.botling = botling
        self.handler = handler
        self.start_run = start_run

    @property
    def name(self):
        """A helper that gets a human-readable name for the observer (including the Botling name and the function names)."""
        def get_name(func: Callable[[Any], Any]): getattr(func, "__name__", getattr(func, "__qualname__", repr(func)))  # Handle lambdas and such
        return f"{self.botling.name} ({get_name(self.handler)}" + (f", {get_name(self.start_run)}" if self.start_run else "") + ")"


class Stream(Regi, Generic[T]):
    """Scans incoming entries of type T and notifies observers about them."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__("Stream", name)
        self.__observers: list[ObserverBundle[T]] = []

    @property
    def is_active(self) -> bool:
        """Whether this Stream wants to poll.
        Streams turn themselves off when they have no observers.
        Not the same as is_alive - death is permanent, inactivity is not."""
        return len(self.__observers) > 0

    def accept_registration(self, storage: StorageDict, setup: bool = True) -> None:
        super().accept_registration(storage, setup=False)

        # Initialize last_processed
        latest = self.get_latest_item()
        self.storage["last_processed"] = None if latest is None else self.id(latest)

        if setup:
            self.setup()

    def subscribe(self, botling: Botling, handler: Callable[[T], None], start_run: Callable[[], None] | None = None) -> ObserverBundle[T]:
        """Subscribe an observer with the stream.
        Optionally, you can also pass a start_run function that is run when we get a new batch of items (most useful for invalidating caches).
        Returns an ObserverBundle which you can keep if you want to unsubscribe later."""
        bundle = ObserverBundle(botling, handler, start_run)
        self.__observers.append(bundle)
        log.debug(f"Observer {bundle.name} subscribed to Stream {name_of(self)}.")
        return bundle

    def unsubscribe(self, bundle: ObserverBundle[T]) -> bool:
        """Unsubscribe an observer from the stream. Keep the ObserverBundle that subscribe() returns if you want to use this.
        Returns True if deregistration was successful."""
        if bundle in self.__observers:
            self.__observers.remove(bundle)
            log.debug(f"Observer {bundle.name} unsubscribed from Stream {name_of(self)}.")
            return True
        else:
            log.debug(f"Couldn't unsubscribe observer {bundle.name} from Stream {name_of(self)} because it's not subscribed.")
            return False

    def run(self) -> None:
        """Poll the stream. Looks for new items and notifies observers.
        Handles killing and unsubscribing any observers that error."""

        if not self.storage:
            raise RuntimeError(f"Stream {name_of(self)} was run before it was registered.")

        items = [item for item in self.get_items() if not self.skip_item(item)]
        if len(items) == 0:
            return
        log.info(f"Stream {name_of(self)} processing {len(items)} new items.")

        # Let all the handlers know we're starting a new run
        for i in reversed(range(len(self.__observers))):  # Reversed iteration since we may remove some items
            bundle = self.__observers[i]
            if not bundle.botling.is_alive:
                log.debug(f"Unsubscribing observer {bundle.name} from Stream {name_of(self)} since it is dead.")
                del self.__observers[i]
            if bundle.start_run:
                log.debug(f"Stream {name_of(self)} notifying observer {bundle.name} about the start of a new run.")
                try:
                    bundle.start_run()
                except Exception:
                    bundle.botling.die()
                    del self.__observers[i]
                    log.exception(f"Observer {bundle.name} of Stream {name_of(self)} crashed during start_run.")

        # Process items
        for item in items:
            log.debug(f"Stream {name_of(self)} handling item {self.id(item)}")
            for i in reversed(range(len(self.__observers))):  # Reversed iteration since we may remove some items
                bundle = self.__observers[i]
                if not bundle.botling.is_alive:
                    log.debug(f"Unsubscribing observer {bundle.name} from Stream {name_of(self)} since it is dead.")
                    del self.__observers[i]
                try:
                    bundle.handler(item)
                except Exception:
                    bundle.botling.die()
                    del self.__observers[i]
                    log.exception(f"Observer {bundle.name} of Stream {name_of(self)} crashed during handler.")
            self.storage["last_processed"] = self.id(item)

        # Save our storage right now to make sure we don't reprocess any items,
        # even if bad things happen before the next scheduled save.
        self.storage.force_save()

    @abstractmethod
    def get_items(self) -> Iterable[T]:
        """Get all new items for the agent to process. E.g. all new modlog entries.
        You can use self.storage["last_processed"] for this purpose."""
        pass

    @abstractmethod
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
