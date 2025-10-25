from __future__ import annotations

import random
import time
from typing import Any, Dict, List, Tuple

import requests

from integrations.libertyrx_client import fra_api_base_url
from utils.logging_utils import get_logger
from core.license_client import initialize_session
from core.app_state import app_state

log = get_logger("sync_client")

MAX_PAGE = 500
TIMEOUTS = (10, 30)  # (connect, read)


def _auth_header(jwt_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}"}


def _jwt() -> str | None:
    return getattr(app_state.global_cfg, "jwt_token", None)


def _refresh_jwt() -> bool:
    try:
        domain = app_state.global_cfg.fax_user
        token = getattr(app_state.global_cfg, "authentication_token", None)
        if not domain or not token:
            log.warning("Cannot refresh JWT: missing domain or authentication_token in config")
            return False
        res = initialize_session(app_state, domain, token, mode=app_state.device_cfg.retriever_mode or "sender")
        if res.get("error"):
            log.error(f"JWT refresh failed: {res.get('error')}")
            return False
        return True
    except Exception:
        log.exception("JWT refresh crashed")
        return False


def _backoff_sleep(attempt: int) -> None:
    # Exponential backoff with jitter: base 0.5s, cap 8s
    base = min(8.0, 0.5 * (2 ** attempt))
    time.sleep(base * (0.5 + random.random()))


def post_ids(ids: List[str]) -> Dict[str, Any]:
    if not ids:
        return {"ok": True, "inserted": 0, "total": 0}
    url = f"{fra_api_base_url()}/sync/post"
    payload = {"ids": list(dict.fromkeys([str(x).strip() for x in ids if str(x).strip()]))}
    if not payload["ids"]:
        return {"ok": True, "inserted": 0, "total": 0}

    attempts = 0
    while attempts < 5:
        attempts += 1
        jwt = _jwt()
        if not jwt:
            if not _refresh_jwt():
                return {"error": "jwt_missing"}
            jwt = _jwt()
            if not jwt:
                return {"error": "jwt_missing"}
        try:
            r = requests.post(url, headers=_auth_header(jwt), json=payload, timeout=TIMEOUTS)
        except requests.RequestException as e:
            log.warning(f"/sync/post network error: {e}")
            _backoff_sleep(attempts)
            continue
        if r.status_code == 200:
            try:
                return r.json() or {"ok": True}
            except Exception:
                return {"ok": True}
        if r.status_code in (401, 403):
            if _refresh_jwt():
                continue
            return {"error": "unauthorized", "status": r.status_code}
        if 500 <= r.status_code < 600:
            _backoff_sleep(attempts)
            continue
        try:
            data = r.json()
            msg = (data or {}).get("detail") if isinstance(data, dict) else None
        except Exception:
            msg = None
        return {"error": msg or f"HTTP {r.status_code}", "status": r.status_code}
    return {"error": "retry_exhausted"}


def list_page(offset: int = 0, limit: int = MAX_PAGE) -> Tuple[List[str], int | None, int]:
    url = f"{fra_api_base_url()}/sync/list"
    payload = {"offset": max(0, int(offset or 0)), "limit": min(MAX_PAGE, max(1, int(limit or MAX_PAGE)))}

    attempts = 0
    while attempts < 5:
        attempts += 1
        jwt = _jwt()
        if not jwt:
            if not _refresh_jwt():
                return [], None, 0
            jwt = _jwt()
            if not jwt:
                return [], None, 0
        try:
            r = requests.post(url, headers=_auth_header(jwt), json=payload, timeout=TIMEOUTS)
        except requests.RequestException as e:
            log.warning(f"/sync/list network error: {e}")
            _backoff_sleep(attempts)
            continue
        if r.status_code == 200:
            try:
                data = r.json() or {}
            except Exception:
                data = {}
            ids = list((data or {}).get("ids") or [])
            next_offset = (data or {}).get("next_offset")
            total = int((data or {}).get("total") or 0)
            return ids, next_offset, total
        if r.status_code in (401, 403):
            if _refresh_jwt():
                continue
            return [], None, 0
        if 500 <= r.status_code < 600:
            _backoff_sleep(attempts)
            continue
        return [], None, 0
    return [], None, 0
