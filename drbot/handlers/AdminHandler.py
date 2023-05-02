from __future__ import annotations
import re
from datetime import datetime
import urllib.request
import json
from praw.models import ModAction
from drbot import settings, log
from drbot.util import send_modmail
from drbot.handlers import Handler


class AdminHandler(Handler[ModAction]):
    """Scans the modlog for actions by reddit's admins."""

    def handle(self, item: ModAction) -> None:
        if item._mod == "Anti-Evil Operations":
            log.warning(f"Reddit admins took action {item.action} on item {item.target_fullname} on {datetime.fromtimestamp(item.created_utc)}")

            if item.action == 'removecomment':
                kind = "comment"
            elif item.action == 'removelink':
                kind = "post"
            else:
                # Strange action, send a simple modmail and return
                if settings.admin_modmail:
                    send_modmail(self.reddit, subject=f'Admins took action "{item.action}" in your sub',
                                 body=f"Reddit's Anti-Evil Operations took action {item.action} in your sub. See DRBOT's log for more details.")
                log.info(f"Full info for unknown action type:\n{vars(item)}")
                return

            if settings.admin_modmail:
                message = f"On {datetime.fromtimestamp(item.created_utc)}, reddit's Anti-Evil Operations removed a {kind} in your sub."

                data = json.loads(urllib.request.urlopen(
                    f"https://api.pushshift.io/reddit/{'comment' if kind == 'comment' else 'submission'}/search?ids={item.target_fullname[3:]}&limit=1"
                ).read())['data']

                message += f"\n\nThe [{kind}](https://www.unddit.com{item.target_permalink}) by u/{item.target_author}"

                if len(data) == 0:
                    message += " could not be retrieved from Pushshift."
                else:
                    data = data[0]
                    message += f":\n\n"
                    if kind == "post":
                        message += f">**{data['title']}**\n>\n"
                    message += re.sub(r"^", ">", data['body' if kind == 'comment' else 'selftext'], flags=re.MULTILINE)

                send_modmail(self.reddit, subject=f"Admins removed a {kind} in your sub", body=message)
