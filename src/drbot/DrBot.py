from __future__ import annotations
import logging
import schedule
import time
from .log import log
from .storage import DataStore
from .settings import SettingsManager, settings
from .Botling import Botling
from .Stream import Stream
from .streams import PostStream, CommentStream, ModlogStream, ModmailConversationStream, ModmailMessageStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterator, Any
    from .Regi import Regi
    from .storage import StorageDict
    from .settings import DotDict


SLEEP_EPSILON = 1  # How long to sleep the scheduler


class Streams:
    """A helper class that holds the various Streams for DrBot to make them easy for Botlings to access."""

    def __init__(self) -> None:
        self.__streams: dict[str, Stream[Any]] = {}  # This contains all streams including the standard ones, to allow access via string (e.g. streams["PostStream"]) and simplify the logic
        self._standard: list[Stream[Any]] = []  # This only holds standard streams until they're registered

        # Standard streams
        self.post = self.__pre_add(PostStream())
        self.comment = self.__pre_add(CommentStream())
        self.modlog = self.__pre_add(ModlogStream())
        self.modmail_conversation = self.__pre_add(ModmailConversationStream())
        self.modmail_message = self.__pre_add(ModmailMessageStream())

    def __pre_add(self, stream: Stream[Any]) -> Stream[Any]:
        """Add a standard stream, putting it in _standard so it can be registered later."""
        self._standard.append(stream)
        return stream

    def append(self, stream: Stream[Any]) -> Stream[Any]:
        """Add a custom Stream, accessible via `streams["name"]`.
        Called "append" for streamlining of registration logic.
        Returns the stream back to the caller for convenience.
        You should not call this directly or the Stream will not be registered properly."""
        if stream.name in self.__streams:
            raise ValueError(f"Can't append {stream} with duplicate name")
        self.__streams[stream.name] = stream
        return stream

    def __iter__(self) -> Iterator[Stream[Any]]:
        return iter(self.__streams.values())

    def __contains__(self, item: Any) -> bool:
        if isinstance(item, str):
            return item in self.__streams
        if isinstance(item, Stream):
            return item in self.__streams.values()
        return False

    def __getitem__(self, name: str) -> Stream[Any]:
        """Get a Stream by name, e.g. `streams["PostStream"]`."""
        return self.__streams[name]


class DrBot:
    """The main DrBot class. Use it like this:

    drbot = DrBot()
    drbot.register(Botling1())
    drbot.register(Botling2())
    drbot.run()"""

    def __init__(self) -> None:
        self.storage = DataStore()
        self.botlings: list[Botling] = []
        self.streams = Streams()

        # Initialize standard streams
        for stream in self.streams._standard:
            self.register(stream)

        log.debug("DrBot initialized.")

    def register(self, regi: Regi) -> Regi | None:
        """Register a registerable object (i.e. Botling or Stream) with DrBot.
        Returns the object back for convenience, or None if registration failed."""

        log.debug(f"Registering {regi}.")

        # Get the relevant collection we're registering to
        if isinstance(regi, Botling):
            l = self.botlings
        elif isinstance(regi, Stream):
            l = self.streams
        else:
            raise ValueError(f"Can't register object of unknown type: {type(regi)}")

        # Check for dupes
        if regi in l:
            log.warning(f"Ignored attempt to register the already-registered {regi}.")
            return regi

        # Actually register
        try:
            l.append(regi)
            settings = SettingsManager().process_settings(regi)
            storage = self.storage[regi]
            scheduler = schedule.Scheduler()
            regi.accept_registration(DrBotRep(self, regi, storage, settings, scheduler))
            return regi
        except Exception:
            log.exception(f"{regi} crashed during registration.")
            regi.die(do_log=False)

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
        """The true main loop, wrapped by `run()` for error handling."""

        log.info("DrBot is online.")

        # Regularly poll all streams
        def poll_streams():
            for stream in self.streams:
                if stream.is_active:
                    try:
                        stream.run()
                    except Exception:
                        log.exception(f"{stream} crashed during polling.")
                        stream.die(do_log=False)
            self.reschedule_all()  # If Botlings do any scheduling during their Stream handlers, we don't want to miss polling their sub-schedulers
        poll_job = schedule.every(10).seconds.do(poll_streams)  # TBD generalize polling intervals (vary by stream?)

        # Poll streams immediately
        # This will also set up sub-scheduler polling
        poll_job.run()

        # Main loop
        while True:
            schedule.run_pending()
            t = schedule.idle_seconds()
            if t is not None and t > 0:
                time.sleep(t)

    def reschedule_all(self) -> None:
        """Schedules polling for all sub-schedulers, cancelling any existing polling jobs.
        This is an internal method and should not be called externally."""

        # Clear existing jobs
        schedule.clear("sub-scheduler")

        def schedule_next(botling: Botling):
            """Helper that runs the pending jobs for a botling and then schedules the next time that botling needs to run jobs.
            Technically this may break if one botling messes with another botling's schedule, but honestly that's on you at that point."""
            if botling.is_alive:
                num_jobs = sum(1 for job in botling.DR.scheduler.jobs if job.should_run)
                botling.DR.scheduler.run_pending()
                if num_jobs > 0:  # If we just ran some jobs, save
                    log.debug(f"Triggering a save because {botling} ran some scheduled actions.")
                    self.storage.save()
                if botling.is_alive:  # Check again in case we died during the scheduler tasks
                    t = max(botling.DR.scheduler.idle_seconds or SLEEP_EPSILON, 0)
                    log.debug(f"Scheduling next check for {botling} in {t} seconds.")
                    schedule.every(t).seconds.do(schedule_next, botling).tag("sub-scheduler")
            return schedule.CancelJob  # This is a one-time job

        for botling in self.botlings:
            if botling.is_alive:
                schedule_next(botling)


class DrBotRep:
    """A representative of DrBot, passed to a Regi so it can have keyed access to a restricted subset of DrBot functions.
    This is not a security feature! It's only intended to prevent Regis from accidentally messing something up."""

    def __init__(self, drbot: DrBot, regi: Regi, storage: StorageDict, settings: DotDict, scheduler: schedule.Scheduler) -> None:
        self._drbot = drbot
        self._regi = regi
        self.storage = storage
        self.settings = settings
        self.scheduler = scheduler

    @property
    def streams(self) -> Streams:
        """Accessor for streams. For example, you could do self.DR.streams.modmail or self.DR.streams.custom["MyStream"]."""
        return self._drbot.streams

    @property
    def global_settings(self) -> DotDict:
        """The global settings used across all of DrBot. You might want to access some of these, e.g. dry_run."""
        return settings
