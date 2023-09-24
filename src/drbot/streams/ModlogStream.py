from __future__ import annotations
from praw.models import ModAction
from ..reddit import reddit
from ..Stream import Stream


class ModlogStream(Stream[ModAction]):
    """A stream of modlog entries."""

    def get_items(self) -> list[ModAction]:
        items = reddit.sub.mod.log(limit=None, params={"before": self.DR.storage["last_processed"]})  # Yes really, it's 'before' not 'after' - reddit convention has the top of the list being the 'first'
        return list(reversed(list(items)))  # Process from earliest to latest

    def id(self, item: ModAction) -> str:
        return item.id

    def get_latest_item(self) -> ModAction | None:
        return next(reddit.sub.mod.log(limit=1), None)

    def skip_item(self, item: ModAction) -> bool:
        # Very important: skip any items created by DrBot, otherwise we would end up in an infinite loop,
        # since every time we save last_processed it would create a modlog entry.
        return item._mod == reddit.user.me().name
