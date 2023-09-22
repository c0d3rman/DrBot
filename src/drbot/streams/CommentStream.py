from __future__ import annotations
from typing import Iterable
from datetime import datetime, timezone
from praw.models import Comment
from ..reddit import reddit
from .TimeGuardedStream import TimeGuardedStream


class CommentStream(TimeGuardedStream[Comment]):
    """A stream of all comments on a subreddit."""

    def get_items_raw(self) -> Iterable[Comment]:
        return reddit.sub.comments(limit=None)

    def id(self, item: Comment) -> str:
        return item.id

    def timestamp(self, item: Comment) -> datetime:
        return datetime.fromtimestamp(item.created_utc).astimezone(timezone.utc)

    def get_latest_item(self) -> Comment | None:
        return next(reddit.sub.comments(limit=1), None)

    # Skip own comments?
