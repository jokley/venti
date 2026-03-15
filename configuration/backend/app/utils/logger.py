import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
import pytz
import os
import sys

def create_logger(name='venti'):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)  # capture all levels

    # Avoid adding multiple handlers if called multiple times
    if not logger.handlers:

        # ---- File handler ----
        log_file = os.path.join(os.path.dirname(__file__), '../debug.log')
        rfh = RotatingFileHandler(
            filename=log_file,
            maxBytes=1*1024*1024,
            backupCount=1,
            encoding='utf-8'
        )
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        logging.Formatter.converter = lambda *args: datetime.now(pytz.timezone("Europe/Berlin")).timetuple()
        rfh.setFormatter(formatter)
        logger.addHandler(rfh)

        # ---- Console handler ----
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

        # Don't propagate to root logger
        logger.propagate = False

    return logger

# global logger instance
logger = create_logger()