"""
LibertyRx delivery queue and backoff (Sprint 8)

Purpose
- Persist a lightweight queue of LibertyRx handoff jobs so failures can be retried
  with exponential backoff and survive app restarts.
- Provide a processing routine that can be invoked periodically (e.g., at the end
  of each receiver polling cycle) to attempt due jobs.
- Enforce a 401 gate: if Liberty returns 401 (bad vendor/customer auth), pause
  all Liberty retries until credentials are refreshed (e.g., next bearer refresh).

Storage
- Queue directory: %LOCALAPPDATA%\Clinic Networking, LLC\FaxRetriever\2.0\libertyrx_queue
- Each job is a JSON file: {id}.json with fields listed below.
- The PDF bytes are stored DPAPI-encrypted as base64 in the JSON file under
  key "pdf_enc"; decrypted only at processing time.

Job schema (JSON)
- id: str (unique)
- fax_id: str
- from_number: str
- created_at: ISO str
- updated_at: ISO str
- attempts: int
- next_attempt_at: ISO str
- status: str (queued|retry|final_error)
- last_error: Optional[str]
- endpoint_url: str (the target URL used when first enqueued; usually liberty_base_url())
- pdf_enc: str (DPAPI-protected base64 of the PDF bytes)

Notes
- Secrets (NPI/API key/vendor basic) are NOT stored in the queue. They are read
  from the existing config at processing time so rotations take effect.
- Logging MUST avoid PHI and secrets.
"""
from __future__ import annotations

import base64
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from core.config_loader import device_config, global_config
from integrations.libertyrx_client import encode_customer, liberty_base_url, send_fax
from utils.logging_utils import get_logger
from utils.pdf_utils import split_pdf_pages
from utils.secure_store import secure_decrypt_for_machine, secure_encrypt_for_machine

log = get_logger("libertyrx.queue")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def queue_dir() -> str:
    base = os.environ.get("LOCALAPPDATA") or os.getcwd()
    d = os.path.join(base, "Clinic Networking, LLC", "FaxRetriever", "2.0", "libertyrx_queue")
    os.makedirs(d, exist_ok=True)
    return d


def _job_path(job_id: str) -> str:
    return os.path.join(queue_dir(), f"{job_id}.json")


BACKOFF_STEPS = [60, 300, 900, 3600, 14400, 43200]  # seconds: 1m,5m,15m,1h,4h,12h


def next_backoff_secs(attempt: int) -> int:
    """Return backoff seconds for the given attempt number (1-based) with jitter.

    For attempt <= len(BACKOFF_STEPS) use the step, else repeat the last step.
    Apply +/-10% jitter to avoid thundering herds.
    """
    if attempt <= 0:
        attempt = 1
    base = BACKOFF_STEPS[min(attempt - 1, len(BACKOFF_STEPS) - 1)]
    jitter = 0.1 * base
    return int(base + random.uniform(-jitter, jitter))


def _read_job(path: str) -> Optional[Dict[str, Any]]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_all_jobs() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for name in os.listdir(queue_dir()):
        if not name.lower().endswith(".json"):
            continue
        job = _read_job(os.path.join(queue_dir(), name))
        if job and isinstance(job, dict):
            out.append(job)
    return out


def save_job(job: Dict[str, Any]) -> None:
    try:
        job["updated_at"] = _now_iso()
        with open(_job_path(job["id"]), "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2)
    except Exception:
        try:
            log.debug("Failed to save Liberty queue job", exc_info=True)
        except Exception:
            pass


def delete_job(job_id: str) -> None:
    try:
        p = _job_path(job_id)
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        try:
            log.debug("Failed to delete Liberty queue job", exc_info=True)
        except Exception:
            pass


def enqueue(fax_id: str, from_number: str, pdf_bytes: bytes, endpoint_url: Optional[str] = None, source_file: Optional[str] = None) -> str:
    """Create a queued job for Liberty delivery with encrypted PDF content.

    Returns the job id.
    """
    try:
        enc = secure_encrypt_for_machine(base64.b64encode(pdf_bytes).decode("ascii"))
    except Exception:
        # As a last resort, avoid enqueueing plaintext – drop the job if we cannot protect it.
        try:
            log.warning("Liberty queue: failed to encrypt PDF for retry; job not enqueued.")
        except Exception:
            pass
        return ""

    job_id = f"{fax_id}-{int(time.time())}"
    job = {
        "id": job_id,
        "fax_id": str(fax_id),
        "from_number": str(from_number or ""),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "attempts": 0,
        "next_attempt_at": _now_iso(),
        "status": "queued",
        "last_error": None,
        "endpoint_url": (endpoint_url or liberty_base_url()),
        "pdf_enc": enc,
    }
    if source_file:
        job["source_file"] = os.path.abspath(source_file)
    save_job(job)
    try:
        log.info(f"Liberty queue: enqueued fax {fax_id} for retry")
    except Exception:
        pass
    return job_id


def _is_due(job: Dict[str, Any], now: Optional[datetime] = None) -> bool:
    now = now or _now()
    try:
        nxt = job.get("next_attempt_at") or ""
        dt = datetime.fromisoformat(nxt)
        return dt <= now
    except Exception:
        return True


def _set_next_attempt(job: Dict[str, Any], reason_status: str) -> None:
    job["attempts"] = int(job.get("attempts", 0) or 0) + 1
    secs = next_backoff_secs(job["attempts"]) if reason_status != "401_gate" else 7200
    job["next_attempt_at"] = (_now() + timedelta(seconds=secs)).isoformat()
    job["status"] = "retry"


def _set_final_error(job: Dict[str, Any], code: str) -> None:
    job["status"] = "final_error"
    # Do not schedule further retries
    job["next_attempt_at"] = ("1970-01-01T00:00:00+00:00")
    job["last_error"] = code


def _liberty_gate_active() -> bool:
    try:
        gate = global_config.get("Integrations", "liberty_retry_gate_401", {}) or {}
        return bool((gate.get("active") or False))
    except Exception:
        return False


def _activate_401_gate():
    try:
        global_config.set(
            "Integrations",
            "liberty_retry_gate_401",
            {"active": True, "since": _now_iso()},
        )
        global_config.save()
    except Exception:
        pass


def clear_401_gate():
    try:
        global_config.set(
            "Integrations",
            "liberty_retry_gate_401",
            {"active": False, "since": None, "cleared_at": _now_iso()},
        )
        global_config.save()
    except Exception:
        pass


def _default_from_number() -> str:
    """Resolve a default FromNumber for Liberty posts.

    Prefers device_config Account.selected_fax_number, then Account.selected_fax_numbers[0],
    then global_config Account.all_fax_numbers[0]. Returns digits-only string or empty.
    """
    try:
        sel = device_config.get("Account", "selected_fax_number", "") or ""
        if not sel:
            arr = device_config.get("Account", "selected_fax_numbers", []) or []
            sel = (arr[0] if arr else "")
        if not sel:
            arr2 = global_config.get("Account", "all_fax_numbers", []) or []
            sel = (arr2[0] if arr2 else "")
        # Strip to digits
        digits = "".join(ch for ch in str(sel) if ch.isdigit())
        return digits
    except Exception:
        return ""


def _parse_from_number_from_stem(stem: str) -> str | None:
    """Attempt to parse caller ID (11 digits) from a dropped PDF file name stem.

    Accepts stems matching one of the following formats:
    - CID-DDMM-HHMM
    - CID-DDMMYY-HHMMSS

    Where CID is exactly 11 digits. If the stem does not match these patterns,
    returns None so the caller can fall back to the configured default.
    """
    try:
        s = (stem or "").strip()
        import re
        m = re.match(r"^(\d{11})-(\d{4,6})-(\d{4,6})$", s)
        if not m:
            return None
        return m.group(1)
    except Exception:
        return None


def _ingest_dropped_pdfs() -> None:
    """Create queue jobs for any bare PDF files dropped into queue_dir().

    - Skips files that already have an associated job (matching source_file).
    - Does not delete PDFs here; deletion occurs after successful delivery.
    """
    try:
        qd = queue_dir()
        # Build set of existing source files to avoid duplicate jobs
        existing_sources: set[str] = set()
        try:
            for j in load_all_jobs():
                p = j.get("source_file")
                if p:
                    existing_sources.add(os.path.abspath(p).lower())
        except Exception:
            pass
        for name in os.listdir(qd):
            if not name.lower().endswith(".pdf"):
                continue
            p = os.path.abspath(os.path.join(qd, name))
            if p.lower() in existing_sources:
                continue
            # Try read bytes
            try:
                with open(p, "rb") as f:
                    data = f.read()
            except Exception as e:
                try:
                    log.warning(f"Liberty queue: failed to read dropped PDF '{name}': {e}")
                except Exception:
                    pass
                continue
            if not data:
                try:
                    log.warning(f"Liberty queue: dropped PDF '{name}' is empty; skipping")
                except Exception:
                    pass
                continue
            stem = os.path.splitext(name)[0]
            cid = _parse_from_number_from_stem(stem)
            if cid:
                from_num = cid
                _src = "filename"
            else:
                from_num = _default_from_number()
                _src = "default"
            job_id = enqueue(f"drop-{stem}", from_num, data, source_file=p)
            if job_id:
                try:
                    log.info(f"Liberty queue: ingested dropped PDF '{name}' as job {job_id} (from_source={_src})")
                except Exception:
                    pass
    except Exception:
        try:
            log.debug("Liberty queue: ingest dropped PDFs failed", exc_info=True)
        except Exception:
            pass


def process_due_jobs(max_jobs: int = 5) -> None:
    """Process due Liberty jobs. Safe to call periodically.

    - Imports any manually dropped PDFs in the queue folder as jobs.
    - Respects 401 gate: if active, returns without processing any jobs.
    - Processes up to max_jobs that are due by next_attempt_at.
    - Uses current NPI/API key and vendor header from config (supports rotation).
    """
    try:
        # First, ingest any manually dropped PDFs
        _ingest_dropped_pdfs()
        if _liberty_gate_active():
            return
        jobs = [j for j in load_all_jobs() if _is_due(j)]
        # Sort by next_attempt_at (oldest first)
        try:
            jobs.sort(key=lambda j: j.get("next_attempt_at") or "")
        except Exception:
            pass
        count = 0
        for job in jobs:
            if count >= max_jobs:
                break
            _process_one(job)
            count += 1
    except Exception:
        try:
            log.debug("Liberty queue processing failed", exc_info=True)
        except Exception:
            pass


def _process_one(job: Dict[str, Any]) -> None:
    job_id = job.get("id")
    fax_id = job.get("fax_id")
    # Resolve credentials on demand
    npi = (device_config.get("Integrations", "liberty_npi", "") or "").strip()
    api_key_enc = device_config.get("Integrations", "liberty_api_key_enc", "") or ""
    vendor_b64_enc = global_config.get("Integrations", "liberty_vendor_basic_b64_enc", "") or ""

    if not (npi and api_key_enc and vendor_b64_enc):
        # Missing secrets; reschedule in 1 hour
        _set_next_attempt(job, reason_status="secrets_missing")
        save_job(job)
        return

    try:
        api_key = secure_decrypt_for_machine(api_key_enc) or ""
        vendor_basic = secure_decrypt_for_machine(vendor_b64_enc) or ""
    except Exception:
        api_key = ""
        vendor_basic = ""
    if not api_key or not vendor_basic:
        _set_next_attempt(job, reason_status="secrets_missing")
        save_job(job)
        return

    # Decrypt PDF
    try:
        b64 = secure_decrypt_for_machine(job.get("pdf_enc") or "") or ""
        pdf_bytes = base64.b64decode(b64) if b64 else b""
    except Exception:
        pdf_bytes = b""
    if not pdf_bytes:
        # Can't recover payload – mark final error to avoid infinite loop
        _set_final_error(job, code="payload_missing")
        save_job(job)
        return

    endpoint = liberty_base_url()  # prefer current build endpoint
    customer_b64 = encode_customer(npi, api_key)
    res = send_fax(endpoint, vendor_basic, customer_b64, job.get("from_number") or "", pdf_bytes)

    if res.get("ok"):
        # Success: remove job and any source drop-file if present
        delete_job(job_id)
        try:
            src = job.get("source_file")
            if src and os.path.exists(src):
                os.remove(src)
                try:
                    log.info(f"Liberty queue: removed dropped file after success: {os.path.basename(src)}")
                except Exception:
                    pass
        except Exception:
            try:
                log.debug("Liberty queue: failed to remove source drop-file after success", exc_info=True)
            except Exception:
                pass
        try:
            log.info(f"Liberty queue: delivered fax {fax_id} from queue")
        except Exception:
            pass
        return

    status = int(res.get("status") or 0)
    # Handle 413 with per-page split
    if status == 413:
        parts = split_pdf_pages(pdf_bytes)
        if parts:
            all_ok = True
            for idx, part in enumerate(parts, start=1):
                r2 = send_fax(endpoint, vendor_basic, customer_b64, job.get("from_number") or "", part)
                if not r2.get("ok"):
                    all_ok = False
                    status = int(r2.get("status") or 0)
                    break
            if all_ok:
                delete_job(job_id)
                # Remove original dropped file if present
                try:
                    src = job.get("source_file")
                    if src and os.path.exists(src):
                        os.remove(src)
                        try:
                            log.info(f"Liberty queue: removed dropped file after split-success: {os.path.basename(src)}")
                        except Exception:
                            pass
                except Exception:
                    try:
                        log.debug("Liberty queue: failed to remove source drop-file after split-success", exc_info=True)
                    except Exception:
                        pass
                try:
                    log.info(f"Liberty queue: delivered fax {fax_id} in {len(parts)} parts")
                except Exception:
                    pass
                return
        # If split failed, fall through to error handling using last status

    if status == 400:
        # Do not retry
        _set_final_error(job, code="400")
        save_job(job)
        try:
            log.warning(f"Liberty queue: permanent failure 400 for fax {fax_id}")
        except Exception:
            pass
        return
    if status == 401:
        # Activate gate and push out retries
        _activate_401_gate()
        _set_next_attempt(job, reason_status="401_gate")
        save_job(job)
        try:
            log.warning("Liberty queue: received 401; activating retry gate until credentials refresh")
        except Exception:
            pass
        return

    # 429 or 5xx or unknown: back off
    _set_next_attempt(job, reason_status=str(status or "transient"))
    save_job(job)
    try:
        log.info(f"Liberty queue: transient failure (status {status}); scheduled retry for fax {fax_id}")
    except Exception:
        pass
