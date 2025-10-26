"""FRAAPI Host — Simple operator app to run and monitor the API

Purpose
- Start the FaxRetriever Admin API (FastAPI/uvicorn) without any Windows service.
- Provide a minimal GUI to show status (health), live logs, and start/stop controls.
- Provide a CLI/headless mode for console operation.

Quick start (PowerShell from Admin\licensing_server)
- GUI mode (default):
    python fraapi_host.py --port 8000 --mongo "mongodb://user:pass@host:27017/?authSource=fra2&tls=true"
- Headless mode (console only):
    python fraapi_host.py --port 8000 --mongo "mongodb://..." --nogui

Notes
- FRAAPI_PORT and FRA_MONGO_URI are honored if set; CLI flags override them.
- OpenAPI docs after start: http://localhost:<port>/docs
- Health check endpoint: http://localhost:<port>/health

"""

from __future__ import annotations

import argparse
import logging
import os
import queue
import sys
import threading
import time
import webbrowser
from typing import Optional

import requests
import uvicorn

# FastAPI application import path (lazy-imported by uvicorn)
APP_PATH = "api_app:app"


class TokenRefresher(threading.Thread):
    """Runs the periodic bearer token refresher without blocking the UI."""

    def __init__(self, stop_event: threading.Event, interval_seconds: int = 300):
        super().__init__(daemon=True)
        self._stop = stop_event
        self._interval = interval_seconds
        self._runner = None

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                if self._runner is None:
                    from tasks.token_refresher import \
                        refresh_bearer_tokens as _ref

                    self._runner = _ref
                self._runner()
            except Exception:
                # token_refresher logs its own failures
                pass
            finally:
                # Wait until next cycle or until stopped
                self._stop.wait(self._interval)


class UvicornThread(threading.Thread):
    """Runs uvicorn programmatically and allows cooperative shutdown."""

    def __init__(
        self,
        app_path: str,
        host: str,
        port: int,
        stop_event: threading.Event,
        clear_modules_cb=None,
    ):
        super().__init__(daemon=True)
        self._stop = stop_event
        self._server = None
        self._host = host
        self._port = port
        self._app_path = app_path
        self._clear_modules_cb = clear_modules_cb

    def run(self) -> None:
        try:
            if callable(self._clear_modules_cb):
                self._clear_modules_cb()
            config = uvicorn.Config(
                self._app_path,
                host=self._host,
                port=self._port,
                log_level="info",
                access_log=True,
            )
            server = uvicorn.Server(config)
            self._server = server

            def _watch():
                self._stop.wait()
                server.should_exit = True

            threading.Thread(target=_watch, daemon=True).start()

            server.run()
        except Exception as e:
            logging.getLogger("fraapi.host").exception(f"Uvicorn crashed: {e}")


# ----- Logging bridge to GUI -----
class QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue[str]):
        super().__init__()
        self.q = q
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
            )
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.q.put_nowait(msg)
        except Exception:
            pass


class _StreamToLogger:
    def __init__(self, logger: logging.Logger, level: int = logging.INFO):
        self.logger = logger
        self.level = level
        self._buffer = ""

    def write(self, msg):
        if msg and not msg.isspace():
            for line in str(msg).splitlines():
                self.logger.log(self.level, line)

    def flush(self):
        # No-op for compatibility
        pass

    def isatty(self) -> bool:
        # Uvicorn's DefaultFormatter checks sys.stdout.isatty(); return False for GUI redirect
        return False


def configure_logging(
    q: Optional[queue.Queue[str]] = None, console: bool = False
) -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Remove existing handlers
    for h in list(root.handlers):
        root.removeHandler(h)
    if console:
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S"
            )
        )
        root.addHandler(ch)
    if q is not None:
        gh = QueueLogHandler(q)
        gh.setLevel(logging.INFO)
        # Root handler to capture most logs
        root.addHandler(gh)
        # Attach queue handler directly to uvicorn loggers to ensure access lines appear in GUI
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_error = logging.getLogger("uvicorn.error")
        uvicorn_access = logging.getLogger("uvicorn.access")
        fastapi_logger = logging.getLogger("fastapi")
        for lg in (uvicorn_logger, uvicorn_error, fastapi_logger):
            lg.setLevel(logging.INFO)
            lg.propagate = True
            lg.addHandler(gh)
        # For access logs, add a slim formatter that matches the expected style
        access_handler = QueueLogHandler(q)
        access_handler.setLevel(logging.INFO)
        access_handler.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        uvicorn_access.setLevel(logging.INFO)
        # Avoid double-printing by preventing propagation to root for access lines
        uvicorn_access.propagate = False
        uvicorn_access.addHandler(access_handler)
        # Redirect stdout/stderr to loggers so GUI captures all CLI output
        sys.stdout = _StreamToLogger(logging.getLogger("stdout"), logging.INFO)
        sys.stderr = _StreamToLogger(logging.getLogger("stderr"), logging.ERROR)


# ---- Module reload helper to pick up new env on restart ----
def _clear_app_modules():
    try:
        import sys as _sys

        to_drop = [
            "api_app",
            "config",
            "db.mongo_interface",
            "core.logger",
            "routes.init_route",
            "routes.bearer_route",
            "routes.assignments_route",
            "routes.admin_route",
        ]
        for name in list(_sys.modules.keys()):
            if name in to_drop:
                _sys.modules.pop(name, None)
    except Exception:
        pass


# ---- Secure settings (Windows DPAPI) ----
try:
    import base64
    import ctypes
    import ctypes.wintypes as wintypes
except Exception:
    ctypes = None
    wintypes = None

SETTINGS_FILE = "fraapi_host_settings.json"


def _executable_dir() -> str:
    if getattr(sys, "frozen", False):  # PyInstaller
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _settings_path() -> str:
    return os.path.join(_executable_dir(), SETTINGS_FILE)


if ctypes:

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

else:
    _DATA_BLOB = None


def _dpapi_protect(raw: bytes) -> str:
    if not ctypes:
        return ""
    try:
        in_blob = _DATA_BLOB(
            len(raw),
            ctypes.cast(
                ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)
            ),
        )
        out_blob = _DATA_BLOB()
        flags = 0x5  # CRYPTPROTECT_LOCAL_MACHINE | CRYPTPROTECT_UI_FORBIDDEN
        CryptProtectData = ctypes.windll.crypt32.CryptProtectData
        CryptProtectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB),
            wintypes.LPCWSTR,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        CryptProtectData.restype = wintypes.BOOL
        if not CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob)
        ):
            return ""
        try:
            buf = ctypes.string_at(out_blob.pbData, out_blob.cbData)
            return base64.b64encode(buf).decode("utf-8")
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return ""


def _dpapi_unprotect(b64: str) -> Optional[bytes]:
    if not ctypes:
        return None
    try:
        raw = base64.b64decode(b64)
        in_blob = _DATA_BLOB(
            len(raw),
            ctypes.cast(
                ctypes.create_string_buffer(raw), ctypes.POINTER(ctypes.c_char)
            ),
        )
        out_blob = _DATA_BLOB()
        CryptUnprotectData = ctypes.windll.crypt32.CryptUnprotectData
        CryptUnprotectData.argtypes = [
            ctypes.POINTER(_DATA_BLOB),
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(_DATA_BLOB),
        ]
        CryptUnprotectData.restype = wintypes.BOOL
        if not CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _read_settings() -> dict:
    try:
        import json

        with open(_settings_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    # Do not persist plaintext mongo; only store encrypted
    data.pop("mongo_uri", None)
    return data


def _write_settings(
    *, mongo_uri: Optional[str] = None, port: Optional[int] = None
) -> bool:
    try:
        import json

        data = _read_settings()
        data.pop("mongo_uri", None)
        if mongo_uri is not None:
            data["encrypted_mongo_uri"] = (
                _dpapi_protect(mongo_uri.encode("utf-8")) if mongo_uri else ""
            )
        if port is not None:
            try:
                data["port"] = int(port)
            except Exception:
                data["port"] = None
        with open(_settings_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def _apply_persisted_settings() -> tuple[Optional[str], Optional[int]]:
    data = _read_settings()
    dec_uri: Optional[str] = None
    enc = data.get("encrypted_mongo_uri")
    if isinstance(enc, str) and enc:
        try:
            raw = _dpapi_unprotect(enc)
            if raw:
                dec_uri = raw.decode("utf-8")
        except Exception:
            dec_uri = None
    port = data.get("port") if isinstance(data.get("port"), int) else None
    if port:
        os.environ["FRAAPI_PORT"] = str(port)
    if dec_uri:
        os.environ["FRA_MONGO_URI"] = dec_uri
    # Log sanitized
    try:
        safe = (dec_uri or "").split("@")[-1]
    except Exception:
        safe = "<redacted>"
    logging.getLogger("fraapi.host").info(
        f"Applied settings: port={port or os.environ.get('FRAAPI_PORT')}, mongo={safe or '<not set>'}"
    )
    return dec_uri, port


# ----- GUI (PyQt5) -----
class HostWindow:  # built without subclassing to avoid hard dependency at import time
    def __init__(
        self, port: int, mongo_uri: Optional[str], start_immediately: bool = True
    ):
        from PyQt5.QtCore import QTimer
        from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QInputDialog,
                                     QLabel, QMainWindow, QPushButton,
                                     QTextEdit, QVBoxLayout, QWidget)

        class _Win(QMainWindow):
            def __init__(self, outer):
                super().__init__()
                self.outer = outer
                self.setWindowTitle("FRAAPI Host")
                self.setMinimumSize(900, 600)

                # Menu
                menu = self.menuBar().addMenu("&Settings")
                act_set_port = menu.addAction("Set Port…")
                act_set_port.triggered.connect(self.outer.prompt_set_port)
                act_set_mongo = menu.addAction("Set Mongo connection…")
                act_set_mongo.triggered.connect(self.outer.prompt_set_mongo)

                central = QWidget(self)
                v = QVBoxLayout(central)
                self.setCentralWidget(central)

                # Status row
                row = QHBoxLayout()
                self.lbl_status = QLabel("Status: Stopped")
                safe_mongo = HostWindow._safe_uri(mongo_uri)
                self.lbl_cfg = QLabel(f"Port: {port} | Mongo: {safe_mongo}")
                self.btn_start = QPushButton("Start API")
                self.btn_stop = QPushButton("Stop API")
                self.btn_stop.setEnabled(False)
                self.btn_docs = QPushButton("Open /docs")
                self.btn_health = QPushButton("Health")

                row.addWidget(self.lbl_status)
                row.addStretch()
                row.addWidget(self.lbl_cfg)
                row.addStretch()
                row.addWidget(self.btn_health)
                row.addWidget(self.btn_docs)
                row.addWidget(self.btn_start)
                row.addWidget(self.btn_stop)
                v.addLayout(row)

                # Log view
                self.txt = QTextEdit()
                self.txt.setReadOnly(True)
                v.addWidget(self.txt, 1)

                # Wire buttons
                self.btn_start.clicked.connect(self.outer.start)
                self.btn_stop.clicked.connect(self.outer.stop)
                self.btn_docs.clicked.connect(self.outer.open_docs)
                self.btn_health.clicked.connect(self.outer.check_health)

                # Timer to poll queue
                self.timer = QTimer(self)
                self.timer.setInterval(200)
                self.timer.timeout.connect(self.outer.drain_logs)
                self.timer.start()

        self._QApp = None
        self._WinClass = _Win
        self._win = None
        self._port = port
        self._mongo = mongo_uri
        self._log_queue: queue.Queue[str] = queue.Queue()
        self._stop_evt = threading.Event()
        self._server_thread: Optional[UvicornThread] = None
        self._refresher: Optional[TokenRefresher] = None
        self._running = False

        # Configure logging to feed the queue
        configure_logging(self._log_queue, console=False)

        # Create app/window
        self._QApp = QApplication.instance() or QApplication(sys.argv)
        self._win = self._WinClass(self)

        if start_immediately:
            # Auto-start
            self.start()

    @staticmethod
    def _safe_uri(uri: Optional[str]) -> str:
        if not uri:
            return "<not set>"
        # show only host part after @ if present
        try:
            # take everything after the last '@'
            hostpart = uri.split("@")[-1]
            # strip off query string and path, keep only host:port
            return hostpart.split("/")[0]
        except Exception:
            return "<configured>"

    def open_docs(self) -> None:
        webbrowser.open(f"http://localhost:{self._port}/docs")

    def check_health(self) -> None:
        try:
            r = requests.get(f"http://localhost:{self._port}/health", timeout=3)
            if r.status_code == 200:
                self._append("Health: OK")
                return
        except Exception as e:
            self._append(f"Health check error: {e}")
        self._append("Health: NOT OK")

    def _append(self, text: str) -> None:
        try:
            self._win.txt.append(text)
        except Exception:
            pass

    def drain_logs(self) -> None:
        try:
            while True:
                msg = self._log_queue.get_nowait()
                self._append(msg)
        except queue.Empty:
            pass

    def start(self) -> None:
        if self._running:
            return
        # Start uvicorn server thread
        self._stop_evt.clear()
        self._server_thread = UvicornThread(
            APP_PATH,
            "0.0.0.0",
            int(self._port),
            self._stop_evt,
            clear_modules_cb=_clear_app_modules,
        )
        self._server_thread.start()
        # Start token refresher
        self._refresher = TokenRefresher(self._stop_evt)
        self._refresher.start()
        self._running = True
        try:
            self._win.lbl_status.setText("Status: Running")
            self._win.btn_start.setEnabled(False)
            self._win.btn_stop.setEnabled(True)
        except Exception:
            pass

    def stop(self) -> None:
        if not self._running:
            return
        self._stop_evt.set()
        try:
            if self._server_thread:
                self._server_thread.join(timeout=5)
            if self._refresher:
                self._refresher.join(timeout=5)
        except Exception:
            pass
        self._running = False
        try:
            self._win.lbl_status.setText("Status: Stopped")
            self._win.btn_start.setEnabled(True)
            self._win.btn_stop.setEnabled(False)
        except Exception:
            pass

    def _update_cfg_label(self) -> None:
        try:
            safe_mongo = HostWindow._safe_uri(self._mongo)
            self._win.lbl_cfg.setText(f"Port: {self._port} | Mongo: {safe_mongo}")
        except Exception:
            pass

    def _restart(self) -> None:
        self.stop()
        # Short delay to allow socket release
        time.sleep(0.2)
        self.start()

    def prompt_set_port(self) -> None:
        try:
            from PyQt5.QtWidgets import QInputDialog

            val, ok = QInputDialog.getInt(
                self._win,
                "Set Port",
                "Listening port:",
                value=int(self._port),
                min=1,
                max=65535,
            )
            if not ok:
                return
            if int(val) == int(self._port):
                return
            self._port = int(val)
            _write_settings(port=self._port)
            _apply_env_overrides(self._port, self._mongo)
            self._append(f"Port updated to {self._port}. Restarting API…")
            self._update_cfg_label()
            self._restart()
        except Exception as e:
            self._append(f"Failed to update port: {e}")

    def prompt_set_mongo(self) -> None:
        try:
            from PyQt5.QtWidgets import QInputDialog

            current = self._mongo or ""
            new_uri, ok = QInputDialog.getText(
                self._win, "Set Mongo connection", "MongoDB URI:", text=current
            )
            if not ok:
                return
            new_uri = (new_uri or "").strip()
            if not new_uri or new_uri == self._mongo:
                return
            self._mongo = new_uri
            _write_settings(mongo_uri=self._mongo)
            _apply_env_overrides(self._port, self._mongo)
            self._append("MongoDB connection updated. Restarting API…")
            self._update_cfg_label()
            self._restart()
        except Exception as e:
            self._append(f"Failed to update Mongo connection: {e}")

    def exec(self) -> int:
        try:
            self._win.show()
            return self._QApp.exec()
        finally:
            # Ensure everything stops when GUI closes
            self.stop()


def _apply_env_overrides(port: Optional[int], mongo_uri: Optional[str]):
    if port is not None:
        os.environ["FRAAPI_PORT"] = str(port)
    if mongo_uri is not None:
        os.environ["FRA_MONGO_URI"] = mongo_uri


def run_headless(port: int, mongo_uri: Optional[str]) -> None:
    configure_logging(None, console=True)
    stop_evt = threading.Event()
    # Start token refresher in background
    refresher = TokenRefresher(stop_evt)
    refresher.start()
    try:
        uvicorn.run(APP_PATH, host="0.0.0.0", port=port, log_level="info")
    except KeyboardInterrupt:
        pass
    finally:
        stop_evt.set()
        try:
            refresher.join(timeout=5)
        except Exception:
            pass


def main(argv: list[str]) -> int:
    # First apply any persisted settings to environment (if available)
    saved_mongo, saved_port = _apply_persisted_settings()

    parser = argparse.ArgumentParser(
        description="Run FRAAPI with a simple GUI or in headless mode."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("FRAAPI_PORT", "8000")),
        help="Port to listen on (default 8000)",
    )
    parser.add_argument(
        "--mongo",
        type=str,
        default=os.environ.get("FRA_MONGO_URI"),
        help="MongoDB connection string",
    )
    parser.add_argument("--nogui", action="store_true", help="Run in console (no GUI)")
    args = parser.parse_args(argv)

    # If CLI provided values, persist them securely and re-apply to environment
    if args.port is not None and (
        saved_port is None or int(args.port) != int(saved_port)
    ):
        _write_settings(port=int(args.port))
    if args.mongo is not None and (
        saved_mongo is None or str(args.mongo) != str(saved_mongo)
    ):
        _write_settings(mongo_uri=str(args.mongo))

    # Apply envs for downstream modules (e.g., config.py, Mongo clients)
    _apply_env_overrides(args.port, args.mongo)

    if args.nogui:
        run_headless(args.port, args.mongo)
        return 0

    # GUI mode
    try:
        ui = HostWindow(port=args.port, mongo_uri=args.mongo, start_immediately=True)
        return ui.exec()
    except Exception as e:
        print(f"Failed to start GUI: {e}. Falling back to console mode.")
        run_headless(args.port, args.mongo)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
