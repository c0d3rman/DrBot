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
from src.Agent import Agent
from src.WikiStore import WikiStore
from src.PointsHandler import PointsHandler


def main():
    log.info(f"DRBOT for r/{settings.subreddit} starting up")

    agent = Agent()

    points_handler = PointsHandler()
    agent.register("PointsHandler", points_handler)

    schedule.every(5).seconds.do(agent.run)
    schedule.every().hour.do(points_handler.scan_all)
    if settings.local_backup_file != "":
        schedule.every(5).minutes.do(agent.save)
    if settings.wiki_page != "":
        wiki_store = WikiStore(agent)
        schedule.every().hour.do(wiki_store.save)

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
