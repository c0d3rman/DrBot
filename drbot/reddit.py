import praw
import prawcore
import random
from typing import Optional
import logging
from drbot import settings, log
from drbot.log import ModmailLoggingHandler, TemplateLoggingFormatter, BASE_FORMAT

DRBOT_CLIENT_ID_PATH = "drbot/drbot_client_id.txt"

_reddit = None


def reddit() -> praw.Reddit:
    global _reddit
    if _reddit is None:
        raise Exception("You need to call reddit.login() before you can use the reddit() object.")
    return _reddit


def login() -> praw.Reddit:
    global _reddit

    if settings.refresh_token != "":
        with open(DRBOT_CLIENT_ID_PATH, "r") as f:
            drbot_client_id = f.read()
        _reddit = praw.Reddit(client_id=drbot_client_id,
                              client_secret=None,
                              refresh_token=settings.refresh_token,
                              user_agent="DRBOT")
    else:
        _reddit = praw.Reddit(client_id=settings.client_id,
                              client_secret=settings.client_secret,
                              username=settings.username,
                              password=settings.password,
                              user_agent=f"DRBOT")

    log.info(f"Logged in to Reddit as u/{_reddit.user.me().name}")

    class InfiniteRetryStrategy(prawcore.sessions.RetryStrategy):
        """For use with PRAW.
        Retries requests forever using capped exponential backoff with jitter.
        This prevents the bot from dying when reddit's servers have an outage or the internet is down.
        Use by setting
            reddit._core._retry_strategy_class = InfiniteRetryStrategy
        right after initializing your praw.Reddit object."""

        def _sleep_seconds(self):
            if self._attempts == 0:
                return None
            if self._attempts > 3:
                log.warn(f"Request still failing after multiple tries, retrying... ({self._attempts})")
            return random.randrange(0, min(self._cap, self._base * 2 ** self._attempts))

        def __init__(self, _base=2, _cap=60, _attempts=0):
            self._base = _base
            self._cap = _cap
            self._attempts = _attempts

        def consume_available_retry(self):
            return type(self)(_base=self._base, _cap=self._cap, _attempts=self._attempts + 1)

        def should_retry_on_failure(self):
            return True

    _reddit._core._retry_strategy_class = InfiniteRetryStrategy

    try:
        if not _reddit.subreddit(settings.subreddit).user_is_moderator:
            raise Exception(f"u/{_reddit.user.me().name} is not a mod in r/{settings.subreddit}")
    except prawcore.exceptions.Forbidden:
        raise Exception(f"r/{settings.subreddit} is private or quarantined.")
    except prawcore.exceptions.NotFound:
        raise Exception(f"r/{settings.subreddit} is banned.")

    # Helper functions bound to the reddit object

    _reddit.sub = _reddit.subreddit(settings.subreddit)

    def user_exists(username: str) -> bool:
        """Check if a user exists on reddit."""
        try:
            _reddit.redditor(username).fullname
        except prawcore.exceptions.NotFound:
            return False  # Account deleted
        except AttributeError:
            return False  # Account suspended
        else:
            return True

    def page_exists(page: str) -> bool:
        try:
            _reddit.sub.wiki[page].may_revise
            return True
        except prawcore.exceptions.NotFound:
            return False

    def get_thing(fullname: str) -> praw.reddit.models.Comment | praw.reddit.models.Submission:
        """For getting a comment or submission from a fullname when you don't know which one it is."""
        if fullname.startswith("t1_"):
            return _reddit.comment(fullname)
        elif fullname.startswith("t3_"):
            return _reddit.submission(fullname[3:])  # PRAW requires us to chop off the "t3_"
        else:
            raise Exception(f"Unknown fullname type: {fullname}")

    def send_modmail(subject: str, body: str, recipient: Optional[praw.reddit.models.Redditor | str] = None, add_common: bool = True, **kwargs) -> None:
        """Sends modmail, handling dry_run mode.
        Creates a moderator discussion by default if a recipient is not provided."""

        # Add common elements
        if add_common:
            subject = "DRBOT: " + subject
            body += "\n\n(This is an automated message by [DRBOT](https://github.com/c0d3rman/DRBOT).)"

        # Hide username by default in modmails to users
        if not recipient is None and not 'author_hidden' in kwargs:
            kwargs['author_hidden'] = True

        if settings.dry_run:
            log.info(f"""[DRY RUN: would have sent the following modmail:
    Subject: "{subject}"
    {body}]""")
        else:
            log.debug(f"""Sending modmail:
    Subject: "{subject}"
    {body}""")

            if len(body) > 10000:
                log.warning(f'Modlog "{subject}" over maximum length, truncating.')
                trailer = "... [truncated]"
                body = body[:10000 - len(trailer)] + trailer

            _reddit.sub.modmail.create(subject=subject, body=body, recipient=recipient, **kwargs)

    def is_mod(username: str | praw.reddit.models.Redditor) -> bool:
        """Check if a user is a mod in your sub"""
        if isinstance(username, praw.reddit.models.Redditor):
            username = username.name
        return len(_reddit.sub.moderator(username)) > 0

    _reddit.user_exists = user_exists
    _reddit.page_exists = page_exists
    _reddit.get_thing = get_thing
    _reddit.send_modmail = send_modmail
    _reddit.is_mod = is_mod

    # Set up logging to modmail
    modmail_handler = ModmailLoggingHandler(_reddit)
    modmail_handler.setFormatter(TemplateLoggingFormatter(fmt=BASE_FORMAT, template={
        logging.ERROR: """DRBOT has encountered a non-fatal error:

```
{log}
```

DRBOT is still running. Check the log for more details.""",
        logging.CRITICAL: """DRBOT has encountered a fatal error and crashed:

```
{log}
```"""}))
    modmail_handler.setLevel(logging.ERROR)
    log.addHandler(modmail_handler)


reddit.login = login
