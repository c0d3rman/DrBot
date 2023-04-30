import datetime
import json
from .config import settings
from .log import log
from .Handler import Handler


class ModlogAgent:
    """Scans incoming modlog entries and runs sub-tools on them.
    Provides a Reddit object and a writable data store.
    Manages syncing data to the wiki."""

    def __init__(self, reddit):
        self.reddit = reddit
        self.data_store = {"_meta": {"version": "1.0", "last_processed": None}}
        self.handlers = {}

    def register(self, name: str, handler: Handler) -> None:
        if name == "_meta":
            log.error(f"Illegal handler name - cannot be _meta. Ignoring.")
            return
        if name in self.handlers:
            log.warning(f"Handler {name} already registered, overwriting.")
        self.handlers[name] = handler
        self.data_store[name] = {}
        handler.init(self.data_store[name], self.reddit)

    def run(self) -> None:
        # Gather new modlog entries
        entries = list(self.reddit.subreddit(settings.subreddit).mod.log(limit=None, params={"before": self.data_store["_meta"]["last_processed"]}))  # Yes really, it's 'before' not 'after' - reddit convention has the top of the list being the 'first'
        if len(entries) == 0:
            return
        log.info(f"Processing {len(entries)} new modlog entries.")

        # Process entries from earliest to latest
        for mod_action in reversed(entries):
            self.data_store["_meta"]["last_processed"] = mod_action.id
            for handler in self.handlers.values():
                handler.handle(mod_action)

        # Make a local backup
        self.save()

    @classmethod
    def _json_encoder(self, obj):
        if isinstance(obj, (datetime.date, datetime.datetime)):
            return {"$date": obj.isoformat()}
        return obj

    @classmethod
    def _json_decoder(self, d):
        if "$date" in d:
            return datetime.datetime.fromisoformat(d["$date"])
        return d

    def to_json(self) -> None:
        return json.dumps(self.data_store, default=ModlogAgent._json_encoder)

    def from_json(self, s: str) -> None:
        self.data_store = json.loads(s, object_hook=ModlogAgent._json_decoder)
        assert "_meta" in self.data_store

    def save(self):
        if settings.local_backup_file != "":
            log.info(f"Backing up data locally ({settings.local_backup_file}).")
            with open(settings.local_backup_file, "w") as f:
                f.write(self.to_json())
