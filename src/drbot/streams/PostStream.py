from __future__ import annotations
from datetime import datetime, timezone
from praw.models import Submission
from ..reddit import reddit
from .TimeGuardedStream import TimeGuardedStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Iterable


class PostStream(TimeGuardedStream[Submission]):
    """A stream of posts."""

    def get_items_raw(self) -> Iterable[Submission]:
        return reddit.sub.new(limit=None)

    def id(self, item: Submission) -> str:
        return item.id

    def timestamp(self, item: Submission) -> datetime:
        return datetime.fromtimestamp(item.created_utc, timezone.utc)

    def get_latest_item(self) -> Submission | None:
        return next(reddit.sub.new(limit=1), None)
