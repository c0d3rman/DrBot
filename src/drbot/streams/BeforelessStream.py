from __future__ import annotations
from abc import abstractmethod
from typing import TypeVar
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable, Generator

T = TypeVar("T")


class BeforelessStream(Stream[T]):
    """A base class for streams that don't have a "before" parameter in the reddit API."""

    def setup(self) -> None:
        # Since there's no before parameter, so we keep a persistent stream
        # and scroll it forward ourselves at initialization.
        self._stream = self.get_raw_stream()
        for item in self._stream:
            if item is None:
                # If the latest doesn't appear anywhere in the stream, it's too old,
                # so we reset the stream so all items are included.
                self._stream = self.get_raw_stream()
                break
            if self.id(item) == self.DR.storage["last_processed"]:
                # If we find the latest item, we've scrolled far enough -
                # the next time the stream is used it will spit out a not-yet-seen item.
                break

    def get_items(self) -> Iterable[T]:
        for item in self._stream:
            if item is None:
                break
            yield item

    @abstractmethod
    def get_raw_stream(self) -> Generator[T, None, None]:
        """You should return a PRAW stream of your items here.
        Make sure to set pause_after=0. For example:

        ```
        reddit.sub.mod.stream.modmail_conversations(pause_after=0)
        ```"""
        pass
