from __future__ import annotations
from typing import Any
import logging
from drbot.streams import PostStream
import schedule
import time
from .log import log
from .util import name_of
from .storage import DataStore
from .settings import SettingsManager, settings
from .Botling import Botling
from .Stream import Stream
from .streams import ModmailStream, PostStream, ModlogStream, CommentStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterator
    from .Regi import Regi
    from .storage import StorageDict
    from .settings import DotDict


class Streams:
    """A helper class that holds the various Streams for DrBot to make them easy for Botlings to access."""

    def __init__(self, drbot: DrBot) -> None:
        self.__drbot = drbot
        self.custom: dict[str, Stream[Any]] = {}  # This actually contains all streams including the standard ones, to allow access via string (e.g. streams.custom["PostStream"]) and simplify the logic
        self.__standard: list[Stream[Any]] = []  # This only holds standard streams until they're registered

        # All standard streams are initialized and registered here.
        self.modmail = self.__pre_add(ModmailStream())
        self.post = self.__pre_add(PostStream())
        self.comment = self.__pre_add(CommentStream())
        self.modlog = self.__pre_add(ModlogStream())

    def add(self, stream: Stream[Any]) -> None:
        """Add a custom stream, accessible via DR.streams.custom["name"]."""
        self.custom[stream.name] = stream

    def append(self, stream: Stream[Any]) -> None:
        """Alias of add() for streamlining of registration logic."""
        self.add(stream)

    def remove(self, stream: Stream[Any]) -> None:
        if stream.name in self.custom:
            log.debug(f"Removing Stream {name_of(stream)}.")
            del self.custom[stream.name]

    def register_standard(self) -> None:
        """This is an internal method and should not be called.
        Register all standard streams once DrBot is ready.
        Custom streams are registered as they're added."""
        for stream in self.__standard:
            self.__drbot.register(stream)

    def __pre_add(self, stream: Stream[Any]) -> Stream[Any]:
        """Add a standard stream, putting it in __standard so it can be registered later."""
        self.__standard.append(stream)
        return stream

    def __iter__(self) -> Iterator[Stream[Any]]:
        return iter(self.custom.values())

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return item in self.custom
        if isinstance(item, Stream):
            return item in self.custom.values()
        return False


class DrBot:
    """The main DrBot class. Use it like this:

    drbot = DrBot()
    drbot.register(Botling1())
    drbot.register(Botling2())
    drbot.run()"""

    def __init__(self) -> None:
        self.storage = DataStore()
        self.botlings: list[Botling] = []
        self.streams = Streams(self)
        self.streams.register_standard()

        log.debug("DrBot initialized.")

    def register(self, regi: Regi) -> Regi | None:
        """Register a registerable object (i.e. Botling or Stream) with DrBot.
        Returns the object back for convenience, or None if registration failed."""

        log.debug(f"Registering {regi.kind} {name_of(regi)}.")

        # Get the relevant collection we're registering to
        if isinstance(regi, Botling):
            l = self.botlings
        elif isinstance(regi, Stream):
            l = self.streams
        else:
            raise ValueError(f"Can't register object of unknown type: {type(regi)}")

        # Check for dupes
        if regi in l:
            log.warning(f"Ignored attempt to register the already-registered {regi.kind} {name_of(regi)}.")
            return regi

        # Actually register
        try:
            l.append(regi)
            settings = SettingsManager().process_settings(regi)
            storage = self.storage[regi]
            regi.accept_registration(DrBotRep(self, regi, storage, settings))
            return regi
        except Exception:
            log.exception(f"{regi.kind} {name_of(regi)} crashed during registration.")
            regi.die()
            if regi in l:
                l.remove(regi)

    def run(self) -> None:
        """DrBot's main loop. Call this once all Botlings have been registered. Will run forever."""

        # This just handles error guarding, all the juicy stuff happens in _main()
        try:
            self._main()
        except KeyboardInterrupt:
            log.info("Bot manually interrupted - shutting down...")
        except Exception as e:
            log.critical(e)
            raise e
        logging.shutdown()

    def _main(self) -> None:
        # Regularly poll all streams
        def poll_streams():
            for stream in self.streams:
                if stream.is_alive and stream.is_active:
                    try:
                        stream.run()
                    except Exception:
                        log.exception(f"Stream {name_of(stream)} crashed during polling.")
                        stream.die()
        schedule.every(10).seconds.do(poll_streams)  # TBD generalize polling intervals (vary by stream?)

        log.info("DrBot is online.")

        # Run all jobs immediately except those that shouldn't be run initially
        [job.run() for job in schedule.get_jobs() if not "no_initial" in job.tags]
        # The scheduler loop
        while True:
            schedule.run_pending()
            t = schedule.idle_seconds()
            if not t is None and t > 0:
                time.sleep(t)


class DrBotRep:
    """A representative of DrBot, passed to a Regi so it can have keyed access to a restricted subset of DrBot functions.
    This is not a security feature! It's only intended to prevent Regis from accidentally messing something up."""

    def __init__(self, drbot: DrBot, regi: Regi, storage: StorageDict, settings: DotDict) -> None:
        self._drbot = drbot
        self._regi = regi
        self.storage = storage
        self.settings = settings

    @property
    def streams(self):
        """Accessor for streams. For example, you could do self.DR.streams.modmail or self.DR.streams.custom["MyStream"]."""
        return self._drbot.streams
