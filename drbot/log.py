from collections.abc import Mapping
import logging
import sys
import praw
from drbot import settings

BASE_FORMAT = "[%(asctime)s] [%(filename)s/%(funcName)s:%(lineno)d] %(levelname)s | %(message)s"


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
        super().__init__(fmt=f"%(color_on)s{fmt}%(color_off)s", *args, **kwargs)

    RESET_CODE = "\033[0m"

    def format(self, record, *args, **kwargs):
        if (record.levelno in self.COLOR_CODES):
            record.color_on = self.COLOR_CODES[record.levelno]
            record.color_off = self.RESET_CODE
        else:
            record.color_on = ""
            record.color_off = ""
        return super().format(record, *args, **kwargs)


# If enabled, low PRAW output to file
if settings.praw_log_file != "":
    if settings.praw_log_file == settings.log_file:
        raise Exception("You can't set DRBOT's log file and PRAW's log file to the same file!")
    logging.basicConfig(filename=settings.praw_log_file, format=BASE_FORMAT, level=logging.DEBUG)

# Setup logger
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# Logging to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(LogFormatter(fmt=BASE_FORMAT))
console_handler.setLevel(settings.console_log_level)
log.addHandler(console_handler)

# Logging to file
if settings.log_file != "":
    try:
        logfile_handler = logging.FileHandler(settings.log_file)
    except Exception as e:
        log.critical(f"Couldn't open the log file: {settings.log_file}")
        log.critical(e)
        raise e
    logfile_handler.setFormatter(logging.Formatter(fmt=BASE_FORMAT))
    logfile_handler.setLevel(settings.file_log_level)
    log.addHandler(logfile_handler)

# We also log to modmail, which is initialized in drbot.reddit
# The classes below are for that


class ModmailLoggingHandler(logging.Handler):
    """A log handler which sends logs to modmail.
    Not to be confused with DRBOT's Handlers.
    The reddit object must be passed in to avoid circular dependencies."""

    def __init__(self, reddit: praw.Reddit, *args, **kwargs) -> None:
        logging.Handler.__init__(self, *args, **kwargs)
        self.reddit = reddit

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.reddit.send_modmail(subject=f"encountered a {record.levelname} level error", body=self.format(record))
        except Exception:
            self.handleError(record)


class TemplateLoggingFormatter(logging.Formatter):
    """A log formatter which embeds the log text in a customizable template.
    Supports different templates for each log level.
    Include {log} in your template where you want the log to appear."""

    def __init__(self, template: Mapping[int, str] | str = "", *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        if type(template) is str:
            template = {k: template for k in logging._levelToName}
        else:
            for k in logging._levelToName:
                if not k in template:
                    template[k] = ""

        self.template = template

    def format(self, record: logging.LogRecord) -> str:
        if isinstance(record.msg, Exception):  # Show stack trace
            record.exc_info = sys.exc_info()
        base = super().format(record)
        t = self.template[record.levelno]
        if t == "":
            return base
        else:
            return t.format(log=base)
