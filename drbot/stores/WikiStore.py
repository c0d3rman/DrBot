import re
from prawcore.exceptions import NotFound
from drbot import settings, log, reddit
from drbot.stores import DataStore


class WikiStore:
    DATA_PAGE = f"{settings.wiki_page}/data"
    MAX_PAGE_SIZE = 524288  # Experimentally verified

    def __init__(self, data_store: DataStore):
        assert settings.wiki_page != ""

        self.data_store = data_store

        # First time setup - wiki page creation
        if not reddit().page_exists(settings.wiki_page):
            self._create_pages()

        self._load()

    def save(self) -> None:
        dump = f"// This page houses [DRBOT](https://github.com/c0d3rman/DRBOT)'s user records. **DO NOT EDIT!**\n\n{self.data_store.to_json()}"

        if len(dump) > WikiStore.MAX_PAGE_SIZE:
            log.error(f"Data is too long to be written to wiki! ({len(dump)}/{WikiStore.MAX_PAGE_SIZE} characters.) Check log for full data.")
            log.debug(dump)
            return
        
        # Don't write if there's no change
        try:
            data = reddit().sub.wiki[WikiStore.DATA_PAGE].content_md
        except NotFound:
            log.error(f"Somehow, tried to save wiki page {WikiStore.DATA_PAGE} without it existing.")
            return
        else:
            if data == dump:
                log.debug("Not saving to wiki because it's already identical to what we would save.")
                return
        
        log.info("Saving data to wiki.")

        if settings.dry_run:
            log.info("[DRY RUN: would have saved some data to the wiki.]")
            log.debug(f"Data that would be saved:\n\n{dump}")
            return

        reddit().sub.wiki[WikiStore.DATA_PAGE].edit(
            content=dump,
            reason="Automated page for DRBOT")

    def _load(self) -> None:
        log.info("Loading data from wiki.")
        try:
            data = reddit().sub.wiki[WikiStore.DATA_PAGE].content_md
        except NotFound:
            if settings.dry_run:
                log.info("[DRY RUN: because dry-run mode is active, no wiki pages have been created, so no data was loaded from the wiki.]")
                return
            raise Exception("WikiStore couldn't load data because the necessary pages don't exist! Are you trying to manually call _load()?")
        data = re.sub(r"^//.*?\n", "", data)  # Remove comments
        self.data_store.from_json(data)

    def _create_pages(self) -> None:
        log.info(f"Creating necessary wiki pages.")

        if settings.dry_run:
            log.info("[DRY RUN: would have created wiki pages.]")
            return

        reddit().sub.wiki.create(
            name=settings.wiki_page,
            content="This page and its children house the data for [DRBOT](https://github.com/c0d3rman/DRBOT). Do not edit.",
            reason="Automated page for DRBOT")
        reddit().sub.wiki[settings.wiki_page].mod.update(listed=True, permlevel=2)  # Make it mod-only

        reddit().sub.wiki.create(
            name=WikiStore.DATA_PAGE,
            content="",
            reason="Automated page for DRBOT")
        reddit().sub.wiki[WikiStore.DATA_PAGE].mod.update(listed=True, permlevel=2)  # Make it mod-only

        self.save()  # Populate the pages
