from __future__ import annotations
from .Regi import Regi

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .DrBot import DrBotRep


class Botling(Regi):
    """A Botling is an independent module that performs some related set of moderation tasks.
    You can define your own Botlings or use the premade ones.
    Each one is provided with infrastructure to store data, use settings, access Reddit, and more."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__("Botling", name)
        self.__DrBotRep = None

    @property
    def DR(self) -> DrBotRep:
        """An accessor for all of the tools DrBot provides for your Botling.
        Only accessible once you've registered your Botling with DrBot."""
        if not self.__DrBotRep:
            raise ValueError("This Botling has not been registered yet. If you're trying to use self.DR in __init__, override the setup() method instead.")
        return self.__DrBotRep

    @DR.setter
    def DR(self, val: DrBotRep) -> None:
        """Only DrBot should set this property."""
        if self.__DrBotRep:
            raise ValueError("You should not set self.DR! Only DrBot can set this property. Make sure you are registering your Botling properly.")
        self.__DrBotRep = val
