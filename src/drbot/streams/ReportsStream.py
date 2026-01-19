from __future__ import annotations
from praw.models import Submission, Comment
from ..reddit import reddit
from .BeforelessStream import BeforelessStream

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from typing import Generator


class ReportsStream(BeforelessStream[Submission | Comment]):
    """A stream of reported comments and submissions."""

    def setup(self) -> None:
        # TEMP: backfill the most recent items once for testing
        if "temp_backfill_done" not in self.DR.storage:
            self.DR.storage["last_processed"] = None
            self.DR.storage["temp_backfill_done"] = True
        super().setup()

    def get_raw_stream(self) -> Generator[Submission | Comment, None, None]:
        return reddit.sub.mod.stream.reports(pause_after=0)

    def id(self, item: Submission | Comment) -> str:
        return item.fullname

    def get_latest_item(self) -> Submission | Comment | None:
        return next(reddit.sub.mod.reports(limit=1), None)
