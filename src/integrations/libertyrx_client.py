"""
LibertyRx client (Sprint 1 skeleton)

- Simple build-time env switch via module variable `env`.
- Base URL selection helper.
- Customer header encoder.
- Minimal send_fax with explicit timeouts and structured errors.

This module intentionally avoids UI/queueing. It follows the repo's patterns:
- typing annotations (Python 3.10+)
- requests with explicit timeouts
- structured error dicts instead of raising
- no logging of PHI or secrets
"""
from __future__ import annotations

import base64
import os
from typing import Any, Dict

from core.config_loader import global_config
from utils.logging_utils import get_logger
from utils.secure_store import secure_encrypt_for_machine

import requests

# Simple build-time switch (set before building)
# Set to "prod" for release builds; set to "dev" for development/testing builds.
env: str = "prod"  # or "prod"


def liberty_base_url() -> str:
    """Return the LibertyRx fax endpoint URL based on the build-time env.

    env == "prod" -> https://api.libertysoftware.com/fax
    otherwise      -> https://devapi.libertysoftware.com/fax
    """
    base = (
        "https://api.libertysoftware.com" if (env or "").lower() == "prod" else "https://devapi.libertysoftware.com"
    )
    return f"{base}/fax"


def encode_customer(npi: str, key: str) -> str:
    """Encode the Customer header value as base64 of "<NPI>:<KEY>".

    Both inputs are treated as strings; validation occurs in UI/config layers.
    Returns the ASCII base64 string.
    """
    s = f"{npi}:{key}"
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def fra_api_base_url() -> str:
        """FRA API base URL from env FRA_BASE_URL"""
        return (os.environ.get("FRA_BASE_URL") or "http://licensing.clinicnetworking.com:8000").rstrip("/")


def _auth_header(jwt_token: str) -> Dict[str, str]:
        return {"Authorization": f"Bearer {jwt_token}"}


def _fra_get_vendor_basic(jwt_token: str) -> Dict[str, Any]:
        url = f"{fra_api_base_url()}/integrations/libertyrx/vendor_basic.get"
        try:
            r = requests.get(url, headers=_auth_header(jwt_token), timeout=(10, 60))
        except requests.RequestException as e:
            return {"error": f"network_error:{e.__class__.__name__}", "details": str(e)}
        if r.status_code == 200:
            try:
                data = r.json() if r.content else {}
            except Exception:
                data = {}
            b64 = (data or {}).get("basic_b64") if isinstance(data, dict) else None
            if not b64:
                return {"error": "missing_basic_b64"}
            return {"ok": True, "basic_b64": b64}
        if r.status_code == 401:
            return {"error": "unauthorized", "status": 401}
        try:
            data = r.json()
            msg = (data or {}).get("detail") if isinstance(data, dict) else None
        except Exception:
            msg = None
        return {"error": msg or f"HTTP {r.status_code}", "status": r.status_code}


def _fra_enable(jwt_token: str) -> Dict[str, Any]:
        url = f"{fra_api_base_url()}/integrations/libertyrx/enable"
        try:
            r = requests.post(url, headers=_auth_header(jwt_token), timeout=(10, 10))
        except requests.RequestException as e:
            return {"error": f"network_error:{e.__class__.__name__}", "details": str(e)}
        if r.status_code == 200:
            try:
                data = r.json() if r.content else {}
            except Exception:
                data = {}
            new_jwt = (data or {}).get("jwt_token") if isinstance(data, dict) else None
            return {"ok": True, "jwt_token": new_jwt}
        try:
            data = r.json()
            msg = (data or {}).get("detail") if isinstance(data, dict) else None
        except Exception:
            msg = None
        return {"error": msg or f"HTTP {r.status_code}", "status": r.status_code}


def fetch_and_cache_vendor_basic(app_state) -> Dict[str, Any]:
        """Fetch LibertyRx vendor Basic header via FRA and cache it encrypted in global_config.

        Behavior:
        - Uses current JWT from config.
        - If 401, attempts to enable LibertyRx on FRA and upgrade JWT, then retries once.
        - On success, stores Integrations.liberty_vendor_basic_b64_enc (encrypted) and saves config.
        """
        log = get_logger("libertyrx_client")
        jwt_token = global_config.get("Token", "jwt_token", "") or ""
        if not jwt_token:
            log.warning("LibertyRx: cannot fetch vendor header — no JWT present")
            return {"error": "no_jwt"}

        log.info("LibertyRx: fetching vendor header from FRA…")
        res = _fra_get_vendor_basic(jwt_token)
        if res.get("ok"):
            try:
                enc = secure_encrypt_for_machine(res["basic_b64"])  # type: ignore[index]
                global_config.set("Integrations", "liberty_vendor_basic_b64_enc", enc)
                global_config.save()
                log.info("LibertyRx: vendor header retrieved and cached.")
            except Exception as e:
                log.error("LibertyRx: failed to persist vendor header", exc_info=True)
                return {"error": f"persist_failed:{e}"}
            return {"ok": True}

        if res.get("status") == 401 or res.get("error") == "unauthorized":
            log.info("LibertyRx: missing scope — requesting enablement at FRA…")
            en = _fra_enable(jwt_token)
            if not en.get("ok"):
                err = en.get('error') or en.get('status')
                log.warning(f"LibertyRx: enable failed — {err}")
                return {"error": f"enable_failed:{err}"}
            # If we got an upgraded JWT, persist it
            new_jwt = en.get("jwt_token")
            if new_jwt:
                try:
                    global_config.set("Token", "jwt_token", new_jwt)
                    global_config.save()
                    jwt_token = new_jwt
                    log.info("LibertyRx: JWT upgraded after enable.")
                except Exception:
                    log.warning("LibertyRx: failed to persist upgraded JWT")
            # Retry once
            log.info("LibertyRx: retrying vendor header fetch…")
            res2 = _fra_get_vendor_basic(jwt_token)
            if res2.get("ok"):
                try:
                    enc = secure_encrypt_for_machine(res2["basic_b64"])  # type: ignore[index]
                    global_config.set("Integrations", "liberty_vendor_basic_b64_enc", enc)
                    global_config.save()
                    log.info("LibertyRx: vendor header retrieved and cached (after enable).")
                except Exception as e:
                    log.error("LibertyRx: failed to persist vendor header (retry)", exc_info=True)
                    return {"error": f"persist_failed:{e}"}
                return {"ok": True}
            err2 = res2.get("error") or res2.get("status")
            log.warning(f"LibertyRx: vendor header fetch failed after enable — {err2}")
            return {"error": err2}

        # Propagate non-401 error
        errx = res.get("error") or res.get("status")
        log.warning(f"LibertyRx: vendor header fetch failed — {errx}")
        return {"error": errx}


def _digits_only(num: str) -> int:
    d = "".join(ch for ch in (num or "") if ch.isdigit())
    # Default to 0 if empty after stripping digits; server will 400 accordingly.
    return int(d or 0)


def send_fax(
    endpoint_url: str,
    vendor_basic_b64: str,
    customer_b64: str,
    from_number: str,
    pdf_bytes: bytes,
) -> Dict[str, Any]:
    """POST a fax PDF to LibertyRx.

    Parameters
    - endpoint_url: full URL to /fax endpoint (use liberty_base_url()).
    - vendor_basic_b64: base64( vendor_username:vendor_password ).
    - customer_b64: base64( NPI:APIKEY ).
    - from_number: caller ID / source fax number; normalized to digits-only int.
    - pdf_bytes: raw PDF bytes to be base64-encoded in the JSON body.

    Returns
    - {"ok": True} on HTTP 200.
    - {"error": str, "status": int} on non-200 responses.
    - {"error": str, "details": str} on network errors.

    Notes
    - Explicit timeouts are used; do not log headers or FileData outside this function.
    - This function performs no retries; caller should handle backoff/queueing.
    """
    log = get_logger("libertyrx_client")
    size_kb = int(len(pdf_bytes) / 1024) if pdf_bytes else 0
    from_d = _digits_only(from_number)
    try:
        log.info(f"LibertyRx: POST fax attempt size_kb={size_kb} from={from_d} -> {endpoint_url}")
    except Exception:
        pass

    headers = {
        "Authorization": f"Basic {vendor_basic_b64}",
        "Customer": customer_b64,
        "Content-Type": "application/json",
    }
    body = {
        "FromNumber": from_d,
        "ContentType": "application/pdf",
        "FileData": base64.b64encode(pdf_bytes).decode("ascii"),
    }
    try:
        resp = requests.post(endpoint_url, json=body, headers=headers, timeout=(10, 10))
    except requests.RequestException as e:  # network/timeout/connection errors
        try:
            log.warning(f"LibertyRx: network error during POST — {e.__class__.__name__}: {e}")
        except Exception:
            pass
        return {"error": f"network_error:{e.__class__.__name__}", "details": str(e)}

    if resp.status_code == 200:
        try:
            log.info("LibertyRx: POST fax succeeded (HTTP 200)")
        except Exception:
            pass
        return {"ok": True}

    # Try to parse JSON error payload with {"message": "..."}
    msg: str | None
    try:
        data = resp.json()
        msg = (data or {}).get("message") if isinstance(data, dict) else None
    except Exception:
        msg = None

    if not msg:
        # Fallback to text (truncated to reduce noise)
        try:
            msg = (resp.text or "").strip()[:200]
        except Exception:
            msg = None

    try:
        log.warning(f"LibertyRx: POST fax failed (HTTP {resp.status_code}) — {msg or 'no message'}")
    except Exception:
        pass

    return {"error": msg or f"HTTP {resp.status_code}", "status": resp.status_code}
