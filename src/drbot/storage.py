from __future__ import annotations
from typing import Any
import json
import re
import copy
from prawcore.exceptions import NotFound
from .log import log
from .settings import settings
from .util import DateJSONEncoder, DateJSONDecoder
from .reddit import reddit

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .Regi import Regi


class StorageDict(dict[Any, Any]):
    """A magic dictionary that provides persistent storage.
    You can put anything you want in here so long as it's JSON-serializable, and it will be synced to a wiki page on Reddit."""

    def __init__(self, *args: Any, store: DataStore, encoder: type[json.JSONEncoder] | None = None, decoder: type[json.JSONDecoder] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.__encoder = encoder or DateJSONEncoder
        self.__decoder = decoder or DateJSONDecoder
        self.__store = store

    def to_json(self) -> str:
        """Get a JSON dump of the dict."""
        return json.dumps(self, cls=self.__encoder)

    def from_json(self, json_string: str) -> StorageDict:
        """Discard whatever our data currently is and load a JSON string instead."""
        self.clear()
        self.update(json.loads(json_string, cls=self.__decoder))
        return self

    def force_save(self) -> None:
        """Ask the DataStore to save right now. Don't use this unless there's a good reason you can't wait until the next regular save."""
        self.__store.save()


class DataStore:
    """The data manager for DrBot.
    Generates StorageDicts for Botlings and handles saving and loading their data to the wiki."""

    MAX_PAGE_SIZE = 524288  # Experimentally verified
    _default_meta = {"version": "2.0.0"}

    def __init__(self):
        self.WIKI_PAGE: str = settings.storage.wiki_page
        self.DATA_PAGE: str = f"{settings.storage.wiki_page}/{settings.storage.wiki_data_subpage}"
        self.__raws: dict[str, dict[str, str]] = {}
        self.__dicts: dict[str, dict[str, StorageDict]] = {}

        # Load data from the wiki page
        self.__loaded = False
        self._load()

        log.debug("DataStore initialized.")

    def __getitem__(self, regi: Regi) -> StorageDict:
        """Get a StorageDict for a given Botling or Stream."""

        if regi.kind not in self.__dicts:
            self.__dicts[regi.kind] = {}
        dicts = self.__dicts[regi.kind]
        raws = self.__raws.get(regi.kind, {})

        if regi.name not in dicts:
            log.debug(f"Creating StorageDict for {regi}.")
            dicts[regi.name] = StorageDict(store=self, encoder=regi.json_encoder, decoder=regi.json_decoder)
            if regi.name in raws:
                log.debug(f"Loading existing data into the StorageDict for {regi}.")
                dicts[regi.name].from_json(raws[regi.name])
        return dicts[regi.name]

    def to_json(self) -> str:
        """Dump the DataStore to JSON.
        The data is stored with two layers of JSON dumping - each StorageDict is made into a JSON string, and then the overall dict of names to stringified StorageDicts is made into a JSON string.
        We do it this way to allow each Botling to specify custom JSON encoding/decoding without interfering with the others, and so that we can load the data first and then register Botlings one by one.
        Empty storage dicts are omitted."""

        out = copy.deepcopy(self.__raws)  # Preserve any unparsed raws
        for k, d in self.__dicts.items():
            if k not in out:
                out[k] = {}
            for k2, d2 in d.items():
                if not d2:  # Omit empty dicts
                    if k2 in out[k]:
                        del out[k][k2]  # Delete empty parsed raws if present
                    continue
                out[k][k2] = d2.to_json()
        return json.dumps(out)

    def save(self) -> None:
        """Saves data to the wiki (and stores a local backup)."""

        # First time setup - wiki page creation
        if not reddit.DR.wiki_exists(self.WIKI_PAGE):
            log.info(f"Creating necessary wiki pages.")

            if settings.dry_run:
                log.info(f"DRY RUN: would have created wiki pages {self.WIKI_PAGE} and {self.DATA_PAGE}.")
            else:
                reddit.sub.wiki.create(
                    name=self.WIKI_PAGE,
                    content="This page and its children house the data for [DrBot](https://github.com/c0d3rman/DRBOT). Do not edit.",
                    reason="Automated page for DrBot")
                reddit.sub.wiki[self.WIKI_PAGE].mod.update(listed=True, permlevel=2)  # Make it mod-only

                reddit.sub.wiki.create(
                    name=self.DATA_PAGE,
                    content="",
                    reason="Automated page for DrBot")
                reddit.sub.wiki[self.DATA_PAGE].mod.update(listed=True, permlevel=2)  # Make it mod-only

        dump = f"// This page houses [DrBot](https://github.com/c0d3rman/DRBOT)'s records. **DO NOT EDIT!**\n\n{self.to_json()}"

        if len(dump) > DataStore.MAX_PAGE_SIZE:
            log.error(f"Data is too long to be written to wiki! ({len(dump)}/{DataStore.MAX_PAGE_SIZE} characters.) Check log for full data.")
            log.debug(dump)
            return

        if settings.storage.local_backup_path != "":
            log.debug(f"Backing up data locally to {settings.storage.local_backup_path}.")
            with open(settings.storage.local_backup_path, "w") as f:
                f.write(dump)

        # Don't write if there's no change
        try:
            data = reddit.sub.wiki[self.DATA_PAGE].content_md
        except NotFound:
            if settings.dry_run:
                log.info("DRY RUN: because dry-run mode is active, no wiki pages were created, so no data was read from the wiki.")
                return
            else:
                e = RuntimeError(f"Somehow, tried to fetch wiki page {self.DATA_PAGE} without it existing. This shouldn't happen.")
                log.critical(e)
                raise e
        if data == dump:
            log.debug("Not saving to wiki because it's already identical to what we would have saved.")
            return

        log.info("Saving data to wiki.")

        if settings.dry_run:
            log.info("DRY RUN: would have saved some data to the wiki. (See the debug log for the data.)")
            log.debug(dump)
        else:
            reddit.sub.wiki[self.DATA_PAGE].edit(
                content=dump,
                reason="Automated page for DrBot")

    def _load(self) -> None:
        """This is an internal method and should not be called.
        Loads the data from the wiki, which fetches the raw JSON strings for each Botling's storage.
        These strings are not parsed into StorageDicts until their Botling is registered (and tells us how to decode them).
        The exception is the global _meta, which is parsed right away.
        This method will refuse to load data after initialization."""

        if self.__loaded:
            raise RuntimeError("Do not manually call _load! To avoid clobbering your data, DataStore cannot load data after initialization.")
        self.__loaded = True

        if not reddit.DR.wiki_exists(self.DATA_PAGE):
            log.warning(f"Couldn't load data from the wiki because no wiki page '{self.DATA_PAGE}' exists. If this is your first time running DrBot, this is normal. If not then there is some sort of issue.")
            return

        log.info("Loading data from wiki.")
        try:
            data = reddit.sub.wiki[self.DATA_PAGE].content_md
        except NotFound:
            if settings.dry_run:
                log.info("DRY RUN: because dry-run mode is active, no wiki pages were created, so no data was loaded from the wiki.")
                return
            e = RuntimeError("Wiki pages don't exist even though we checked for them - this shouldn't happen.")
            log.critical(e)
            raise e

        # TBD: Special process if the page is empty - if something breaks we tell users to delete everything in the page, and we just pretend the page isn't there.
        if data == "":
            data = "{}"

        data = re.sub(r"^//.*?\n", "", data)  # Remove comments
        try:
            self.__raws = json.loads(data)
        except json.JSONDecodeError as e:
            log.critical(f"Could not decode JSON data from the wiki! If you can, manually fix the JSON issue in {self.DATA_PAGE}. If not, delete everything from the page and rerun DrBot (but this will lose all of your data). See the log for more information. Error:\n{e}")
            log.debug(f"Problematic data:\n\n{data}")
            raise e

        # Load everything in _meta immediately
        if "_meta" in self.__raws:
            try:
                self.__dicts["_meta"] = {k: StorageDict(store=self).from_json(d) for k, d in self.__raws["_meta"].items()}
                log.debug("Loaded DataStore metadata from wiki.")
            except Exception as e:
                log.critical(f"Could not decode _meta data from the wiki! If you can, manually fix the JSON issue in {self.DATA_PAGE}. If not, delete the _meta data from the page and rerun DrBot (but this will lose any data in _meta). See the log for more information. Error:\n{e}")
                log.debug(f"Problematic data:\n\n{self.__raws['_meta']}")
                raise e
        # Or create _meta if required
        else:
            self.__dicts["_meta"] = {"DrBot": StorageDict(self._default_meta, store=self)}

        log.debug(f"Data loaded:\n{self.to_json()}")
