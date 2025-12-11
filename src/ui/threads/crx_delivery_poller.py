import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox
from ui.safe_notifier import get_notifier

from core.app_state import app_state
from core.config_loader import device_config
from utils.crx_outbound_ledger import (
    load_pending,
    new_pending,
    sha1_file,
    update_state,
)
from utils.logging_utils import get_logger


def _parse_iso(ts: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def _e164(num: str) -> str:
    n = re.sub(r"\D", "", num or "")
    if len(n) == 10:
        return "1" + n
    return n


class CrxDeliveryPoller(QThread):
    finished = pyqtSignal()

    def __init__(self, parent=None, interval_sec: int = 60, max_attempts: int = 3):
        super().__init__(parent)
        self._stop = threading.Event()
        self.interval_sec = max(10, int(interval_sec or 60))
        self.max_attempts = max(1, int(max_attempts or 3))
        self.log = get_logger("integration.computer_rx")

    def stop(self):
        try:
            self._stop.set()
        except Exception:
            pass

    def run(self):
        while not self._stop.is_set():
            try:
                self._tick()
            except Exception as e:
                try:
                    self.log.warning(f"CRx poller tick error: {e}")
                except Exception:
                    pass
            # sleep in small steps to be responsive
            for _ in range(self.interval_sec):
                if self._stop.is_set():
                    break
                time.sleep(1)
        try:
            self.finished.emit()
        except Exception:
            pass

    def _tick(self):
        # prerequisites
        fax_user = getattr(app_state.global_cfg, "fax_user", None)
        bearer = app_state.global_cfg.bearer_token or ""
        if not (fax_user and bearer):
            return
        # fetch outbound history (first page is usually enough for recent)
        base_url = "https://telco-api.skyswitch.com"
        outbound_url = f"{base_url}/users/{fax_user}/faxes/outbound"
        headers = {"accept": "application/json", "Authorization": f"Bearer {bearer}"}
        try:
            resp = requests.get(outbound_url, headers=headers, timeout=10)
            if resp.status_code != 200:
                try:
                    self.log.warning(f"CRx poller: outbound history HTTP {resp.status_code}")
                except Exception:
                    pass
                return
            try:
                payload = resp.json() or {}
            except Exception:
                payload = {"data": []}
            history = (payload or {}).get("data", [])
        except Exception as e:
            try:
                self.log.warning(f"CRx poller: outbound history error: {e}")
            except Exception:
                pass
            return

        pendings = list(load_pending())
        if not pendings:
            return

        # for each pending, attempt to correlate
        for p in pendings:
            try:
                self._process_pending(p, history)
            except Exception as e:
                try:
                    self.log.warning(f"CRx poller: pending process error for record {p.get('record_id')}: {e}")
                except Exception:
                    pass

    def _process_pending(self, p: Dict[str, Any], history: List[Dict[str, Any]]):
        rid = p.get("record_id")
        dest = _e164(p.get("dest_e164") or "")
        caller = _e164(p.get("caller_id") or "")
        attempt = int(p.get("attempt_no") or 1)
        submit_time = _parse_iso(str(p.get("submit_time") or ""))
        if not (rid and dest and submit_time):
            return
        # Window for correlation
        start = submit_time - timedelta(minutes=2)
        end = submit_time + timedelta(hours=2)

        # find matching outbound entries
        matches: List[Dict[str, Any]] = []
        for h in history:
            try:
                direction = (h.get("direction") or "").lower()
                if direction and direction != "outbound":
                    continue
                h_to = _e164(h.get("to") or h.get("destination") or "")
                h_from = _e164(h.get("from") or h.get("caller_id") or "")
                created_at = _parse_iso(str(h.get("created_at") or h.get("timestamp") or ""))
                if not (h_to == dest and (not caller or not h_from or h_from == caller) and created_at):
                    continue
                if not (start <= created_at <= end):
                    continue
                matches.append(h)
            except Exception:
                continue

        if not matches:
            return

        # choose the latest match by created_at
        try:
            matches.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        except Exception:
            pass
        m = matches[0]
        status = (m.get("status") or m.get("result") or m.get("state") or "").lower()
        reason = (m.get("reason") or m.get("error") or m.get("message") or "").lower()

        # interpret outcomes
        success_states = {"delivered", "success", "sent"}
        failure_states = {"failed", "busy", "no answer", "no_answer", "timeout", "canceled", "cancelled", "error"}

        if any(kw in reason for kw in ["blocked", "blacklist", "too many attempts"]):
            # treat as terminal blocked
            self._handle_blocked(rid, dest, attempt, reason)
            return

        if status in success_states:
            self._handle_delivered(rid, dest, attempt)
            return

        if (status in failure_states) or (status == "" and reason):
            # failure — schedule retry or terminal
            failure_count = int(p.get("failure_count") or 0) + 1
            update_state(rid, attempt, "failed", failure_count=failure_count, reason=reason)
            if failure_count >= self.max_attempts:
                self._handle_failed_terminal(rid, dest, attempt)
                return
            # re-submit immediately as a new attempt
            self._resubmit(rid, dest, caller, p)
            return

    def _handle_delivered(self, record_id: int, dest: str, attempt: int):
        try:
            update_state(record_id, attempt, "delivered")
        except Exception:
            pass
        # Delete from Btrieve and remove file
        self._delete_btrieve_and_file(record_id)
        try:
            get_notifier().info("Computer-Rx", f"Fax to {dest} delivered.")
        except Exception:
            pass

    def _handle_failed_terminal(self, record_id: int, dest: str, attempt: int):
        try:
            update_state(record_id, attempt, "failed_terminal")
        except Exception:
            pass
        self._delete_btrieve_and_file(record_id)
        try:
            get_notifier().info("Computer-Rx: Fax Failed", f"Fax to {dest} failed after {self.max_attempts} attempts and was removed from the queue.")
        except Exception:
            pass

    def _handle_blocked(self, record_id: int, dest: str, attempt: int, reason: str):
        try:
            update_state(record_id, attempt, "blocked", reason=reason)
        except Exception:
            pass
        self._delete_btrieve_and_file(record_id)
        try:
            get_notifier().warning(
                "Computer-Rx: Number Blocked",
                f"Number has been blocked for too many failures.\n\nPlease investigate {dest} in WinRx.\n\nFaxes were not sent; pending records were removed."
            )
        except Exception:
            pass

    def _delete_btrieve_and_file(self, record_id: int):
        # Minimal inline implementation to avoid import cycle
        try:
            winrx_path = device_config.get("Integrations", "winrx_path", "") or ""
            if not (winrx_path and os.path.isdir(winrx_path)):
                return
            # attempt deletion by scanning btrieve
            dll_path1 = r"C:\\Program Files (x86)\\Actian\\PSQL\\bin\\wbtrv32.dll"
            dll_path2 = r"C:\\Program Files (x86)\\Pervasive Software\\PSQL\\bin\\wbtrv32.dll"
            dll_to_load = dll_path1 if os.path.exists(dll_path1) else (dll_path2 if os.path.exists(dll_path2) else None)
            if not dll_to_load:
                return
            import ctypes

            B_OPEN = 0
            B_GET_FIRST = 12
            B_GET_NEXT = 6
            B_DELETE = 4
            B_CLOSE = 1
            B_EOF = 9
            BUFFER_LENGTH = 215
            DATA_BUFFER = ctypes.create_string_buffer(BUFFER_LENGTH)
            POSITION_BLOCK = ctypes.create_string_buffer(128)
            KEY_BUFFER = ctypes.create_string_buffer(4)
            KEY_LENGTH = ctypes.c_ushort(4)
            KEY_NUMBER = ctypes.c_ushort(0)
            data_length = ctypes.c_ushort(BUFFER_LENGTH)
            btrieve = ctypes.WinDLL(dll_to_load)
            # resolve file
            btrieve_file = None
            for name in os.listdir(winrx_path):
                if name.lower() == "faxcontrol.btr":
                    btrieve_file = os.path.join(winrx_path, name)
                    break
            if not btrieve_file:
                return
            status = btrieve.BTRCALL(B_OPEN, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), btrieve_file.encode(), 0, None)
            if status != 0:
                return
            try:
                status = btrieve.BTRCALL(B_GET_FIRST, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), KEY_BUFFER, KEY_LENGTH, None)
                while status == 0:
                    raw = DATA_BUFFER.raw[:data_length.value]
                    try:
                        rec_id = int.from_bytes(raw[0:4], 'little', signed=False)
                        fn = raw[27:80].decode('ascii', errors='ignore').replace('\x00', '').strip()
                    except Exception:
                        rec_id = -1
                        fn = ""
                    if rec_id == record_id:
                        # delete
                        btrieve.BTRCALL(B_DELETE, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), KEY_BUFFER, KEY_NUMBER, None)
                        # delete file
                        fp = os.path.join(winrx_path, fn) if fn else ""
                        try:
                            if fp and os.path.exists(fp):
                                os.remove(fp)
                        except Exception:
                            pass
                        break
                    status = btrieve.BTRCALL(B_GET_NEXT, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), KEY_BUFFER, KEY_NUMBER, None)
            finally:
                try:
                    btrieve.BTRCALL(B_CLOSE, POSITION_BLOCK, None, None, None, 0, None)
                except Exception:
                    pass
        except Exception:
            pass

    def _resubmit(self, record_id: int, dest: str, caller: str, p: Dict[str, Any]):
        # send again using same API and file
        fax_user = getattr(app_state.global_cfg, "fax_user", None)
        bearer = app_state.global_cfg.bearer_token or ""
        if not (fax_user and bearer):
            return
        file_path = p.get("file_path") or ""
        if not (file_path and os.path.exists(file_path)):
            update_state(record_id, int(p.get("attempt_no") or 1), "file_missing")
            return
        url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
        headers = {"Authorization": f"Bearer {bearer}"}
        data = {"caller_id": caller, "destination": dest}
        try:
            files = {"filename": (os.path.basename(file_path), open(file_path, 'rb'), 'application/pdf')}
        except Exception:
            update_state(record_id, int(p.get("attempt_no") or 1), "file_open_error")
            return
        try:
            resp = requests.post(url, files=files, data=data, headers=headers, timeout=60)
            if resp.status_code == 200:
                # new attempt pending
                next_attempt = int(p.get("attempt_no") or 1) + 1
                size_bytes = None
                try:
                    size_bytes = os.path.getsize(file_path)
                except Exception:
                    pass
                new_pending(
                    record_id=record_id,
                    dest_e164=dest,
                    caller_id=caller,
                    file_path=file_path,
                    attempt_no=next_attempt,
                    size_bytes=size_bytes,
                    pages_estimate=None,
                    file_hash=sha1_file(file_path),
                    submit_time_iso=None,
                    extra={"failure_count": int(p.get("failure_count") or 1)},
                )
            else:
                # treat as immediate failure and let next tick handle again
                update_state(record_id, int(p.get("attempt_no") or 1), "retry_http_error", status_code=resp.status_code)
        except Exception as e:
            update_state(record_id, int(p.get("attempt_no") or 1), "retry_error", error=str(e))
        finally:
            try:
                files["filename"][1].close()
            except Exception:
                pass
