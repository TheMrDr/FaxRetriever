import os
import tempfile
from typing import Dict, Set

# In-memory cache — single canonical path
_cached_path: str | None = None
_cached_mtime: float | None = None
_cached_ids: set[str] = set()
_migrated: bool = False


def _safe_localappdata_dir() -> str:
    """Resolve a writable per-user LocalAppData directory safely (Windows-oriented)."""
    lad = os.getenv("LOCALAPPDATA")
    if lad and os.path.isdir(lad):
        return lad
    home = os.path.expanduser("~")
    fallback = os.path.join(home, "AppData", "Local")
    return fallback if os.path.isdir(fallback) else (lad or fallback)


def _log_path(base_dir: str) -> str:
    """Single canonical path for the downloaded fax ID log."""
    try:
        shared_dir = os.path.join(base_dir, "shared", "history")
        os.makedirs(shared_dir, exist_ok=True)
        return os.path.join(shared_dir, "downloaded_faxes.log")
    except Exception:
        return os.path.join(base_dir, "downloaded_faxes.log")


def _old_localappdata_path() -> str | None:
    """Return the legacy LocalAppData log path if it exists."""
    try:
        lad = _safe_localappdata_dir()
        path = os.path.join(
            lad, "Clinic Networking, LLC", "FaxRetriever", "2.0",
            "history", "downloaded_faxes.log",
        )
        return path if os.path.exists(path) else None
    except Exception:
        return None


def _legacy_json_candidates(base_dir: str) -> list[str]:
    """Return possible legacy JSON index paths to migrate from."""
    cands: list[str] = []
    try:
        cands.append(os.path.join(base_dir, "log", "downloaded_index.json"))
        try:
            from utils.logging_utils import LOG_DIR, LOG_FILE  # type: ignore
            if isinstance(LOG_FILE, str) and LOG_FILE:
                cands.append(os.path.join(os.path.dirname(LOG_FILE), "downloaded_index.json"))
            if isinstance(LOG_DIR, str) and LOG_DIR:
                cands.append(os.path.join(LOG_DIR, "downloaded_index.json"))
        except Exception:
            pass
        cands.append(os.path.join(base_dir, "cache", "downloaded_index.json"))
        cands.append(os.path.join(base_dir, "downloaded_index.json"))
    except Exception:
        pass
    seen: set[str] = set()
    out: list[str] = []
    for p in cands:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out


def _read_single_log(path: str) -> set[str]:
    ids: set[str] = set()
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    s = line.strip()
                    if s:
                        ids.add(s)
    except Exception:
        pass
    return ids


def _append_log(path: str, fax_id: str) -> bool:
    """Append to the log file. Returns True on success."""
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    except Exception:
        pass
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"{fax_id}\n")
            try:
                f.flush()
                os.fsync(f.fileno())
            except Exception:
                pass
        return True
    except Exception:
        return False


def _rewrite_log(path: str, ids: set[str]) -> None:
    """Atomically rewrite the log file with the given IDs."""
    dir_path = os.path.dirname(path) or "."
    try:
        os.makedirs(dir_path, exist_ok=True)
    except Exception:
        pass
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(dir=dir_path, suffix=".tmp", prefix=".hist_")
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            for fid in sorted(ids):
                f.write(f"{fid}\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        if tmp:
            try:
                os.unlink(tmp)
            except Exception:
                pass


def _migrate_to_single_file(base_dir: str, canonical: str) -> None:
    """One-time migration: merge LocalAppData log + legacy JSON into the single canonical file."""
    global _migrated, _cached_path, _cached_ids, _cached_mtime
    if _migrated:
        return
    _migrated = True

    existing = _read_single_log(canonical)
    changed = False

    # Merge from old LocalAppData log
    old_lad = _old_localappdata_path()
    if old_lad:
        lad_ids = _read_single_log(old_lad)
        new_ids = lad_ids - existing
        if new_ids:
            existing |= new_ids
            changed = True
        try:
            os.rename(old_lad, old_lad + ".migrated")
        except Exception:
            pass

    # Merge from legacy JSON files
    for p in _legacy_json_candidates(base_dir):
        try:
            if not os.path.exists(p):
                continue
            import json as _json
            with open(p, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if isinstance(data, dict):
                for k, v in data.items():
                    if v and isinstance(k, str) and k not in existing:
                        existing.add(k)
                        changed = True
        except Exception:
            continue

    if changed:
        _rewrite_log(canonical, existing)

    _cached_path = canonical
    _cached_ids = existing
    try:
        _cached_mtime = os.path.getmtime(canonical) if os.path.exists(canonical) else None
    except Exception:
        _cached_mtime = None


def _ensure_cache(base_dir: str) -> str:
    """Return canonical path, running migration if needed, and refresh cache if file changed."""
    global _cached_path, _cached_mtime, _cached_ids
    path = _log_path(base_dir)
    _migrate_to_single_file(base_dir, path)

    try:
        mt = os.path.getmtime(path) if os.path.exists(path) else None
    except Exception:
        mt = None

    if _cached_path != path or _cached_mtime != mt:
        _cached_ids = _read_single_log(path)
        _cached_path = path
        _cached_mtime = mt

    return path


# --- Public API (signatures unchanged) ---

def load_index(base_dir: str) -> Dict[str, bool]:
    """Compatibility: return a dict view of all known IDs."""
    _ensure_cache(base_dir)
    return {k: True for k in _cached_ids}


def save_index(base_dir: str, index: Dict[str, bool]) -> None:
    """Compatibility: ensure all True entries are present in the log."""
    if not index:
        return
    global _cached_path, _cached_ids, _cached_mtime
    path = _ensure_cache(base_dir)
    to_add = [k for k, v in index.items() if v and k not in _cached_ids]
    for fid in to_add:
        _append_log(path, fid)
        _cached_ids.add(fid)
    if to_add:
        try:
            _cached_mtime = os.path.getmtime(path) if os.path.exists(path) else None
        except Exception:
            _cached_mtime = None


def mark_downloaded(base_dir: str, fax_id: str) -> None:
    if not fax_id:
        return
    s = str(fax_id).strip()
    if not s:
        return
    global _cached_ids, _cached_mtime
    path = _ensure_cache(base_dir)
    if s in _cached_ids:
        return
    _append_log(path, s)
    _cached_ids.add(s)
    try:
        _cached_mtime = os.path.getmtime(path) if os.path.exists(path) else None
    except Exception:
        _cached_mtime = None


def is_downloaded(base_dir: str, fax_id: str) -> bool:
    if not fax_id:
        return False
    s = str(fax_id).strip()
    if not s:
        return False
    _ensure_cache(base_dir)
    return s in _cached_ids


def remove_ids(base_dir: str, fax_ids) -> None:
    """Remove fax IDs from local history (pruning after SkySwitch deletion)."""
    if not fax_ids:
        return
    to_remove: Set[str] = set()
    for fid in fax_ids:
        s = (str(fid) or "").strip()
        if s:
            to_remove.add(s)
    if not to_remove:
        return

    global _cached_ids, _cached_mtime
    path = _ensure_cache(base_dir)

    before = len(_cached_ids)
    remaining = _cached_ids - to_remove
    if len(remaining) == before:
        return  # nothing to remove

    _rewrite_log(path, remaining)
    _cached_ids = remaining
    try:
        _cached_mtime = os.path.getmtime(path) if os.path.exists(path) else None
    except Exception:
        _cached_mtime = None
