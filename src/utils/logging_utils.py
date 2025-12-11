"""
utils/logging_utils.py

Provides centralized, rotating file logging for FaxRetriever.
Supports multiple named loggers and structured level output.
Also provides crash/exit handlers to capture unhandled exceptions and app shutdowns.
"""

import logging
import os
import sys
import atexit
import threading
import traceback
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

# Crash/exit state
_crash_handlers_installed = False
_last_unhandled: str | None = None


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
    # Default new loggers to current root level so they inherit the selected verbosity
    if logger.level == logging.NOTSET:
        try:
            root_level = logging.getLogger().level
            logger.setLevel(root_level)
        except Exception:
            logger.setLevel(logging.INFO)

    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(name)s: %(message)s")

    global _shared_file_handler
    if _shared_file_handler is None:
        _shared_file_handler = RotatingFileHandler(
            LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT
        )
        _shared_file_handler.setFormatter(formatter)
        try:
            _shared_file_handler.setLevel(logging.getLogger().level)
        except Exception:
            _shared_file_handler.setLevel(logger.level)

    # Avoid duplicate handlers if reloaded
    if _shared_file_handler not in logger.handlers:
        logger.addHandler(_shared_file_handler)

    _logger_cache[name] = logger
    return logger


def _log_unhandled(exc_type, exc, tb) -> None:
    """Default unhandled exception logger used for sys.excepthook and threading.excepthook."""
    global _last_unhandled
    try:
        log = get_logger("crash")
        tb_str = "".join(traceback.format_exception(exc_type, exc, tb))
        _last_unhandled = tb_str
        log.critical(
            f"Unhandled exception: {exc_type.__name__}: {exc}\n{tb_str}".rstrip()
        )
    except Exception:
        try:
            # Fallback to stderr
            print(f"Unhandled exception: {exc}", file=sys.stderr)
        except Exception:
            pass


def _on_process_exit() -> None:
    """atexit hook that logs process shutdown. Includes last crash info marker if present."""
    try:
        log = get_logger("lifecycle")
        if _last_unhandled:
            log.error("Application exiting after unhandled exception (see above).")
        else:
            log.info("Application exiting.")
    except Exception:
        pass


def install_crash_handlers() -> None:
    """Install global hooks to log crashes and exits.

    - sys.excepthook to capture main-thread unhandled exceptions
    - threading.excepthook (Py 3.8+) to capture thread exceptions
    - atexit hook to record application shutdown
    """
    global _crash_handlers_installed
    if _crash_handlers_installed:
        return
    try:
        sys.excepthook = _log_unhandled  # type: ignore[assignment]
    except Exception:
        pass
    try:
        # Python 3.8+
        def _threading_hook(args):
            try:
                _log_unhandled(args.exc_type, args.exc_value, args.exc_traceback)
            except Exception:
                pass
        threading.excepthook = _threading_hook  # type: ignore[attr-defined]
    except Exception:
        pass
    try:
        atexit.register(_on_process_exit)
    except Exception:
        pass
    _crash_handlers_installed = True
