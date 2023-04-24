"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import sys
import praw
import logging
from datetime import datetime

from config import settings
import util
from DataStores import LocalDataStore
from PointStore import PointStore
from PointMap import PointMap


# Setup logger
try:
    logger = util.getLogger()
except:
    sys.exit(1)







def main():
    logger.info(f"DRBOT for r/{settings.subreddit} starting up")
    
    reddit = praw.Reddit(client_id=settings.client_id,
                         client_secret=settings.client_secret,
                         username=settings.username,
                         password=settings.password,
                         user_agent=f"DRBOT r/${settings.subreddit} automated moderation bot")
    logger.info(f"Logged in to Reddit as u/{settings.username}")



    data_store = LocalDataStore(logger)
    point_map = PointMap(logger, reddit)
    point_store = PointStore(logger, reddit, point_map, data_store)
    

    # Continually iterate through modlog entries
    for modaction in subreddit.mod.stream.log(skip_existing=True):
    subreddit = reddit.subreddit(settings.subreddit)
        # Ignore any modlog entries that have already been processed
        if datetime.fromtimestamp(modaction.created_utc) <= data_store.get_last_updated():
            continue

        # If a removal reason is added, add the violation to the user's record
        if modaction.action == "addremovalreason":
            point_store.add(modaction)
        # If a comment has been re-approved, remove it from the record
        elif modaction.action == "approvecomment":
            userdict = data_store.get_user(modaction.target_author)
            if modaction.target_fullname in userdict and data_store.remove(modaction.target_author, modaction.target_fullname):
                logger.info(f"-{userdict[modaction.target_fullname]['cost']} to u/{modaction.target_author} from {modaction.target_fullname} (re-approved), now at {data_store.get_user_total(modaction.target_author)}.")



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot manually interrupted - shutting down...")
    except Exception as e:
        logger.critical(e)
        raise e
    logging.shutdown()
