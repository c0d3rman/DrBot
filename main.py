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


# Logging formatter supporting colorized output
class LogFormatter(logging.Formatter):
    COLOR_CODES = {
        logging.CRITICAL: "\033[1;35m",  # bright/bold magenta
        logging.ERROR:    "\033[1;31m",  # bright/bold red
        logging.WARNING:  "\033[1;33m",  # bright/bold yellow
        logging.INFO:     "\033[0;37m",  # white / light gray
        logging.DEBUG:    "\033[1;30m"  # bright/bold black / dark gray
    }

    def __init__(self, fmt="[%(asctime)s] [%(threadName)s] %(levelname)-8s | %(message)s", *args, **kwargs):
        super(LogFormatter, self).__init__(
            fmt=f"%(color_on)s{fmt}%(color_off)s", *args, **kwargs)

    RESET_CODE = "\033[0m"

    def format(self, record, *args, **kwargs):
        if (record.levelno in self.COLOR_CODES):
            record.color_on = self.COLOR_CODES[record.levelno]
            record.color_off = self.RESET_CODE
        else:
            record.color_on = ""
            record.color_off = ""
        return super(LogFormatter, self).format(record, *args, **kwargs)


class PointStore:
    def __init__(self):
        self.megadict = {}
        pass

    # Add points for a removal.
    # Returns true if it was added and false if it wasn't.
    # Triggers a ban if the addition causes the user goes over the threshold.
    def add(self, username, submission_fullname, point_cost):
        if point_cost == 0:
            logger.debug(
                f"{submission_fullname} ignored because it costs 0 points.")
            return False

        if not username in self.megadict:
            self.megadict[username] = {}
        if submission_fullname in self.megadict[username]:
            logger.debug(f"{submission_fullname} already accounted for.")
            return False

        self.megadict[username][submission_fullname] = point_cost
        new_total = self.get_total(username)
        logger.info(
            f"+{point_cost} to u/{username} from {submission_fullname} (now at {new_total}).")

        # Check for ban
        if new_total >= int(os.getenv("DRBOT_POINT_THRESHOLD")):
            self.ban(username, new_total)

    # Get the total current points for a user
    def get_total(self, username):
        return sum(self.megadict[username].values())

    # Act on a user hitting the threshold.
    # Either bans them or just sends modmail.
    # Assumes you've already checked the total is over the threshold.
    def ban(self, username, total):
        logger.error(f"Banning u/{username} for reaching {total} points.")


# Load environment variables from .env
load_dotenv()

# Setup logger
BASE_FORMAT = "[%(asctime)s] [%(threadName)s] %(levelname)-8s | %(message)s"
logger = logging.getLogger("DRBOT")
logger.setLevel(logging.DEBUG)
console_handler = logging.StreamHandler()
console_handler.setFormatter(LogFormatter(fmt=BASE_FORMAT))
valid_log_level = True
try:
    console_handler.setLevel(os.getenv("DRBOT_LOGLEVEL").upper())
except ValueError:
    valid_log_level = False
logger.addHandler(console_handler)
try:
    logfile_handler = logging.FileHandler(os.getenv("DRBOT_LOGFILE"))
except Exception as e:
    logger.critical("Couldn't open the log file. Did you set it in .env?")
    logger.critical(e)
    sys.exit(1)
logfile_handler.setFormatter(logging.Formatter(fmt=BASE_FORMAT))
logger.addHandler(logfile_handler)
if not valid_log_level:  # Now that logging's done setting up, complain about an invalid log level
    logger.warning(
        f"Invalid log level set in DRBOT_LOGLEVEL: '{os.getenv('DRBOT_LOGLEVEL')}'. Must be one of CRITICAL, ERROR, WARNING, INFO, DEBUG. Defaulting to INFO.")
    console_handler.setLevel(logging.INFO)

last_update_utc = 0
point_store = PointStore()

# Given a list, get a set of all elements which appear more than once.


def get_dupes(L):
    seen, seen2 = set(), set()
    for item in L:
        seen2.add(item) if item in seen else seen.add(item)
    return seen2


def main():
    logger.info(f"DRBOT for r/{os.getenv('DRBOT_SUB')} starting up")

    # Set up reddit access
    logger.info("Logging in to Reddit (u/%s)...", os.getenv('DRBOT_USERNAME'))
    reddit = praw.Reddit(client_id=os.getenv('DRBOT_CLIENT_ID'),
                         client_secret=os.getenv('DRBOT_CLIENT_SECRET'),
                         username=os.getenv('DRBOT_USERNAME'),
                         password=os.getenv('DRBOT_PASSWORD'),
                         user_agent=f"DRBOT r/${os.getenv('DRBOT_SUB')} automated moderation bot")
    logger.info("Logged in successfully")

    # Load removal reason point mapping
    logger.info("Loading removal reasons...")
    with open("points.json", "r") as f:
        raw = json.load(f)

        # Check for dupes
        if len(raw) != len(set(x["id"] for x in raw)):
            logger.error("Duplicate removal reason IDs in points.json:")
            for r in get_dupes(x["id"] for x in raw):
                logger.error(f"\t{r}")
            logger.error("The last instance of each one will be used.")

        # Build the id => points map
        points_map = {x["id"]: x["points"] for x in raw}
        logger.debug(f"Points map: {json.dumps(points_map)}")

        # Check for removal reasons on your sub that aren't in the map
        missing_reasons = set(r.title for r in reddit.subreddit(
            os.getenv("DRBOT_SUB")).mod.removal_reasons) - set(points_map.keys())
        if len(missing_reasons) > 0:
            logger.warning("Some removal reasons on your sub don't have an entry in points.json:")
            for r in missing_reasons:
                logger.warning(f"\t{r}")
            logger.warning("These removal reasons will be treated as costing 0 points.")

    # Continually iterate through modlog entries
    subreddit = reddit.subreddit(os.getenv("DRBOT_SUB"))
    for modaction in subreddit.mod.stream.log(skip_existing=True):
        # Ignore any modlog entries that have already been processed
        if modaction.created_utc <= last_update_utc:
            continue

        # We only care about removal reasons
        if modaction.action != "addremovalreason":
            continue

        removal_reason_id = modaction.description
        submission_fullname = modaction.target_fullname
        author = modaction.target_author

        logger.debug(
            f"Processing removal of {submission_fullname} with reason: {removal_reason_id}")
        if removal_reason_id in points_map:
            point_cost = points_map[removal_reason_id]
        else:
            point_cost = 0
            logger.debug(f"Unknown removal reason, defaulting to 0 points.")

        point_store.add(author, submission_fullname, point_cost)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    logging.shutdown()
