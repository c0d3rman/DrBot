from __future__ import annotations
import abc
from typing import Any, Optional
from datetime import datetime
import json
import re
from prawcore.exceptions import NotFound

from log import log
from config import settings


class DataStore(metaclass=abc.ABCMeta):
    @classmethod
    def __subclasshook__(cls, subclass):
        abstract_methods = ["add", "remove", "get_user", "remove_user", "all_users", "_is_after_last_updated", "_set_last_updated"]
        return all(hasattr(subclass, x) and callable(getattr(subclass, x)) for x in abstract_methods) or NotImplemented

    @abc.abstractmethod
    def add(self, username: str, violation_fullname: str, point_cost: int, expires: Optional[datetime] = None) -> bool:
        """Add a violation to a user's record. Returns True if the data structure was changed."""
        raise NotImplementedError

    @abc.abstractmethod
    def remove(self, username: str, violation_fullname: str) -> bool:
        """Remove a violation from a user's record. Returns True if the data structure was changed."""
        raise NotImplementedError

    @abc.abstractmethod
    def get_user(self, username: str) -> dict[str, Any]:
        """Get all violations of a user."""
        raise NotImplementedError

    def get_user_total(self, username: str):
        """Convenience method to get the total points from a user."""
        return sum(x["cost"] for x in self.get_user(username).values())

    @abc.abstractmethod
    def remove_user(self, username: str) -> bool:
        """Remove a user's entire record. Returns True if the data structure was changed."""
        raise NotImplementedError

    @abc.abstractmethod
    def all_users(self) -> list[str]:
        """Get a list of all users who have violations."""
        raise NotImplementedError

    def is_after_last_updated(self, time: datetime | int, id: str) -> bool:
        """Check if a given time and id has been processed already (i.e. is not after the last updated)."""
        if type(time) is datetime:
            time = int(datetime.timestamp(time))
        return self._is_after_last_updated(time, id)

    @abc.abstractmethod
    def _is_after_last_updated(self, time: int, id: str) -> bool:
        """Check if a given time and id has been processed already (i.e. is not after the last updated)."""
        raise NotImplementedError

    def set_last_updated(self, time: datetime | int, id: str) -> bool:
        """Set the time of the latest entry with which the data store was updated.
        Will refuse to decrement the time - it can only increase.
        Returns True if the time was updated and False if it wasn't."""
        if type(time) is datetime:
            time = int(datetime.timestamp(time))
        return self._set_last_updated(time, id) if self.is_after_last_updated(time, id) else False

    @abc.abstractmethod
    def _set_last_updated(self, time: int, id: str) -> bool:
        """Set the time of the latest entry with which the data store was updated.
        Implement this without safety checking for decrementing the time; the parent class method takes care of it.
        Returns True if the time was updated and False if it wasn't."""
        raise NotImplementedError


class LocalDataStore(DataStore):
    """Stores all data locally in a dict."""

    def __init__(self):
        self.megadict = {}
        self.meta = {
            "last_updated": {"time": 0, "ids": []}
        }
        super().__init__()

    def add(self, username: str, violation_fullname: str, point_cost: int, expires: Optional[datetime] = None) -> bool:
        if not username in self.megadict:
            self.megadict[username] = {}
        elif violation_fullname in self.megadict[username]:
            log.debug(f"Can't add {violation_fullname} to u/{username} (already exists).")
            return False
        self.megadict[username][violation_fullname] = {"cost": point_cost}
        if not expires is None:
            self.megadict[username][violation_fullname]["expires"] = int(datetime.timestamp(expires))
        log.debug(f"Added {violation_fullname} to u/{username}.")
        return True

    def remove(self, username: str, violation_fullname: str) -> bool:
        if not username in self.megadict:
            log.debug(f"Can't remove {violation_fullname} from u/{username} (user doesn't exist).")
            return False
        if not violation_fullname in self.megadict[username]:
            log.debug(f"Can't remove {violation_fullname} from u/{username} (violation doesn't exist).")
            return False
        del self.megadict[username][violation_fullname]
        log.debug(f"Removed {violation_fullname} from u/{username}.")
        if len(self.megadict[username]) == 0:
            del self.megadict[username]
        return True

    def get_user(self, username: str) -> dict[str, Any]:
        return {k1: {k2: datetime.fromtimestamp(v2) if k2 == "expires" else v2 for k2, v2 in v1.items()} for k1, v1 in self.megadict.get(username, {}).items()}

    def remove_user(self, username: str) -> bool:
        if not username in self.megadict:
            log.debug(f"Can't remove u/{username} (doesn't exist).")
            return False
        log.debug(f"Removed u/{username}.")
        del self.megadict[username]
        return True

    def all_users(self) -> list[str]:
        return list(self.megadict.keys())

    def _is_after_last_updated(self, time: int, id: str) -> bool:
        return time > self.meta["last_updated"]["time"] or (time == self.meta["last_updated"]["time"] and id in self.meta["last_updated"]["ids"])

    def _set_last_updated(self, time: int, id: str) -> bool:
        if time > self.meta["last_updated"]["time"]:
            self.meta["last_updated"]["time"] = time
            self.meta["last_updated"]["ids"] = [id]
            return True
        # Edge case: multiple modlog entries with exact same timestamp.
        # In this case we keep a running list of the ones we've already processed
        elif time == self.meta["last_updated"]["time"]:
            if id in self.meta["last_updated"]["ids"]:
                return False
            self.meta["last_updated"]["ids"].append(id)
            return True

    def to_json(self, path: str | None = None) -> None:
        data = json.dumps({"meta": self.meta, "megadict": self.megadict})
        if not path is None:
            with open(path, "w") as f:
                f.write(data)
            log.debug(f"Saved LocalDataStore to {path}")
        return data

    @classmethod
    def from_json(cls, path: str) -> LocalDataStore:
        x = cls()
        with open(path, "r") as f:
            raw = json.load(f)
            x.meta = raw["meta"]
            x.megadict = raw["megadict"]
        log.debug(f"Loaded LocalDataStore from {path}")


class WikiDataStore(LocalDataStore):
    DATA_PAGE = f"{settings.wiki_page}/data"

    def __init__(self, reddit):
        super().__init__()
        self.reddit = reddit

        # First time setup - wiki page creation
        if not self.page_exists(settings.wiki_page):
            self._create_pages()

        self._load()

    def page_exists(self, page: str) -> bool:
        try:
            self.reddit.subreddit(settings.subreddit).wiki[page].may_revise
            return True
        except NotFound:
            return False

    def save(self) -> None:
        log.info("Saving data to wiki.")

        if settings.dry_run:
            log.info("(Skipping actual save because dry-run mode is active.)")
            return

        self.reddit.subreddit(settings.subreddit).wiki[WikiDataStore.DATA_PAGE].edit(
            content=f"// This page houses [DRBOT](https://github.com/c0d3rman/DRBOT)'s user records. **DO NOT EDIT!**\n\n{self.to_json()}",
            reason="Automated page for DRBOT")

    def _load(self) -> None:
        log.info("Loading data from wiki.")
        try:
            data = self.reddit.subreddit(settings.subreddit).wiki[WikiDataStore.DATA_PAGE].content_md
        except NotFound:
            if settings.dry_run:
                log.info("Because dry-run mode is active, no wiki pages have been created, so no data was loaded from the wiki.")
                return
            raise Exception("WikiDataStore couldn't load data because the necessary pages don't exist! Are you trying to manually call _load()?")
        data = re.sub(r"^//.*?\n", "", data)  # Remove comments
        data = json.loads(data)
        self.megadict = data["megadict"]
        self.meta = data["meta"]

    def _create_pages(self) -> None:
        log.info(f"Creating necessary wiki pages.")

        if settings.dry_run:
            log.info("(Skipping actual page creation because dry-run mode is active.)")
            return

        self.reddit.subreddit(settings.subreddit).wiki.create(
            name=settings.wiki_page,
            content="This page and its children house the data for [DRBOT](https://github.com/c0d3rman/DRBOT). Do not edit.",
            reason="Automated page for DRBOT")
        self.reddit.subreddit(settings.subreddit).wiki[settings.wiki_page].mod.update(listed=True, permlevel=2)  # Make it mod-only

        self.reddit.subreddit(settings.subreddit).wiki.create(
            name=WikiDataStore.DATA_PAGE,
            content=f"",
            reason="Automated page for DRBOT")
        self.reddit.subreddit(settings.subreddit).wiki[WikiDataStore.DATA_PAGE].mod.update(listed=True, permlevel=2)  # Make it mod-only

        self.save() # Populate the pages
