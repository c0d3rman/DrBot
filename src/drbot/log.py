from __future__ import annotations
from typing import Any, Mapping
import logging
import inspect
import praw
import sys
from .settings import settings


BASE_FORMAT = "[%(asctime)s] [%(filename)s/%(funcName)s:%(lineno)d] | %(reginame)s (%(regiclass)s) | %(levelname)s | %(message)s"


class LogFormatter(logging.Formatter):
    """Logging formatter supporting colorized output and Regi name detection."""

    COLOR_CODES = {
        logging.CRITICAL: "\033[1;35m",  # bright/bold magenta
        logging.ERROR:    "\033[1;31m",  # bright/bold red
        logging.WARNING:  "\033[1;33m",  # bright/bold yellow
        logging.INFO:     "\033[0;37m",  # white / light gray
        logging.DEBUG:    "\033[1;30m",  # bright/bold black / dark gray
    }

    RESET_CODE = "\033[0m"

    def __init__(self, fmt: str = "[%(asctime)s] [%(threadName)s] %(levelname)-8s | %(message)s", *args: Any, **kwargs: Any):
        super().__init__(fmt=f"%(color_on)s{fmt}%(color_off)s", *args, **kwargs)

    def format(self, record: logging.LogRecord, detect_regi: bool = True, *args: Any, **kwargs: Any):
        # Colors
        if (record.levelno in self.COLOR_CODES):
            record.color_on = self.COLOR_CODES[record.levelno]
            record.color_off = self.RESET_CODE
        else:
            record.color_on = ""
            record.color_off = ""

        record.regiclass = "N/A"
        record.reginame = "-"

        # Regi detection
        if detect_regi:
            from .Regi import Regi  # Lazy import to avoid circular dependency
            for frame_record in inspect.stack():
                self_obj = frame_record.frame.f_locals.get('self')
                if isinstance(self_obj, Regi):
                    record.regiclass = self_obj.__class__.__name__
                    record.reginame = self_obj.name
                    break

        return super().format(record, *args, **kwargs)


# Setup logger
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# Logging to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(LogFormatter(fmt=BASE_FORMAT))
console_handler.setLevel(settings.logging.console_log_level)
log.addHandler(console_handler)

# Logging to file
if settings.logging.log_path != "":
    try:
        logfile_handler = logging.FileHandler(settings.logging.log_path)
    except Exception as e:
        log.critical(f"Couldn't open the log file: {settings.logging.log_path}")
        log.critical(e)
        raise e
    logfile_handler.setFormatter(LogFormatter(fmt=BASE_FORMAT))
    logfile_handler.setLevel(settings.logging.file_log_level)
    log.addHandler(logfile_handler)


def smart_error(*args: Any, **kwargs: Any) -> None:
    """Automatically use whichever of log.error() or log.exception() is appropriate."""

    if sys.exc_info() == (None, None, None):
        log.error(*args, **kwargs)
    else:
        log.exception(*args, **kwargs)


log.smart_error = smart_error


# We also log to modmail, which is initialized in reddit.py
# The classes below are for that


class ModmailLoggingHandler(logging.Handler):
    """A log handler which sends logs to modmail.
    Not to be confused with DrBot's Handlers.
    The reddit object must be passed in to avoid circular dependencies."""

    def __init__(self, reddit: praw.Reddit, *args: Any, **kwargs: Any) -> None:
        logging.Handler.__init__(self, *args, **kwargs)
        self.reddit = reddit

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.reddit.DR.send_modmail(subject=f"Encountered a{'n' if record.levelname[0].lower() in 'aeiou' else ''} {record.levelname} level error", body=self.format(record))
        except Exception:
            self.handleError(record)


class TemplateLoggingFormatter(logging.Formatter):
    """A log formatter which embeds the log text in a customizable template.
    Supports different templates for each log level.
    Include {log} in your template where you want the log to appear."""

    def __init__(self, template: Mapping[int, str] | str = "", *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if type(template) is str:
            template = {k: template for k in logging._levelToName}
        else:
            for k in logging._levelToName:
                if k not in template:
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
            # Prepend 4 spaces to each line for Reddit's pre-formatted blocks, since modmails don't support multiline code blocks
            # Need to refactor this out, since this template handler is meant to be general
            base = '\n'.join(f"    {l}" for l in base.split('\n'))
            return t.format(log=base)
