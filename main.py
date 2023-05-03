"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import logging
import schedule
import time
from drbot import settings, log
from drbot.stores import *
from drbot.agents import *
from drbot.handlers import *
from drbot.util import init_reddit


def main():
    log.info(f"DRBOT for r/{settings.subreddit} starting up")

    reddit = init_reddit()
    data_store = DataStore()

    # Load from wiki before creating any agents to avoid conflicts
    if settings.wiki_page != "":
        wiki_store = WikiStore(reddit, data_store)
        schedule.every(10).minutes.do(wiki_store.save)

    # Modlog agent
    modlog_agent = ModlogAgent(reddit, data_store)
    points_handler = PointsHandler()
    modlog_agent.register(points_handler)
    modlog_agent.register(SelfModerationHandler())
    modlog_agent.register(AdminHandler())
    schedule.every(5).seconds.do(modlog_agent.run)
    schedule.every().hour.do(points_handler.scan_all)

    # Post agent
    post_agent = PostAgent(reddit, data_store)
    # FF flair ID: 3674207c-e8cc-11ed-83d0-52d642db35f8
    post_agent.register(WeekdayFlairEnforcerHandler(flair_id="d3f4fc1a-ef48-11e1-8db7-12313d28169d", weekday=1))
    schedule.every(5).seconds.do(post_agent.run)

    # Sidebar sync
    sidebar_sync_agent = SidebarSyncAgent(reddit)
    schedule.every(1).hour.do(sidebar_sync_agent.run)

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
