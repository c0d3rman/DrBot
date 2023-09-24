from __future__ import annotations
from .Regi import Regi


class Botling(Regi):
    """A Botling is an independent module that performs some related set of moderation tasks.
    You can define your own Botlings or use the premade ones.
    Each one is provided with infrastructure to store data, use settings, access Reddit, and more."""

    def __init__(self, name: str | None = None) -> None:
        super().__init__("Botling", name)
