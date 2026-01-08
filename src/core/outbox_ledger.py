"""
core/outbox_ledger.py

Lightweight persistent ledger for outbound fax jobs (Computer-Rx and manual sends).
Stores a JSON file under <base_dir>/shared/outbox_ledger.json with atomic writes.

Job statuses:
- queued: discovered but not yet attempted (or awaiting next eligible time)
- accepted: submitted to carrier (HTTP 2xx); awaiting delivery correlation
- delivered: carrier reports delivered
- failed_delivery: carrier reports failed/undelivered
- invalid_number: local validation rejected number
- quarantined: after N failed attempts, removed from BTR and parked for operator action
- delivery_unknown: timed out waiting for correlation

Each job should include at least:
- type: "crx" | "manual" (future)
- record_id: int (for crx)
- file: str (path to PDF)
- dest: str (E.164 digits only)
- caller: str (E.164 digits only)
- attempts: int
- status: str
- last_error: str | None
- accepted_at: ISO str | None
- next_eligible: ISO str | None
- client_ref: str (stable id for correlation)
- bytes: int (optional, total payload size)
- created_at: ISO str (first time we saw the job)
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

_LEDGER_FILENAME = "outbox_ledger.json"
_VERSION = 1


def _ledger_path(base_dir: str) -> str:
    return os.path.join(base_dir, "shared", _LEDGER_FILENAME)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse_iso(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        if "." in s:
            # allow fractional seconds
            return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def load(base_dir: str) -> Dict[str, Any]:
    path = _ledger_path(base_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("ledger root not a dict")
        if "jobs" not in data:
            data["jobs"] = {}
        if "version" not in data:
            data["version"] = _VERSION
        return data
    except Exception:
        return {"version": _VERSION, "jobs": {}}


def save(base_dir: str, data: Dict[str, Any]) -> None:
    path = _ledger_path(base_dir)
    try:
        _atomic_write_json(path, data)
    except Exception:
        # best-effort; do not raise to callers in production code
        pass


def sha1_of(*parts: str) -> str:
    h = hashlib.sha1()
    for p in parts:
        try:
            h.update((p or "").encode("utf-8", errors="ignore"))
        except Exception:
            pass
    return h.hexdigest()


def make_key_crx(record_id: int, file_name: str) -> str:
    base = os.path.basename(file_name or "")
    return f"crx:{record_id}:{sha1_of(base)}"


def make_key_manual(file_path: str, destination: str, session_idx: int | None = None) -> str:
    """
    Build a stable-ish key for manual sends based on file name, destination, and optional session index.
    We avoid including absolute path to allow portability; basename + dest is sufficient for correlation.
    """
    base = os.path.basename(file_path or "")
    dest_digits = "".join(ch for ch in (destination or "") if ch.isdigit())
    suffix = f":{int(session_idx)}" if session_idx is not None else ""
    return f"manual:{sha1_of(base, dest_digits)}{suffix}"


def get_job(base_dir: str, key: str) -> Dict[str, Any]:
    led = load(base_dir)
    job = led["jobs"].get(key) or {}
    return job


def upsert_job(base_dir: str, key: str, initializer: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    led = load(base_dir)
    jobs = led["jobs"]
    job = jobs.get(key)
    if not job:
        job = initializer.copy() if initializer else {}
        jobs[key] = job
        # First seen timestamp
        job.setdefault("created_at", _iso(_now_utc()))
        job.setdefault("attempts", 0)
        job.setdefault("status", "queued")
    save(base_dir, led)
    return job


_BACKOFF_SECONDS = [60, 300, 900]  # 1 min, 5 min, 15 min


def _schedule_next_eligible(attempts: int) -> datetime:
    idx = min(max(attempts - 1, 0), len(_BACKOFF_SECONDS) - 1)
    return _now_utc() + timedelta(seconds=_BACKOFF_SECONDS[idx])


def should_backoff(job: Dict[str, Any]) -> bool:
    ne = _parse_iso(job.get("next_eligible"))
    if not ne:
        return False
    return _now_utc() < ne


def record_failure(base_dir: str, key: str, last_error: str) -> Dict[str, Any]:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {"attempts": 0})
    job["attempts"] = int(job.get("attempts", 0)) + 1
    job["last_error"] = last_error
    job["status"] = job.get("status") or "queued"
    job["next_eligible"] = _iso(_schedule_next_eligible(job["attempts"]))
    save(base_dir, led)
    return job


def mark_quarantined(base_dir: str, key: str, reason: str | None = None) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {"attempts": 0})
    job["status"] = "quarantined"
    if reason:
        job["last_error"] = reason
    job.pop("next_eligible", None)
    save(base_dir, led)


def mark_invalid_number(base_dir: str, key: str, original: str) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {})
    job["status"] = "invalid_number"
    job["last_error"] = f"Invalid/ambiguous number: {original}"
    job["attempts"] = int(job.get("attempts", 0))
    job.pop("next_eligible", None)
    save(base_dir, led)


def mark_accepted(base_dir: str, key: str, dest: str, caller: str, bytes_total: int | None = None) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {})
    job["status"] = "accepted"
    job["dest"] = dest
    job["caller"] = caller
    job["accepted_at"] = _iso(_now_utc())
    if bytes_total is not None:
        job["bytes"] = int(bytes_total)
    job.pop("next_eligible", None)
    save(base_dir, led)


def update_metadata(base_dir: str, key: str, **fields: Any) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {})
    job.update({k: v for k, v in fields.items() if v is not None})
    save(base_dir, led)


def mark_delivered(base_dir: str, key: str) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {})
    job["status"] = "delivered"
    job.pop("next_eligible", None)
    save(base_dir, led)


def mark_failed_delivery(base_dir: str, key: str, reason: str | None = None) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {})
    job["status"] = "failed_delivery"
    if reason:
        job["last_error"] = reason
    save(base_dir, led)


def mark_delivery_unknown(base_dir: str, key: str) -> None:
    led = load(base_dir)
    job = led["jobs"].setdefault(key, {})
    job["status"] = "delivery_unknown"
    save(base_dir, led)


def all_jobs(base_dir: str) -> Dict[str, Any]:
    return load(base_dir).get("jobs", {})


def delete_job(base_dir: str, key: str) -> None:
    led = load(base_dir)
    try:
        if key in led.get("jobs", {}):
            del led["jobs"][key]
            save(base_dir, led)
    except Exception:
        pass


def prune_old(base_dir: str, max_age_days: int = 30) -> None:
    led = load(base_dir)
    cutoff = _now_utc() - timedelta(days=max_age_days)
    to_del = []
    for k, v in list(led.get("jobs", {}).items()):
        ca = _parse_iso(v.get("created_at"))
        if ca and ca < cutoff:
            to_del.append(k)
    for k in to_del:
        try:
            del led["jobs"][k]
        except Exception:
            pass
    if to_del:
        save(base_dir, led)
