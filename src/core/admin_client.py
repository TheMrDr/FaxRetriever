# core/admin_client.py

import os
from platform import node
import requests
from typing import Dict, Any, List
from utils.logging_utils import get_logger
from core.config_loader import global_config

log = get_logger("admin_api")

# Base URL for FRA admin utility (adjust if configured elsewhere)
FRA_BASE_URL = os.environ.get("FRA_BASE_URL", "http://licensing.clinicnetworking.com:8000")
ASSIGNMENTS_LIST_URL = f"{FRA_BASE_URL}/assignments.list"
ASSIGNMENTS_REQUEST_URL = f"{FRA_BASE_URL}/assignments.request"
ASSIGNMENTS_UNREGISTER_URL = f"{FRA_BASE_URL}/assignments.unregister"


def _headers_with_jwt(jwt_token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {jwt_token}"}


def get_device_id() -> str:
    return os.environ.get("COMPUTERNAME") or node() or "UNKNOWN-DEVICE"


def list_assignments(jwt_token: str) -> Dict[str, Any]:
    """Call /assignments.list and return JSON or {error:...}."""
    try:
        resp = requests.post(ASSIGNMENTS_LIST_URL, headers=_headers_with_jwt(jwt_token), timeout=10)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            return {"error": detail or f"HTTP {resp.status_code}"}
        return resp.json()
    except Exception as e:
        log.exception("assignments.list failed")
        return {"error": str(e)}


def request_assignments(jwt_token: str, numbers: List[str], device_id: str | None = None) -> Dict[str, Any]:
    """Call /assignments.request for the given numbers."""
    try:
        payload = {"device_id": device_id or get_device_id(), "numbers": numbers}
        resp = requests.post(ASSIGNMENTS_REQUEST_URL, headers=_headers_with_jwt(jwt_token), json=payload, timeout=10)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            return {"error": detail or f"HTTP {resp.status_code}"}
        return resp.json()
    except Exception as e:
        log.exception("assignments.request failed")
        return {"error": str(e)}


def unregister_assignments(jwt_token: str, numbers: List[str] | None = None, device_id: str | None = None) -> Dict[str, Any]:
    """Call /assignments.unregister for optional list of numbers (or all if None)."""
    try:
        payload = {"device_id": device_id or get_device_id()}
        if numbers is not None:
            payload["numbers"] = numbers
        resp = requests.post(ASSIGNMENTS_UNREGISTER_URL, headers=_headers_with_jwt(jwt_token), json=payload, timeout=10)
        if resp.status_code != 200:
            try:
                detail = resp.json().get("detail")
            except Exception:
                detail = None
            return {"error": detail or f"HTTP {resp.status_code}"}
        return resp.json()
    except Exception as e:
        log.exception("assignments.unregister failed")
        return {"error": str(e)}
