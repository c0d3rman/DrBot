from __future__ import annotations
import json
import os.path
from praw.models import ModAction
from ..Botling import Botling


class ModlogArchiver(Botling):
    """Archives your modlog to a JSONL file so you can always have a copy even after reddit clears it."""

    default_settings = {"path": "modlog.jsonl"}
    attrs = ['action', 'created_utc', 'description', 'details', 'id', 'mod_id36', 'sr_id36', 'subreddit', 'subreddit_name_prefixed', 'target_author', 'target_body', 'target_fullname', 'target_permalink', 'target_title']

    def setup(self) -> None:
        self.DR.streams.modlog.subscribe(self, self.handle)
        self.file = open(os.path.join(self.DR.global_settings.config.data_folder_path, self.DR.settings.path), 'a', buffering=1)

    def handle(self, item: ModAction) -> None:
        data = {attr: getattr(item, attr) for attr in ModlogArchiver.attrs}
        data["mod"] = item.mod.name  # This is a praw.Redditor object, not a raw data attribute, so we process it separately
        self.file.write(json.dumps(data) + "\n")
        self.file.flush()
