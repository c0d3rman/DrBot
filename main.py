"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import os
import sys
import praw
from dotenv import load_dotenv
import logging
import json

import util
from PointMap import PointMap
from PointStore import PointStore


# Load environment variables from .env
load_dotenv()

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
    logger.info(f"Logging in to Reddit (u/{os.getenv('DRBOT_USERNAME')})...")
    reddit = praw.Reddit(client_id=os.getenv('DRBOT_CLIENT_ID'),
                         client_secret=os.getenv('DRBOT_CLIENT_SECRET'),
                         username=os.getenv('DRBOT_USERNAME'),
                         password=os.getenv('DRBOT_PASSWORD'),
                         user_agent=f"DRBOT r/${os.getenv('DRBOT_SUB')} automated moderation bot")
    logger.info("Logged in successfully")
    return reddit


def main():
    logger.info(f"DRBOT for r/{os.getenv('DRBOT_SUB')} starting up")

    reddit = setup_reddit()
    point_map = PointMap(logger, reddit)
    point_store = PointStore(logger, reddit, point_map)

    # Continually iterate through modlog entries
    subreddit = reddit.subreddit(os.getenv("DRBOT_SUB"))
    for modaction in subreddit.mod.stream.log(skip_existing=True):
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
