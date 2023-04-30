import praw
from typing import Optional
from .config import settings
from .log import log


class UserFlairAgent:
    """Allows you to set a restricted phrase that can only be used by certain users in their flair.
    Scans every single user who has ever assigned themselves flair in your sub,
    so this is not a good idea for bigger subs.
    TBD: recommended alongside an automod rule"""

    def __init__(self, reddit: praw.Reddit, restricted_phrase: str, permitted_css_class: Optional[str] = None):
        self.reddit = reddit
        self.restricted_phrase = restricted_phrase
        self.permitted_css_class = permitted_css_class

    def run(self) -> None:
        log.info(f'Scanning user flair for restricted phrase "{self.restricted_phrase}", which is only permitted for users with CSS class "{self.permitted_css_class}".')
        count = 0
        for flair in self.reddit.subreddit(settings.subreddit).flair(limit=None):
            count += 1
            if (flair['flair_css_class'] != self.permitted_css_class
                    and not flair['flair_text'] is None
                    and self.restricted_phrase in flair['flair_text']):
                log.warning(f"u/{flair['user'].name} (class {flair['flair_css_class']}) has banned flair: <{flair['flair_text']}>")
        log.info(f"Scanned flair for {count} users.")
