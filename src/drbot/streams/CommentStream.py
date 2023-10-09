from __future__ import annotations
from praw.models import Comment
from ..reddit import reddit
from ..Stream import Stream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable


class CommentStream(Stream[Comment]):
    """A stream of all comments on a subreddit."""

    def get_items(self) -> Iterable[Comment]:
        for item in reddit.sub.stream.comments(continue_after_id=self.DR.storage["last_processed"], pause_after=0):
            if item is None:
                break
            yield item

    def id(self, item: Comment) -> str:
        return item.fullname

    def get_latest_item(self) -> Comment | None:
        return next(reddit.sub.comments(limit=1), None)
