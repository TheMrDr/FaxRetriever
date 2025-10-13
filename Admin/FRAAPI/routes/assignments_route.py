# Admin/licensing_server/routes/assignments_route.py

import re
from datetime import datetime, timedelta, timezone
from typing import List, Union

from auth.token_utils import (TokenError, decode_jwt_token, generate_jwt_token,
                              require_scopes)
from config import JWT_TTL_SECONDS, SYSTEM_ACTOR
from db.mongo_interface import \
    get_assignments_version  # monotonic version getter
from db.mongo_interface import get_client_by_uuid  # domain lookup
from db.mongo_interface import \
    unclaim_all_for_device  # bulk unclaim for a device
from db.mongo_interface import \
    unclaim_retriever_number  # atomic per-number unclaim
from db.mongo_interface import \
    unclaim_retriever_numbers  # multi-number unclaim
from db.mongo_interface import \
    claim_retriever_number  # atomic per-number claim (returns True if assigned to caller)
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field, validator
from starlette.status import (HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED,
                              HTTP_403_FORBIDDEN, HTTP_404_NOT_FOUND,
                              HTTP_409_CONFLICT)

from core.logger import log_event_v2

router = APIRouter()
E164 = re.compile(r"^\+\d{8,15}$")

# ---------- helpers ----------


def _err(
    status: int,
    code: str,
    detail: str,
    *,
    ip: str,
    domain_uuid=None,
    device_id=None,
    event_type="assignments_error",
    note="",
    obj_type="retriever_assignments",
    obj_op="error",
    payload=None,
):
    log_event_v2(
        event_type=event_type,
        domain_uuid=domain_uuid,
        device_id=device_id,
        ip=ip,
        note=note or detail,
        actor_component=SYSTEM_ACTOR,
        actor_function="assignments",
        object_type=obj_type,
        object_operation=obj_op,
        payload=payload,
        audit=True,
    )
    raise HTTPException(
        status_code=status, detail=detail, headers={"X-Error-Code": code}
    )


def _parse_numbers(value: Union[str, List[str]]) -> List[str]:
    # Accept string or list; trim, validate E.164, dedupe (preserve order)
    nums_in = value if isinstance(value, list) else [value]
    cleaned, seen = [], set()
    for raw in nums_in:
        n = (raw or "").strip()
        if not E164.match(n):
            raise HTTPException(
                status_code=HTTP_400_BAD_REQUEST,
                detail=f"Invalid number format (must be E.164): {raw!r}",
                headers={"X-Error-Code": "ERR_INVALID_NUMBER"},
            )
        if n not in seen:
            seen.add(n)
            cleaned.append(n)
    if not cleaned:
        raise HTTPException(
            status_code=HTTP_400_BAD_REQUEST,
            detail="numbers must not be empty",
            headers={"X-Error-Code": "ERR_EMPTY_NUMBERS"},
        )
    return cleaned


# ---------- models ----------


class AssignmentRequest(BaseModel):
    device_id: str = Field(..., description="Requesting device hostname")
    numbers: Union[str, List[str]] = Field(..., description="Fax number(s) to claim")

    @validator("device_id")
    def _device_nonempty(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("device_id must not be empty")
        return v


class UnregisterRequest(BaseModel):
    device_id: str = Field(..., description="Requesting device hostname")
    numbers: Union[str, List[str], None] = Field(
        None,
        description="Optional fax number(s) to unregister; if omitted, unregister all numbers owned by this device",
    )

    @validator("device_id")
    def _device_nonempty_u(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("device_id must not be empty")
        return v


# ---------- routes ----------


@router.post("/assignments.list")
async def list_assignments(request: Request, authorization: str = Header(None)):
    """
    JWT-only, bodyless: returns the caller domain’s current retriever assignments.
    """
    ip = request.client.host
    domain_uuid = None
    device_id = None

    # Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_MISSING_AUTH_HEADER",
            "Missing or malformed Authorization header",
            ip=ip,
            event_type="auth_header_invalid",
            obj_type="jwt",
            obj_op="parse",
        )

    token = authorization.split(" ", 1)[1]

    # Decode + scope enforcement (assignments.list)
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["assignments.list"])
    except TokenError as e:
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_INVALID_JWT",
            str(e),
            ip=ip,
            event_type="invalid_jwt",
            obj_type="jwt",
            obj_op="validate",
        )

    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    # Domain lookup
    client = get_client_by_uuid(domain_uuid)
    if not client:
        _err(
            HTTP_404_NOT_FOUND,
            "ERR_DOMAIN_NOT_FOUND",
            "Domain not found",
            ip=ip,
            domain_uuid=domain_uuid,
            device_id=device_id,
            event_type="client_not_found",
            obj_type="client",
            obj_op="lookup",
        )

    domain_numbers = list(client.get("all_fax_numbers", []) or [])
    assignments = client.get("retriever_assignments") or {}  # {number: owner_device_id}

    results = {}
    for n in domain_numbers:
        owner = assignments.get(n)
        results[n] = {"owner": owner if owner else None}

    version = get_assignments_version(domain_uuid)
    return {"results": results, "version": version}


@router.post("/assignments.request")
async def request_assignments(
    request: Request, body: AssignmentRequest, authorization: str = Header(None)
):
    """
    Request retriever assignment(s) for one or more numbers.
    Accepts a string or array for 'numbers'.
    """
    ip = request.client.host
    domain_uuid = None
    jwt_device_id = None

    # Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_MISSING_AUTH_HEADER",
            "Missing or malformed Authorization header",
            ip=ip,
            event_type="auth_header_invalid",
            obj_type="jwt",
            obj_op="parse",
        )

    token = authorization.split(" ", 1)[1]

    # Decode + scope enforcement (assignments.request)
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["assignments.request"])
    except TokenError as e:
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_INVALID_JWT",
            str(e),
            ip=ip,
            event_type="invalid_jwt",
            obj_type="jwt",
            obj_op="validate",
        )

    domain_uuid = payload.get("sub")
    jwt_device_id = payload.get("device_id")

    # Device-id match
    if jwt_device_id != body.device_id:
        _err(
            HTTP_403_FORBIDDEN,
            "ERR_DEVICE_MISMATCH",
            "Device mismatch",
            ip=ip,
            domain_uuid=domain_uuid,
            device_id=jwt_device_id,
            obj_type="jwt",
            obj_op="claims",
        )

    # Domain lookup
    client = get_client_by_uuid(domain_uuid)
    if not client:
        _err(
            HTTP_404_NOT_FOUND,
            "ERR_DOMAIN_NOT_FOUND",
            "Domain not found",
            ip=ip,
            domain_uuid=domain_uuid,
            device_id=jwt_device_id,
            event_type="client_not_found",
            obj_type="client",
            obj_op="lookup",
        )

    # Validate + coerce numbers, ensure in-domain
    numbers = _parse_numbers(body.numbers)
    domain_numbers = set(client.get("all_fax_numbers", []) or [])
    out_of_domain = [n for n in numbers if n not in domain_numbers]
    if out_of_domain:
        _err(
            HTTP_409_CONFLICT,
            "ERR_NUMBER_NOT_IN_DOMAIN",
            "One or more numbers are not in the caller's domain",
            ip=ip,
            domain_uuid=domain_uuid,
            device_id=jwt_device_id,
            obj_type="fax_numbers",
            obj_op="validate",
            payload={"invalid_numbers": out_of_domain},
        )

    # Per-number arbitration (atomic in DB)
    results = {}
    for n in numbers:
        assigned = claim_retriever_number(domain_uuid, n, jwt_device_id)
        if assigned:
            results[n] = {"status": "allowed", "owner": jwt_device_id}
        else:
            fresh = get_client_by_uuid(domain_uuid) or {}
            owner = (fresh.get("retriever_assignments") or {}).get(n)

            # Treat None, empty string, or "<unknown>" as unassigned
            if owner in (None, "", "<unknown>"):
                assigned = claim_retriever_number(domain_uuid, n, jwt_device_id)
                if assigned:
                    results[n] = {"status": "allowed", "owner": jwt_device_id}
                    continue

            if owner == jwt_device_id:
                results[n] = {"status": "allowed", "owner": jwt_device_id}
            else:
                results[n] = {"status": "denied", "owner": owner or "<unknown>"}

    log_event_v2(
        event_type="assignments_processed",
        domain_uuid=domain_uuid,
        device_id=jwt_device_id,
        ip=ip,
        note="Assignments evaluated",
        actor_component=SYSTEM_ACTOR,
        actor_function="assignments",
        object_type="retriever_assignments",
        object_operation="evaluate",
        payload={"results": results},
        audit=True,
    )

    version = get_assignments_version(domain_uuid)

    # If at least one assignment was allowed and the current token lacks the unregister scope,
    # issue an upgraded JWT that includes "assignments.unregister" while preserving expiration.
    allowed = [n for n, r in results.items() if (r or {}).get("status") == "allowed"]
    upgrade_token = None
    try:
        current_scopes = payload.get("scope") or []
        if isinstance(current_scopes, str):
            # Normalize string scope to list if provided as space-delimited string
            current_scopes = (
                [s.strip() for s in current_scopes.split()] if current_scopes else []
            )
        if allowed and "assignments.unregister" not in current_scopes:
            new_scopes = sorted(set(current_scopes + ["assignments.unregister"]))
            exp_ts = payload.get("exp")
            if exp_ts:
                exp_dt = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            else:
                exp_dt = datetime.now(timezone.utc) + timedelta(seconds=JWT_TTL_SECONDS)
            upgrade_token = generate_jwt_token(
                domain_uuid=domain_uuid,
                device_id=jwt_device_id,
                scope=new_scopes,
                expiration=exp_dt,
            )
    except Exception:
        upgrade_token = None

    resp = {"results": results, "version": version}
    if upgrade_token:
        resp["jwt_token"] = upgrade_token
    return resp


@router.post("/assignments.unregister")
async def unregister_assignments(
    request: Request, body: UnregisterRequest, authorization: str = Header(None)
):
    """
    Unregister this device as retriever for the given numbers; if numbers omitted, unregister all for device.
    """
    ip = request.client.host
    domain_uuid = None
    jwt_device_id = None

    # Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_MISSING_AUTH_HEADER",
            "Missing or malformed Authorization header",
            ip=ip,
            event_type="auth_header_invalid",
            obj_type="jwt",
            obj_op="parse",
        )

    token = authorization.split(" ", 1)[1]

    # Decode + scope enforcement (assignments.unregister)
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["assignments.unregister"])
    except TokenError as e:
        _err(
            HTTP_401_UNAUTHORIZED,
            "ERR_INVALID_JWT",
            str(e),
            ip=ip,
            event_type="invalid_jwt",
            obj_type="jwt",
            obj_op="validate",
        )

    domain_uuid = payload.get("sub")
    jwt_device_id = payload.get("device_id")

    # Device-id match
    if jwt_device_id != body.device_id:
        _err(
            HTTP_403_FORBIDDEN,
            "ERR_DEVICE_MISMATCH",
            "Device mismatch",
            ip=ip,
            domain_uuid=domain_uuid,
            device_id=jwt_device_id,
            obj_type="jwt",
            obj_op="claims",
        )

    # Domain lookup
    client = get_client_by_uuid(domain_uuid)
    if not client:
        _err(
            HTTP_404_NOT_FOUND,
            "ERR_DOMAIN_NOT_FOUND",
            "Domain not found",
            ip=ip,
            domain_uuid=domain_uuid,
            device_id=jwt_device_id,
            event_type="client_not_found",
            obj_type="client",
            obj_op="lookup",
        )

    domain_numbers = set(client.get("all_fax_numbers", []) or [])

    results = {}
    if body.numbers is None:
        # Bulk unregister all numbers for this device
        changed = unclaim_all_for_device(domain_uuid, jwt_device_id)
        for n in changed:
            results[n] = {"status": "unregistered"}
    else:
        numbers = _parse_numbers(body.numbers)
        out_of_domain = [n for n in numbers if n not in domain_numbers]
        if out_of_domain:
            _err(
                HTTP_409_CONFLICT,
                "ERR_NUMBER_NOT_IN_DOMAIN",
                "One or more numbers are not in the caller's domain",
                ip=ip,
                domain_uuid=domain_uuid,
                device_id=jwt_device_id,
                obj_type="fax_numbers",
                obj_op="validate",
                payload={"invalid_numbers": out_of_domain},
            )
        res_map = unclaim_retriever_numbers(domain_uuid, numbers, jwt_device_id)
        for n, ok in res_map.items():
            results[n] = {"status": "unregistered" if ok else "not_owner"}

    log_event_v2(
        event_type="assignments_unregistered",
        domain_uuid=domain_uuid,
        device_id=jwt_device_id,
        ip=ip,
        note="Assignments unregistered",
        actor_component=SYSTEM_ACTOR,
        actor_function="assignments",
        object_type="retriever_assignments",
        object_operation="unregister",
        payload={"results": results},
        audit=True,
    )

    version = get_assignments_version(domain_uuid)
    return {"results": results, "version": version}
