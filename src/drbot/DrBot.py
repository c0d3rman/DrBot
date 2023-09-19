from __future__ import annotations
import logging
import schedule
import time
from .log import log
from .storage import DrStore
from .settings import DrSettings, settings

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .DrBotling import DrBotling


class DrBot:
    def __init__(self) -> None:
        self.botlings: list[DrBotling] = []
        self.store = DrStore()
        log.debug("DrBot initialized.")

    def register(self, botling: DrBotling) -> None:
        # TBD Dupe check
        log.debug(f"Registering Botling {botling.name} ({botling.__class__.__name__})")
        self.botlings.append(botling)
        DrSettings().process_settings(botling)
        storage = self.store[botling]
        botling.register_init(DrRep(self, botling), storage)

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
        log.info("DrBot's main loop has started.")

        # Run all jobs immediately except those that shouldn't be run initially
        [job.run() for job in schedule.get_jobs() if not "no_initial" in job.tags]
        # The scheduler loop
        while True:
            schedule.run_pending()
            t = schedule.idle_seconds()
            if not t is None and t > 0:
                time.sleep(t)


class DrRep:
    """A representative of DrBot, passed to a Botling so it can have keyed access to a restricted subset of DrBot functions.
    This is not a security feature - it's only intended to prevent Botlings from accidentally messing something up."""

    def __init__(self, drbot: DrBot, botling: DrBotling) -> None:
        self.__drbot = drbot
        self.__botling = botling

    # TBD do we actually have anything here?
