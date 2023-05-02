from typing import Optional, List
from praw.models import ModAction
from drbot import settings
from drbot.agents import Agent


class ModlogAgent(Agent[ModAction]):
    """Scans incoming modlog entries and runs handlers on them."""

    def get_items(self) -> List[ModAction]:
        items = self.reddit.subreddit(settings.subreddit).mod.log(
            limit=None, params={"before": self.data_store["_meta"]["last_processed"]})  # Yes really, it's 'before' not 'after' - reddit convention has the top of the list being the 'first'
        return list(reversed(list(items)))  # Process from earliest to latest

    def id(self, item: ModAction) -> str:
        return item.id

    def get_latest_item(self) -> Optional[ModAction]:
        if not settings.first_time_retroactive_modlog:
            return next(self.reddit.subreddit(settings.subreddit).mod.log(limit=1))
