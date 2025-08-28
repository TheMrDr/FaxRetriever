import os
import json
from typing import Dict


def _index_path(base_dir: str) -> str:
    """
    Resolve the path for the downloaded index file.
    New location: <base_dir>\\log\\downloaded_index.json
    Legacy location (pre-change): <base_dir>\\cache\\downloaded_index.json
    We migrate the legacy file to the new location if present.
    """
    try:
        log_dir = os.path.join(base_dir, "log")
        os.makedirs(log_dir, exist_ok=True)
        new_path = os.path.join(log_dir, "downloaded_index.json")
        # Migrate legacy file if needed
        try:
            old_path = os.path.join(base_dir, "cache", "downloaded_index.json")
            if os.path.exists(old_path) and not os.path.exists(new_path):
                # Ensure old dir exists is not required here; just move/rename
                try:
                    os.replace(old_path, new_path)
                except Exception:
                    # If replace fails, attempt copy then best-effort remove
                    try:
                        with open(old_path, "r", encoding="utf-8") as rf:
                            data = rf.read()
                        with open(new_path, "w", encoding="utf-8") as wf:
                            wf.write(data)
                        try:
                            os.remove(old_path)
                        except Exception:
                            pass
                    except Exception:
                        pass
        except Exception:
            pass
        return new_path
    except Exception:
        # Fallback to base_dir if log cannot be created
        return os.path.join(base_dir, "downloaded_index.json")


def load_index(base_dir: str) -> Dict[str, bool]:
    path = _index_path(base_dir)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    # Ensure boolean values
                    return {str(k): bool(v) for k, v in data.items()}
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
