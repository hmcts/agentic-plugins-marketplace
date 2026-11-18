"""File logging to <data>/forwarder.log.

Log lines carry events and counts only: never record content, never identity
values (user names, paths, host names, emails, tenant or client ids).
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILE = "forwarder.log"
LOGGER_NAME = "cpp_telemetry"
MAX_BYTES = 5_000_000
BACKUP_COUNT = 2


def get_logger(data_dir: Path) -> logging.Logger:
    """Return the package logger writing to ``<data_dir>/forwarder.log``.

    The file is opened on the first record, so a dormant run creates nothing.
    Calling again with another directory moves the single handler there.
    """
    logger = logging.getLogger(LOGGER_NAME)
    target = os.path.abspath(str(Path(data_dir) / LOG_FILE))
    handlers = logger.handlers
    if len(handlers) == 1 and getattr(handlers[0], "baseFilename", None) == target:
        return logger
    for handler in list(handlers):
        logger.removeHandler(handler)
        handler.close()
    handler = RotatingFileHandler(
        target, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8", delay=True
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
