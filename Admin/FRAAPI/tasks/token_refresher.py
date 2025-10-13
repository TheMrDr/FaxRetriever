# token_refresher.py

from datetime import datetime, timedelta, timezone

import requests
from auth.crypto_utils import CryptoError, decrypt_blob
from config import SKYSWITCH_TOKEN_URL, SYSTEM_ACTOR, TOKEN_GRANT_TYPE
from db.mongo_interface import (get_all_clients, get_cached_bearer,
                                get_reseller_blob, save_bearer_token)

from core.logger import log_event_v2
from utils.fax_user_utils import parse_reseller_id

# Refresh window: always refresh within 1 hour of upstream expiry
REFRESH_WINDOW = timedelta(hours=1)


def _parse_iso_utc(ts):
    if isinstance(ts, datetime):
        # Handle naive datetimes by assuming UTC
        if ts.tzinfo is None:
            return ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    if isinstance(ts, str):
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    raise ValueError("Unsupported timestamp type")


def token_expiring_soon(upstream_expires_at):
    """
    True if we're inside the pre-refresh window:
    now >= (upstream_expires_at - REFRESH_WINDOW)
    """
    try:
        exp = _parse_iso_utc(upstream_expires_at)
        return datetime.now(timezone.utc) >= (exp - REFRESH_WINDOW)
    except Exception:
        return True  # force refresh on parse errors


def refresh_bearer_tokens():
    for client in get_all_clients():
        if not client.get("active"):
            continue

        fax_user = client.get("fax_user")
        fax_numbers = client.get("all_fax_numbers", [])

        cached = get_cached_bearer(fax_user)
        cached_bearer = (cached or {}).get("bearer_token")
        expires_at = (cached or {}).get("expires_at")

        # Only skip refresh when we both have a bearer value and it's not expiring soon
        if cached_bearer and expires_at and not token_expiring_soon(expires_at):
            continue

        # Derive reseller_id from fax_user (supports ext@domain.reseller.service and domain.reseller.service)
        try:
            reseller_id = parse_reseller_id(fax_user)
        except Exception as e:
            log_event_v2(
                event_type="refresh_skipped",
                domain_uuid=client.get("domain_uuid"),
                note=f"Failed to parse reseller_id from fax_user: {e}",
                actor_component=SYSTEM_ACTOR,
                actor_function="refresh_bearer_tokens",
                object_type="client",
                object_operation="parse_error",
                payload={"fax_user": fax_user},
                audit=True,
            )
            continue

        try:
            blob = get_reseller_blob(reseller_id)
            if not blob:
                log_event_v2(
                    event_type="refresh_skipped",
                    domain_uuid=client.get("domain_uuid"),
                    note=f"Missing reseller blob for {reseller_id}",
                    actor_component=SYSTEM_ACTOR,
                    actor_function="refresh_bearer_tokens",
                    object_type="reseller_blob",
                    object_operation="read",
                    payload={"fax_user": fax_user, "reseller_id": reseller_id},
                    audit=True,
                )
                continue

            creds = decrypt_blob(reseller_id, blob)
        except CryptoError:
            log_event_v2(
                event_type="refresh_skipped",
                domain_uuid=client.get("domain_uuid"),
                note="Blob decryption failed",
                actor_component=SYSTEM_ACTOR,
                actor_function="refresh_bearer_tokens",
                object_type="reseller_blob",
                object_operation="decrypt",
                payload={"reseller_id": reseller_id},
                audit=True,
            )
            continue

        payload = {
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
            response = requests.post(
                SKYSWITCH_TOKEN_URL, data=payload, headers=headers, timeout=10
            )
            if response.status_code != 200:
                log_event_v2(
                    event_type="refresh_failed",
                    domain_uuid=client.get("domain_uuid"),
                    note=f"SkySwitch returned status {response.status_code}",
                    actor_component=SYSTEM_ACTOR,
                    actor_function="refresh_bearer_tokens",
                    object_type="skyswitch_api",
                    object_operation="token_request",
                    payload={"response_code": response.status_code},
                    audit=True,
                )
                continue

            data = response.json() or {}
            bearer = data.get("access_token")
            if not bearer:
                log_event_v2(
                    event_type="refresh_failed",
                    domain_uuid=client.get("domain_uuid"),
                    note="SkySwitch response missing access_token",
                    actor_component=SYSTEM_ACTOR,
                    actor_function="refresh_bearer_tokens",
                    object_type="skyswitch_api",
                    object_operation="token_request",
                    payload={"response_body": data},
                    audit=True,
                )
                continue

            expires_sec = data.get("expires_in", 21600)
            try:
                expires_sec = int(expires_sec)
            except Exception:
                expires_sec = 21600

            upstream_expires_at = datetime.now(timezone.utc) + timedelta(
                seconds=expires_sec
            )

            save_bearer_token(fax_user, bearer, upstream_expires_at, fax_numbers)
            log_event_v2(
                event_type="refresh_success",
                domain_uuid=client.get("domain_uuid"),
                note="Bearer token refreshed successfully",
                actor_component=SYSTEM_ACTOR,
                actor_function="refresh_bearer_tokens",
                object_type="bearer_token",
                object_operation="refresh",
                payload={"expires_at": upstream_expires_at.isoformat()},
                audit=True,
            )

        except Exception as e:
            log_event_v2(
                event_type="refresh_failed",
                domain_uuid=client.get("domain_uuid"),
                note=f"Token refresh exception: {str(e)}",
                actor_component=SYSTEM_ACTOR,
                actor_function="refresh_bearer_tokens",
                object_type="bearer_token",
                object_operation="refresh",
                payload={"error": str(e)},
                audit=True,
            )


if __name__ == "__main__":
    refresh_bearer_tokens()
