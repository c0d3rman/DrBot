from __future__ import annotations
from typing import Any
from abc import ABC
import copy
from .log import log
from .util import name_of

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .storage import StorageDict


class Regi(ABC):
    """A base class for Botling and Stream's shared functionalities,
    particularly dealing with registration with DrBot and graceful error handling.
    The name is short for "Registerable"."""

    # If you want your Regi to have settings, override this property and define its default settings.
    # WARNING: due to the limitations of TOML, this does not support None. Do not put None anywhere in here.
    default_settings: dict[str, Any] = {}

    def __init__(self, kind: str, name: str | None = None) -> None:
        """Each Regi must have a unique name within its kind.
        You can set json_encoder and json_decoder to custom ones in __init__ if you want custom serialization."""
        self.__kind = kind
        self.__name = name or self.__class__.__name__
        self.__is_alive = True
        self.__is_registered = False
        self.json_encoder = self.json_decoder = None
        self.settings = copy.deepcopy(self.default_settings)
        log.debug(f"{self.__kind} {name_of(self)} intialized.")

    def accept_registration(self, storage: StorageDict, setup: bool = True) -> None:
        """This should only ever be called by DrBot.register(). Do not call it yourself.
        The setup flag is used to allow overriding this method without messing up the order of operations. setup() must be called in the override."""
        if self.__is_registered:
            raise ValueError(f"{self.__kind} {name_of(self)} cannot be registered multiple times.")
        self.__is_registered = True
        self.storage = storage
        log.debug(f"{self.__kind} {name_of(self)} registered.")
        if setup:
            self.setup()

    @property
    def name(self) -> str:
        """The Regi's name. Each Regi must have a unique name within its kind.
        Equal to the class name by default."""
        return self.__name
    
    @property
    def kind(self) -> str:
        """The Regi's kind, i.e. Botling or Stream."""
        return self.__kind

    @property
    def is_alive(self) -> bool:
        """Is this Regi alive? A Regi dies if it causes any errors,
        and this property signals DrBot to stop interacting with it without affecting other Regis."""
        return self.__is_alive

    @property
    def is_registered(self) -> bool:
        """Has this Regi been registered with DrBot?"""
        return self.__is_registered

    def die(self) -> None:
        """Kill the Regi. Should only be used if it errors."""
        self.__is_alive = False
    
    def dependency_died(self, dependency: Regi) -> None:
        """Called when a dependency of yours dies. By default, you die as well.
        You can override this if you want to be resilient to dependencies dying, but you'll have to make sure you use them carefully."""
        self.die()

    def setup(self) -> None:
        """Called once a Regi is registered and has access to its storage and settings.
        This method is meant to be overriden, and you should do most setup here instead of __init__."""
        pass

    def validate_settings(self) -> None:
        """
        Optionally, override this method with logic that validates self.settings.
        If a setting is invalid, raise a descriptive error.
        """
        pass
