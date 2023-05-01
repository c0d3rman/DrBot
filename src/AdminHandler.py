import re
from datetime import datetime
import urllib.request
import json
from .config import settings
from .log import log
from .Handler import Handler


class AdminHandler(Handler):
    """Scans the modlog for actions by reddit's admins."""

    def handle(self, mod_action):
        if mod_action._mod == "Anti-Evil Operations":
            log.warning(f"Reddit admins took action {mod_action.action} on item {mod_action.target_fullname} on {datetime.fromtimestamp(mod_action.created_utc)}")

            if mod_action.action == 'removecomment':
                kind = "comment"
            elif mod_action.action == 'removelink':
                kind = "post"
            else:
                # Strange action, send a simple modmail and return
                message = f"""Reddit's Anti-Evil Operations took action {mod_action.action} in your sub. See DRBOT's log for more details.

(This is an automated message by [DRBOT](https://github.com/c0d3rman/DRBOT).)"""
                if settings.dry_run:
                    log.info(f"[DRY RUN: would have sent this modmail about the admin removal:\n\n{message}\n\n]")
                else:
                    self.reddit.subreddit(settings.subreddit).modmail.create(
                        subject=f'DRBOT: admins took action "{mod_action.action}" in your sub',
                        body=message,
                        recipient=None)  # None makes it create a moderator discussion
                    log.warning(f"Full info:\n{vars(mod_action)}")
                return

            message = f"On {datetime.fromtimestamp(mod_action.created_utc)}, reddit's Anti-Evil Operations removed a {kind} in your sub."

            data = json.loads(urllib.request.urlopen(
                f"https://api.pushshift.io/reddit/{'comment' if kind == 'comment' else 'submission'}/search?ids={mod_action.target_fullname[3:]}&limit=1"
            ).read())['data']

            message += f"\n\nThe [{kind}](https://www.unddit.com{mod_action.target_permalink}) by u/{mod_action.target_author}"

            if len(data) == 0:
                message += " could not be retrieved from Pushshift."
            else:
                data = data[0]
                message += f":\n\n"
                if kind == "post":
                    message += f">**{data['title']}**\n>\n"
                message += re.sub(r"^", ">", data['body' if kind == 'comment' else 'selftext'], flags=re.MULTILINE)

            message += "\n\n(This is an automated message by [DRBOT](https://github.com/c0d3rman/DRBOT).)"

            if settings.dry_run:
                log.info(f"[DRY RUN: would have sent the following modmail:\n\n{message}\n\n]")
            else:
                self.reddit.subreddit(settings.subreddit).modmail.create(
                    subject=f"DRBOT: admins removed a {kind} in your sub",
                    body=message,
                    recipient=None)  # None makes it create a moderator discussion
