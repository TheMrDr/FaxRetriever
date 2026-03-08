"""System-level RPC handlers: version, logs, PDF conversion."""

import os
import subprocess
import sys

from registry import register, EXE_DIR


@register("get_version")
def get_version(params: dict) -> dict:
    """Return the current app version."""
    try:
        from version import __version__
        version = __version__
    except ImportError:
        version = "3.0.0-dev"
    return {"version": version}


@register("ping")
def ping(params: dict) -> dict:
    """Health check."""
    return {"pong": True}


@register("open_log_folder")
def open_log_folder(params: dict) -> dict:
    """Open the log folder in Windows Explorer."""
    log_dir = os.path.join(EXE_DIR, "log")
    if os.path.isdir(log_dir):
        subprocess.Popen(["explorer", log_dir])
        return {"opened": True}
    return {"opened": False, "error": f"Log directory not found: {log_dir}"}


@register("get_app_info")
def get_app_info(params: dict) -> dict:
    """Return basic app info for the About dialog."""
    try:
        from version import __version__
        version = __version__
    except ImportError:
        version = "3.0.0-dev"
    return {
        "version": version,
        "exe_dir": EXE_DIR,
        "python_version": sys.version,
        "frozen": getattr(sys, "frozen", False),
    }
