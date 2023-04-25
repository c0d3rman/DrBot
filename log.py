import logging
from config import settings
import util

# Setup logger
BASE_FORMAT = "[%(asctime)s] [%(filename)s/%(funcName)s:%(lineno)d] %(levelname)s | %(message)s"
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

# Logging to console
console_handler = logging.StreamHandler()
console_handler.setFormatter(util.LogFormatter(fmt=BASE_FORMAT))
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
