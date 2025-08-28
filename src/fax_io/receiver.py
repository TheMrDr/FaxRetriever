# fax_io/receiver.py

"""
Manages download and processing of inbound faxes from the SkySwitch API.
Handles file conversion, archiving, optional printing, and cleanup.
"""

import os
import shutil
import tempfile
import subprocess
import requests
from datetime import datetime, timezone, timedelta
from PyQt5.QtCore import QThread, pyqtSignal, Qt, QRect
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtPrintSupport import QPrinter

from utils.history_index import is_downloaded

from core.app_state import app_state
from utils.logging_utils import get_logger


def _poppler_pdftoppm_path(base_dir: str) -> str:
    exe = os.path.join(base_dir, "poppler", "bin", "pdftoppm.exe")
    return exe if os.path.exists(exe) else "pdftoppm"


def convert_pdf_to_jpg(pdf_path: str, output_prefix: str, base_dir: str, dpi: int = 200) -> list:
    """
    Convert a PDF into JPG image(s) using poppler's pdftoppm.
    Returns a list of generated JPG file paths.
    """
    try:
        exe = _poppler_pdftoppm_path(base_dir)
        cmd = [exe, "-jpeg", f"-r", str(dpi), pdf_path, output_prefix]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if proc.returncode != 0:
            return []
        # Gather generated files: output_prefix-1.jpg, output_prefix-2.jpg, ...
        parent = os.path.dirname(output_prefix)
        base = os.path.basename(output_prefix)
        jpgs = []
        for name in os.listdir(parent):
            if name.startswith(base + "-") and name.lower().endswith(".jpg"):
                jpgs.append(os.path.join(parent, name))
        return sorted(jpgs)
    except Exception:
        return []

class FaxReceiver(QThread):
    finished = pyqtSignal()

    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.log = get_logger("fax_receiver")
        # self.archive_manager = ArchiveManager(base_dir)

    def run(self):
        self.start_download()

    def start_download(self):
        try:
            inbox_path = app_state.device_cfg.save_path or os.path.join(self.base_dir, "Inbox")
            os.makedirs(inbox_path, exist_ok=True)

            download_format = (app_state.device_cfg.download_method or "PDF").upper()
            should_print = str(app_state.device_cfg.print_faxes).strip().lower() == "yes"

            fax_user = getattr(app_state.global_cfg, 'fax_user', None)
            bearer = app_state.global_cfg.bearer_token
            if not fax_user:
                try:
                    self.log.error("fax_user missing from config; skipping fax retrieval until account is configured.")
                except Exception:
                    pass
                self.finished.emit()
                return
            if not bearer:
                self.log.warning("Missing bearer token; cannot retrieve faxes.")
                self.finished.emit()
                return

            headers = {"accept": "application/json", "Authorization": f"Bearer {bearer}"}
            base_url = "https://telco-api.skyswitch.com"
            list_url = f"{base_url}/users/{fax_user}/faxes/inbound"

            # Aggregate all pages
            all_faxes = []
            next_url = list_url
            while next_url:
                resp = requests.get(next_url, headers=headers, timeout=30)
                if resp.status_code != 200:
                    self.log.error(f"Failed to list inbound faxes: HTTP {resp.status_code} {resp.text}")
                    break
                payload = resp.json() or {}
                all_faxes.extend(payload.get("data", []) or [])
                links = payload.get("links", {}) or {}
                nxt = links.get("next")
                next_url = (list_url + nxt) if (nxt and not nxt.startswith("http")) else nxt

            # Server-side cleanup threshold
            try:
                retention_days = int(app_state.device_cfg.archive_duration or 365)
            except Exception:
                retention_days = 365
            if retention_days > 365:
                retention_days = 365
            cutoff_dt = datetime.now(timezone.utc) - timedelta(days=retention_days)

            processed = 0
            for fax in all_faxes:
                try:
                    fax_id = fax.get("id")
                    caller_id = (fax.get("caller_id") or "").strip()
                    created_at = fax.get("created_at")
                    pdf_url = fax.get("pdf")

                    # Skip if missing essentials
                    if not fax_id or not pdf_url or not created_at:
                        continue

                    # If we've already downloaded/processed this fax (via UI download or prior receiver run), skip.
                    try:
                        if is_downloaded(self.base_dir, str(fax_id)):
                            continue
                    except Exception:
                        pass

                    # Parse timestamp (assume Zulu ISO)
                    try:
                        if "." in created_at:
                            ts = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                        else:
                            ts = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    except Exception:
                        ts = datetime.now(timezone.utc)

                    # Server retention delete: if older than cutoff, delete and skip processing
                    if ts < cutoff_dt:
                        self._delete_server_fax(base_url, fax_user, fax_id, headers)
                        continue

                    # Build filename
                    file_base = self._build_filename(fax_id, caller_id, ts)
                    pdf_name = f"{file_base}.pdf"
                    pdf_path = os.path.join(inbox_path, pdf_name)
                    jpg_prefix = os.path.join(inbox_path, file_base)

                    # Skip if already downloaded (either pdf exists or jpgs exist for JPG/Both)
                    if os.path.exists(pdf_path):
                        continue
                    if download_format in ("JPG", "BOTH"):
                        existing_jpgs = [n for n in os.listdir(inbox_path) if n.startswith(file_base + "-") and n.lower().endswith('.jpg')]
                        if existing_jpgs:
                            continue

                    # Download PDF
                    r = requests.get(pdf_url, headers=headers, timeout=60)
                    if r.status_code != 200:
                        self.log.error(f"Failed to download fax {fax_id}: HTTP {r.status_code}")
                        continue
                    with open(pdf_path, "wb") as f:
                        f.write(r.content)
                    self.log.info(f"Downloaded fax {fax_id} -> {pdf_path}")
                    try:
                        from utils.history_index import mark_downloaded
                        mark_downloaded(self.base_dir, str(fax_id))
                    except Exception:
                        pass

                    # Convert if needed
                    if download_format == "JPG":
                        jpgs = convert_pdf_to_jpg(pdf_path, jpg_prefix, self.base_dir)
                        if not jpgs:
                            self.log.error(f"JPG conversion failed for {pdf_path}")
                        else:
                            # If printing is not requested, remove the PDF in JPG-only mode.
                            if not should_print and os.path.exists(pdf_path):
                                os.remove(pdf_path)
                    elif download_format == "BOTH":
                        _ = convert_pdf_to_jpg(pdf_path, jpg_prefix, self.base_dir)

                    # Optional printing hook
                    if should_print:
                        try:
                            self._print_pdf(pdf_path)
                        except Exception as pe:
                            self.log.error(f"Failed to start print job for {pdf_path}: {pe}")

                    processed += 1
                except Exception as ie:
                    self.log.error(f"Error processing fax item: {ie}")

            try:
                self._cleanup_server_outbound(base_url, fax_user, headers, cutoff_dt)
            except Exception as oe:
                try:
                    self.log.warning(f"Outbound cleanup encountered an error: {oe}")
                except Exception:
                    pass

            # Local inbox cleanup (delete old downloaded files)
            try:
                self._cleanup_local_inbox(inbox_path, cutoff_dt)
            except Exception as le:
                try:
                    self.log.warning(f"Local inbox cleanup encountered an error: {le}")
                except Exception:
                    pass

            self.log.info(f"Receiver pass complete. Processed {processed} item(s).")
            try:
                notif_enabled = str(getattr(app_state.device_cfg, 'notifications_enabled', 'Yes') or 'Yes').strip().lower() == 'yes'
                if processed > 0 and notif_enabled:
                    self._notify_toast(processed)
            except Exception:
                pass
            self.finished.emit()
        
        except Exception as e:
            self.log.error(f"Fax retrieval failed: {e}")
            self.finished.emit()

    def _print_pdf(self, pdf_path: str):
        try:
            # Ensure file exists
            if not os.path.exists(pdf_path):
                self.log.warning(f"Print skipped; file not found: {pdf_path}")
                return
            # Read printer settings from app_state
            printer_name = getattr(app_state.device_cfg, 'printer_name', '') or ''
            if not printer_name:
                self.log.warning("Print requested but no printer configured.")
                return

            # Convert PDF to temporary JPGs for printing (avoid external viewers entirely)
            tmpdir = tempfile.mkdtemp(prefix="fr_print_")
            prefix = os.path.join(tmpdir, "page")
            jpgs = convert_pdf_to_jpg(pdf_path, prefix, self.base_dir, dpi=200)
            if not jpgs:
                self.log.error(f"Print conversion failed (no pages) for {pdf_path}")
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                return

            # Prepare printer
            qprinter = QPrinter(QPrinter.HighResolution)
            qprinter.setPrinterName(printer_name)
            # Apply saved printer settings (best-effort)
            try:
                from core.config_loader import device_config as _devcfg
                ps = _devcfg.get("Fax Options", "printer_settings", {}) or {}
                orient = ps.get("orientation")
                if orient == "Portrait":
                    qprinter.setOrientation(QPrinter.Portrait)
                elif orient == "Landscape":
                    qprinter.setOrientation(QPrinter.Landscape)
                dp = ps.get("duplex")
                if dp == "LongSide":
                    qprinter.setDuplex(QPrinter.DuplexLongSide)
                elif dp == "ShortSide":
                    qprinter.setDuplex(QPrinter.DuplexShortSide)
                elif dp == "None":
                    qprinter.setDuplex(QPrinter.DuplexNone)
                cm = ps.get("color_mode")
                if cm == "GrayScale":
                    qprinter.setColorMode(QPrinter.GrayScale)
                elif cm == "Color":
                    qprinter.setColorMode(QPrinter.Color)
            except Exception:
                pass

            if not qprinter.isValid():
                self.log.error(f"Selected printer is not valid or not found: '{printer_name}'")
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                return

            painter = QPainter()
            if not painter.begin(qprinter):
                self.log.error("Failed to begin print job (QPainter)")
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
                return

            try:
                for idx, img_path in enumerate(jpgs):
                    img = QImage(img_path)
                    if img.isNull():
                        self.log.warning(f"Skipping null image page: {img_path}")
                        continue
                    # Fit image to page rect preserving aspect ratio
                    page_rect = qprinter.pageRect()
                    scaled_size = img.size().scaled(page_rect.size(), Qt.KeepAspectRatio)
                    # Center within page
                    x = page_rect.x() + (page_rect.width() - scaled_size.width()) // 2
                    y = page_rect.y() + (page_rect.height() - scaled_size.height()) // 2
                    target_rect = QRect(x, y, scaled_size.width(), scaled_size.height())
                    painter.drawImage(target_rect, img)
                    if idx < len(jpgs) - 1:
                        qprinter.newPage()
                self.log.info(f"Print job sent: {os.path.basename(pdf_path)} -> '{printer_name}' ({len(jpgs)} page(s))")
            finally:
                painter.end()
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                except Exception:
                    pass
        except Exception as e:
            self.log.error(f"Print failed for {pdf_path}: {e}")

    def _notify_toast(self, processed: int):
        # Safety: do not notify for zero or negative counts
        try:
            count = int(processed)
        except Exception:
            count = 0
        if count <= 0:
            return

        title = "FaxRetriever"
        plural = "" if count == 1 else "es"
        msg = f"Downloaded {count} fax{plural}."

        # Resolve icon paths
        icon_ico = os.path.join(self.base_dir, "images", "logo.ico")
        icon_png = os.path.join(self.base_dir, "images", "logo.png")
        has_ico = os.path.exists(icon_ico)
        has_png = os.path.exists(icon_png)

        # Try winotify (PNG typically supported) first to ensure icon appears even if .ico is invalid
        try:
            from winotify import Notification
            try:
                toast = Notification(app_id="FaxRetriever", title=title, msg=msg, icon=(icon_png if has_png else (icon_ico if has_ico else None)))
                toast.show()
                return
            except Exception:
                pass
        except Exception:
            pass

        # Fallback: win10toast (uses .ico)
        try:
            from win10toast import ToastNotifier
            try:
                notifier = ToastNotifier()
                notifier.show_toast(title, msg, icon_path=(icon_ico if has_ico else None), duration=5, threaded=True)
                return
            except Exception:
                pass
        except Exception:
            pass

        # Try plyer
        try:
            from plyer import notification
            try:
                notification.notify(title=title, message=msg, app_name="FaxRetriever", app_icon=(icon_ico if has_ico else (icon_png if has_png else None)), timeout=5)
                return
            except Exception:
                pass
        except Exception:
            pass

        # Try PowerShell BurntToast if available
        try:
            if has_png or has_ico:
                icon_path = icon_png if has_png else icon_ico
                ps_script = f"$title='{title}'; $msg='{msg}'; if (Get-Module -ListAvailable -Name BurntToast) {{ New-BurntToastNotification -Text $title,$msg -AppLogo '{icon_path}' }} else {{ $null }} "
            else:
                ps_script = f"$title='{title}'; $msg='{msg}'; if (Get-Module -ListAvailable -Name BurntToast) {{ New-BurntToastNotification -Text $title,$msg }} else {{ $null }} "
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_script], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return
        except Exception:
            pass

        # If everything failed, just log
        try:
            self.log.debug("Toast notification could not be shown (no supported library found).")
        except Exception:
            pass

    def _delete_server_fax(self, base_url: str, fax_user: str, fax_id: str, headers: dict):
        try:
            del_url = f"{base_url}/users/{fax_user}/faxes/{fax_id}/delete"
            resp = requests.post(del_url, headers=headers, timeout=15)
            if resp.status_code == 200:
                self.log.info(f"Deleted server fax {fax_id} per retention policy.")
            else:
                self.log.warning(f"Failed to delete server fax {fax_id}: HTTP {resp.status_code}")
        except Exception as e:
            self.log.warning(f"Delete server fax error for {fax_id}: {e}")

    def _cleanup_server_outbound(self, base_url: str, fax_user: str, headers: dict, cutoff_dt: datetime):
        """List outbound faxes and delete those older than cutoff_dt."""
        try:
            list_url = f"{base_url}/users/{fax_user}/faxes/outbound"
            next_url = list_url
            total_deleted = 0
            while next_url:
                resp = requests.get(next_url, headers=headers, timeout=30)
                if resp.status_code != 200:
                    self.log.error(f"Failed to list outbound faxes: HTTP {resp.status_code} {resp.text}")
                    break
                payload = resp.json() or {}
                for fax in (payload.get("data", []) or []):
                    try:
                        fax_id = fax.get("id")
                        created_at = fax.get("created_at")
                        if not fax_id or not created_at:
                            continue
                        try:
                            if "." in created_at:
                                ts = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
                            else:
                                ts = datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                        except Exception:
                            ts = datetime.now(timezone.utc)
                        if ts < cutoff_dt:
                            self._delete_server_fax(base_url, fax_user, fax_id, headers)
                            total_deleted += 1
                    except Exception as ie:
                        self.log.warning(f"Error evaluating outbound fax for deletion: {ie}")
                links = payload.get("links", {}) or {}
                nxt = links.get("next")
                next_url = (list_url + nxt) if (nxt and not nxt.startswith("http")) else nxt
            if total_deleted:
                self.log.info(f"Outbound cleanup deleted {total_deleted} fax(es) older than retention.")
        except Exception as e:
            self.log.warning(f"Outbound cleanup error: {e}")

    def _cleanup_local_inbox(self, inbox_path: str, cutoff_dt: datetime):
        """Delete local inbox files (PDF/JPG) older than cutoff_dt based on file mtime."""
        try:
            now = datetime.now(timezone.utc)
            removed = 0
            for name in os.listdir(inbox_path):
                low = name.lower()
                if not (low.endswith('.pdf') or low.endswith('.jpg')):
                    continue
                fpath = os.path.join(inbox_path, name)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(fpath), tz=timezone.utc)
                except Exception:
                    continue
                if mtime < cutoff_dt:
                    try:
                        os.remove(fpath)
                        removed += 1
                    except Exception as de:
                        self.log.warning(f"Failed to remove old file '{fpath}': {de}")
            if removed:
                self.log.info(f"Local inbox cleanup removed {removed} old file(s).")
        except Exception as e:
            self.log.warning(f"Local inbox cleanup error: {e}")

    def _build_filename(self, fax_id: str, caller_id: str, ts: datetime) -> str:
        """
        Build a safe filename base for a fax using the configured naming scheme.
        Always returns a string and strips characters invalid for Windows filenames.
        """
        def _sanitize(part: str) -> str:
            try:
                s = str(part)
            except Exception:
                s = ""
            # Replace invalid Windows filename characters
            invalid = '<>:"/\\|?*'
            s = ''.join((ch if ch not in invalid else '_') for ch in s)
            # Remove leading/trailing spaces and dots
            s = s.strip().strip('.')
            # Avoid empty component
            return s or "fax"

        naming = (app_state.device_cfg.file_name_format or "faxid").lower()
        if naming == "cid" and caller_id:
            # CID-DDMMYY-HHMMSS
            base = f"{_sanitize(caller_id)}-{ts.strftime('%d%m%y-%H%M%S')}"
            return _sanitize(base)
        # Default to fax id
        return _sanitize(fax_id)
