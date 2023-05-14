from praw.models import ModmailConversation
from datetime import datetime
from drbot import log, reddit
from drbot.agents import HandlerAgent
from drbot.stores import DataStore


class ModmailAgent(HandlerAgent[ModmailConversation]):
    """Scans incoming modmail entries and runs handlers on them."""

    def __init__(self, data_store: DataStore, state: str = "all", name: str | None = None) -> None:
        self.state = state  # Must happen first since get_latest_item is called in the super-constructor
        self.data_store["_meta"]["last_processed_time"] = datetime.min
        super().__init__(data_store, name)

    def get_items(self) -> list[ModmailConversation]:
        # This endpoint doesn't have a 'before' parameter for some reason, so we do it manually
        items = []
        for item in reddit().sub.modmail.conversations(state=self.state, limit=None):
            if self.id(item) == self.data_store["_meta"]["last_processed"]:
                break
            items.append(item)
        return list(reversed(items))  # Process from earliest to latest

    def id(self, item: ModmailConversation) -> str:
        return item.id

    def get_latest_item(self) -> ModmailConversation | None:
        return next(reddit().sub.modmail.conversations(state=self.state, limit=1))

    def skip_item(self, item: ModmailConversation) -> bool:
        # Make sure DRBOT's not already in the thread.
        me = reddit().user.me().name
        if any(me == author.name for author in item.authors):
            return True

        # Safety check to make sure we don't go back in time somehow, which happened once.
        if item.messages[0].date < self.data_store["_meta"]["last_processed_time"]:
            return True
        self.data_store["_meta"]["last_processed_time"] = item.messages[0].date
