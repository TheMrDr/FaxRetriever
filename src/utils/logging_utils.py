"""
utils/logging_utils.py

Provides centralized, rotating file logging for FaxRetriever.
Supports multiple named loggers and structured level output.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from typing import Dict

# Global logger cache
_logger_cache: Dict[str, logging.Logger] = {}

# Log file configuration
LOG_DIR = os.path.join(os.getcwd(), "log")
LOG_FILE = os.path.join(LOG_DIR, "ClinicFax.log")
MAX_BYTES = 1 * 1024 * 1024  # 1 MB
BACKUP_COUNT = 3

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

# Track a shared handler so we can update level across all loggers
_shared_file_handler: RotatingFileHandler | None = None

# Map friendly names to logging levels
_LEVEL_MAP = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _resolve_level(level_name: str | int | None) -> int:
    if isinstance(level_name, int):
        return level_name
    if not level_name:
        return logging.DEBUG
    return _LEVEL_MAP.get(str(level_name).strip().upper(), logging.DEBUG)


def set_global_logging_level(level_name: str | int) -> None:
    """Set logging level for all cached loggers and the shared handler.

    This should be called after loading configuration (e.g., from Options dialog)
    to reflect the user's chosen verbosity.
    """
    level = _resolve_level(level_name)

    # Update root logger too (without adding handlers)
    logging.getLogger().setLevel(level)

    # Update all cached loggers
    for lg in _logger_cache.values():
        lg.setLevel(level)
        for h in lg.handlers:
            try:
                h.setLevel(level)
            except Exception:
                pass

    # Update shared handler if created
    global _shared_file_handler
    if _shared_file_handler is not None:
        try:
            _shared_file_handler.setLevel(level)
        except Exception:
            pass


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured logger instance.
    All loggers share a rotating file handler.
    """
    if name in _logger_cache:
        return _logger_cache[name]

    logger = logging.getLogger(name)
    # Default to DEBUG; can be lowered later via set_global_logging_level
    if logger.level == logging.NOTSET:
        logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")

    global _shared_file_handler
    if _shared_file_handler is None:
        _shared_file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
        )
        _shared_file_handler.setFormatter(formatter)
        _shared_file_handler.setLevel(logger.level)

    # Avoid duplicate handlers if reloaded
    if _shared_file_handler not in logger.handlers:
        logger.addHandler(_shared_file_handler)

    _logger_cache[name] = logger
    return logger
