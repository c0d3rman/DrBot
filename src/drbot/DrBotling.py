from __future__ import annotations
from typing import Any
import json
import copy
from .log import log
from .util import name_of

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .DrBot import DrRep
    from .storage import DrDict


class DrBotling:
    """A Botling is an independent module that performs some related set of moderation tasks.
    You can define your own Botlings or use the premade ones.
    Each one is provided with infrastructure to store data, use settings, access Reddit, and more."""

    # If you want your Botling to have settings, override this property and define its default settings.
    # WARNING: due to the limitations of TOML, this does not support None. Do not put None anywhere in here.
    default_settings: dict[str, Any] = {}

    def __init__(self, name: str | None = None) -> None:
        """Each Botling must have a unique name.
        You can set json_encoder and json_decoder to custom ones in __init__ if you want custom serialization."""
        self.__name = name or self.__class__.__name__
        self.json_encoder = self.json_decoder = None
        self.__is_alive = True
        self.settings = copy.deepcopy(self.default_settings)
        log.debug(f"Botling {name_of(self)} intialized.")

    def register_init(self, DR: DrRep, storage: DrDict):
        """This should only ever be called by DrBot.register_botling(). Do not call it yourself."""
        if hasattr(self, "storage"):
            raise ValueError("A Botling cannot be registered multiple times.")
        self.storage = storage
        self.__DR = DR
        log.debug(f"Botling {name_of(self)} registered.")
        self.setup()

    @property
    def name(self) -> str:
        """The Botling's name. Each Botling must have a unique name.
        Equal to the class name by default."""
        return self.__name

    @property
    def is_alive(self) -> bool:
        """Is this Botling alive? The Botling dies if it causes any errors,
        and this property signals DrBot to stop interacting with it without affecting the other Botlings."""
        return self.__is_alive

    def die(self) -> None:
        """Kill the Botling. Should only be used if it errors."""
        self.__is_alive = True

    @property
    def DR(self) -> DrRep:
        """An accessor for all of the tools DrBot provides for your Botling.
        Only accessible once you've registered your Botling with DrBot."""
        if not hasattr(self, "_DrBotling__DR"):
            raise ValueError("This Botling has not been registered yet. If you're trying to use self.DR in __init__, override the setup() method instead.")
        return self.__DR

    def setup(self) -> None:
        """Called once a Botling is registered and has access to its storage and Reddit.
        This method is meant to be overriden, and you should do most setup here instead of __init__."""
        pass

    def validate_settings(self) -> None:
        """
        Optionally, override this method with logic that validates self.settings.
        If a setting is invalid, raise a descriptive error.
        """
        pass
