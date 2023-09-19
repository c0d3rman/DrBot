from __future__ import annotations
from typing import Any
import json
import re
from prawcore.exceptions import NotFound
from .log import log
from .settings import settings
from .util import DateJSONEncoder, DateJSONDecoder
from .reddit import reddit

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .DrBotling import DrBotling


class DrDict(dict[Any, Any]):
    """A magic dictionary that provides persistent storage for a Botling.
    You can put anything you want in here so long as it's JSON-serializable, and it will be synced to a wiki page on Reddit."""

    def __init__(self, *args: Any, encoder: type[json.JSONEncoder] | None = None, decoder: type[json.JSONDecoder] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__encoder = encoder or DateJSONEncoder
        self.__decoder = decoder or DateJSONDecoder

    def to_json(self) -> str:
        """Get a JSON dump of the dict."""
        return json.dumps(self, cls=self.__encoder)

    def from_json(self, json_string: str) -> DrDict:
        """Discard whatever our data currently is and load a JSON string instead."""
        self.clear()
        self.update(json.loads(json_string, cls=self.__decoder))
        return self


class DrStore:
    """The data manager for DrBot.
    Generates DrDicts for Botlings and handles saving and loading their data to the wiki."""

    MAX_PAGE_SIZE = 524288  # Experimentally verified

    def __init__(self):
        self.WIKI_PAGE: str = settings.storage.wiki_page
        self.DATA_PAGE: str = f"{settings.storage.wiki_page}/{settings.storage.wiki_data_subpage}"
        self.__raws: dict[str, str] = {}
        self.__dicts: dict[str, DrDict] = {}

        # Load data from the wiki page
        self._load()

        # Create a meta dict if needed.
        if not "_meta" in self.__dicts:
            self.__dicts["_meta"] = DrDict({"version": "2.0.0"})

        log.debug("DrStore initialized.")

    def __getitem__(self, botling: DrBotling) -> DrDict:
        """Get a DrDict for a given botling.
        _meta is a reserved name and cannot be used."""

        if botling.name == "_meta":
            raise IndexError("_meta is a reserved name and cannot be used.")
        if not botling.name in self.__dicts:
            log.debug(f"Creating DrDict for Botling {botling.name} ({botling.__class__.__name__}).")
            self.__dicts[botling.name] = DrDict(encoder=botling.json_encoder, decoder=botling.json_decoder)
            if botling.name in self.__raws:
                log.debug(f"Loading existing data into the DrDict for Botling {botling.name} ({botling.__class__.__name__}).")
                self.__dicts[botling.name].from_json(self.__raws[botling.name])
        return self.__dicts[botling.name]

    def to_json(self) -> str:
        """Dump the DrStore to JSON.
        The data is stored with two layers of JSON dumping - each DrDict is made into a JSON string, and then the overall dict of names to stringified DrDicts is made into a JSON string.
        We do it this way to allow each Botling to specify custom JSON encoding/decoding without interfering with the others, and so that we can load the data first and then register Botlings one by one."""

        out = dict(self.__raws)  # Preserve any unparsed raws
        out.update({k: d.to_json() for k, d in self.__dicts.items()})
        return json.dumps(out)

    def save(self) -> None:
        """Saves data to the wiki (and stores a local backup)."""

        # First time setup - wiki page creation
        if not reddit.page_exists(self.WIKI_PAGE):
            log.info(f"Creating necessary wiki pages.")

            # if settings.dry_run:
            #     log.info("[DRY RUN: would have created wiki pages.]")
            #     return

            # self.reddit.sub.wiki.create(
            #     name=self.WIKI_PAGE,
            #     content="This page and its children house the data for [DrBot](https://github.com/c0d3rman/DRBOT). Do not edit.",
            #     reason="Automated page for DrBot")
            # self.reddit.sub.wiki[self.WIKI_PAGE].mod.update(listed=True, permlevel=2)  # Make it mod-only

            # self.reddit.sub.wiki.create(
            #     name=self.DATA_PAGE,
            #     content="",
            #     reason="Automated page for DrBot")
            # self.reddit.sub.wiki[self.DATA_PAGE].mod.update(listed=True, permlevel=2)  # Make it mod-only

        dump = f"// This page houses [DrBot](https://github.com/c0d3rman/DRBOT)'s records. **DO NOT EDIT!**\n\n{self.to_json()}"

        if len(dump) > DrStore.MAX_PAGE_SIZE:
            log.error(f"Data is too long to be written to wiki! ({len(dump)}/{DrStore.MAX_PAGE_SIZE} characters.) Check log for full data.")
            log.debug(dump)
            return

        if settings.storage.local_backup_path != "":
            log.debug(f"Backing up data locally to {settings.storage.local_backup_path}.")
            with open(settings.storage.local_backup_path, "w") as f:
                f.write(dump)

        # Don't write if there's no change
        # try:
        #     data = self.reddit.sub.wiki[self.DATA_PAGE].content_md
        # except NotFound:
        #     log.error(f"Somehow, tried to save wiki page {self.DATA_PAGE} without it existing. This shouldn't happen.")
        #     return
        # else:
        #     if data == dump:
        #         log.debug("Not saving to wiki because it's already identical to what we would save.")
        #         return

        log.info("Saving data to wiki.")

        # if settings.dry_run:
        #     log.info("[DRY RUN: would have saved some data to the wiki.]")
        #     log.debug(f"Data that would be saved:\n\n{dump}")
        #     return

        # self.reddit.sub.wiki[self.DATA_PAGE].edit(
        #     content=dump,
        #     reason="Automated page for DrBot")

    def _load(self) -> None:
        """This is an internal method and should not be called.
        Loads the data from the wiki, which fetches the raw JSON strings for each Botling's storage.
        These strings are not parsed into DrDicts until their Botling is registered (and tells us how to decode them).
        The exception is the global _meta, which is parsed right away."""

        # if not reddit.page_exists(self.DATA_PAGE):
        #     log.info("Couldn't load data from the wiki because no wiki page exists. If this is your first time running DrBot, this is normal. If not then there is some sort of issue.")
        #     return

        log.info("Loading data from wiki.")
        # try:
        #     data = self.reddit.sub.wiki[self.DATA_PAGE].content_md
        # except NotFound:
        #     # if settings.dry_run:
        #     #     log.info("[DRY RUN: because dry-run mode is active, no wiki pages have been created, so no data was loaded from the wiki.]")
        #     #     return
        #     raise Exception("Couldn't load data from wiki because the necessary pages don't exist! Are you trying to manually call _load()?")

        # Special process if the page is empty - if something breaks we tell users to delete everything in the page, and we just pretend the page isn't there.

        data = "{}"

        data = re.sub(r"^//.*?\n", "", data)  # Remove comments
        try:
            self.__raws = json.loads(data)
        except json.JSONDecodeError as e:
            log.critical(f"Could not decode the JSON data from the wiki! If you can, manually fix the JSON issue in {self.DATA_PAGE}. If not, delete everything from the page and rerun DrBot (but this will lose all of your data). Error text:\n{e}")
            raise e

        # Load _meta into a DrDict immediately
        # It should always exist, but if it doesn't we just make a new one.
        if "_meta" in self.__raws:
            self.__dicts["_meta"] = DrDict().from_json(self.__raws["_meta"])
