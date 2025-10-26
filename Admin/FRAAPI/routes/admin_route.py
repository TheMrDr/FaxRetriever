# Admin/licensing_server/routes/admin_route.py
# Admin-only API endpoints for FRA GUI. These endpoints proxy MongoDB operations so the GUI never
# accesses Mongo directly.
#
# Security: If environment variable ADMIN_API_KEY is set, requests must include header X-Admin-Key
# with its exact value. If ADMIN_API_KEY is not set, endpoints are open (development mode only).

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from auth.crypto_utils import decrypt_blob
from db.mongo_interface import resellers  # Collection for list/delete
from db.mongo_interface import (delete_client, get_all_clients,
                                get_cached_bearer, get_fax_numbers,
                                get_known_devices, get_reseller_blob,
                                save_fax_user, save_reseller_blob,
                                toggle_client_active,
                                update_client_retriever_assignment)
from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.status import (HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED,
                              HTTP_404_NOT_FOUND)

router = APIRouter()


def _admin_key() -> Optional[str]:
    # Prefer env var; could be extended to read from config.py if desired.
    return os.environ.get("ADMIN_API_KEY")


def require_admin(request: Request):
    key = _admin_key()
    if not key:
        return  # dev mode: allow
    provided = request.headers.get("X-Admin-Key")
    if not provided or provided != key:
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED, detail="Admin authentication required"
        )


# -------- Clients --------


@router.get("/clients", dependencies=[Depends(require_admin)])
def list_clients() -> List[Dict[str, Any]]:
    """
    Returns all clients with fields needed by the GUI.
    """
    docs = []
    for d in get_all_clients():
        docs.append(
            {
                "fax_user": d.get("fax_user"),
                "authentication_token": d.get("authentication_token"),
                "domain_uuid": d.get("domain_uuid"),
                "active": d.get("active", False),
                "all_fax_numbers": d.get("all_fax_numbers", []),
                "retriever_assignments": d.get("retriever_assignments", {}),
            }
        )
    return docs


@router.get("/clients/full", dependencies=[Depends(require_admin)])
def list_clients_full() -> List[Dict[str, Any]]:
    """
    Returns all clients plus aggregated auxiliary data needed for a full refresh
    in a single call, to avoid N+1 requests from the GUI.
    """
    out: List[Dict[str, Any]] = []
    for d in get_all_clients():
        fax_user = d.get("fax_user")
        domain_uuid = d.get("domain_uuid")
        devices = get_known_devices(domain_uuid) or []
        bearer = get_cached_bearer(fax_user) or {}
        out.append(
            {
                "fax_user": fax_user,
                "authentication_token": d.get("authentication_token"),
                "domain_uuid": domain_uuid,
                "active": d.get("active", False),
                "all_fax_numbers": d.get("all_fax_numbers", []),
                "retriever_assignments": d.get("retriever_assignments", {}),
                # Aggregated extras
                "known_devices": devices,
                "bearer_expires_at": bearer.get("expires_at"),
            }
        )
    return out


@router.post("/clients", dependencies=[Depends(require_admin)])
def create_or_update_client(payload: Dict[str, Any]) -> Dict[str, Any]:
    domain = (payload.get("fax_user") or "").strip().lower()
    token = (payload.get("authentication_token") or "").strip().upper()
    numbers = payload.get("all_fax_numbers") or []
    if not domain or not token or not isinstance(numbers, list) or not numbers:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="fax_user, authentication_token, all_fax_numbers required",
        )
    uuid = save_fax_user(domain, token, numbers)
    return {"domain_uuid": uuid}


@router.post(
    "/clients/{domain_uuid}/toggle_active", dependencies=[Depends(require_admin)]
)
def client_toggle_active(domain_uuid: str) -> Dict[str, Any]:
    ok = toggle_client_active(domain_uuid)
    return {"success": bool(ok)}


@router.delete("/clients/{domain_uuid}", dependencies=[Depends(require_admin)])
def client_delete(domain_uuid: str) -> Dict[str, Any]:
    ok = delete_client(domain_uuid)
    return {"success": bool(ok)}


@router.get("/clients/{domain_uuid}/devices", dependencies=[Depends(require_admin)])
def client_known_devices(domain_uuid: str) -> Dict[str, Any]:
    return {"devices": get_known_devices(domain_uuid) or []}


@router.get("/clients/{fax_user}/bearer", dependencies=[Depends(require_admin)])
def client_cached_bearer(fax_user: str) -> Dict[str, Any]:
    cached = get_cached_bearer(fax_user)
    return cached or {}


@router.post("/clients/{fax_user}/assignments", dependencies=[Depends(require_admin)])
def client_update_assignments(fax_user: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    assignments = payload.get("assignments")
    if not isinstance(assignments, dict):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="assignments must be an object"
        )
    ok = update_client_retriever_assignment(fax_user, assignments)
    return {"success": bool(ok)}


@router.get("/clients/{domain_uuid}/numbers", dependencies=[Depends(require_admin)])
def client_numbers(domain_uuid: str) -> Dict[str, Any]:
    return {"numbers": get_fax_numbers(domain_uuid) or []}


# -------- Resellers --------


@router.get("/resellers", dependencies=[Depends(require_admin)])
def reseller_list() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rec in resellers.find({}, {"_id": 0, "reseller_id": 1, "encrypted_blob": 1}):
        out.append(
            {
                "reseller_id": rec.get("reseller_id"),
                "encrypted_blob": rec.get("encrypted_blob"),
            }
        )
    return out


@router.get("/resellers/{reseller_id}", dependencies=[Depends(require_admin)])
def reseller_get(reseller_id: str) -> Dict[str, Any]:
    blob = get_reseller_blob(reseller_id)
    if not blob:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Not found")
    return {"encrypted_blob": blob}


@router.post("/resellers", dependencies=[Depends(require_admin)])
def reseller_save(payload: Dict[str, Any]) -> Dict[str, Any]:
    rid = (payload.get("reseller_id") or "").strip()
    data = payload.get("data")
    if not rid or not isinstance(data, dict):
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST, detail="reseller_id and data required"
        )
    save_reseller_blob(rid, data)
    return {"success": True}


@router.delete("/resellers/{reseller_id}", dependencies=[Depends(require_admin)])
def reseller_delete(reseller_id: str) -> Dict[str, Any]:
    res = resellers.delete_one({"reseller_id": reseller_id})
    return {"success": res.deleted_count > 0}


# -------- Logs (admin) --------
from core.logger import audit_collection as _audit_coll
from core.logger import log_collection as _access_coll


def _resolve_log_collection(name: str):
    name = (name or "").strip().lower()
    if name == "audit_logs":
        return _audit_coll
    # default to access_logs
    return _access_coll


@router.get("/logs/types", dependencies=[Depends(require_admin)])
def log_event_types(collection: str = "access_logs") -> Dict[str, Any]:
    coll = _resolve_log_collection(collection)
    try:
        types = coll.distinct("event_type")
        types = sorted([t for t in types if isinstance(t, str)])
    except Exception:
        types = []
    return {"event_types": types}


@router.get("/logs", dependencies=[Depends(require_admin)])
def list_logs(
    collection: str = "access_logs", event_type: Optional[str] = None, limit: int = 200
) -> Dict[str, Any]:
    coll = _resolve_log_collection(collection)
    try:
        q = {}
        if event_type and event_type.strip() and event_type != "<All>":
            q["event_type"] = event_type.strip()
        cursor = coll.find(q).sort("timestamp", -1).limit(int(limit or 200))
        out: List[Dict[str, Any]] = []
        for doc in cursor:
            d = dict(doc)
            d.pop("_id", None)
            out.append(d)
        return {"entries": out}
    except Exception:
        return {"entries": []}


# -------- Integrations (admin) --------
from db.mongo_interface import (
    get_reseller_liberty_basic,
    resellers as _resellers_coll,
    set_reseller_liberty_basic,
)
from pydantic import BaseModel
import base64 as _b64
from datetime import datetime as _dt, timezone as _tz


class _AdminLibertyBody(BaseModel):
    basic_b64: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None


@router.get("/integrations/liberty/{reseller_id}/basic", dependencies=[Depends(require_admin)])
def admin_liberty_get(reseller_id: str) -> Dict[str, Any]:
    rec = get_reseller_liberty_basic(reseller_id)
    if not rec:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Not found")
    return rec


@router.post("/integrations/liberty/{reseller_id}/basic", dependencies=[Depends(require_admin)])
def admin_liberty_set(reseller_id: str, body: _AdminLibertyBody) -> Dict[str, Any]:
    b64 = (body.basic_b64 or "").strip()
    if not b64:
        user = (body.username or "").strip()
        pwd = (body.password or "").strip()
        if not user or not pwd:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Provide basic_b64 or username+password",
            )
        b64 = _b64.b64encode(f"{user}:{pwd}".encode("utf-8")).decode("ascii")
    ok = set_reseller_liberty_basic(reseller_id, b64, username=body.username, password=body.password)
    if not ok:
        raise HTTPException(status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Persist failed")
    return {"success": True, "basic_b64": b64, "rotated_at": _dt.now(_tz.utc).isoformat()}


@router.delete("/integrations/liberty/{reseller_id}/basic", dependencies=[Depends(require_admin)])
def admin_liberty_clear(reseller_id: str) -> Dict[str, Any]:
    _resellers_coll.update_one(
        {"reseller_id": reseller_id},
        {
            "$unset": {
                "integrations.libertyrx.vendor_basic_b64": "",
                "integrations.libertyrx.vendor_rotated_at": "",
                "integrations.libertyrx.encrypted_vendor_creds": "",
            }
        },
    )
    return {"success": True}
