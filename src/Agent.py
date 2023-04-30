import praw
import datetime
import json
from .config import settings
from .log import log
from .InfiniteRetryStrategy import InfiniteRetryStrategy
from .Handler import Handler


DRBOT_CLIENT_ID_PATH = "src/drbot_client_id.txt"


class Agent:
    """A bot that scans incoming modlog entries and runs sub-tools on them.
    Provides a Reddit object and a writable data store.
    Manages syncing data to the wiki."""

    def __init__(self):
        self.data_store = {"_meta": {"version": "1.0", "last_processed": None}}
        self._initialize_reddit()
        self.handlers = {}

    def _initialize_reddit(self):
        if settings.refresh_token != "":
            with open(DRBOT_CLIENT_ID_PATH, "r") as f:
                drbot_client_id = f.read()
            self.reddit = praw.Reddit(client_id=drbot_client_id,
                                      client_secret=None,
                                      refresh_token=settings.refresh_token,
                                      user_agent="DRBOT")
        else:
            self.reddit = praw.Reddit(client_id=settings.client_id,
                                      client_secret=settings.client_secret,
                                      username=settings.username,
                                      password=settings.password,
                                      user_agent=f"DRBOT")
        self.reddit._core._retry_strategy_class = InfiniteRetryStrategy
        log.info(f"Logged in to Reddit as u/{settings.username}")

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
        return json.dumps(self.data_store, default=Agent._json_encoder)

    def from_json(self, s: str) -> None:
        self.data_store = json.loads(s, object_hook=Agent._json_decoder)
        assert "_meta" in self.data_store

    def save(self):
        if settings.local_backup_file != "":
            log.info(f"Backing up data locally ({settings.local_backup_file}).")
            with open(settings.local_backup_file, "w") as f:
                f.write(self.to_json())
