"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import sys
import praw
import logging

from config import settings
import util
from PointMap import PointMap
from PointStore import PointStore



# Setup logger
try:
    logger = util.getLogger()
except:
    sys.exit(1)

last_update_utc = 0






def setup_reddit():
    """
    Setup reddit access.
    """
    logger.info(f"Logging in to Reddit (u/{settings.username})...")
    reddit = praw.Reddit(client_id=settings.client_id,
                         client_secret=settings.client_secret,
                         username=settings.username,
                         password=settings.password,
                         user_agent=f"DRBOT r/${settings.subreddit} automated moderation bot")
    logger.info("Logged in successfully")
    return reddit


def main():
    logger.info(f"DRBOT for r/{settings.subreddit} starting up")

    reddit = setup_reddit()
    point_map = PointMap(logger, reddit)
    point_store = PointStore(logger, reddit, point_map)

    # Continually iterate through modlog entries
    for modaction in subreddit.mod.stream.log(skip_existing=True):
    subreddit = reddit.subreddit(settings.subreddit)
        # Ignore any modlog entries that have already been processed
        if modaction.created_utc <= last_update_utc:
            continue

        # We only care about removal reasons
        if modaction.action != "addremovalreason":
            continue

        point_store.add(modaction)




if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot manually interrupted - shutting down...")
    logging.shutdown()
