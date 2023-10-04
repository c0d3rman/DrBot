from __future__ import annotations
from typing import Any
import random
import logging
from uuid import uuid4
from requests.status_codes import codes
import praw
import prawcore
from drbot import __version__
from .settings import settings
from .log import log, ModmailLoggingHandler, TemplateLoggingFormatter, BASE_FORMAT
from .util import Singleton


class InfiniteRetryStrategy(prawcore.sessions.RetryStrategy):
    """For use with PRAW.
    Retries requests forever using capped exponential backoff with jitter.
    This prevents the bot from dying when reddit's servers have an outage or the internet is down.
    Use by setting
        reddit._core._retry_strategy_class = InfiniteRetryStrategy
    right after initializing your praw.Reddit object."""

    def _sleep_seconds(self) -> int | None:
        if self._attempts == 0:
            return None
        if self._attempts > 3:
            log.warn(f"Request still failing after {self._attempts} tries, retrying...")
        return random.randrange(0, min(self._cap, self._base * 2 ** self._attempts))

    def __init__(self, _base: int = 2, _cap: int = 60, _attempts: int = 0) -> None:
        self._base = _base
        self._cap = _cap
        self._attempts = _attempts

    def consume_available_retry(self) -> InfiniteRetryStrategy:
        return type(self)(_base=self._base, _cap=self._cap, _attempts=self._attempts + 1)

    def should_retry_on_failure(self) -> bool:
        return True


# Hack to solve 429s
del prawcore.Session.STATUS_EXCEPTIONS[codes["too_many_requests"]]
prawcore.Session.RETRY_STATUSES.add(codes["too_many_requests"])


class DrReddit(praw.Reddit, Singleton):
    """A singleton that handles all of DrBot's communication with Reddit.
    Everything passes through here so that safeguards, rate limits, and dry run mode function globally."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        if self._initialized:
            return
        super().__init__(*args, **kwargs)
        self._core._retry_strategy_class = InfiniteRetryStrategy
        self.DR = self._DrRedditHelper(self)

    @property
    def sub(self) -> praw.reddit.models.SubredditHelper:
        return self.subreddit(settings.subreddit)

    class _DrRedditHelper():
        """A helper that contains a bunch of convenient reddit functions for use by Botlings and other DrBot components."""

        def __init__(self, reddit: DrReddit):
            self._reddit = reddit

        def user_exists(self, username: str) -> bool:
            """Check if a user exists on reddit."""
            try:
                self._reddit.redditor(username).fullname
            except prawcore.exceptions.NotFound:
                return False  # Account deleted
            except AttributeError:
                return False  # Account suspended
            else:
                return True

        def wiki_exists(self, page: str) -> bool:
            """Check if a wiki page exists on reddit."""
            try:
                self._reddit.sub.wiki[page].may_revise
                return True
            except prawcore.exceptions.NotFound:
                return False

        def get_thing(self, fullname: str) -> praw.reddit.models.Comment | praw.reddit.models.Submission:
            """For getting a comment or submission from a fullname when you don't know which one it is."""
            if fullname.startswith("t1_"):
                return self._reddit.comment(fullname)
            elif fullname.startswith("t3_"):
                return self._reddit.submission(fullname[3:])  # PRAW requires us to chop off the "t3_"
            else:
                raise ValueError(f"Unknown fullname type: {fullname}")

        def send_modmail(self, subject: str, body: str, recipient: praw.reddit.models.Redditor | str | None = None, add_common: bool = True, archive: bool = False, **kwargs: Any) -> praw.reddit.models.ModmailConversation | None:
            """Sends modmail while handling adding common DrBot elements and such.
            Creates a moderator discussion by default if a recipient is not provided."""

            # Add common elements
            if add_common:
                subject = "DrBot: " + subject
                body += "\n\n(This is an automated message by [DrBot](https://github.com/c0d3rman/DrBot).)"

            # Hide username by default in modmails to users
            if recipient is not None and 'author_hidden' not in kwargs:
                kwargs['author_hidden'] = True

            # Truncate if necessary
            if len(body) > 10000:
                log.warning(f'Modlog "{subject}" over maximum length, truncating.')
                trailer = "... [truncated]"
                body = body[:10000 - len(trailer)] + trailer

            log.info(f'Sending modmail {"as mod discussion " if recipient is None else f"to u/{recipient} "}with subject "{subject}"')

            if settings.dry_run:
                log.info(f"""DRY RUN: would have sent the following modmail:
Recipient: {"mod discussion" if recipient is None else f"u/{recipient}"}
Subject: "{subject}"
{body}""")

                # Create a fake modmail to return so as to not break callers that need one in dry run mode
                def fake_modmail(): return None
                fake_modmail.id = f"fakeid_{uuid4().hex}"
                return fake_modmail
            else:
                log.debug(f"""Sending modmail:
Recipient: {"mod discussion" if recipient is None else f"u/{recipient}"}
Subject: "{subject}"
{body}""")

                modmail = self._reddit.sub.modmail.create(subject=subject, body=body, recipient=recipient, **kwargs)
                if archive:
                    modmail.archive()
                return modmail

        def is_mod(self, username: str | praw.reddit.models.Redditor | None) -> bool:
            """Check if a user is a mod in your sub."""
            if username is None:
                return False
            if isinstance(username, praw.reddit.models.Redditor):
                username = username.name
            return len(self._reddit.sub.moderator(username)) > 0


# Log in to reddit and initialize the singleton
if settings.reddit_auth._refresh_token != "":
    log.debug(f"Logging in to reddit using refresh token... (client id '{settings.reddit_auth.drbot_client_id}')")
    reddit = DrReddit(client_id=settings.reddit_auth.drbot_client_id,
                      client_secret=None,
                      refresh_token=settings.reddit_auth._refresh_token,
                      user_agent=f"DrBot v{__version__}")
elif settings.reddit_auth.manual._username != "":
    log.debug(f"Logging in to reddit using username + password + client_secret... (client id '{settings.reddit_auth.drbot_client_id}')")
    reddit = DrReddit(client_id=settings.reddit_auth.drbot_client_id,
                      client_secret=settings.reddit_auth.manual._client_secret,
                      username=settings.reddit_auth.manual._username,
                      password=settings.reddit_auth.manual._password,
                      user_agent=f"DrBot v{__version__}")
else:
    e = RuntimeError("You need to set a login method in settings/secrets.toml!")
    log.critical(e)
    raise e

# Make sure we're logged in
try:
    assert reddit.user.me() is not None
except (prawcore.exceptions.ResponseException, AssertionError) as e:
    log.critical("Failed to log in to reddit. Are your login details correct?")
    raise RuntimeError("Failed to log in to reddit. Are your login details correct?") from None

log.info(f"Logged in to reddit as u/{reddit.user.me().name}")

try:
    if not reddit.subreddit(settings.subreddit).user_is_moderator:
        e = RuntimeError(f"u/{reddit.user.me().name} is not a mod in r/{settings.subreddit}")
        log.critical(e)
        raise e
except prawcore.exceptions.Forbidden:
    e = RuntimeError(f"r/{settings.subreddit} is private or quarantined.")
    log.critical(e)
    raise e
except prawcore.exceptions.NotFound:
    e = RuntimeError(f"r/{settings.subreddit} is banned.")
    log.critical(e)
    raise e

# Set up logging to modmail
if settings.logging.modmail_errors:
    modmail_handler = ModmailLoggingHandler(reddit)
    modmail_handler.setFormatter(TemplateLoggingFormatter(fmt=BASE_FORMAT, template={
        logging.ERROR: """DrBot has encountered a non-fatal error:

{log}

DrBot is still running. Check the log for more details.""",
        logging.CRITICAL: """DrBot has encountered a fatal error and crashed:

{log}"""}))
    modmail_handler.setLevel(logging.ERROR)
    log.addHandler(modmail_handler)
