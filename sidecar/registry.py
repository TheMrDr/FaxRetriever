"""
RPC handler registry. Shared between main.py and handler modules.
This module exists to avoid circular imports.
"""

import json
import os
import sys
import threading
from typing import Any, Callable

# ── Resolve paths ──
if hasattr(sys, "_MEIPASS"):
    BASE_DIR = sys._MEIPASS
    # When frozen, src/ modules are bundled as data at _MEIPASS root
    # (core/, fax_io/, utils/, integrations/ are direct children)
    sys.path.insert(0, BASE_DIR)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BASE_DIR = os.path.dirname(BASE_DIR)  # Go up from sidecar/ to project root
    # Add src/ to path for development
    sys.path.insert(0, os.path.join(BASE_DIR, "src"))

# If frozen, EXE_DIR is the real install directory
if getattr(sys, "frozen", False):
    EXE_DIR = os.path.dirname(sys.executable)
else:
    EXE_DIR = BASE_DIR

# ── stdout lock (thread-safe writes) ──
_stdout_lock = threading.Lock()


def _write_stdout(data: dict) -> None:
    """Thread-safe write a JSON line to stdout."""
    with _stdout_lock:
        sys.stdout.write(json.dumps(data, default=str) + "\n")
        sys.stdout.flush()


def emit_event(event: str, data: Any = None) -> None:
    """Push an event to the Tauri frontend."""
    _write_stdout({"event": event, "data": data})


# ── Handler Registry ──
_handlers: dict[str, Callable] = {}


def register(method: str) -> Callable:
    """Decorator to register an RPC handler."""
    def decorator(fn: Callable) -> Callable:
        _handlers[method] = fn
        return fn
    return decorator


def dispatch(method: str, params: dict) -> Any:
    """Dispatch a method call to its registered handler."""
    handler = _handlers.get(method)
    if handler is None:
        raise ValueError(f"Unknown method: {method}")
    return handler(params)
