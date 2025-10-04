import json
import os
from typing import Dict


def _index_path(base_dir: str) -> str:
    """
    Resolve a stable path for the downloaded index file.
    Stable location: <base_dir>\\log\\downloaded_index.json (independent of CWD and logging handler path).
    Also migrate legacy locations if present (including any prior logging_utils-based log dir or cache).
    """
    try:
        # Stable target path under the application base_dir
        stable_log_dir = os.path.join(base_dir, "log")
        os.makedirs(stable_log_dir, exist_ok=True)
        target_path = os.path.join(stable_log_dir, "downloaded_index.json")

        # If already exists, use it directly
        if os.path.exists(target_path):
            return target_path

        # Attempt migrations from legacy locations
        try:
            candidates = []
            # 1) From the logging_utils-configured LOG_DIR/LOG_FILE directory (may depend on CWD)
            try:
                from utils.logging_utils import LOG_DIR, LOG_FILE  # type: ignore

                if isinstance(LOG_FILE, str) and LOG_FILE:
                    candidates.append(os.path.join(os.path.dirname(LOG_FILE), "downloaded_index.json"))
                if isinstance(LOG_DIR, str) and LOG_DIR:
                    candidates.append(os.path.join(LOG_DIR, "downloaded_index.json"))
            except Exception:
                pass
            # 2) From <base_dir>\\cache
            candidates.append(os.path.join(base_dir, "cache", "downloaded_index.json"))
            # 3) From a previous <base_dir> root fallback
            candidates.append(os.path.join(base_dir, "downloaded_index.json"))

            # Copy/move the first existing candidate
            for old_path in candidates:
                try:
                    if old_path and os.path.exists(old_path) and old_path != target_path:
                        try:
                            os.replace(old_path, target_path)
                        except Exception:
                            # Fallback to copy+remove
                            try:
                                with open(old_path, "r", encoding="utf-8") as rf:
                                    data = rf.read()
                                with open(target_path, "w", encoding="utf-8") as wf:
                                    wf.write(data)
                                try:
                                    os.remove(old_path)
                                except Exception:
                                    pass
                            except Exception:
                                # If copy failed, try next candidate
                                pass
                        # If we successfully moved or copied, break
                        if os.path.exists(target_path):
                            return target_path
                except Exception:
                    continue
        except Exception:
            pass

        # Create an empty index at the stable location if none existed
        try:
            with open(target_path, "w", encoding="utf-8") as f:
                import json as _json
                _json.dump({}, f, indent=2)
        except Exception:
            pass
        return target_path
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
