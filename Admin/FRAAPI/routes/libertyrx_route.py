# Admin/FRAAPI/routes/libertyrx_route.py
# LibertyRx vendor auth brokerage endpoints (Sprint 3)
#
# Exposes:
# - Admin GUI endpoints (admin-only via X-Admin-Key):
#     GET  /admin/integrations/liberty/{reseller_id}/basic
#     POST /admin/integrations/liberty/{reseller_id}/basic
#     DELETE /admin/integrations/liberty/{reseller_id}/basic
# - Device endpoint (JWT with scope 'liberty:basic.read'):
#     GET  /integrations/libertyrx/vendor_basic.get
#
# Admin POST accepts a body with either basic_b64 (preferred) or username/password
# to compute base64(username:password). Server stores only the computed base64 and a timestamp.

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from auth.token_utils import TokenError, decode_jwt_token, require_scopes, generate_jwt_token
from db.mongo_interface import (
    get_client_by_uuid,
    get_reseller_liberty_basic,
    resellers,
    set_reseller_liberty_basic,
)
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.status import (
    HTTP_200_OK,
    HTTP_204_NO_CONTENT,
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_500_INTERNAL_SERVER_ERROR,
)
from utils.fax_user_utils import parse_reseller_id

from core.logger import log_event_v2
from config import SYSTEM_ACTOR

router = APIRouter()


# ---- Admin auth (mirrors routes/admin_route.require_admin) ----

def _admin_key() -> Optional[str]:
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


# ---- Models ----


class AdminBasicSetBody(BaseModel):
    basic_b64: Optional[str] = Field(default=None, description="Base64( user:pass )")
    username: Optional[str] = Field(default=None)
    password: Optional[str] = Field(default=None)


# ---- Admin GUI endpoints ----


@router.get("/admin/integrations/liberty/{reseller_id}/basic", dependencies=[Depends(require_admin)])
def admin_get_vendor_basic(reseller_id: str) -> dict:
    rec = get_reseller_liberty_basic(reseller_id)
    if not rec:
        raise HTTPException(status_code=HTTP_404_NOT_FOUND, detail="Not found")
    # Trivial pass-through; never include raw credentials
    return rec


@router.post("/admin/integrations/liberty/{reseller_id}/basic", dependencies=[Depends(require_admin)])
def admin_set_vendor_basic(reseller_id: str, body: AdminBasicSetBody) -> dict:
    # Accept either precomputed basic_b64 or username/password to compute it
    b64 = (body.basic_b64 or "").strip()
    if not b64:
        user = (body.username or "").strip()
        pwd = (body.password or "").strip()
        if not user or not pwd:
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail="Provide basic_b64 or username+password",
            )
        pair = f"{user}:{pwd}".encode("utf-8")
        b64 = base64.b64encode(pair).decode("ascii")
    ok = set_reseller_liberty_basic(reseller_id, b64, username=body.username, password=body.password)
    if not ok:
        raise HTTPException(
            status_code=HTTP_500_INTERNAL_SERVER_ERROR, detail="Persist failed"
        )
    return {"success": True, "basic_b64": b64, "rotated_at": datetime.now(timezone.utc).isoformat()}


@router.delete("/admin/integrations/liberty/{reseller_id}/basic", dependencies=[Depends(require_admin)])
def admin_clear_vendor_basic(reseller_id: str):
    # Clear by unsetting fields
    res = resellers.update_one(
        {"reseller_id": reseller_id},
        {
            "$unset": {
                "integrations.libertyrx.vendor_basic_b64": "",
                "integrations.libertyrx.vendor_rotated_at": "",
                "integrations.libertyrx.encrypted_vendor_creds": "",
            }
        },
    )
    _ = res.modified_count
    return {"success": True}


# ---- Device endpoint ----


@router.post("/enable")
async def device_enable_liberty(request: Request, authorization: str = Header(None)) -> dict:
    ip = request.client.host if request and request.client else None
    domain_uuid = None
    device_id = None

    def _err(status: int, code: str, detail: str, *, event_type: str, note: str):
        log_event_v2(
            event_type=event_type,
            domain_uuid=domain_uuid,
            device_id=device_id,
            ip=ip,
            note=note,
            actor_component=SYSTEM_ACTOR,
            actor_function="device_enable_liberty",
            object_type="integrations.libertyrx",
            object_operation="error",
            payload={"code": code},
            audit=True,
        )
        raise HTTPException(status_code=status, detail=detail, headers={"X-Error-Code": code})

    if not authorization or not authorization.startswith("Bearer "):
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_MISSING_AUTH_HEADER",
            "Missing or malformed Authorization header",
            event_type="auth_header_invalid",
            note="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt_token(token)
        # assignments.list is sufficient to request enabling LibertyRx
        require_scopes(payload, ["assignments.list"])
    except TokenError as e:
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_INVALID_JWT",
            str(e),
            event_type="invalid_jwt",
            note=f"JWT validation failed: {e}",
        )

    from db.mongo_interface import set_client_libertyrx_enabled  # local import to avoid cycles

    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    ok = set_client_libertyrx_enabled(domain_uuid, True)
    if not ok:
        _err(
            HTTP_500_INTERNAL_SERVER_ERROR,
            "ERR_ENABLE_UPDATE_FAILED",
            "Failed to persist LibertyRx enabled flag",
            event_type="liberty_enable_failed",
            note="DB update failed",
        )

    # Prepare upgraded JWT including liberty:basic.read while preserving expiration
    try:
        current_scopes = payload.get("scope") or []
        if isinstance(current_scopes, str):
            current_scopes = [s.strip() for s in current_scopes.split()] if current_scopes else []
        new_scopes = sorted(set(current_scopes + ["liberty:basic.read"]))
        exp_ts = payload.get("exp")
        if exp_ts:
            exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
        else:
            from config import JWT_TTL_SECONDS
            exp_dt = datetime.now(timezone.utc) + timedelta(seconds=JWT_TTL_SECONDS)
        new_jwt = generate_jwt_token(domain_uuid=domain_uuid, device_id=device_id, scope=new_scopes, expiration=exp_dt)
    except Exception as e:
        _err(
            HTTP_500_INTERNAL_SERVER_ERROR,
            "ERR_JWT_UPGRADE_FAILED",
            f"Failed to issue upgraded JWT: {e}",
            event_type="jwt_issue_failed",
            note=str(e),
        )

    log_event_v2(
        event_type="liberty_enabled",
        domain_uuid=domain_uuid,
        device_id=device_id,
        ip=ip,
        note="LibertyRx enabled for domain and JWT upgraded",
        actor_component=SYSTEM_ACTOR,
        actor_function="device_enable_liberty",
        object_type="integrations.libertyrx",
        object_operation="enable",
        audit=True,
    )
    return {"success": True, "jwt_token": new_jwt}


@router.get("/vendor_basic.get")
async def device_get_vendor_basic(request: Request, authorization: str = Header(None)) -> dict:
    ip = request.client.host if request and request.client else None
    domain_uuid = None
    device_id = None

    def err(status: int, code: str, detail: str, *, event_type: str, note: str):
        log_event_v2(
            event_type=event_type,
            domain_uuid=domain_uuid,
            device_id=device_id,
            ip=ip,
            note=note,
            actor_component=SYSTEM_ACTOR,
            actor_function="device_get_vendor_basic",
            object_type="integrations.libertyrx.vendor_basic",
            object_operation="error",
            payload={"code": code},
            audit=True,
        )
        raise HTTPException(status_code=status, detail=detail, headers={"X-Error-Code": code})

    # Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        err(
            HTTP_401_UNAUTHORIZED,
            "ERR_MISSING_AUTH_HEADER",
            "Missing or malformed Authorization header",
            event_type="auth_header_invalid",
            note="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["liberty:basic.read"])  # enforce scope
    except TokenError as e:
        err(
            HTTP_401_UNAUTHORIZED,
            "ERR_INVALID_JWT",
            str(e),
            event_type="invalid_jwt",
            note=f"JWT validation failed: {e}",
        )

    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    client = get_client_by_uuid(domain_uuid)
    if not client:
        err(
            HTTP_404_NOT_FOUND,
            "ERR_DOMAIN_NOT_FOUND",
            "Domain not found",
            event_type="client_not_found",
            note="Client not found or inactive",
        )

    fax_user = client.get("fax_user") or ""
    try:
        reseller_id = parse_reseller_id(fax_user)
    except Exception as e:
        err(
            HTTP_500_INTERNAL_SERVER_ERROR,
            "ERR_RESELLER_PARSE_FAIL",
            "Unable to resolve reseller from fax_user",
            event_type="vendor_basic_exception",
            note=f"parse_reseller_id failed: {e}",
        )

    rec = get_reseller_liberty_basic(reseller_id)
    if not rec:
        err(
            HTTP_404_NOT_FOUND,
            "ERR_VENDOR_BASIC_NOT_CONFIGURED",
            "Liberty vendor credentials not configured",
            event_type="vendor_basic_missing",
            note="No vendor basic_b64 configured for reseller",
        )

    # Success path: log and return
    log_event_v2(
        event_type="vendor_basic_served",
        domain_uuid=domain_uuid,
        device_id=device_id,
        ip=ip,
        note="Returned Liberty vendor basic (b64 only)",
        actor_component=SYSTEM_ACTOR,
        actor_function="device_get_vendor_basic",
        object_type="integrations.libertyrx.vendor_basic",
        object_operation="read",
        payload={"reseller_id": reseller_id},
        audit=True,
    )
    return rec
