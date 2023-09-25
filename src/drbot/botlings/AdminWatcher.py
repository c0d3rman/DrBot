from __future__ import annotations
from datetime import datetime, timezone
from praw.models import ModAction
from ..log import log
from ..reddit import reddit
from ..Botling import Botling


class AdminWatcher(Botling):
    """Scans the modlog for actions by reddit's admins."""

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
            reddit.DR.send_modmail(subject=f'Admins took action "{item.action}" in your sub',
                                 body=f"Reddit's Anti-Evil Operations took action {item.action} in your sub. See DRBOT's log for more details.")
            log.info(f"Full info for unknown action type:\n\n{vars(item)}")
            return

        reddit.DR.send_modmail(subject=f"Admins removed a {kind} in your sub",
                             body=f"On {time}, reddit's Anti-Evil Operations removed a [{kind}](https://reddit.com{item.target_permalink}) by u/{item.target_author} in your sub.")
