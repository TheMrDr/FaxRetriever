import os
import json
from typing import Dict


def _index_path(base_dir: str) -> str:
    """
    Resolve the path for the downloaded index file.
    Requirement: downloaded_index.json must live in the same directory as ClinicFax.log (./log).
    Primary location is the logging directory configured by utils.logging_utils.
    Fallback: <base_dir>\\log\\downloaded_index.json
    Also migrate legacy locations if present.
    """
    try:
        # Prefer the actual logging directory used by ClinicFax.log
        log_dir = None
        try:
            # Importing here avoids hard coupling at module import time
            from utils.logging_utils import LOG_FILE, LOG_DIR  # type: ignore
            if isinstance(LOG_FILE, str) and LOG_FILE:
                log_dir = os.path.dirname(LOG_FILE)
            elif isinstance(LOG_DIR, str) and LOG_DIR:
                log_dir = LOG_DIR
        except Exception:
            log_dir = None

        if not log_dir:
            # Fallback to base_dir\\log
            log_dir = os.path.join(base_dir, "log")
        os.makedirs(log_dir, exist_ok=True)
        new_path = os.path.join(log_dir, "downloaded_index.json")

        # Migrate legacy files if needed
        try:
            # 1) From <base_dir>\\cache\\downloaded_index.json
            old_cache = os.path.join(base_dir, "cache", "downloaded_index.json")
            if os.path.exists(old_cache) and not os.path.exists(new_path):
                try:
                    os.replace(old_cache, new_path)
                except Exception:
                    try:
                        with open(old_cache, "r", encoding="utf-8") as rf:
                            data = rf.read()
                        with open(new_path, "w", encoding="utf-8") as wf:
                            wf.write(data)
                        try:
                            os.remove(old_cache)
                        except Exception:
                            pass
                    except Exception:
                        pass
            # 2) From <base_dir>\\log\\downloaded_index.json if different from current log_dir
            old_log = os.path.join(base_dir, "log", "downloaded_index.json")
            if os.path.exists(old_log) and old_log != new_path and not os.path.exists(new_path):
                try:
                    os.replace(old_log, new_path)
                except Exception:
                    try:
                        with open(old_log, "r", encoding="utf-8") as rf:
                            data = rf.read()
                        with open(new_path, "w", encoding="utf-8") as wf:
                            wf.write(data)
                        try:
                            os.remove(old_log)
                        except Exception:
                            pass
                    except Exception:
                        pass
        except Exception:
            pass
        return new_path
    except Exception:
        # Fallback: put it under base_dir as a last resort
        return os.path.join(base_dir, "downloaded_index.json")


def load_index(base_dir: str) -> Dict[str, bool]:
    path = _index_path(base_dir)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    data = json.load(f)
                except Exception:
                    # Corrupted or empty file: rewrite as empty index
                    data = {}
                    try:
                        with open(path, "w", encoding="utf-8") as wf:
                            json.dump({}, wf, indent=2)
                    except Exception:
                        pass
                if isinstance(data, dict):
                    # Ensure boolean values
                    return {str(k): bool(v) for k, v in data.items()}
        else:
            # Auto-create empty index file if it doesn't exist
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump({}, f, indent=2)
            except Exception:
                pass
    except Exception:
        pass
    return {}


def save_index(base_dir: str, index: Dict[str, bool]) -> None:
    path = _index_path(base_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
    except Exception:
        pass


def mark_downloaded(base_dir: str, fax_id: str) -> None:
    if not fax_id:
        return
    idx = load_index(base_dir)
    if not idx.get(fax_id):
        idx[fax_id] = True
        save_index(base_dir, idx)


def is_downloaded(base_dir: str, fax_id: str) -> bool:
    if not fax_id:
        return False
    idx = load_index(base_dir)
    return bool(idx.get(fax_id))
