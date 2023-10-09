from __future__ import annotations
from praw.models import ModAction
from ..reddit import reddit
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable


class ModlogStream(Stream[ModAction]):
    """A stream of modlog entries.
    Does not include modlog entries related to DrBot, otherwise we'd end up in infinite loops every time we did something."""

    def get_items(self) -> Iterable[ModAction]:
        for item in reddit.sub.mod.stream.log(continue_after_id=self.DR.storage["last_processed"], pause_after=0):
            if item is None:
                break
            yield item

    def id(self, item: ModAction) -> str:
        return item.id

    def get_latest_item(self) -> ModAction | None:
        return next(reddit.sub.mod.log(limit=1), None)

    def skip_item(self, item: ModAction) -> bool:
        # Very important: skip any items created by DrBot, otherwise we would end up in an infinite loop,
        # since every time we save last_processed it would create a modlog entry.
        return item._mod == reddit.user.me().name
