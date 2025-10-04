import os
import sys
import shutil
import subprocess
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from utils.logging_utils import get_logger
from core.config_loader import device_config

API_URL = "https://api.github.com/repos/TheMrDr/FaxRetriever/releases/latest"
REQUEST_TIMEOUT = 10  # seconds
GITHUB_HEADERS = {
    "Accept": "application/vnd.github+json",
    "User-Agent": "ClinicFax-FaxRetriever/2.x (AutoUpdate)"
}

log = get_logger("auto_update")


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_version(v: str) -> Tuple[int, int, int, str]:
    # Returns (major, minor, patch, rest) to allow pre-release comparison as tie-breaker
    try:
        v = (v or "").strip()
        if v.startswith("v"):
            v = v[1:]
        parts = v.split("-")  # handle pre-release like 1.2.3-beta
        core = parts[0]
        rest = "-".join(parts[1:]) if len(parts) > 1 else ""
        nums = [int(x) for x in core.split(".")[:3]]
        while len(nums) < 3:
            nums.append(0)
        return nums[0], nums[1], nums[2], rest
    except Exception:
        return 0, 0, 0, ""


def _is_newer(latest: str, current: str) -> bool:
    lmj, lmn, lpt, lrest = _parse_version(latest)
    cmj, cmn, cpt, crest = _parse_version(current)
    if (lmj, lmn, lpt) != (cmj, cmn, cpt):
        return (lmj, lmn, lpt) > (cmj, cmn, cpt)
    # If semantic numbers equal, consider non-empty pre-release as older than release
    if lrest == crest:
        return False
    if not crest and lrest:
        # moving from release to pre-release is not newer
        return False
    if not lrest and crest:
        # moving from pre-release to release is newer
        return True
    # fallback
    return False


def get_current_version() -> str:
    try:
        from version import __version__  # type: ignore
        return str(__version__)
    except Exception:
        # Fallback to device config cached value
        return str(device_config.get("AutoUpdate", "current_version", "0.0.0"))


class UpdateChecker(QThread):
    update_available = pyqtSignal(str, str)  # version, download_url
    no_update = pyqtSignal(str)  # message
    error = pyqtSignal(str)

    def __init__(self, force: bool = False):
        super().__init__()
        self.force = force

    def run(self):
        try:
            # 24h gating
            if not self.force:
                last_check = device_config.get("AutoUpdate", "last_check_utc")
                if last_check:
                    try:
                        dt = datetime.fromisoformat(last_check)
                        if datetime.now(timezone.utc) - dt < timedelta(hours=24):
                            self.no_update.emit("Checked recently; skipping (24h window).")
                            return
                    except Exception:
                        pass

            current_version = get_current_version()
            log.info(f"Checking for updates (current={current_version})")
            resp = requests.get(API_URL, headers=GITHUB_HEADERS, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                msg = f"GitHub API error: {resp.status_code}"
                log.warning(msg)
                self.error.emit(msg)
                device_config.set("AutoUpdate", "last_check_utc", _now_utc_iso())
                device_config.save()
                return
            data = resp.json() or {}
            tag = str(data.get("tag_name") or "").strip()
            assets = data.get("assets") or []
            download_url = None
            if assets:
                # Prefer .exe asset
                for a in assets:
                    url = a.get("browser_download_url")
                    if isinstance(url, str) and url.lower().endswith(".exe"):
                        download_url = url
                        break
                if not download_url:
                    # fallback to first asset
                    url = assets[0].get("browser_download_url")
                    download_url = url if isinstance(url, str) else None
            if not tag:
                self.error.emit("Latest release has no tag_name.")
            else:
                if _is_newer(tag, current_version) and download_url:
                    self.update_available.emit(tag, download_url)
                else:
                    self.no_update.emit("You are on the latest version.")
            device_config.set("AutoUpdate", "last_check_utc", _now_utc_iso())
            if tag:
                device_config.set("AutoUpdate", "latest_remote_tag", tag)
            device_config.set("AutoUpdate", "current_version", current_version)
            device_config.save()
        except Exception as e:
            log.exception(f"Update check failed: {e}")
            self.error.emit(f"Update check failed: {e}")


class UpdateInstaller(QThread):
    progress = pyqtSignal(str)
    completed = pyqtSignal()
    failed = pyqtSignal(str)

    def __init__(self, version: str, download_url: str, exe_dir: str):
        super().__init__()
        self.version = version
        self.download_url = download_url
        self.exe_dir = exe_dir

    def run(self):
        try:
            # If not frozen (development run), just open the URL and fail gracefully
            if not getattr(sys, 'frozen', False):
                try:
                    import webbrowser
                    webbrowser.open(self.download_url)
                except Exception:
                    pass
                self.failed.emit("Running from source; please install from GitHub release.")
                return

            current_exe = sys.executable
            self.progress.emit("Downloading update...")
            tmp_path = os.path.join(self.exe_dir, f"update_{self.version}.exe")
            tmp_part = tmp_path + ".part"
            try:
                with requests.get(self.download_url, timeout=REQUEST_TIMEOUT, stream=True) as r:
                    if r.status_code != 200:
                        self.failed.emit(f"Failed to download update: HTTP {r.status_code}")
                        return
                    total = int(r.headers.get("Content-Length", 0))
                    if total:
                        mb = max(1, total // (1024 * 1024))
                        self.progress.emit(f"Downloading update ({mb} MB)...")
                    with open(tmp_part, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024 * 128):
                            if chunk:
                                f.write(chunk)
                # Atomic replace
                try:
                    os.replace(tmp_part, tmp_path)
                except Exception:
                    shutil.move(tmp_part, tmp_path)
            finally:
                # Clean up partial file on failure paths
                try:
                    if os.path.exists(tmp_part):
                        os.remove(tmp_part)
                except Exception:
                    pass

            # Create timestamped backup directory
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir = os.path.join(self.exe_dir, 'backup', ts)
            os.makedirs(backup_dir, exist_ok=True)
            backup_exe = os.path.join(backup_dir, os.path.basename(current_exe))

            # Write updater batch
            self.progress.emit("Preparing installer...")
            bat_path = os.path.join(self.exe_dir, f"update_{ts}.bat")
            exe_name = os.path.basename(current_exe)
            bat_lines = [
                "@echo off",
                "setlocal enableextensions",
                "rem Use robust quoting for all path variables",
                f"set \"CURRENT={current_exe}\"",
                f"set \"TMPFILE={tmp_path}\"",
                f"set \"BACKUPDIR={backup_dir}\"",
                f"set \"BACKUPEXE={backup_exe}\"",
                "rem Script directory (installation directory)",
                "set \"SCRIPT_DIR=%~dp0\"",
                "echo Stopping FaxRetriever...",
                f"taskkill /f /im {os.path.basename(current_exe)} >nul 2>&1",
                ":waitloop",
                f"tasklist /fi \"IMAGENAME eq {os.path.basename(current_exe)}\" | find /i \"{os.path.basename(current_exe)}\" >nul",
                "if errorlevel 1 goto do_update",
                "timeout /t 1 >nul",
                "goto waitloop",
                ":do_update",
                "echo Backing up current version...",
                "if not exist \"%BACKUPDIR%\" mkdir \"%BACKUPDIR%\"",
                "copy /y \"%CURRENT%\" \"%BACKUPEXE%\" >nul",
                "echo Installing update...",
                "move /y \"%TMPFILE%\" \"%CURRENT%\" >nul",
                "if errorlevel 1 goto restore",
                "echo Update successful. Restarting...",
                "pushd \"%SCRIPT_DIR%\"",
                "start \"\" \"%CURRENT%\"",
                "popd",
                "goto end",
                ":restore",
                "echo Update failed. Restoring backup...",
                "copy /y \"%BACKUPEXE%\" \"%CURRENT%\" >nul",
                ":end",
                "del \"%~f0\"",
            ]
            with open(bat_path, 'w', encoding='utf-8') as bf:
                bf.write("\r\n".join(bat_lines) + "\r\n")

            # Launch updater and exit app
            self.progress.emit("Applying update... The app will restart.")
            subprocess.Popen(['cmd.exe', '/c', bat_path], close_fds=True)
            self.completed.emit()
        except Exception as e:
            log.exception(f"Update install failed: {e}")
            try:
                self.failed.emit(str(e))
            except Exception:
                pass


def is_time_to_check(force: bool = False) -> bool:
    if force:
        return True
    last_check = device_config.get("AutoUpdate", "last_check_utc")
    try:
        if last_check:
            dt = datetime.fromisoformat(last_check)
            return datetime.now(timezone.utc) - dt >= timedelta(hours=24)
    except Exception:
        pass
    return True
