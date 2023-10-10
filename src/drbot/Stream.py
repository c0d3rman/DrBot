from __future__ import annotations
from abc import abstractmethod
from typing import Generic, TypeVar
from .log import log
from .Regi import Regi

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Callable, Iterable, Any
    from .DrBot import DrBotRep

T = TypeVar("T")


class ObserverBundle(Generic[T]):
    """A class used to hold information about a subscribed observer."""

    def __init__(self, observer: Regi, handler: Callable[[T], None], start_run: Callable[[], None] | None = None) -> None:
        self.observer = observer
        self.handler = handler
        self.start_run = start_run

    def __str__(self) -> str:
        """A human-readable name for the observer (including the Botling name and the function names)."""
        def get_name(func: Callable[..., Any]): return getattr(func, "__name__", getattr(func, "__qualname__", repr(func)))  # Handle lambdas and such
        return f'Observer "{self.observer.name}" (handler: {get_name(self.handler)}' + (f", start_run: {get_name(self.start_run)}" if self.start_run else "") + ")"


class Stream(Regi, Generic[T]):
    """Scans incoming entries of type T and notifies observers about them."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__("Stream", name)
        self.__observers: list[ObserverBundle[T]] = []

    @property
    def is_active(self) -> bool:
        """Whether this Stream wants to poll.
        Streams turn themselves off when they have no active observers (i.e. an active Stream or a living Botling).
        Not the same as is_alive - death is permanent, inactivity is not. (But dead streams are never active.)"""
        return self.is_alive and sum(getattr(b.observer, "is_active", b.observer.is_alive) for b in self.__observers) > 0

    def die(self, do_log: bool = True) -> None:
        dead_regis = super().die(do_log=False)
        if not self in dead_regis:
            return dead_regis  # If we didn't die (since we're already dead), no need to warn our dependents again

        for bundle in self.__observers:
            dead_regis += bundle.observer.dependency_died(self, do_log=False)
        if do_log:
            message = f"{self} has died."
            if len(dead_regis) > 1:  # Since we're always in it
                message += " This lead to the death of the following dependents:\n\n- "
                message += "\n- ".join(str(regi) for regi in dead_regis if regi is not self)
                message += "\n\n"
            log.smart_error(message)
        return dead_regis

    def accept_registration(self, DR: DrBotRep) -> None:
        super().accept_registration(DR)

        # Initialize last_processed
        if "last_processed" not in self.DR.storage:
            latest = self.get_latest_item()
            self.DR.storage["last_processed"] = None if latest is None else self.id(latest)
            log.debug(f"Initialized last_processed for {self} - {self.DR.storage['last_processed']}")

    def subscribe(self, observer: Regi, handler: Callable[[T], None], start_run: Callable[[], None] | None = None) -> ObserverBundle[T] | None:
        """Subscribe an observer with the stream.
        Optionally, you can also pass a start_run function that is run when we get a new batch of items (most useful for invalidating caches).
        Returns an ObserverBundle which you can keep if you want to unsubscribe later, or None if subscribing failed."""
        if not self.is_alive:
            log.debug(f"{observer} tried to subscribe to {self}, but the Stream is dead.")
            observer.dependency_died(self)
            return
        bundle = ObserverBundle(observer, handler, start_run)
        self.__observers.append(bundle)
        log.debug(f"{bundle} subscribed to {self}.")
        return bundle

    def unsubscribe(self, bundle: ObserverBundle[T]) -> bool:
        """Unsubscribe an observer from the stream. Keep the ObserverBundle that subscribe() returns if you want to use this.
        Returns True if deregistration was successful."""
        if bundle in self.__observers:
            self.__observers.remove(bundle)
            log.debug(f"{bundle} unsubscribed from {self}.")
            return True
        else:
            log.debug(f"Couldn't unsubscribe {bundle} from {self} because it's not subscribed.")
            return False

    @property
    def observers(self) -> list[Regi]:
        return list(bundle.observer for bundle in self.__observers)

    def run(self) -> None:
        """Poll the stream. Looks for new items and notifies observers.
        Handles killing and unsubscribing any observers that error."""

        if not self.is_alive:
            raise RuntimeError(f"Tried to run() a dead {self}.")

        try:
            self.DR
        except ValueError:
            raise RuntimeError(f"{self} was run before it was registered.") from None

        iter_items = iter(self.get_items())
        item = next(iter_items, None)
        while item is not None and self.skip_item(item):
            item = next(iter_items, None)
        if item is None:
            return
        log.info(f"{self} processing new items.")

        # Let all the handlers know we're starting a new run
        for i in reversed(range(len(self.__observers))):  # Reversed iteration since we may remove some items
            bundle = self.__observers[i]
            if not bundle.observer.is_alive:
                log.debug(f"Unsubscribing {bundle} from {self} since it is dead.")
                del self.__observers[i]
            if bundle.start_run:
                log.debug(f"{self} notifying {bundle} about the start of a new run.")
                try:
                    bundle.start_run()
                except Exception:
                    log.exception(f"{bundle} of {self} crashed during start_run.")
                    bundle.observer.die(do_log=False)
                    del self.__observers[i]

        # Process items
        count = 0
        while item is not None:
            count += 1
            log.debug(f"{self} handling item {self.id(item)}")
            for i in reversed(range(len(self.__observers))):  # Reversed iteration since we may remove some items
                bundle = self.__observers[i]
                if not bundle.observer.is_alive:
                    log.debug(f"Unsubscribing {bundle} from {self} since it is dead.")
                    del self.__observers[i]
                try:
                    bundle.handler(item)
                except Exception:
                    log.exception(f"{bundle} of {self} crashed during handler.")
                    bundle.observer.die(do_log=False)
                    del self.__observers[i]
            self.DR.storage["last_processed"] = self.id(item)
            item = next(iter_items, None)

        log.info(f"{self} processed {count} items.")

        # Save our storage right now to make sure we don't reprocess any items,
        # even if bad things happen before the next scheduled save.
        log.debug(f"Triggering a save because {self} finished processing new items.")
        self.DR.storage.force_save()

    @abstractmethod
    def get_items(self) -> Iterable[T]:
        """Get all new items for the agent to process. E.g. all new modlog entries.
        You can use self.DR.storage["last_processed"] for this purpose. Make sure to handle the None case (e.g. when your sub is brand new and has no posts/modmails/whatever)."""
        pass

    @abstractmethod
    def id(self, item: T) -> Any:
        """Get a unique ID for a given item. Used for keeping track of last_processed."""
        pass

    def get_latest_item(self) -> T | None:
        """Get the latest item. Used for setting the initial last_processed,
        so you don't process items stretching backwards forever on the first run.
        If you don't return an item (or don't implement this), it will in fact process backwards forever.
        It's OK to return an item that would be skipped by skip_item(), so long as it's one that will be returned by your get_items()."""
        pass

    def skip_item(self, item: T) -> bool:
        """Optionally, you can override this to skip cetain items.
        mostly useful to avoid updating last_processed with your own modlog entries,
        which can get you stuck in update loops."""
        return False
