import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

# Simple, durable JSONL ledger for Computer-Rx outbound submissions
# File location: %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\history\crx_outbound_ledger.log

_lock = threading.RLock()


def _safe_localappdata_dir() -> str:
    lad = os.getenv("LOCALAPPDATA")
    if lad and os.path.isdir(lad):
        return lad
    home = os.path.expanduser("~")
    fallback = os.path.join(home, "AppData", "Local")
    return fallback if os.path.isdir(fallback) else (lad or fallback)


def ledger_path() -> str:
    try:
        lad = _safe_localappdata_dir()
        d = os.path.join(lad, "Clinic Networking, LLC", "FaxRetriever", "2.0", "history")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "crx_outbound_ledger.log")
    except Exception:
        # fallback to repo cache folder
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        cache_dir = os.path.join(base, "cache")
        try:
            os.makedirs(cache_dir, exist_ok=True)
        except Exception:
            pass
        return os.path.join(cache_dir, "crx_outbound_ledger.log")


def _fsync_file(f):
    try:
        f.flush()
        os.fsync(f.fileno())
    except Exception:
        try:
            f.flush()
        except Exception:
            pass


def _now_iso() -> str:
    try:
        return datetime.now(timezone.utc).isoformat()
    except Exception:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha1_file(path: str) -> Optional[str]:
    try:
        h = hashlib.sha1()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def append_entry(entry: Dict[str, Any]) -> None:
    """Append a single JSON object as one line with durability."""
    p = ledger_path()
    line = json.dumps(entry, ensure_ascii=False)
    with _lock:
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            _fsync_file(f)


def new_pending(
    record_id: int,
    dest_e164: str,
    caller_id: str,
    file_path: str,
    attempt_no: int,
    size_bytes: Optional[int] = None,
    pages_estimate: Optional[int] = None,
    file_hash: Optional[str] = None,
    submit_time_iso: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    entry = {
        "type": "crx_outbound",
        "state": "pending",
        "record_id": record_id,
        "dest_e164": dest_e164,
        "caller_id": caller_id,
        "file_path": file_path,
        "attempt_no": attempt_no,
        "failure_count": 0,
        "size_bytes": size_bytes,
        "pages_estimate": pages_estimate,
        "file_hash": file_hash,
        "submit_time": submit_time_iso or _now_iso(),
        "last_update": _now_iso(),
    }
    if extra:
        entry.update(extra)
    append_entry(entry)
    return entry


def load_entries() -> List[Dict[str, Any]]:
    p = ledger_path()
    out: List[Dict[str, Any]] = []
    if not os.path.exists(p):
        return out
    with _lock:
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    s = (line or "").strip()
                    if not s:
                        continue
                    try:
                        obj = json.loads(s)
                        out.append(obj)
                    except Exception:
                        continue
        except Exception:
            return out
    return out


def iter_latest_by_record() -> Iterable[Dict[str, Any]]:
    """Return the latest state per (record_id, attempt_no)."""
    all_entries = load_entries()
    latest: Dict[tuple, Dict[str, Any]] = {}
    for e in all_entries:
        if not isinstance(e, dict):
            continue
        rid = e.get("record_id")
        attempt = e.get("attempt_no")
        key = (rid, attempt)
        prev = latest.get(key)
        if not prev:
            latest[key] = e
        else:
            # choose the one with newer last_update/submit_time
            t_prev = prev.get("last_update") or prev.get("submit_time") or ""
            t_cur = e.get("last_update") or e.get("submit_time") or ""
            if t_cur > t_prev:
                latest[key] = e
    # collapse to only the latest attempt per record
    per_record: Dict[Any, Dict[str, Any]] = {}
    for (rid, attempt), e in latest.items():
        prev = per_record.get(rid)
        if not prev or (attempt or 0) > (prev.get("attempt_no") or 0):
            per_record[rid] = e
    return per_record.values()


def load_pending() -> List[Dict[str, Any]]:
    return [e for e in iter_latest_by_record() if e.get("state") == "pending"]


def update_state(record_id: int, attempt_no: int, new_state: str, **kwargs) -> None:
    """Append a state update line for a ledger item."""
    e = {
        "type": "crx_outbound_update",
        "record_id": record_id,
        "attempt_no": attempt_no,
        "state": new_state,
        "last_update": _now_iso(),
    }
    e.update(kwargs or {})
    append_entry(e)

