import praw
import prawcore
from .config import settings
from .log import log
from .InfiniteRetryStrategy import InfiniteRetryStrategy

DRBOT_CLIENT_ID_PATH = "src/drbot_client_id.txt"


def init_reddit():
    if settings.refresh_token != "":
        with open(DRBOT_CLIENT_ID_PATH, "r") as f:
            drbot_client_id = f.read()
        reddit = praw.Reddit(client_id=drbot_client_id,
                             client_secret=None,
                             refresh_token=settings.refresh_token,
                             user_agent="DRBOT")
    else:
        reddit = praw.Reddit(client_id=settings.client_id,
                             client_secret=settings.client_secret,
                             username=settings.username,
                             password=settings.password,
                             user_agent=f"DRBOT")
    reddit._core._retry_strategy_class = InfiniteRetryStrategy
    log.info(f"Logged in to Reddit as u/{reddit.user.me().name}")

    try:
        if not reddit.subreddit(settings.subreddit).user_is_moderator:
            raise Exception(f"u/{reddit.user.me().name} is not a mod in r/{settings.subreddit}")
    except prawcore.exceptions.Forbidden:
        raise Exception(f"r/{settings.subreddit} is private or quarantined.")
    except prawcore.exceptions.NotFound:
        raise Exception(f"r/{settings.subreddit} is banned.")

    return reddit


def get_dupes(L):
    """
    Given a list, get a set of all elements which appear more than once.
    """
    seen, seen2 = set(), set()
    for item in L:
        seen2.add(item) if item in seen else seen.add(item)
    return seen2


def user_exists(reddit, username):
    """Check if a user exists on reddit."""
    try:
        reddit.redditor(username).fullname
    except prawcore.exceptions.NotFound:
        return False  # Account deleted
    except AttributeError:
        return False  # Account suspended
    else:
        return True


def get_thing(reddit, fullname):
    """For getting a comment or submission from a fullname when you don't know which one it is."""
    if fullname.startswith("t1_"):
        return reddit.comment(fullname)
    elif fullname.startswith("t3_"):
        return reddit.submission(fullname[3:])  # PRAW requires us to chop off the "t3_"
    else:
        raise Exception(f"Unknown fullname type: {fullname}")
