from __future__ import annotations
from typing import Any
import json
import copy
from .log import log

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
        In your Botling's __init__, you can set the json_encoder and json_decoder properties to custom ones if you want custom serialization."""
        self.__name = name or self.__class__.__name__
        self.__json_encoder = self.__json_decoder = None
        self.__coder_lock = False
        self.settings = copy.deepcopy(self.default_settings)
        log.debug(f"Botling {self.name} ({self.__class__.__name__}) intialized.")

    def register_init(self, DR: DrRep, storage: DrDict):
        """This should only ever be called by DrBot.register(). Do not call it yourself."""
        if hasattr(self, "_DRBotling__DR"):
            raise ValueError("A Botling cannot be registered multiple times.")
        self.__DR = DR
        self.storage = storage
        self.__coder_lock = True  # Lock the JSON coders so they can't be changed anymore.
        log.debug(f"Botling {self.name} ({self.__class__.__name__}) registered.")
        self.setup()

    @property
    def name(self) -> str:
        """The Botling's name. Each Botling must have a unique name.
        Equal to the class name by default."""
        return self.__name

    @property
    def DR(self) -> DrRep:
        """An accessor for all of the tools DrBot provides for your Botling.
        Only accessible once you've registered your Botling with DrBot."""
        if not hasattr(self, "_DRBotling__DR"):
            raise ValueError("This Botling has not been registered yet. If you're trying to use self.DR in __init__, override the setup() method instead.")
        return self.__DR

    @property
    def json_encoder(self) -> type[json.JSONEncoder] | None:
        return self.__json_encoder

    @json_encoder.setter
    def json_encoder(self, value: type[json.JSONEncoder] | None):
        if self.__coder_lock:
            raise ValueError("This Botling's JSON encoder can no longer be set. Are you trying to set it in setup()? It must be set in __init__.")
        self.__json_encoder = value
        log.debug(f"Registered new JSON encoder for Botling {self.name} ({self.__class__.__name__}).")

    @property
    def json_decoder(self) -> type[json.JSONDecoder] | None:
        return self.__json_decoder

    @json_decoder.setter
    def json_decoder(self, value: type[json.JSONDecoder] | None):
        if self.__coder_lock:
            raise ValueError("This Botling's JSON decoder can no longer be set. Are you trying to set it in setup()? It must be set in __init__.")
        self.__json_decoder = value
        log.debug(f"Registered new JSON decoder for Botling {self.name} ({self.__class__.__name__}).")

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
