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
from .streams import ModmailStream, PostStream, ModlogStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterator, TypeVar
    from .Regi import Regi
    SubRegi = TypeVar('SubRegi', bound=Regi)


class Streams:
    """A helper class that holds the various Streams for DrBot to make them easy for Botlings to access."""

    def __init__(self, drbot: DrBot) -> None:
        self.__drbot = drbot
        self.custom: dict[str, Stream[Any]] = {}
        self.__standard: list[Stream[Any]] = []

        # All standard streams are initialized and registered here.
        self.modmail = self.__add(ModmailStream())
        self.post = self.__add(PostStream())
        self.modlog = self.__add(ModlogStream())

    def add(self, stream: Stream[Any]) -> None:
        """Add a custom stream, accessible via DR.streams.custom["name"]."""
        self.custom[stream.name] = stream

    def register_standard(self) -> None:
        """This is an internal method and should not be called.
        Register all standard streams once DrBot is ready.
        Custom streams are registered as they're added."""
        for stream in self.__standard:
            self.__drbot.register(stream)

    def __add(self, stream: Stream[Any]) -> Stream[Any]:
        """Add a standard stream, putting it in __standard so we can iterate over all streams in __iter__."""
        self.__standard.append(stream)
        return stream

    def __iter__(self) -> Iterator[Stream[Any]]:
        yield from self.__standard
        yield from self.custom.values()


class DrBot:
    """TBD"""

    def __init__(self) -> None:
        self.storage = DataStore()
        self.botlings: list[Botling] = []
        self.streams = Streams(self)
        self.streams.register_standard()

        log.debug("DrBot initialized.")

    def register(self, regi: SubRegi) -> SubRegi:
        """Register a registerable object (i.e. Botling or Stream) with DrBot.
        Returns the object back for convenience."""
        # TBD Dupe check. For streams, make sure to check for dupes across both standard and custom
        log.debug(f"Registering {regi.kind}: {name_of(regi)}.")
        SettingsManager().process_settings(regi)
        if isinstance(regi, Botling):
            self.botlings.append(regi)
            regi.DR = DrBotRep(self, regi)
        elif isinstance(regi, Stream):
            self.streams.add(regi)
        else:
            raise ValueError(f"Can't register object of unknown type: {type(regi)}")
        regi.accept_registration(self.storage[regi])
        return regi

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
                if stream.is_active:
                    stream.run()  # Error guard?
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
    """A representative of DrBot, passed to a Botling so it can have keyed access to a restricted subset of DrBot functions.
    This is not a security feature - it's only intended to prevent Botlings from accidentally messing something up."""

    def __init__(self, drbot: DrBot, botling: Botling) -> None:
        self.__drbot = drbot
        self.__botling = botling

        # import copy
        # self.settings = copy.deepcopy(botling.default_settings) # TBD

    @property
    def stream(self):
        """Accessor for streams. For example, you could do self.DR.stream.modmail or self.DR.stream.custom["my_stream"]."""
        return self.__drbot.streams
