"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import logging
import schedule
import time
from datetime import timedelta
from drbot import settings, log
from drbot.stores import *
from drbot.agents import *
from drbot.handlers import *


def main():
    log.info(f"DRBOT for r/{settings.subreddit} starting up")

    from drbot import reddit  # Make sure we can login before doing anything else

    data_store = DataStore()

    # Load from wiki before creating any agents to avoid conflicts
    if settings.wiki_page != "":
        wiki_store = WikiStore(data_store)
        schedule.every(10).minutes.do(wiki_store.save)

    # Modlog agent
    modlog_agent = ModlogAgent(data_store)
    points_handler = PointsHandler()
    modlog_agent.register(points_handler)
    modlog_agent.register(SelfModerationHandler())
    modlog_agent.register(AdminHandler())
    schedule.every(5).seconds.do(modlog_agent.run)
    schedule.every().hour.do(points_handler.scan_all)

    # Post agent
    post_agent = PostAgent(data_store)
    # FF flair ID: 3674207c-e8cc-11ed-83d0-52d642db35f8
    post_agent.register(WeekdayFlairEnforcerHandler(flair_id="d3f4fc1a-ef48-11e1-8db7-12313d28169d", weekday=1))
    schedule.every().friday.at("00:00").do(
        lambda: schedule.every(5).seconds.until(timedelta(days=1)).do(post_agent.run)).tag("no_initial")

    # Sidebar sync
    sidebar_sync_agent = SidebarSyncAgent()
    schedule.every(1).hour.do(sidebar_sync_agent.run)

    # Star User flair enforcement
    user_flair_agent = UserFlairAgent(restricted_phrase="⭐", permitted_css_class="staruser")
    schedule.every(1).hour.do(user_flair_agent.run)

    # Run all jobs immediately except those that shouldn't be run initially
    [job.run() for job in schedule.get_jobs() if not "no_initial" in job.tags]
    # The scheduler loop
    while True:
        schedule.run_pending()
        time.sleep(schedule.idle_seconds())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Bot manually interrupted - shutting down...")
    except Exception as e:
        log.critical(e)
        raise e
    logging.shutdown()
