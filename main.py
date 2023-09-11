"""
DRBOT - Do Really Boring Overhead Tasks
Developed for r/DebateReligion by u/c0d3rman
Free to use by anyone for any reason (licensed under CC0)
"""


import logging
import schedule
import time
from datetime import datetime, timezone
from drbot import settings, log, reddit
from drbot.stores import *
from drbot.agents import *
from drbot.handlers import *


def main():
    log.info(f"DRBOT for r/{settings.subreddit} starting up")

    reddit.login()

    data_store = DataStore()
    schedule.every(1).minute.do(data_store.save)

    # Modlog agent
    modlog_agent = ModlogAgent(data_store)
    points_handler = PointsHandler()
    modlog_agent.register(points_handler)
    modlog_agent.register(SelfModerationHandler())
    modlog_agent.register(AdminHandler())
    schedule.every(5).seconds.do(modlog_agent.run)

    # Post agent
    post_agent = PostAgent(data_store)
    post_agent.register(WeekdayFlairEnforcerHandler(flair_id="3674207c-e8cc-11ed-83d0-52d642db35f8", weekday=4))
    friday_job = schedule.every().friday.at("00:00").do(
        lambda: schedule.every(5).seconds.until("23:59").do(post_agent.run))
    if datetime.now(timezone.utc).weekday() != 4:
        friday_job.tag("no_initial")

    # Sidebar sync
    sidebar_sync_agent = SidebarSyncAgent(data_store)
    schedule.every(1).hour.do(sidebar_sync_agent.run)

    # Archived modmail agent
    archived_modmail_agent = ModmailAgent(data_store, state="archived")
    archived_modmail_agent.register(ModmailMobileLinkHandler())
    archived_modmail_agent.register(ViolationsNotifierHandler(points_handler))
    schedule.every(5).seconds.do(archived_modmail_agent.run)

    # Star User flair enforcement
    user_flair_agent = UserFlairAgent(data_store, restricted_phrase="⭐", permitted_css_class="staruser")
    schedule.every(1).hour.do(user_flair_agent.run)

    # Load from wiki last to load data into the existing agents' data stores
    if settings.wiki_page != "":
        wiki_store = WikiStore(data_store)
        schedule.every(1).minute.do(wiki_store.save)

    # Run all jobs immediately except those that shouldn't be run initially
    [job.run() for job in schedule.get_jobs() if not "no_initial" in job.tags]
    # The scheduler loop
    while True:
        schedule.run_pending()
        t = schedule.idle_seconds()
        if not t is None and t > 0:
            time.sleep(t)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log.info("Bot manually interrupted - shutting down...")
    except Exception as e:
        log.critical(e)
        raise e
    logging.shutdown()
