"""
FaxRetriever Sidecar — JSON-RPC over stdin/stdout

This is the headless Python backend that Tauri launches as a sidecar process.
It receives JSON-RPC commands on stdin and sends responses + events on stdout.

Protocol:
  Request:  {"id": 1, "method": "get_version", "params": {}}
  Response: {"id": 1, "result": {"version": "3.0.0"}}
  Event:    {"event": "fax_received", "data": {...}}
"""

import json
import sys
import threading
import traceback
from typing import Optional

# Import the shared registry (sets up paths, provides dispatch/emit_event)
from registry import dispatch, emit_event, EXE_DIR  # noqa: F401

# ── Import handlers (registers methods via @register decorator) ──
from handlers import system_handlers  # noqa: E402, F401
from handlers import config_handlers  # noqa: E402, F401
from handlers import auth_handlers  # noqa: E402, F401
from handlers import fax_handlers  # noqa: E402, F401
from handlers import outbox_handlers  # noqa: E402, F401
from handlers import contacts_handlers  # noqa: E402, F401
from handlers import send_handlers  # noqa: E402, F401


def _send_response(msg_id: int, result) -> None:
    """Send a JSON-RPC response."""
    from registry import _write_stdout
    _write_stdout({"id": msg_id, "result": result})


def _send_error(msg_id: int, error: str) -> None:
    """Send a JSON-RPC error response."""
    from registry import _write_stdout
    _write_stdout({"id": msg_id, "error": error})


def _handle_request(msg_id: int, method: str, params: dict) -> None:
    """Handle a single RPC request (runs in a worker thread)."""
    try:
        result = dispatch(method, params)
        _send_response(msg_id, result)
    except Exception as e:
        tb = traceback.format_exc()
        sys.stderr.write(f"Error handling {method}: {tb}\n")
        sys.stderr.flush()
        _send_error(msg_id, str(e))


def _startup_maintenance() -> None:
    """One-time maintenance tasks on sidecar launch."""
    try:
        from core.outbox_ledger import prune_old
        prune_old(EXE_DIR, max_age_days=30)
    except Exception:
        pass  # Non-critical


def main() -> None:
    """Read JSON-RPC commands from stdin, dispatch, respond."""
    _startup_maintenance()

    # Signal readiness
    emit_event("sidecar_ready", {"version": "3.0.0", "exe_dir": EXE_DIR})

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            msg = json.loads(line)
        except json.JSONDecodeError as e:
            sys.stderr.write(f"Invalid JSON: {e}\n")
            sys.stderr.flush()
            continue

        msg_id: Optional[int] = msg.get("id")
        method: Optional[str] = msg.get("method")
        params: dict = msg.get("params", {})

        if method is None or msg_id is None:
            if msg_id is not None:
                _send_error(msg_id, "Missing 'method' field")
            continue

        # Handle each request in a thread so we don't block the main loop
        threading.Thread(
            target=_handle_request,
            args=(msg_id, method, params),
            daemon=True,
        ).start()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        sys.stderr.write(f"Sidecar fatal error: {e}\n")
        sys.stderr.flush()
        sys.exit(1)
