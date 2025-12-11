import ctypes
import os
import re
import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QMessageBox

from core.app_state import app_state
from core.config_loader import device_config, global_config
from utils.logging_utils import get_logger


class CRxIntegration2(QThread):
    """
    Computer-Rx integration thread for FaxRetriever 2.0.
    Reads FaxControl.btr from the configured WinRx path and sends faxes via SkySwitch API.
    Only runs when 3rd party integrations are enabled and Computer-Rx is selected.
    """
    finished = pyqtSignal()

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
                self.finished.emit()
            except Exception:
                pass

    @staticmethod
    def _format_phone_number(phone_number: str, caller_id: str) -> str:
        phone_number = re.sub(r"\D", "", phone_number or "")
        caller_id = re.sub(r"\D", "", caller_id or "")
        # Try to extract area code from caller_id if 11 digits
        if len(caller_id) == 11:
            area_code = caller_id[1:4]
        else:
            area_code = "000"
        if len(phone_number) == 7:
            phone_number = "1" + area_code + phone_number
        elif len(phone_number) == 10:
            phone_number = "1" + phone_number
        elif len(phone_number) != 11:
            return ""
        return phone_number

    def _resolve_btrieve_file(self, winrx_path: str) -> str | None:
        try:
            for name in os.listdir(winrx_path):
                if name.lower() == "faxcontrol.btr":
                    return os.path.join(winrx_path, name)
        except Exception:
            return None
        return None

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
                    self.log.warning(f"Computer-Rx: Invalid destination number for record {record_id}; skipping.")
                    status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    continue
                if not (full_file_path and os.path.exists(full_file_path)):
                    self.log.warning(f"Computer-Rx: Missing fax file for record {record_id}: {full_file_path}")
                    status = btrieve.BTRCALL(self.B_GET_NEXT, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                    continue
                # Send fax with up to 3 attempts; special handling for blocked numbers
                url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
                headers = {"Authorization": f"Bearer {bearer}"}
                data = {"caller_id": caller_id, "destination": dest}
                attempts = 0
                sent_ok = False
                blocked_number = False
                last_status = None
                last_text = None
                while attempts < 3 and not sent_ok and not blocked_number:
                    attempts += 1
                    files = {"filename": (os.path.basename(full_file_path), open(full_file_path, 'rb'), 'application/pdf')}
                    try:
                        resp = requests.post(url, files=files, data=data, headers=headers, timeout=60)
                        last_status = resp.status_code
                        try:
                            last_text = resp.text
                        except Exception:
                            last_text = None
                        if resp.status_code == 200:
                            sent_ok = True
                            try:
                                from utils.crx_outbound_ledger import new_pending, sha1_file
                            except Exception:
                                new_pending = None
                                sha1_file = None
                            # On API 200 (queued), do NOT delete the Btrieve record or file yet.
                            # Append a pending ledger entry for delivery tracking.
                            size_bytes = None
                            try:
                                size_bytes = os.path.getsize(full_file_path)
                            except Exception:
                                pass
                            file_hash = None
                            try:
                                if sha1_file:
                                    file_hash = sha1_file(full_file_path)
                            except Exception:
                                file_hash = None
                            if new_pending:
                                try:
                                    new_pending(
                                        record_id=record_id,
                                        dest_e164=dest,
                                        caller_id=caller_id,
                                        file_path=full_file_path,
                                        attempt_no=attempts,
                                        size_bytes=size_bytes,
                                        pages_estimate=None,
                                        file_hash=file_hash,
                                        submit_time_iso=None,
                                        extra={}
                                    )
                                    self.log.info(f"Computer-Rx: Fax queued (record {record_id}) to {dest} on attempt {attempts}; awaiting delivery status.")
                                except Exception as le:
                                    self.log.warning(f"Computer-Rx: Failed to append ledger entry for record {record_id}: {le}")
                            else:
                                self.log.info(f"Computer-Rx: Fax queued (record {record_id}) to {dest} on attempt {attempts}; ledger unavailable, will rely on queue state.")
                        else:
                            # Check for blocked number message (HTTP 400 with specific message)
                            msg_body = ""
                            try:
                                j = resp.json()
                                msg_body = (j.get("message") or "") if isinstance(j, dict) else ""
                            except Exception:
                                # Fallback to text
                                msg_body = (resp.text or "")
                            combined = f"{msg_body} {resp.text if hasattr(resp, 'text') else ''}".lower()
                            if resp.status_code == 400 and ("number is blocked" in combined or "blocked" in combined and "many attempts" in combined):
                                blocked_number = True
                                self.log.error(f"Computer-Rx: Send failed for record {record_id} -> {dest}; HTTP {resp.status_code} {resp.text}")
                                # Inform user and remove records/files to prevent infinite retries
                                try:
                                    QMessageBox.warning(None,
                                        "Computer-Rx: Number Blocked",
                                        (
                                            "The destination fax number appears to be blocked by the upstream carrier due to repeated failures.\n\n"
                                            "Action required: Investigate this fax number in WinRx.\n\n"
                                            "These faxes have NOT been sent. The related pending records will be removed from FaxControl.btr to stop further attempts."
                                        ))
                                except Exception:
                                    pass
                                # Delete current record now
                                del_status = btrieve.BTRCALL(self.B_DELETE, self.POSITION_BLOCK, self.DATA_BUFFER, ctypes.byref(data_length), self.KEY_BUFFER, self.KEY_NUMBER, None)
                                if del_status != 0:
                                    self.log.warning(f"Computer-Rx: Failed to remove record {record_id} after block detection. Status {del_status}")
                                # Try to delete the associated file
                                try:
                                    if os.path.exists(full_file_path):
                                        os.remove(full_file_path)
                                except Exception as de:
                                    self.log.warning(f"Computer-Rx: Failed to delete file {full_file_path}: {de}")
                                # Sweep remaining records for this destination and remove them to stop future attempts
                                try:
                                    P2 = ctypes.create_string_buffer(128)
                                    D2 = ctypes.create_string_buffer(self.BUFFER_LENGTH)
                                    K2 = ctypes.create_string_buffer(4)
                                    L2 = ctypes.c_ushort(4)
                                    N2 = ctypes.c_ushort(0)
                                    DL2 = ctypes.c_ushort(self.BUFFER_LENGTH)
                                    s2 = btrieve.BTRCALL(self.B_GET_FIRST, P2, D2, ctypes.byref(DL2), K2, L2, None)
                                    removed_count = 0
                                    while s2 == 0:
                                        try:
                                            raw2 = D2.raw[:DL2.value]
                                            rec2_id = int.from_bytes(raw2[0:4], 'little', signed=False)
                                            pn2 = raw2[4:18].decode('ascii', errors='ignore').replace('\x00', '').strip()
                                            fn2 = raw2[27:80].decode('ascii', errors='ignore').replace('\x00', '').strip()
                                        except Exception:
                                            rec2_id = -1
                                            pn2 = ""
                                            fn2 = ""
                                        dest2 = self._format_phone_number(pn2, caller_id)
                                        if dest2 == dest:
                                            # delete this record
                                            ds2 = btrieve.BTRCALL(self.B_DELETE, P2, D2, ctypes.byref(DL2), K2, N2, None)
                                            if ds2 != 0:
                                                self.log.warning(f"Computer-Rx: Sweep delete failed for record {rec2_id}; status {ds2}")
                                            else:
                                                removed_count += 1
                                                # remove file
                                                fp2 = os.path.join(winrx_path, fn2) if fn2 else ""
                                                try:
                                                    if fp2 and os.path.exists(fp2):
                                                        os.remove(fp2)
                                                except Exception as de2:
                                                    self.log.warning(f"Computer-Rx: Sweep failed to delete file {fp2}: {de2}")
                                            # After delete, do not call GET_NEXT immediately; current position should now be at prior; call GET_NEXT to continue
                                            s2 = btrieve.BTRCALL(self.B_GET_NEXT, P2, D2, ctypes.byref(DL2), K2, N2, None)
                                        else:
                                            s2 = btrieve.BTRCALL(self.B_GET_NEXT, P2, D2, ctypes.byref(DL2), K2, N2, None)
                                    if removed_count:
                                        self.log.info(f"Computer-Rx: Removed {removed_count} additional pending record(s) for blocked number {dest}.")
                                except Exception as swe:
                                    self.log.warning(f"Computer-Rx: Sweep removal error for blocked number {dest}: {swe}")
                            else:
                                self.log.error(f"Computer-Rx: Send failed for record {record_id} -> {dest}; HTTP {resp.status_code} {resp.text}")
                    except Exception as se:
                        self.log.error(f"Computer-Rx: Error sending record {record_id} (attempt {attempts}): {se}")
                    finally:
                        try:
                            files["filename"][1].close()
                        except Exception:
                            pass
                # If not sent and not blocked after 3 attempts, notify user
                if (not sent_ok) and (not blocked_number) and attempts >= 3:
                    try:
                        QMessageBox.information(None,
                                                "Computer-Rx: Fax Failed",
                                                f"Fax to {dest} failed after 3 attempts. It will remain in the queue. Please verify the number and try again.")
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
