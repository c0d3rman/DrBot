import datetime
import json
from typing import Any
from drbot import settings, log


class DataStore(dict):
    def __init__(self) -> None:
        super().__init__()
        self["_meta"] = {"version": "1.0"}

    @classmethod
    def _json_encoder(self, obj: Any) -> Any:
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return {"$date": obj.isoformat()}
        return obj

    @classmethod
    def _json_decoder(self, d: dict) -> dict:
        if "$date" in d:
            return datetime.datetime.fromisoformat(d["$date"])
        return d

    def to_json(self) -> None:
        """Get the DataStore as a JSON dump."""

        return json.dumps(self, default=DataStore._json_encoder)

    def from_json(self, s: str) -> None:
        """Initialize the DataStore from a JSON dump (overwrites whatever's already there)."""

        self.clear()
        for k, v in json.loads(s, object_hook=DataStore._json_decoder).items():
            self[k] = v
        assert "_meta" in self

    def save(self) -> None:
        """Save the DataStore to a local file."""

        if settings.local_backup_file != "":
            log.info(f"Backing up data locally ({settings.local_backup_file}).")
            with open(settings.local_backup_file, "w") as f:
                f.write(self.to_json())
