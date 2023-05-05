from typing import Optional, List
from praw.models import ModAction
from praw.models.mod_action import ModAction
from drbot import settings, reddit
from drbot.agents import Agent


class ModlogAgent(Agent[ModAction]):
    """Scans incoming modlog entries and runs handlers on them."""

    def get_items(self) -> List[ModAction]:
        items = reddit().sub.mod.log(
            limit=None, params={"before": self.data_store["_meta"]["last_processed"]})  # Yes really, it's 'before' not 'after' - reddit convention has the top of the list being the 'first'
        return list(reversed(list(items)))  # Process from earliest to latest

    def id(self, item: ModAction) -> str:
        return item.id

    def get_latest_item(self) -> Optional[ModAction]:
        if not settings.first_time_retroactive_modlog:
            return next(reddit().sub.mod.log(limit=1))
        
    def skip_item(self, item: ModAction) -> bool:
        return item._mod == reddit().user.me().name
