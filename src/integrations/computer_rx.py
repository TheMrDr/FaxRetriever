import ctypes
import os
import re
import time
import shutil
import tempfile
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from core.app_state import app_state
from core.config_loader import device_config, global_config
from utils.logging_utils import get_logger
from core.outbox_ledger import (
    make_key_crx,
    get_job,
    upsert_job,
    should_backoff,
    record_failure,
    mark_quarantined,
    mark_invalid_number,
    mark_accepted,
    update_metadata,
)


class CRxIntegration2(QThread):
    """
    Computer-Rx integration thread for FaxRetriever 2.0.
    Reads FaxControl.btr from the configured WinRx path and sends faxes via SkySwitch API.
    Only runs when 3rd party integrations are enabled and Computer-Rx is selected.
    """
    finished = pyqtSignal()
    invalid_number_detected = pyqtSignal(dict)

    def __init__(self, base_dir: str, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.log = get_logger("integration.computer_rx")
        # Btrieve DLL search locations
        self.dll_path1 = r"C:\\Program Files (x86)\\Actian\\PSQL\\bin\\wbtrv32.dll"
        self.dll_path2 = r"C:\\Program Files (x86)\\Pervasive Software\\PSQL\\bin\\wbtrv32.dll"
        # Btrieve constants
        self.B_OPEN = 0
        self.B_GET_FIRST = 12
        self.B_GET_NEXT = 6
        self.B_DELETE = 4
        self.B_CLOSE = 1
        self.B_EOF = 9
        self.BUFFER_LENGTH = 215
        self.DATA_BUFFER = ctypes.create_string_buffer(self.BUFFER_LENGTH)
        self.POSITION_BLOCK = ctypes.create_string_buffer(128)
        self.KEY_BUFFER = ctypes.create_string_buffer(4)
        self.KEY_LENGTH = ctypes.c_ushort(4)
        self.KEY_NUMBER = ctypes.c_ushort(0)
        self._should_run = self._check_enabled()
        self._http_session = None

    def _check_enabled(self) -> bool:
        try:
            # Prefer device-level integration settings if present
            dev_settings = device_config.get("Integrations", "integration_settings", {}) or {}
            glob_settings = app_state.global_cfg.integration_settings or {}
            enabled = ((dev_settings.get("enable_third_party") or glob_settings.get("enable_third_party") or "No").strip().lower() == "yes")
            software = (dev_settings.get("integration_software") or glob_settings.get("integration_software") or "None").strip()
            if not enabled or software != "Computer-Rx":
                return False
            # WinRx path must be present
            winrx_path = device_config.get("Integrations", "winrx_path", "") or ""
            if not winrx_path:
                self.log.debug("Computer-Rx enabled but WinRx path not configured; skipping.")
                return False
            return True
        except Exception:
            return False

    def run(self):
        try:
            if not self._should_run:
                self.finished.emit()
                return
            self._process_records()
        except Exception as e:
            try:
                self.log.error(f"Computer-Rx run failed: {e}")
            except Exception:
                pass
        finally:
            try:
                if self._http_session is not None:
                    self._http_session.close()
                    self._http_session = None
            except Exception:
                pass
            try:
                self.finished.emit()
            except Exception:
                pass

    @staticmethod
    def _format_phone_number(phone_number: str, caller_id: str) -> str:
        """
        Normalize destination to NANP E.164 using the sender's caller ID area code by default.
        Rules:
        - Strip non-digits
        - 7-digit local -> prepend area from caller_id (if available)
        - 12-digit starting with '11' -> drop one leading '1'
        - 10-digit -> prepend leading '1'
        - Accept only if final form is 11 digits starting with '1'
        """
        digits = re.sub(r"\D", "", phone_number or "")
        cid = re.sub(r"\D", "", caller_id or "")
        area = None
        if len(cid) == 11 and cid.startswith("1"):
            area = cid[1:4]
        elif len(cid) == 10:
            area = cid[0:3]
        # Local 7-digit -> use sender area if present
        if len(digits) == 7 and area:
            digits = area + digits
        # Double leading '1' case (e.g., '11XXXXXXXXXX')
        if len(digits) == 12 and digits.startswith("11"):
            digits = digits[1:]
        # 10-digit -> add leading 1
        if len(digits) == 10:
            digits = "1" + digits
        return digits if (len(digits) == 11 and digits.startswith("1")) else ""

    def _resolve_btrieve_file(self, winrx_path: str) -> str | None:
        try:
            for name in os.listdir(winrx_path):
                if name.lower() == "faxcontrol.btr":
                    return os.path.join(winrx_path, name)
        except Exception:
            return None
        return None

    def _get_session(self) -> requests.Session:
        try:
            if self._http_session is None:
                s = requests.Session()
                retry = Retry(
                    total=3,
                    connect=3,
                    read=3,
                    backoff_factor=1.5,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["POST", "GET"],
                    raise_on_status=False,
                )
                adapter = HTTPAdapter(max_retries=retry)
                s.mount("https://", adapter)
                s.mount("http://", adapter)
                self._http_session = s
            return self._http_session
        except Exception:
            # Fallback to plain requests
            return requests.Session()

    def _is_file_stable(self, path: str, min_age_sec: float = 1.5) -> bool:
        try:
            s1 = os.stat(path)
            time.sleep(0.5)
            s2 = os.stat(path)
            return (s1.st_size == s2.st_size) and ((time.time() - s2.st_mtime) >= min_age_sec)
        except Exception:
            return False

    def _notify_toast(self, message: str) -> None:
        try:
            icon_ico = os.path.join(self.base_dir, "images", "logo.ico")
            icon_png = os.path.join(self.base_dir, "images", "logo.png")
            has_ico = os.path.exists(icon_ico)
            has_png = os.path.exists(icon_png)
            try:
                from winotify import Notification
                toast = Notification(
                    app_id="FaxRetriever",
                    title="FaxRetriever",
                    msg=message,
                    icon=(icon_png if has_png else (icon_ico if has_ico else None)),
                )
                toast.show()
                return
            except Exception:
                pass
            try:
                from win10toast import ToastNotifier
                notifier = ToastNotifier()
                notifier.show_toast(
                    "FaxRetriever",
                    message,
                    icon_path=(icon_ico if has_ico else None),
                    duration=5,
                    threaded=True,
                )
                return
            except Exception:
                pass
        except Exception:
            pass

    @staticmethod
    def run_initial_cleanup_if_needed(parent=None):
        """
        One-time first-run process for Computer-Rx integration.
        - Checks if integrations are enabled and Computer-Rx selected.
        - Verifies WinRx path and Btrieve DLL presence.
        - If FaxControl.btr has records, prompts user to clear all existing faxes (records + files).
        - Uses global_config flag Integrations.crx_initial_cleanup_done to ensure it fires only once
          after prerequisites are satisfied.
        """
        log = get_logger("integration.computer_rx")
        try:
            # Global guard: only run if not already completed
            already_done = global_config.get("Integrations", "crx_initial_cleanup_done", False) or False
            if already_done:
                return

            # Check if integration is enabled and Computer-Rx selected (prefer device-level settings)
            dev_settings = device_config.get("Integrations", "integration_settings", {}) or {}
            glob_settings = app_state.global_cfg.integration_settings or {}
            enabled = ((dev_settings.get("enable_third_party") or glob_settings.get("enable_third_party") or "No").strip().lower() == "yes")
            software = (dev_settings.get("integration_software") or glob_settings.get("integration_software") or "None").strip()
            if not (enabled and software == "Computer-Rx"):
                return

            # WinRx path must exist
            winrx_path = device_config.get("Integrations", "winrx_path", "") or ""
            if not (winrx_path and os.path.isdir(winrx_path)):
                # Do not set the flag yet; prerequisites not met
                log.debug("Computer-Rx initial cleanup: WinRx path not configured or invalid; deferring.")
                return

            # Resolve FaxControl.btr
            btrieve_file = None
            try:
                for name in os.listdir(winrx_path):
                    if name.lower() == "faxcontrol.btr":
                        btrieve_file = os.path.join(winrx_path, name)
                        break
            except Exception:
                btrieve_file = None
            if not btrieve_file:
                log.debug("Computer-Rx initial cleanup: FaxControl.btr not found; nothing to do.")
                # Prereqs partially met, but file absent; consider this complete to avoid re-prompting.
                global_config.set("Integrations", "crx_initial_cleanup_done", True)
                global_config.save()
                return

            # Determine Btrieve DLL presence
            dll_path1 = r"C:\\Program Files (x86)\\Actian\\PSQL\\bin\\wbtrv32.dll"
            dll_path2 = r"C:\\Program Files (x86)\\Pervasive Software\\PSQL\\bin\\wbtrv32.dll"
            dll_to_load = dll_path1 if os.path.exists(dll_path1) else (dll_path2 if os.path.exists(dll_path2) else None)
            if not dll_to_load:
                log.debug("Computer-Rx initial cleanup: Btrieve DLL not found; deferring until installed.")
                return

            # Btrieve constants and buffers
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

            # Load and open
            try:
                btrieve = ctypes.WinDLL(dll_to_load)
            except OSError as e:
                log.debug(f"Computer-Rx initial cleanup: Failed to load Btrieve DLL: {e}; deferring.")
                return

            status = btrieve.BTRCALL(B_OPEN, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), btrieve_file.encode(), 0, None)
            if status != 0:
                log.warning(f"Computer-Rx initial cleanup: Failed to open {btrieve_file}; status {status}")
                # If we cannot open, don't set flag so we might retry later when fixed
                return

            had_error = False
            try:
                # Is there at least one record?
                status = btrieve.BTRCALL(B_GET_FIRST, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), KEY_BUFFER, KEY_LENGTH, None)
                if status != 0 and status != B_EOF:
                    log.warning(f"Computer-Rx initial cleanup: GET_FIRST returned status {status}")
                records_present = (status == 0)

                if records_present:
                    # Ask user whether to clear
                    try:
                        response = QMessageBox.question(
                            parent,
                            "Computer-Rx: Clear Existing Faxes?",
                            (
                                "Existing outgoing fax records were found in FaxControl.btr.\n\n"
                                "To prevent stale faxes from being sent, do you want to clear ALL existing faxes now?\n\n"
                                "This will delete all pending fax records and any associated files in the WinRx folder."
                            ),
                            QMessageBox.Yes | QMessageBox.No
                        )
                    except Exception:
                        # If UI not available, default to not clearing but still consider process shown
                        response = QMessageBox.No

                    if response == QMessageBox.Yes:
                        # Iterate and delete all records and referenced files
                        while status == 0:
                            raw = DATA_BUFFER.raw[:data_length.value]
                            try:
                                file_name = raw[27:80].decode('ascii', errors='ignore').replace('\x00', '').strip()
                            except Exception:
                                file_name = ""
                            full_file_path = os.path.join(winrx_path, file_name) if file_name else ""
                            # Delete record first
                            del_status = btrieve.BTRCALL(B_DELETE, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), KEY_BUFFER, KEY_NUMBER, None)
                            if del_status != 0:
                                log.warning(f"Computer-Rx initial cleanup: Failed to delete a record; status {del_status}")
                            # Delete file if exists
                            if full_file_path and os.path.exists(full_file_path):
                                try:
                                    os.remove(full_file_path)
                                except Exception as de:
                                    log.warning(f"Computer-Rx initial cleanup: Failed to delete file {full_file_path}: {de}")
                            # Next
                            status = btrieve.BTRCALL(B_GET_NEXT, POSITION_BLOCK, DATA_BUFFER, ctypes.byref(data_length), KEY_BUFFER, KEY_NUMBER, None)
                            if status == B_EOF:
                                break
                        log.info("Computer-Rx initial cleanup: Cleared existing Btrieve records and files.")
                    else:
                        log.info("Computer-Rx initial cleanup: User declined to clear existing records.")
                else:
                    log.info("Computer-Rx initial cleanup: No existing records found.")
            except Exception as e:
                had_error = True
                log.error(f"Computer-Rx initial cleanup: Error during cleanup: {e}")
            finally:
                try:
                    btrieve.BTRCALL(B_CLOSE, POSITION_BLOCK, None, None, None, 0, None)
                except Exception:
                    pass

            # If we reached here, prerequisites were satisfied and user was prompted (or no records).
            # Mark as done to ensure it does not run again.
            global_config.set("Integrations", "crx_initial_cleanup_done", True)
            try:
                global_config.save()
            except Exception:
                pass
        except Exception as e:
            try:
                log.error(f"Computer-Rx initial cleanup: unexpected error: {e}")
            except Exception:
                pass

    def _process_records(self):
        # Preconditions: bearer token + fax_user
        fax_user = getattr(app_state.global_cfg, 'fax_user', None)
        bearer = app_state.global_cfg.bearer_token or ""
        if not fax_user:
            try:
                self.log.error("Computer-Rx: fax_user missing from config; skipping run until account is configured.")
            except Exception:
                pass
            return
        if not bearer:
            self.log.info("Computer-Rx: Missing bearer token; skipping run.")
            return
        # Caller ID source: prefer selected_fax_number, then first selected, then first known account number
        caller_id = (app_state.device_cfg.selected_fax_number or (app_state.device_cfg.selected_fax_numbers[0] if app_state.device_cfg.selected_fax_numbers else (app_state.global_cfg.all_numbers[0] if app_state.global_cfg.all_numbers else "")))
        caller_id = re.sub(r"\D", "", caller_id or "")
        if len(caller_id) < 10:
            self.log.warning("Computer-Rx: Caller ID appears invalid/missing; proceeding but number formatting may fail.")
        winrx_path = device_config.get("Integrations", "winrx_path", "") or ""
        if not winrx_path or not os.path.isdir(winrx_path):
            self.log.error("Computer-Rx: WinRx path not set or invalid; skipping run.")
            return
        btrieve_file = self._resolve_btrieve_file(winrx_path)
        if not btrieve_file:
            self.log.error("Computer-Rx: FaxControl.btr not found in WinRx path; skipping run.")
            return
        # Load Btrieve dll
        dll_to_load = self.dll_path1 if os.path.exists(self.dll_path1) else (self.dll_path2 if os.path.exists(self.dll_path2) else None)
        if not dll_to_load:
            self.log.error("Computer-Rx: Btrieve DLL not found. Ensure Actian/Pervasive PSQL is installed.")
            return
        try:
            btrieve = ctypes.WinDLL(dll_to_load)
        except OSError as e:
            self.log.error(f"Computer-Rx: Failed to load Btrieve DLL: {e}")
            return
        # Open file
        data_length = ctypes.c_ushort(self.BUFFER_LENGTH)
        status = btrieve.BTRCALL(self.B_OPEN, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), btrieve_file.encode(), 0, None)
        if status != 0:
            self.log.error(f"Computer-Rx: Failed to open Btrieve file: {btrieve_file} | Status: {status}")
            return
        try:
            # Iterate records
            status = btrieve.BTRCALL(self.B_GET_FIRST, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_LENGTH, None)
            while status == 0:
                raw = self.DATA_BUFFER.raw[:data_length.value]
                try:
                    record_id = int.from_bytes(raw[0:4], 'little', signed=False)
                    phone_number = raw[4:18].decode('ascii', errors='ignore').replace('\x00', '').strip()
                    file_name = raw[27:80].decode('ascii', errors='ignore').replace('\x00', '').strip()
                except Exception:
                    record_id = -1
                    phone_number = ""
                    file_name = ""
                full_file_path = os.path.join(winrx_path, file_name) if file_name else ""
                dest = self._format_phone_number(phone_number, caller_id)
                if len(dest) != 11:
                    try:
                        self.log.warning(f"Computer-Rx: Invalid/ambiguous destination for record {record_id}; removing record and parking file.")
                    except Exception:
                        pass
                    # Remove BTR record to avoid infinite retries
                    try:
                        _ = btrieve.BTRCALL(self.B_DELETE, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    except Exception:
                        pass
                    # Move file to WinRx\\FaxRetriever\\Failed for operator retry
                    failed_full = ""
                    try:
                        if full_file_path and os.path.exists(full_file_path):
                            failed_dir = os.path.join(winrx_path, "FaxRetriever", "Failed")
                            os.makedirs(failed_dir, exist_ok=True)
                            safe_name = f"invalid_{record_id}_" + os.path.basename(full_file_path)
                            failed_full = os.path.join(failed_dir, safe_name)
                            os.replace(full_file_path, failed_full)
                    except Exception:
                        pass
                    # Ledger note
                    try:
                        key = make_key_crx(record_id, file_name)
                        mark_invalid_number(self.base_dir, key, phone_number or "")
                        update_metadata(self.base_dir, key, type="crx", record_id=record_id, file=failed_full or full_file_path, dest="", caller=caller_id)
                    except Exception:
                        pass
                    # Emit non-blocking UI event to prompt correction
                    try:
                        payload = {
                            "source": "crx",
                            "record_id": record_id,
                            "original_number": phone_number or "",
                            "file_path": failed_full or (os.path.join(winrx_path, "FaxRetriever", "Failed", f"invalid_{record_id}_" + os.path.basename(full_file_path)) if (full_file_path and os.path.basename(full_file_path)) else ""),
                            "suggested": "",
                        }
                        self.invalid_number_detected.emit(payload)
                    except Exception:
                        pass
                    status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    continue
                if not (full_file_path and os.path.exists(full_file_path)):
                    self.log.warning(f"Computer-Rx: Missing fax file for record {record_id}: {full_file_path}")
                    status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    continue
                # Ledger metadata & backoff check
                key = make_key_crx(record_id, file_name)
                try:
                    upsert_job(self.base_dir, key, initializer={
                        "type": "crx",
                        "record_id": record_id,
                        "file": full_file_path,
                        "dest": dest,
                        "caller": caller_id,
                    })
                except Exception:
                    pass
                try:
                    job = get_job(self.base_dir, key)
                    if should_backoff(job):
                        try:
                            self.log.info(f"Computer-Rx: Backing off record {record_id}; next eligible later.")
                        except Exception:
                            pass
                        status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                        continue
                except Exception:
                    pass

                # Ensure file is stable; stage to temp before sending
                if not self._is_file_stable(full_file_path):
                    try:
                        self.log.info(f"Computer-Rx: File not stable yet for record {record_id}; will retry next pass.")
                    except Exception:
                        pass
                    status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    continue
                try:
                    staged = shutil.copy(full_file_path, os.path.join(tempfile.gettempdir(), f"crx_{record_id}_" + os.path.basename(full_file_path)))
                except Exception:
                    staged = full_file_path

                # Send fax
                url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
                headers = {"Authorization": f"Bearer {bearer}"}
                data = {"caller_id": caller_id, "destination": dest}
                session = self._get_session()
                resp = None
                try:
                    with open(staged, 'rb') as fh:
                        files = {"filename": (os.path.basename(staged), fh, 'application/pdf')}
                        resp = session.post(url, files=files, data=data, headers=headers, timeout=60)
                    code = getattr(resp, 'status_code', 0)
                    if code == 429:
                        self.log.warning("Computer-Rx: Throttled by provider (429). Deferring remaining records to next run.")
                        break
                    if 200 <= code < 300:
                        try:
                            size_bytes = os.path.getsize(staged) if os.path.exists(staged) else None
                        except Exception:
                            size_bytes = None
                        try:
                            mark_accepted(self.base_dir, key, dest=dest, caller=caller_id, bytes_total=size_bytes)
                        except Exception:
                            pass
                        # Immediate operator feedback: upstream acceptance
                        try:
                            self._notify_toast(f"Fax accepted by carrier for {dest}.")
                        except Exception:
                            pass
                        self.log.info(f"Computer-Rx: Fax accepted (record {record_id}) to {dest}; removing record and file.")
                        del_status = btrieve.BTRCALL(self.B_DELETE, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                        if del_status != 0:
                            self.log.warning(f"Computer-Rx: Failed to remove record {record_id} from Btrieve. Status {del_status}")
                        try:
                            if full_file_path != staged and os.path.exists(staged):
                                os.remove(staged)
                        except Exception:
                            pass
                        try:
                            if os.path.exists(full_file_path):
                                os.remove(full_file_path)
                        except Exception as de:
                            self.log.warning(f"Computer-Rx: Failed to delete file {full_file_path}: {de}")
                    else:
                        msg = None
                        try:
                            msg = resp.text[:500]
                        except Exception:
                            msg = ""
                        self.log.error(f"Computer-Rx: Send failed for record {record_id} -> {dest}; HTTP {code} {msg}")
                        # Record failure and possibly quarantine
                        try:
                            job = record_failure(self.base_dir, key, f"HTTP {code}")
                            attempts = int(job.get('attempts', 0))
                            if attempts >= 3:
                                # Delete BTR record and move file to Failed
                                _ = btrieve.BTRCALL(self.B_DELETE, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                                try:
                                    if full_file_path and os.path.exists(full_file_path):
                                        failed_dir = os.path.join(winrx_path, "FaxRetriever", "Failed")
                                        os.makedirs(failed_dir, exist_ok=True)
                                        safe_name = f"failed_{record_id}_" + os.path.basename(full_file_path)
                                        os.replace(full_file_path, os.path.join(failed_dir, safe_name))
                                except Exception:
                                    pass
                                mark_quarantined(self.base_dir, key, reason=f"HTTP {code}")
                                self._notify_toast(f"Fax failed after 3 attempts to {dest}.")
                        except Exception:
                            pass
                except Exception as se:
                    try:
                        self.log.error(f"Computer-Rx: Error sending record {record_id}: {se}")
                    except Exception:
                        pass
                    try:
                        job = record_failure(self.base_dir, key, f"EXC: {se}")
                        attempts = int(job.get('attempts', 0))
                        if attempts >= 3:
                            _ = btrieve.BTRCALL(self.B_DELETE, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                            try:
                                if full_file_path and os.path.exists(full_file_path):
                                    failed_dir = os.path.join(winrx_path, "FaxRetriever", "Failed")
                                    os.makedirs(failed_dir, exist_ok=True)
                                    safe_name = f"failed_{record_id}_" + os.path.basename(full_file_path)
                                    os.replace(full_file_path, os.path.join(failed_dir, safe_name))
                            except Exception:
                                pass
                            mark_quarantined(self.base_dir, key, reason="exception")
                            self._notify_toast(f"Fax failed after 3 attempts to {dest}.")
                    except Exception:
                        pass
                # Next
                status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                if status == self.B_EOF:
                    break
            if status not in (0, self.B_EOF):
                self.log.warning(f"Computer-Rx: Iteration ended with status {status}")
        finally:
            try:
                btrieve.BTRCALL(self.B_CLOSE, self.POSITION_BLOCK, None, None, None, 0, None)
            except Exception:
                pass
            self.log.info("Computer-Rx: Processing complete.")
