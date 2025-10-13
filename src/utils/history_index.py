import os
from typing import Dict, Tuple

# In-memory cache to reduce file reads (combined across both locations)
_cached_paths: Tuple[str | None, str | None] = (None, None)
_cached_mtimes: Tuple[float | None, float | None] = (None, None)
_cached_ids: set[str] = set()


def _safe_localappdata_dir() -> str:
    """Resolve a writable per-user LocalAppData directory safely (Windows-oriented)."""
    lad = os.getenv("LOCALAPPDATA")
    if lad and os.path.isdir(lad):
        return lad
    # Fallback: construct from user profile if env var missing
    home = os.path.expanduser("~")
    fallback = os.path.join(home, "AppData", "Local")
    return fallback if os.path.isdir(fallback) else (lad or fallback)


def _log_paths(base_dir: str) -> Tuple[str, str]:
    """
    Resolve two stable paths for the immutable downloaded fax ID log:
    - Global/shared path: <base_dir>\shared\history\downloaded_faxes.log
    - Per-user writable clone: %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\history\downloaded_faxes.log
    We will read from both and write to both when possible.
    """
    # Global/shared
    try:
        shared_dir = os.path.join(base_dir, "shared", "history")
        os.makedirs(shared_dir, exist_ok=True)
        shared_path = os.path.join(shared_dir, "downloaded_faxes.log")
    except Exception:
        shared_path = os.path.join(base_dir, "downloaded_faxes.log")

    # LocalAppData (per-user, expected to be writable)
    try:
        lad = _safe_localappdata_dir()
        local_dir = os.path.join(
            lad,
            "Clinic Networking, LLC",
            "FaxRetriever",
            "2.0",
            "history",
        )
        os.makedirs(local_dir, exist_ok=True)
        local_path = os.path.join(local_dir, "downloaded_faxes.log")
    except Exception:
        # Last resort: drop under base_dir/cache (still better than temp)
        try:
            local_dir = os.path.join(base_dir, "cache")
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, "downloaded_faxes.log")
        except Exception:
            local_path = os.path.join(base_dir, "downloaded_faxes.log")

    return (shared_path, local_path)


def _legacy_json_candidates(base_dir: str) -> list[str]:
    """Return possible legacy JSON index paths to migrate from."""
    cands: list[str] = []
    try:
        # Prior stable target under log/
        cands.append(os.path.join(base_dir, "log", "downloaded_index.json"))
        # Logging utils configured paths
        try:
            from utils.logging_utils import LOG_DIR, LOG_FILE  # type: ignore

            if isinstance(LOG_FILE, str) and LOG_FILE:
                cands.append(os.path.join(os.path.dirname(LOG_FILE), "downloaded_index.json"))
            if isinstance(LOG_DIR, str) and LOG_DIR:
                cands.append(os.path.join(LOG_DIR, "downloaded_index.json"))
        except Exception:
            pass
        # cache/ and base root fallbacks
        cands.append(os.path.join(base_dir, "cache", "downloaded_index.json"))
        cands.append(os.path.join(base_dir, "downloaded_index.json"))
    except Exception:
        pass
    # Deduplicate while preserving order
    seen = set()
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
                    if not s:
                        continue
                    ids.add(s)
    except Exception:
        pass
    return ids


def _read_logs(paths: Tuple[str, str]) -> set[str]:
    a, b = paths
    ids = set()
    ids.update(_read_single_log(a))
    if b != a:
        ids.update(_read_single_log(b))
    return ids


def _append_log(path: str, fax_id: str) -> bool:
    """Append to a single path. Returns True on success, False otherwise."""
    # Ensure directory exists
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


def _append_both(paths: Tuple[str, str], fax_id: str) -> None:
    """Attempt to append to both paths; at least one must succeed."""
    a, b = paths
    ok1 = _append_log(a, fax_id)
    ok2 = _append_log(b, fax_id) if b != a else ok1
    # If both failed, we silently ignore to avoid crashing UI; cache will still reflect the intended state.


def _migrate_legacy_to_logs(base_dir: str, paths: Tuple[str, str]) -> None:
    """Migrate IDs from any legacy JSON index into both append-only logs once."""
    try:
        existing = _read_logs(paths)
        candidates = _legacy_json_candidates(base_dir)
        migrated_any = False
        for p in candidates:
            try:
                if not os.path.exists(p):
                    continue
                import json as _json
                with open(p, "r", encoding="utf-8") as f:
                    data = _json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if v and isinstance(k, str) and k not in existing:
                            _append_both(paths, k)
                            existing.add(k)
                            migrated_any = True
            except Exception:
                continue
        # Also ensure the two logs are mutually synced (clone missing IDs between them)
        a_ids = _read_single_log(paths[0])
        b_ids = _read_single_log(paths[1]) if paths[1] != paths[0] else a_ids
        for k in a_ids - b_ids:
            _append_log(paths[1], k)
            migrated_any = True
        for k in b_ids - a_ids:
            _append_log(paths[0], k)
            migrated_any = True

        if migrated_any:
            global _cached_paths, _cached_ids, _cached_mtimes
            _cached_paths = paths
            _cached_ids = existing
            try:
                mt_a = os.path.getmtime(paths[0]) if os.path.exists(paths[0]) else None
            except Exception:
                mt_a = None
            try:
                mt_b = os.path.getmtime(paths[1]) if os.path.exists(paths[1]) else None
            except Exception:
                mt_b = None
            _cached_mtimes = (mt_a, mt_b)
    except Exception:
        pass


def load_index(base_dir: str) -> Dict[str, bool]:
    """Compatibility: return a dict view of the combined logs (True for seen IDs)."""
    paths = _log_paths(base_dir)
    _migrate_legacy_to_logs(base_dir, paths)
    ids = _read_logs(paths)
    return {k: True for k in ids}


def save_index(base_dir: str, index: Dict[str, bool]) -> None:
    """Compatibility: ensure all True entries are present in both logs."""
    if not index:
        return
    paths = _log_paths(base_dir)
    _migrate_legacy_to_logs(base_dir, paths)
    existing = _read_logs(paths)
    for k, v in index.items():
        if v and k not in existing:
            _append_both(paths, k)
            existing.add(k)
    # refresh cache
    global _cached_paths, _cached_ids, _cached_mtimes
    _cached_paths = paths
    _cached_ids = existing
    try:
        mt_a = os.path.getmtime(paths[0]) if os.path.exists(paths[0]) else None
    except Exception:
        mt_a = None
    try:
        mt_b = os.path.getmtime(paths[1]) if os.path.exists(paths[1]) else None
    except Exception:
        mt_b = None
    _cached_mtimes = (mt_a, mt_b)


def mark_downloaded(base_dir: str, fax_id: str) -> None:
    if not fax_id:
        return
    s = str(fax_id).strip()
    if not s:
        return
    paths = _log_paths(base_dir)
    _migrate_legacy_to_logs(base_dir, paths)

    # Use cache to avoid duplicate writes when possible
    global _cached_paths, _cached_mtimes, _cached_ids
    try:
        mt_a = os.path.getmtime(paths[0]) if os.path.exists(paths[0]) else None
    except Exception:
        mt_a = None
    try:
        mt_b = os.path.getmtime(paths[1]) if os.path.exists(paths[1]) else None
    except Exception:
        mt_b = None

    if _cached_paths != paths or _cached_mtimes != (mt_a, mt_b):
        _cached_ids = _read_logs(paths)
        _cached_paths = paths
        _cached_mtimes = (mt_a, mt_b)

    if s in _cached_ids:
        return

    _append_both(paths, s)
    # Update cache optimistically
    _cached_ids.add(s)
    try:
        mt_a = os.path.getmtime(paths[0]) if os.path.exists(paths[0]) else None
    except Exception:
        mt_a = None
    try:
        mt_b = os.path.getmtime(paths[1]) if os.path.exists(paths[1]) else None
    except Exception:
        mt_b = None
    _cached_mtimes = (mt_a, mt_b)


def is_downloaded(base_dir: str, fax_id: str) -> bool:
    if not fax_id:
        return False
    s = str(fax_id).strip()
    if not s:
        return False
    paths = _log_paths(base_dir)
    _migrate_legacy_to_logs(base_dir, paths)

    global _cached_paths, _cached_mtimes, _cached_ids
    try:
        mt_a = os.path.getmtime(paths[0]) if os.path.exists(paths[0]) else None
    except Exception:
        mt_a = None
    try:
        mt_b = os.path.getmtime(paths[1]) if os.path.exists(paths[1]) else None
    except Exception:
        mt_b = None

    if _cached_paths != paths or _cached_mtimes != (mt_a, mt_b):
        _cached_ids = _read_logs(paths)
        _cached_paths = paths
        _cached_mtimes = (mt_a, mt_b)

    return s in _cached_ids
