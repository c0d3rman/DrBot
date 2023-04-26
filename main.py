"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import praw
import logging
import schedule
import time
from src.config import settings
from src.log import log
from src.DataStores import LocalDataStore, WikiDataStore
from src.PointStore import PointStore
from src.PointMap import PointMap
from src.InfiniteRetryStrategy import InfiniteRetryStrategy



DRBOT_CLIENT_ID_PATH = "src/drbot_client_id.txt"


def main():
    log.info(f"DRBOT for r/{settings.subreddit} starting up")

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
    log.info(f"Logged in to Reddit as u/{settings.username}")



    if settings.wiki_page != "":
        data_store = WikiDataStore(reddit)
    else:
        data_store = LocalDataStore()
    point_map = PointMap(reddit)
    point_store = PointStore(reddit, point_map, data_store)

    def process_modlog():
        log.debug("Processing new modlog entries.")

        # Collect relevant entries
        entries = []
        for mod_action in reddit.subreddit(settings.subreddit).mod.log(limit=100):
            if not data_store.is_after_last_updated(int(mod_action.created_utc), mod_action.id):
                break
            entries.append(mod_action)

        # Process them in reverse order (earliest to latest)
        for mod_action in reversed(entries):
            # If a removal reason is added, add the violation to the user's record
            if mod_action.action == "addremovalreason":
                point_store.add(mod_action)
            # If a comment has been re-approved, remove it from the record
            elif mod_action.action == "approvecomment":
                userdict = data_store.get_user(mod_action.target_author)
                if mod_action.target_fullname in userdict and data_store.remove(mod_action.target_author, mod_action.target_fullname):
                    log.info(f"-{userdict[mod_action.target_fullname]['cost']} to u/{mod_action.target_author} from {mod_action.target_fullname} (re-approved), now at {data_store.get_user_total(mod_action.target_author)}.")

            data_store.set_last_updated(int(mod_action.created_utc), mod_action.id)

    def save_local():
        if settings.local_backup_file != "":
            log.info(f"Backing up data locally ({settings.local_backup_file})")
            data_store.to_json(settings.local_backup_file)

    schedule.every(5).seconds.do(process_modlog)
    schedule.every().hour.do(point_store.scan_all)
    if settings.local_backup_file != "":
        save_local()
        schedule.every(5).minutes.do(save_local)
    if type(data_store) is WikiDataStore:
        schedule.every().hour.do(data_store.save)

    while True:
        schedule.run_pending()
        time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Bot manually interrupted - shutting down...")
    except Exception as e:
        log.critical(e)
        raise e
    logging.shutdown()
