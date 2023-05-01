from datetime import datetime
from .config import settings
from .log import log
from .Handler import Handler


class AdminHandler(Handler):
    """Scans the modlog for actions by reddit's admins."""

    def handle(self, mod_action):
        if mod_action._mod == "Anti-Evil Operations":
            log.warning(f"Reddit admins took action {mod_action.action} on item {mod_action.target_fullname} on {datetime.fromtimestamp(mod_action.created_utc)}")
