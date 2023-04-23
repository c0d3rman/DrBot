import os
import logging


class LogFormatter(logging.Formatter):
    """
    Logging formatter supporting colorized output.
    """

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


def getLogger():
    """
    Setup logger.
    """
    BASE_FORMAT = "[%(asctime)s] [%(threadName)s] %(levelname)-8s | %(message)s"

    logger = logging.getLogger("DRBOT")
    logger.setLevel(logging.DEBUG)

    # Logging to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(LogFormatter(fmt=BASE_FORMAT))
    valid_log_level = True
    try:
        console_handler.setLevel(os.getenv("DRBOT_LOGLEVEL").upper())
    except ValueError:
        valid_log_level = False
    logger.addHandler(console_handler)

    # Logging to file
    try:
        logfile_handler = logging.FileHandler(os.getenv("DRBOT_LOGFILE"))
    except Exception as e:
        logger.critical("Couldn't open the log file. Did you set it in .env?")
        logger.critical(e)
        raise e
    logfile_handler.setFormatter(logging.Formatter(fmt=BASE_FORMAT))
    logger.addHandler(logfile_handler)

    # Now that logging's done setting up, complain about an invalid log level
    if not valid_log_level:
        logger.warning(f"Invalid log level set in DRBOT_LOGLEVEL: '{os.getenv('DRBOT_LOGLEVEL')}'. Must be one of CRITICAL, ERROR, WARNING, INFO, DEBUG. Defaulting to INFO.")
        console_handler.setLevel(logging.INFO)

    return logger


def get_dupes(L):
    """
    Given a list, get a set of all elements which appear more than once.
    """
    seen, seen2 = set(), set()
    for item in L:
        seen2.add(item) if item in seen else seen.add(item)
    return seen2

def is_mod(reddit, username):
    return len(reddit.subreddit(os.getenv("DRBOT_SUB")).moderator(username)) > 0