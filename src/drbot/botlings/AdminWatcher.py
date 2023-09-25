from __future__ import annotations
from datetime import datetime, timezone
from praw.models import ModAction
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class AdminWatcher(Botling):
    """Scans the modlog for actions by reddit's admins."""

    default_settings = {
        "modmail": True,  # When we find an admin action, should we send a modmail about it? (Otherwise we just log)
    }

    def setup(self) -> None:
        self.DR.streams.modlog.subscribe(self, self.handle)

    def handle(self, item: ModAction) -> None:
        if item._mod != "Anti-Evil Operations":
            return

        time = datetime.fromtimestamp(item.created_utc, timezone.utc)
        log.info(f"Reddit admins took action {item.action} on item {item.target_fullname} on {time}.")

        if item.action == 'removecomment':
            kind = "comment"
        elif item.action == 'removelink':
            kind = "post"
        else:
            # Strange action, send a simple modmail and return
            if self.DR.settings.modmail:
                reddit.DR.send_modmail(subject=f'Admins took action "{item.action}" in your sub',
                                   body=f"Reddit's Anti-Evil Operations took action {item.action} in your sub. See DRBOT's log for more details.")
            log.info(f'Admins took unknown action "{item.action}". Full info:\n\n{vars(item)}')
            return

        message = f"On {time}, reddit's Anti-Evil Operations removed a [{kind}](https://reddit.com{item.target_permalink}) by u/{item.target_author} in your sub."
        if self.DR.settings.modmail:
            reddit.DR.send_modmail(subject=f"Admins removed a {kind} in your sub", body=message)
        log.info(message)
    
    def validate_settings(self) -> None:
        assert isinstance(self.DR.settings.modmail, bool), "modmail must be a bool"
