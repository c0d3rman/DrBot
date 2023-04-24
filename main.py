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
    subreddit = reddit.subreddit(settings.subreddit)
    for mod_action in subreddit.mod.stream.log(skip_existing=True):
        # Ignore any modlog entries that have already been processed
        if not data_store.is_after_last_updated(int(mod_action.created_utc), mod_action.id):
            continue

        # If a removal reason is added, add the violation to the user's record
        if mod_action.action == "addremovalreason":
            point_store.add(mod_action)
        # If a comment has been re-approved, remove it from the record
        elif mod_action.action == "approvecomment":
            userdict = data_store.get_user(mod_action.target_author)
            if mod_action.target_fullname in userdict and data_store.remove(mod_action.target_author, mod_action.target_fullname):
                logger.info(f"-{userdict[mod_action.target_fullname]['cost']} to u/{mod_action.target_author} from {mod_action.target_fullname} (re-approved), now at {data_store.get_user_total(mod_action.target_author)}.")



if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot manually interrupted - shutting down...")
    except Exception as e:
        logger.critical(e)
        raise e
    logging.shutdown()
