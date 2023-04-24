import logging
import prawcore

from config import settings


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
    BASE_FORMAT = "[%(asctime)s] [%(filename)s/%(funcName)s:%(lineno)d] %(levelname)s | %(message)s"

    logger = logging.getLogger("DRBOT")
    logger.setLevel(logging.DEBUG)

    # Logging to console
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(LogFormatter(fmt=BASE_FORMAT))
    console_handler.setLevel(settings.console_log_level)
    logger.addHandler(console_handler)

    # Logging to file
    try:
        logfile_handler = logging.FileHandler(settings.log_file)
    except Exception as e:
        logger.critical(f"Couldn't open the log file: {settings.log_file}")
        logger.critical(e)
        raise e
    logfile_handler.setFormatter(logging.Formatter(fmt=BASE_FORMAT))
    logfile_handler.setLevel(settings.file_log_level)
    logger.addHandler(logfile_handler)

    return logger


def get_dupes(L):
    """
    Given a list, get a set of all elements which appear more than once.
    """
    seen, seen2 = set(), set()
    for item in L:
        seen2.add(item) if item in seen else seen.add(item)
    return seen2

def user_exists(reddit, username):
    """Check if a user exists on reddit."""
    try:
        reddit.redditor(username).fullname
    except prawcore.exceptions.NotFound:
        return False
    else:
        return True