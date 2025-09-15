"""
utils/logging_utils.py

Provides centralized, rotating file logging for FaxRetriever.
Supports multiple named loggers and structured level output.
"""

import logging
import os
from logging.handlers import RotatingFileHandler

# Global logger cache
_logger_cache = {}

# Log file configuration
LOG_DIR = os.path.join(os.getcwd(), "log")
LOG_FILE = os.path.join(LOG_DIR, "ClinicFax.log")
MAX_BYTES = 1 * 1024 * 1024  # 1 MB
BACKUP_COUNT = 3

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger instance.
    All loggers share a rotating file handler.
    """
    if name in _logger_cache:
        return _logger_cache[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    # Avoid duplicate handlers if reloaded
    if not logger.handlers:
        logger.addHandler(file_handler)

    _logger_cache[name] = logger
    return logger
