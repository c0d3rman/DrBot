from __future__ import annotations
from praw.models import Comment, Submission
from ..reddit import reddit
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable


class EditedStream(Stream[Submission | Comment]):
    """A stream of edited posts and comments."""

    def get_items(self) -> Iterable[Submission | Comment]:
        for item in reddit.sub.mod.stream.edited(continue_after_id=self.DR.storage["last_processed"], pause_after=0):
            if item is None:
                break
            yield item

    def id(self, item: Submission | Comment) -> str:
        return item.fullname

    def get_latest_item(self) -> Submission | Comment | None:
        return next(reddit.sub.mod.edited(limit=1), None)
