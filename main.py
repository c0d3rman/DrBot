"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import logging
import schedule
import time
from src.config import settings
from src.log import log
from src.util import init_reddit
from src.ModlogAgent import ModlogAgent
from src.SidebarSyncAgent import SidebarSyncAgent
from src.UserFlairAgent import UserFlairAgent
from src.WikiStore import WikiStore
from src.PointsHandler import PointsHandler


def main():
    log.info(f"DRBOT for r/{settings.subreddit} starting up")

    reddit = init_reddit()

    # Sidebar sync
    sidebar_sync_agent = SidebarSyncAgent(reddit)
    schedule.every(1).day.do(sidebar_sync_agent.run)

    # Modlog agent
    modlog_agent = ModlogAgent(reddit)

    points_handler = PointsHandler()
    modlog_agent.register("PointsHandler", points_handler)

    schedule.every(5).seconds.do(modlog_agent.run)
    schedule.every().hour.do(points_handler.scan_all)
    if settings.wiki_page != "":
        wiki_store = WikiStore(modlog_agent)
        schedule.every().hour.do(wiki_store.save)

    # Star User flair enforcement
    user_flair_agent = UserFlairAgent(reddit, restricted_phrase="⭐", permitted_css_class="staruser")
    schedule.every(1).hour.do(user_flair_agent.run)

    # The scheduler loop
    schedule.run_all()
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
