# Admin/licensing_server/routes/init_route.py
from datetime import datetime, timedelta, timezone

from auth.token_utils import generate_jwt_token
from config import JWT_TTL_SECONDS, SYSTEM_ACTOR
from db.mongo_interface import get_client_by_auth, register_device, is_libertyrx_enabled
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from starlette.status import HTTP_401_UNAUTHORIZED

from core.logger import log_event_v2

router = APIRouter()


class InitRequest(BaseModel):
    authentication_token: str
    fax_user: str
    device_id: str  # Hostname from FR


@router.post("/")
async def initialize_client(req: InitRequest, request: Request):
    """
    v2.2: Authentication-only init.
    - Verifies fax_user + authentication_token for an active client
    - Registers device_id into known_devices
    - Issues device-scoped JWT with scopes: bearer.read, assignments.request
    - Returns domain_uuid and expires_in
    """
    ip = request.client.host
    fax_user = req.fax_user.strip().lower()
    # Accept full fax_user (e.g., "100@sample.12345.service") from FaxRetriever but
    # use only the domain portion for client lookup within FRA.
    if "@" in fax_user:
        fax_user = fax_user.split("@", 1)[1]
    auth_token = req.authentication_token.strip()
    device_id = req.device_id.strip()

    log_event_v2(
        event_type="init_received",
        ip=ip,
        note=f"Init request received for fax_user={fax_user}, device_id={device_id}",
        actor_component=SYSTEM_ACTOR,
        actor_function="initialize_client",
        object_type="client_init",
        object_operation="received",
        audit=False,
    )

    client = get_client_by_auth(auth_token, fax_user)
    if not client:
        log_event_v2(
            event_type="init_denied",
            ip=ip,
            note=f"Invalid credentials for domain: {fax_user}",
            actor_component=SYSTEM_ACTOR,
            actor_function="initialize_client",
            object_type="client_init",
            object_operation="deny",
            audit=True,
        )
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials or inactive account",
        )

    domain_uuid = client["domain_uuid"]
    all_fax_numbers = client.get("all_fax_numbers", [])

    # Register the device
    register_device(domain_uuid, device_id)

    # JWT: TTL from config, scopes per v2.2 spec
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=JWT_TTL_SECONDS)
    scopes = ["bearer.request", "assignments.list", "assignments.request"]
    # Grant LibertyRx basic.read scope if integration is enabled for this domain
    try:
        if is_libertyrx_enabled(domain_uuid):
            scopes.append("liberty:basic.read")
    except Exception:
        # If check fails, do not block init; scope can be added later via enable endpoint
        pass

    jwt_token = generate_jwt_token(
        domain_uuid=domain_uuid,
        device_id=device_id,
        scope=scopes,
        expiration=expires_at,
    )

    log_event_v2(
        event_type="init_success",
        domain_uuid=domain_uuid,
        device_id=device_id,
        ip=ip,
        note="Client initialization complete (auth-only)",
        actor_component=SYSTEM_ACTOR,
        actor_function="initialize_client",
        object_type="client_init",
        object_operation="issue_jwt",
        payload={
            "scope": scopes,
            "expires_at": expires_at.isoformat(),
            "all_fax_numbers_count": len(all_fax_numbers),
        },
        audit=True,
    )

    return {
        "jwt_token": jwt_token,
        "domain_uuid": domain_uuid,
        "all_fax_numbers": all_fax_numbers,
        "expires_in": int((expires_at - datetime.now(timezone.utc)).total_seconds()),
    }
