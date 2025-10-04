# core\license_client

import json
import os
from datetime import datetime, timezone
from platform import node

import jwt
import requests

from core.config_loader import device_config, global_config
from utils.logging_utils import get_logger

log = get_logger("license")

FRA_INIT_URL = "http://licensing.clinicnetworking.com:8000/init"
FRA_BEARER_URL = "http://licensing.clinicnetworking.com:8000/bearer"


def initialize_session(
    app_state, client_domain: str, auth_token: str, mode: str = "sender"
) -> dict:
    try:
        # FaxRetriever must always store and send the full fax_user (e.g., "100@sample.12345.service").
        # FRA will strip the extension internally during /init processing.
        fax_user = client_domain

        device_id = os.environ.get("COMPUTERNAME") or node() or "UNKNOWN-DEVICE"
        payload = {
            "fax_user": fax_user,
            "authentication_token": auth_token,
            "device_id": device_id,
        }

        response = requests.post(FRA_INIT_URL, json=payload, timeout=10)
        if response.status_code != 200:
            log.error(f"/init failed: HTTP {response.status_code} - {response.text}")
            try:
                detail = response.json().get("detail")
            except Exception:
                detail = None
            return {"error": detail or "init_failed"}

        data = response.json()
        jwt_token = data.get("jwt_token")
        if not jwt_token:
            log.error("No jwt_token returned from /init.")
            return {"error": "token_missing"}

        domain_uuid = data.get("domain_uuid")
        numbers = data.get("all_fax_numbers", [])

        # Update global config (store only full fax_user)
        global_config.set("Account", "fax_user", fax_user)
        global_config.set("Account", "domain_uuid", domain_uuid)
        global_config.set("Account", "all_fax_numbers", numbers)
        global_config.set("Account", "validation_status", True)
        global_config.set("Token", "jwt_token", jwt_token)
        global_config.save()

        # Update app state
        app_state.global_cfg.jwt_token = jwt_token
        app_state.global_cfg.fax_user = fax_user
        app_state.global_cfg.domain_uuid = domain_uuid
        app_state.global_cfg.validation_status = True
        app_state.global_cfg.all_numbers = numbers

        log.info("JWT initialization successful.")
        return data

    except Exception as e:
        log.exception("Initialization session failed.")
        return {"error": str(e)}


def retrieve_skyswitch_token(app_state) -> dict:
    jwt_token = app_state.global_cfg.jwt_token
    if not jwt_token:
        log.warning("No JWT token present in app state.")
        return {"error": "jwt_missing"}

    # Check expiration
    try:
        decoded = jwt.decode(jwt_token, options={"verify_signature": False})
        exp = decoded.get("exp")
        if exp and datetime.now(timezone.utc).timestamp() > exp:
            log.warning("JWT token expired. Attempting reinitialization...")
            domain = app_state.global_cfg.fax_user
            token = app_state.global_cfg.authentication_token
            mode = app_state.device_cfg.retriever_mode or "sender"
            result = initialize_session(app_state, domain, token, mode=mode)
            if result.get("error"):
                return {"error": "jwt_reinit_failed"}
            jwt_token = result.get("jwt_token")
    except Exception as e:
        log.warning(f"Failed to decode JWT: {e}")
        return {"error": "jwt_decode_failed"}

    # Use (possibly refreshed) JWT
    headers = {"Authorization": f"Bearer {jwt_token}"}

    try:
        response = requests.post(FRA_BEARER_URL, headers=headers, timeout=10)
        if response.status_code != 200:
            log.error(f"/bearer failed: HTTP {response.status_code} - {response.text}")
            return {"error": "bearer_failed"}

        data = response.json()
        token = data.get("bearer_token")
        expiration = data.get("expires_at")

        if not token:
            log.error("Bearer token missing in response.")
            return {"error": "bearer_missing"}

        # Apply to config
        global_config.set("Token", "bearer_token", token)
        global_config.set("Token", "bearer_token_expires_at", expiration)
        global_config.set(
            "Token", "bearer_token_retrieved", datetime.now(timezone.utc).isoformat()
        )
        global_config.save()

        # Apply to runtime state
        app_state.global_cfg.bearer_token = token
        app_state.global_cfg.bearer_token_expiration = expiration
        app_state.global_cfg.bearer_token_retrieved = datetime.now(
            timezone.utc
        ).isoformat()

        log.info("SkySwitch bearer token retrieved and applied.")
        return data

    except Exception as e:
        log.exception("Bearer token request failed.")
        return {"error": str(e)}
