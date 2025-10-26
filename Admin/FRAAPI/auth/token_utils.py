# auth/token_utils.py  (v2.2)
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

import jwt as pyjwt
from config import JWT_ACCEPT_LEEWAY_SECONDS  # e.g., 60
from config import JWT_ACTIVE_KID  # current key id string
from config import JWT_AUDIENCE  # e.g., "fra.api"
from config import JWT_ISSUER  # e.g., "https://licensing.clinicnetworking.com"
from config import JWT_NOT_BEFORE_SKEW_SECONDS  # e.g., 0..120
from config import JWT_PRIVATE_KEYS  # dict: {kid: PEM_PRIVATE_KEY_STRING}
from config import JWT_PUBLIC_KEYS  # dict: {kid: PEM_PUBLIC_KEY_STRING}
from config import JWT_TTL_SECONDS  # e.g., 86400
from config import REQUIRED_CLAIMS, SYSTEM_ACTOR

from core.logger import log_event_v2


class TokenError(Exception):
    """Custom error for token handling failures."""

    pass


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _assert_claim_types(payload: Dict[str, Any]) -> None:
    # sub should be UUID
    try:
        _ = _uuid.UUID(str(payload.get("sub")))
    except Exception:
        raise TokenError("Invalid 'sub' (must be UUID)")

    # device_id non-empty
    device_id = payload.get("device_id")
    if not isinstance(device_id, str) or not device_id.strip():
        raise TokenError("Invalid 'device_id'")

    # scope list[str], non-empty
    scope = payload.get("scope")
    if (
        not isinstance(scope, list)
        or not scope
        or not all(isinstance(s, str) and s for s in scope)
    ):
        raise TokenError("Invalid 'scope'")


def require_scopes(payload: Dict[str, Any], required: Iterable[str]) -> None:
    have = set(payload.get("scope", []))
    missing = [s for s in required if s not in have]
    if missing:
        raise TokenError(f"Insufficient scope: missing {', '.join(missing)}")


def generate_jwt_token(
    domain_uuid: str,
    device_id: str,
    scope: List[str],
    expiration: Optional[datetime] = None,
    nbf_offset_seconds: int = JWT_NOT_BEFORE_SKEW_SECONDS,
) -> str:
    """
    Issues RS256 JWT with rotation via kid.
    Required claims: iss, aud, sub, device_id, scope, jti, iat, nbf, exp
    """
    now = _now_utc()
    exp_ts = int((expiration or (now + timedelta(seconds=JWT_TTL_SECONDS))).timestamp())
    nbf_ts = int((now + timedelta(seconds=nbf_offset_seconds)).timestamp())
    iat_ts = int(now.timestamp())

    kid = JWT_ACTIVE_KID
    private_key = JWT_PRIVATE_KEYS.get(kid)
    if not private_key:
        raise TokenError("Signing key not available")

    payload: Dict[str, Any] = {
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "sub": domain_uuid,
        "device_id": device_id,
        "scope": scope,
        "jti": str(_uuid.uuid4()),
        "iat": iat_ts,
        "nbf": nbf_ts,
        "exp": exp_ts,
    }

    headers = {"kid": kid, "alg": "RS256", "typ": "JWT"}

    token = pyjwt.encode(payload, private_key, algorithm="RS256", headers=headers)

    log_event_v2(
        event_type="jwt_issued",
        domain_uuid=domain_uuid,
        device_id=device_id,
        note="Issued JWT access token (RS256, kid rotation)",
        actor_component=SYSTEM_ACTOR,
        actor_function="generate_jwt_token",
        object_type="jwt",
        object_operation="create",
        payload={"kid": kid, "scope": scope, "exp": exp_ts},
        audit=True,
    )
    return token


def decode_jwt_token(token: str) -> Dict[str, Any]:
    """
    Verifies issuer, audience, exp, nbf, and requires core claims.
    Raises TokenError on any failure.
    """
    try:
        unverified = pyjwt.get_unverified_header(token)
        kid = unverified.get("kid")
        if not kid:
            raise TokenError("Missing kid in token header")

        public_key = JWT_PUBLIC_KEYS.get(kid)
        if not public_key:
            raise TokenError("Unknown kid")

        payload = pyjwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            leeway=JWT_ACCEPT_LEEWAY_SECONDS,
            options={"require": REQUIRED_CLAIMS},
        )

        _assert_claim_types(payload)

        log_event_v2(
            event_type="jwt_validated",
            domain_uuid=payload.get("sub"),
            device_id=payload.get("device_id"),
            note="JWT validated successfully",
            actor_component=SYSTEM_ACTOR,
            actor_function="decode_jwt_token",
            object_type="jwt",
            object_operation="decode",
            payload={"kid": kid, "scope": payload.get("scope")},
            audit=True,
        )
        return payload

    except pyjwt.ExpiredSignatureError:
        log_event_v2(
            event_type="jwt_expired",
            note="JWT expired",
            actor_component=SYSTEM_ACTOR,
            actor_function="decode_jwt_token",
            object_type="jwt",
            object_operation="decode",
            payload={"error": "expired"},
            audit=True,
        )
        raise TokenError("Access token expired")

    except pyjwt.InvalidTokenError as e:
        log_event_v2(
            event_type="jwt_invalid",
            note=f"JWT invalid: {str(e)}",
            actor_component=SYSTEM_ACTOR,
            actor_function="decode_jwt_token",
            object_type="jwt",
            object_operation="decode",
            payload={"error": str(e)},
            audit=True,
        )
        raise TokenError(f"Invalid access token: {str(e)}")
