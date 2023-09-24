from __future__ import annotations
from typing import Any
from abc import ABC
from .log import log

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .DrBot import DrBotRep


class Regi(ABC):
    """A base class for Botling and Stream's shared functionalities,
    particularly dealing with registration with DrBot and graceful error handling.
    The name is short for "Registerable"."""

    __names: dict[str, set[str]] = {}

    # If you want your Regi to have settings, override this property and define its default settings.
    # WARNING: due to the limitations of TOML, this does not support None. Do not put None anywhere in here.
    default_settings: dict[str, Any] = {}

    def __init__(self, kind: str, name: str | None = None) -> None:
        """Each Regi must have a unique name within its kind.
        You can set json_encoder and json_decoder to custom ones in __init__ if you want custom serialization."""
        self.__kind = kind
        self.__name = name or self.__class__.__name__

        # Enforce unique names among kind
        if kind not in self.__names:
            self.__names[kind] = set()
        if self.__name in self.__names[kind]:
            raise ValueError(f"{kind} with name '{self.__name}' already exists.")
        else:
            self.__names[kind].add(self.__name)

        self.__is_alive = True
        self.__is_registered = False
        self.json_encoder = self.json_decoder = None
        self.__DrBotRep = None

        log.debug(f"{self} intialized.")

    @property
    def DR(self) -> DrBotRep:
        """An accessor for all of the tools DrBot provides for your Botling.
        Only accessible once you've registered your Botling with DrBot."""
        if not self.__DrBotRep:
            raise ValueError("This Botling has not been registered yet. If you're trying to use self.DR in __init__, override the setup() method instead.")
        return self.__DrBotRep

    def accept_registration(self, DR: DrBotRep, setup: bool = True) -> None:
        """This should only ever be called by DrBot.register(). Do not call it yourself.
        The setup flag is used to allow overriding this method without messing up the order of operations. setup() must be called in the override."""
        if self.__is_registered:
            raise ValueError(f"{self} cannot be registered multiple times.")
        self.__is_registered = True
        self.__DrBotRep = DR
        self.validate_settings()
        log.debug(f"{self} registered.")
        if setup:
            self.setup()

    @property
    def name(self) -> str:
        """The Regi's name. Each Regi must have a unique name within its kind.
        Equal to the class name by default."""
        return self.__name

    def __str__(self) -> str:
        """A display name for the Regi, used for logging."""
        return f'{self.kind} "{self.name}" ({self.__class__.__name__})'

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
