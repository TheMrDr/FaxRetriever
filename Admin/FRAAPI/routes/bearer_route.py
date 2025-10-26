# Admin/licensing_server/routes/bearer_route.py
# CHANGES:
# - Enforce 'bearer.read' scope
# - Remove 'all_fax_numbers' from responses (cache hit and fresh)
# - Keep existing SkySwitch request/handling and logging patterns

from datetime import datetime, timedelta, timezone

import requests
from auth.crypto_utils import CryptoError, decrypt_blob
from auth.token_utils import TokenError, decode_jwt_token, require_scopes
from config import (BEARER_REFRESH_OFFSET, SKYSWITCH_TOKEN_URL, SYSTEM_ACTOR,
                    TOKEN_GRANT_TYPE)
from db.mongo_interface import (get_cached_bearer, get_client_by_uuid,
                                get_reseller_blob, save_bearer_token)
from fastapi import APIRouter, Header, HTTPException, Request
from starlette.status import (HTTP_401_UNAUTHORIZED, HTTP_403_FORBIDDEN,
                              HTTP_404_NOT_FOUND,
                              HTTP_500_INTERNAL_SERVER_ERROR)

from core.logger import log_event_v2
from utils.fax_user_utils import parse_reseller_id

router = APIRouter()


@router.post("/")
async def get_bearer_token(request: Request, authorization: str = Header(None)):
    ip = request.client.host
    domain_uuid = None
    device_id = None

    def err(
        status: int,
        code: str,
        detail: str,
        *,
        event_type: str,
        note: str,
        obj_type="bearer_token",
        obj_op="error",
        payload=None,
    ):
        log_event_v2(
            event_type=event_type,
            domain_uuid=domain_uuid,
            device_id=device_id,
            ip=ip,
            note=note,
            actor_component=SYSTEM_ACTOR,
            actor_function="get_bearer_token",
            object_type=obj_type,
            object_operation=obj_op,
            payload=payload,
            audit=True,
        )
        raise HTTPException(
            status_code=status, detail=detail, headers={"X-Error-Code": code}
        )

    # --- Authorization header ---
    if not authorization or not authorization.startswith("Bearer "):
        err(
            HTTP_401_UNAUTHORIZED,
            "ERR_MISSING_AUTH_HEADER",
            "Missing or malformed Authorization header",
            event_type="auth_header_invalid",
            note="Missing or malformed Authorization header",
            obj_type="jwt",
            obj_op="parse",
        )

    token = authorization.split(" ", 1)[1]

    # --- Decode JWT ---
    try:
        payload = decode_jwt_token(token)
        # Scope enforcement: raises TokenError if missing
        require_scopes(payload, ["bearer.request"])
    except TokenError as e:
        err(
            HTTP_401_UNAUTHORIZED,
            "ERR_INVALID_JWT",
            str(e),
            event_type="invalid_jwt",
            note=f"JWT validation failed: {e}",
            obj_type="jwt",
            obj_op="validate",
        )

    # Safe after decode
    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    # --- Domain lookup ---
    client = get_client_by_uuid(domain_uuid)
    if not client:
        err(
            HTTP_404_NOT_FOUND,
            "ERR_DOMAIN_NOT_FOUND",
            "Domain not found",
            event_type="client_not_found",
            note="Client not found or inactive",
            obj_type="client",
            obj_op="lookup",
        )

    fax_user = client["fax_user"]

    # --- Cache hit? Return cached token with upstream expiry (Zulu) ---
    cached = get_cached_bearer(fax_user)
    if cached:
        exp = cached.get("expires_at")
        exp_str = exp if isinstance(exp, str) else exp.strftime("%Y-%m-%dT%H:%M:%SZ")
        return {"bearer_token": cached["bearer_token"], "expires_at": exp_str}

    # --- Reseller creds ---
    try:
        try:
            reseller_id = parse_reseller_id(fax_user)
        except Exception as e:
            err(
                HTTP_500_INTERNAL_SERVER_ERROR,
                "ERR_RESELLER_PARSE_FAIL",
                "Unable to parse reseller ID from domain",
                event_type="bearer_exception",
                note=f"Failed to parse reseller_id from fax_user: {e}",
                obj_type="client",
                obj_op="parse_error",
                payload={"fax_user": fax_user},
            )

        blob = get_reseller_blob(reseller_id)
        if not blob:
            err(
                HTTP_500_INTERNAL_SERVER_ERROR,
                "ERR_RESELLER_NOT_FOUND",
                "Missing reseller credential blob",
                event_type="bearer_exception",
                note="Missing reseller credential blob",
                obj_type="reseller_blob",
                obj_op="read",
            )
        creds = decrypt_blob(reseller_id, blob)
    except CryptoError:
        err(
            HTTP_500_INTERNAL_SERVER_ERROR,
            "ERR_RESELLER_DECRYPT_FAIL",
            "Reseller credential decryption failed",
            event_type="bearer_exception",
            note="Reseller credential decryption failed",
            obj_type="reseller_blob",
            obj_op="decrypt",
        )

    # --- SkySwitch token request ---
    form = {
        "grant_type": TOKEN_GRANT_TYPE,
        "client_id": creds["msg_api_user"],
        "client_secret": creds["msg_api_password"],
        "username": creds["voice_api_user"],
        "password": creds["voice_api_password"],
        "scope": "*",
    }
    headers = {
        "accept": "application/json",
        "content-type": "application/x-www-form-urlencoded",
    }

    try:
        resp = requests.post(
            SKYSWITCH_TOKEN_URL, data=form, headers=headers, timeout=10
        )
        if resp.status_code != 200:
            err(
                HTTP_500_INTERNAL_SERVER_ERROR,
                "ERR_SKYSWITCH_API_FAIL",
                "SkySwitch responded with failure",
                event_type="skyswitch_error",
                note=f"SkySwitch returned HTTP {resp.status_code}",
                obj_type="skyswitch_api",
                obj_op="token_request",
                payload={"response_code": resp.status_code},
            )

        try:
            data = resp.json()
        except ValueError:
            import json

            data = json.loads(resp.text)

        bearer = data.get("access_token")
        expires_sec = data.get("expires_in", 21600)
        if not bearer:
            err(
                HTTP_500_INTERNAL_SERVER_ERROR,
                "ERR_BEARER_MISSING",
                "SkySwitch bearer missing from response",
                event_type="bearer_exception",
                note="SkySwitch bearer missing from response",
                obj_type="bearer_token",
                obj_op="parse",
            )

        # TRUE upstream expiry for client response; refresher handles pre-expiry rotation
        upstream_expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=expires_sec
        )
        fax_numbers = client.get("all_fax_numbers", [])
        save_bearer_token(fax_user, bearer, upstream_expires_at, fax_numbers)

        return {
            "bearer_token": bearer,
            "expires_at": upstream_expires_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    except HTTPException:
        raise
    except Exception as e:
        err(
            HTTP_500_INTERNAL_SERVER_ERROR,
            "ERR_REQUEST_EXCEPTION",
            f"Token request failed: {e}",
            event_type="bearer_exception",
            note=f"Token request failed: {e}",
            obj_type="bearer_token",
            obj_op="exception",
            payload={"error": str(e)},
        )
