from prawcore.sessions import RetryStrategy
import random
from .log import log


class InfiniteRetryStrategy(RetryStrategy):
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
