# Admin/licensing_server/db/mongo_interface.py

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import uuid4

from auth.crypto_utils import CryptoError, decrypt_blob, encrypt_blob
from config import (COL_BEARERS, COL_CLIENTS, COL_LOGS, COL_RESELLERS, DB_NAME,
                    MONGO_URI, SYSTEM_ACTOR, COL_DOWNLOAD_HISTORY)
from pymongo import ASCENDING, DESCENDING, MongoClient, ReturnDocument
from pymongo.collection import Collection

from core.logger import log_event_v2

client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
db = client[DB_NAME]

resellers: Collection = db[COL_RESELLERS]
clients: Collection = db[COL_CLIENTS]
bearers: Collection = db[COL_BEARERS]
logs: Collection = db[COL_LOGS]
downloads: Collection = db[COL_DOWNLOAD_HISTORY]

BEARER_REFRESH_OFFSET = timedelta(hours=1)


def ensure_indexes() -> None:
    """Create indexes used by hot paths. Idempotent and safe to call on startup."""
    try:
        # Access logs
        logs.create_index([("timestamp", DESCENDING)], name="logs_ts_desc")
        logs.create_index([("event_type", ASCENDING)], name="logs_event_type")
        logs.create_index(
            [("event_type", ASCENDING), ("timestamp", DESCENDING)],
            name="logs_event_ts_desc",
        )
    except Exception:
        pass
    try:
        # Audit logs (import collection from core.logger lazily to avoid cycles)
        from core.logger import audit_collection as _audit

        _audit.create_index([("timestamp", DESCENDING)], name="audit_ts_desc")
        _audit.create_index([("event_type", ASCENDING)], name="audit_event_type")
        _audit.create_index(
            [("event_type", ASCENDING), ("timestamp", DESCENDING)],
            name="audit_event_ts_desc",
        )
    except Exception:
        pass
    try:
        # Clients
        clients.create_index(
            [("domain_uuid", ASCENDING)], name="clients_domain_uuid", unique=True
        )
        clients.create_index([("fax_user", ASCENDING)], name="clients_fax_user")
        clients.create_index(
            [
                ("authentication_token", ASCENDING),
                ("fax_user", ASCENDING),
                ("active", ASCENDING),
            ],
            name="clients_auth_domain_active",
        )
        clients.create_index(
            [("domain_uuid", ASCENDING), ("active", ASCENDING)],
            name="clients_domain_active",
        )
    except Exception:
        pass
    try:
        # Resellers
        resellers.create_index(
            [("reseller_id", ASCENDING)], name="resellers_id", unique=True
        )
    except Exception:
        pass
    try:
        # Bearers cache
        bearers.create_index([("fax_user", ASCENDING)], name="bearers_fax_user")
        bearers.create_index(
            [("expires_at", DESCENDING)], name="bearers_expires_at_desc"
        )
    except Exception:
        pass
    try:
        # Download history — Single history document per domain (doc_type="history") only
        downloads.create_index(
            [("domain_uuid", ASCENDING), ("doc_type", ASCENDING)],
            name="downloads_history_single_per_domain",
            unique=True,
            partialFilterExpression={"doc_type": "history"},
        )
        downloads.create_index(
            [("doc_type", ASCENDING), ("updated_at", DESCENDING)],
            name="downloads_history_updated_desc",
            partialFilterExpression={"doc_type": "history"},
        )
    except Exception:
        pass

# === Reseller Logic ===


def get_reseller_blob(reseller_id: str) -> Optional[dict]:
    doc = resellers.find_one({"reseller_id": reseller_id})
    return doc.get("encrypted_blob") if doc else None


def save_reseller_blob(reseller_id: str, payload: dict):
    blob = encrypt_blob(reseller_id, payload)
    resellers.update_one(
        {"reseller_id": reseller_id}, {"$set": {"encrypted_blob": blob}}, upsert=True
    )
    log_event_v2(
        event_type="reseller_blob_saved",
        note=f"Encrypted and stored blob for reseller {reseller_id}",
        actor_component=SYSTEM_ACTOR,
        actor_function="save_reseller_blob",
        object_type="reseller_blob",
        object_operation="write",
        payload={"reseller_id": reseller_id},
        audit=True,
    )


def set_reseller_liberty_basic(
    reseller_id: str,
    basic_b64: str,
    *,
    username: Optional[str] = None,
    password: Optional[str] = None,
) -> bool:
    """Persist LibertyRx vendor Basic header value for a reseller.

    Optionally stores encrypted raw vendor creds for future rotation convenience.
    Never returns raw secrets. Returns True on success.
    """
    now = datetime.now(timezone.utc)
    update_doc: dict = {
        "integrations.libertyrx.vendor_basic_b64": (basic_b64 or "").strip(),
        "integrations.libertyrx.vendor_rotated_at": now,
    }
    # Optionally store encrypted vendor creds (username/password)
    try:
        if username is not None and password is not None and username.strip() and password.strip():
            enc = encrypt_blob(
                reseller_id,
                {
                    "username": username.strip(),
                    "password": password.strip(),
                    "updated_at": now.isoformat(),
                },
            )
            update_doc["integrations.libertyrx.encrypted_vendor_creds"] = enc
    except Exception:
        # Do not fail the operation if optional encryption fails
        pass

    res = resellers.update_one(
        {"reseller_id": reseller_id},
        {"$set": update_doc},
        upsert=True,
    )

    log_event_v2(
        event_type="libertyrx_vendor_basic_saved",
        note=f"Saved LibertyRx vendor basic for reseller {reseller_id}",
        actor_component=SYSTEM_ACTOR,
        actor_function="set_reseller_liberty_basic",
        object_type="integrations.libertyrx.vendor_basic",
        object_operation="write",
        payload={"reseller_id": reseller_id, "rotated_at": now.isoformat()},
        audit=True,
    )

    return res.modified_count >= 0


def get_reseller_liberty_basic(reseller_id: str) -> Optional[dict]:
    """Return {basic_b64, rotated_at} if configured for the reseller, else None."""
    doc = resellers.find_one(
        {"reseller_id": reseller_id},
        {"_id": 0, "integrations.libertyrx": 1},
    )
    if not doc:
        return None
    integ = (doc.get("integrations") or {}).get("libertyrx") or {}
    b64 = integ.get("vendor_basic_b64")
    rot = integ.get("vendor_rotated_at")
    if not b64:
        return None
    # Normalize rotated_at to ISO string
    if isinstance(rot, datetime):
        rot_str = rot.replace(tzinfo=timezone.utc).isoformat()
    else:
        rot_str = rot if isinstance(rot, str) else None
    return {"basic_b64": b64, "rotated_at": rot_str}


# === Client Domain Logic ===

def set_client_libertyrx_enabled(domain_uuid: str, enabled: bool) -> bool:
    """Set clients.integrations.libertyrx.enabled flag for a domain (audit logged)."""
    try:
        res = clients.update_one(
            {"domain_uuid": domain_uuid, "active": True},
            {"$set": {"integrations.libertyrx.enabled": bool(enabled)}},
        )
        log_event_v2(
            event_type="libertyrx_flag_updated",
            domain_uuid=domain_uuid,
            note=f"LibertyRx enabled set to {bool(enabled)}",
            actor_component=SYSTEM_ACTOR,
            actor_function="set_client_libertyrx_enabled",
            object_type="integrations.libertyrx",
            object_operation="update",
            payload={"enabled": bool(enabled)},
            audit=True,
        )
        return res.modified_count >= 0
    except Exception:
        return False

# === Client Domain Logic ===


def get_client_by_auth(auth_token: str, fax_user: str) -> Optional[dict]:
    return clients.find_one(
        {
            "authentication_token": auth_token.strip(),
            "fax_user": fax_user.strip().lower(),
            "active": True,
        }
    )


def get_client_by_uuid(domain_uuid: str) -> Optional[dict]:
    return clients.find_one({"domain_uuid": domain_uuid, "active": True})


# === Retriever assignment (v2.2) ===
def claim_retriever_number(domain_uuid: str, number: str, device_id: str) -> bool:
    """
    Atomically claim 'number' for 'device_id' iff currently unassigned.
    Unassigned means the field does not exist, is null, empty string, or the sentinel "<unknown>".
    Returns True if the claim succeeded, False if already owned.
    """
    field = f"retriever_assignments.{number}"
    res = clients.update_one(
        {
            "domain_uuid": domain_uuid,
            "active": True,
            "$or": [
                {field: {"$exists": False}},
                {field: None},
                {field: {"$in": ["", "<unknown>"]}},
            ],
        },
        {"$set": {field: device_id}, "$inc": {"assignments_version": 1}},
    )
    return res.modified_count == 1


def unclaim_retriever_number(domain_uuid: str, number: str, device_id: str) -> bool:
    """
    Atomically unassign 'number' for 'device_id' iff currently owned by that device.
    Returns True if the unassignment succeeded, False otherwise.
    """
    field = f"retriever_assignments.{number}"
    res = clients.update_one(
        {"domain_uuid": domain_uuid, "active": True, field: device_id},
        {"$unset": {field: ""}, "$inc": {"assignments_version": 1}},
    )
    return res.modified_count == 1


def unclaim_retriever_numbers(
    domain_uuid: str, numbers: list[str], device_id: str
) -> dict:
    """Unassign multiple numbers for a device; returns a map of number->bool indicating success."""
    results: dict[str, bool] = {}
    for n in numbers:
        try:
            results[n] = unclaim_retriever_number(domain_uuid, n, device_id)
        except Exception:
            results[n] = False
    return results


def unclaim_all_for_device(domain_uuid: str, device_id: str) -> list[str]:
    """
    Unassign all numbers currently owned by device_id in the domain.
    Returns the list of numbers that were unassigned.
    """
    doc = (
        clients.find_one(
            {"domain_uuid": domain_uuid, "active": True}, {"retriever_assignments": 1}
        )
        or {}
    )
    assignments = doc.get("retriever_assignments") or {}
    changed: list[str] = []
    for number, owner in list(assignments.items()):
        if owner == device_id:
            field = f"retriever_assignments.{number}"
            res = clients.update_one(
                {"domain_uuid": domain_uuid, "active": True, field: device_id},
                {"$unset": {field: ""}, "$inc": {"assignments_version": 1}},
            )
            if res.modified_count == 1:
                changed.append(number)
    return changed


def get_assignments_version(domain_uuid: str) -> int:
    doc = clients.find_one({"domain_uuid": domain_uuid}, {"assignments_version": 1})
    return int((doc or {}).get("assignments_version", 0))


# def update_fax_numbers(domain_uuid: str, numbers: list[str]) -> bool:
#     """
#     Updates the fax_numbers list for a given fax_user.
#     """
#     result = clients.update_one(
#         {"domain_uuid": domain_uuid},
#         {"$set": {"all_fax_numbers": numbers}}
#     )
#     if result.modified_count > 0:
#         log_event_v2(
#             event_type="fax_numbers_updated",
#             domain_uuid=domain_uuid,
#             note="Fax number list updated",
#             actor_component=SYSTEM_ACTOR,
#             actor_function="update_fax_numbers",
#             object_type="client",
#             object_operation="update",
#             payload={"all_fax_numbers": numbers},
#             audit=True
#         )
#
#     return result.modified_count > 0


def get_fax_numbers(domain_uuid: str) -> list[str]:
    doc = clients.find_one({"domain_uuid": domain_uuid})
    return doc.get("all_fax_numbers", []) if doc else []


def save_fax_user(fax_user: str, auth_token: str, fax_numbers: list[str]) -> str:
    domain = fax_user.strip().lower()
    token = auth_token.strip().upper()
    existing = clients.find_one({"fax_user": domain})

    if existing:
        # Update in place
        clients.update_one(
            {"fax_user": domain},
            {"$set": {"authentication_token": token, "all_fax_numbers": fax_numbers}},
        )
        domain_uuid = existing.get("domain_uuid")
        log_event_v2(
            event_type="client_updated",
            domain_uuid=domain_uuid,
            note=f"Client domain {domain} credentials updated",
            actor_component=SYSTEM_ACTOR,
            actor_function="save_fax_user",
            object_type="client",
            object_operation="update",
            payload={"all_fax_numbers": fax_numbers},
            audit=True,
        )
        return domain_uuid

    # Insert new
    domain_uuid = str(uuid4())
    doc = {
        "fax_user": domain,
        "authentication_token": token,
        "domain_uuid": domain_uuid,
        "active": True,
        "retriever_assigned": False,
        "all_fax_numbers": fax_numbers,
    }
    clients.insert_one(doc)
    log_event_v2(
        event_type="client_added",
        domain_uuid=domain_uuid,
        note=f"New client domain registered: {domain}",
        actor_component=SYSTEM_ACTOR,
        actor_function="save_fax_user",
        object_type="client",
        object_operation="create",
        payload={"all_fax_numbers": fax_numbers},
        audit=True,
    )

    return domain_uuid


def get_all_clients() -> list[dict]:
    return list(clients.find())


def toggle_client_active(domain_uuid: str) -> bool:
    doc = clients.find_one({"domain_uuid": domain_uuid})
    if not doc:
        return False
    new_state = not doc.get("active", True)
    result = clients.update_one(
        {"domain_uuid": domain_uuid}, {"$set": {"active": new_state}}
    )
    log_event_v2(
        event_type="client_toggled",
        domain_uuid=domain_uuid,
        note=f"Toggled active flag to {new_state}",
        actor_component=SYSTEM_ACTOR,
        actor_function="toggle_client_active",
        object_type="client",
        object_operation="toggle",
        payload={"active": new_state},
        audit=True,
    )

    return result.modified_count > 0


def delete_client(domain_uuid: str) -> bool:
    result = clients.delete_one({"domain_uuid": domain_uuid})
    log_event_v2(
        event_type="client_deleted",
        domain_uuid=domain_uuid,
        note="Client domain deleted",
        actor_component=SYSTEM_ACTOR,
        actor_function="delete_client",
        object_type="client",
        object_operation="delete",
        audit=True,
    )

    return result.deleted_count > 0


def register_device(domain_uuid: str, device_id: str):
    clients.update_one(
        {"domain_uuid": domain_uuid}, {"$addToSet": {"known_devices": device_id}}
    )


def get_known_devices(domain_uuid: str) -> list[str]:
    doc = clients.find_one({"domain_uuid": domain_uuid})
    return doc.get("known_devices", []) if doc else []


def is_libertyrx_enabled(domain_uuid: str) -> bool:
    """Return True if LibertyRx integration is enabled for the domain.

    Looks for either clients.integrations.libertyrx.enabled == True
    or legacy top-level flag clients.liberty_enabled == True (fallback).
    Missing flags are treated as disabled.
    """
    doc = clients.find_one(
        {"domain_uuid": domain_uuid},
        {"integrations": 1, "liberty_enabled": 1},
    )
    if not doc:
        return False
    integrations = doc.get("integrations") or {}
    libertyrx = integrations.get("libertyrx") or {}
    if bool(libertyrx.get("enabled")):
        return True
    # Fallback legacy flag
    return bool(doc.get("liberty_enabled"))


def update_client_retriever_assignment(
    fax_user: str, updated_assignments: dict
) -> bool:
    """
    Deprecated in v2.2; retain for admin overrides via GUI if needed.
    Prefer claim_retriever_number for runtime arbitration.
    """
    result = clients.update_one(
        {"fax_user": fax_user.lower().strip()},
        {"$set": {"retriever_assignments": updated_assignments}},
    )
    if result.modified_count > 0:
        log_event_v2(
            event_type="retriever_updated",
            note="Retriever assignment map updated",
            actor_component=SYSTEM_ACTOR,
            actor_function="update_client_retriever_assignment",
            object_type="retriever_map",
            object_operation="update",
            payload={"assignments": updated_assignments},
            audit=True,
        )
        return True
    return False


# === Bearer Token Logic ===

from datetime import timezone


def get_cached_bearer(fax_user: str) -> Optional[dict]:
    doc = bearers.find_one({"fax_user": fax_user})
    if not doc:
        return None

    expires = doc.get("expires_at")
    if not expires:
        return None

    if isinstance(expires, datetime) and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)

    # Skip if token expires too soon
    if expires < datetime.now(timezone.utc) + BEARER_REFRESH_OFFSET:
        return None

    encrypted = doc.get("encrypted_token")
    if not encrypted:
        return None

    try:
        decrypted = decrypt_blob(fax_user, encrypted)
        return decrypted
    except CryptoError:
        return None


def save_bearer_token(
    fax_user: str, bearer_token: str, expires_at: datetime, fax_numbers: list[str]
):
    now = datetime.now(timezone.utc)

    payload = {
        "bearer_token": bearer_token,
        "all_fax_numbers": fax_numbers,
        "retrieved_at": now.isoformat(),
        "expires_at": expires_at.isoformat(),
    }

    encrypted = encrypt_blob(fax_user, payload)

    bearers.replace_one(
        {"fax_user": fax_user},
        {
            "fax_user": fax_user,
            "encrypted_token": encrypted,
            "retrieved_at": now,
            "expires_at": expires_at,
        },
        upsert=True,
    )

    log_event_v2(
        event_type="bearer_token_saved",
        note=f"Bearer token stored for {fax_user}",
        actor_component=SYSTEM_ACTOR,
        actor_function="save_bearer_token",
        object_type="bearer_token",
        object_operation="write",
        payload={
            "retrieved_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "all_fax_numbers": fax_numbers,
        },
        audit=True,
    )


# === LibertyRx Integrations (vendor/client secrets) ===

def save_client_libertyrx_keys(domain_uuid: str, npi: str, api_key: str) -> bool:
    """Encrypt and store per-client LibertyRx identifiers (NPI, API key)."""
    now = datetime.now(timezone.utc)
    payload = {
        "npi": (npi or "").strip(),
        "api_key": (api_key or "").strip(),
        "updated_at": now.isoformat(),
    }
    encrypted = encrypt_blob(domain_uuid, payload)
    res = clients.update_one(
        {"domain_uuid": domain_uuid},
        {
            "$set": {
                "integrations.libertyrx.encrypted_client_keys": encrypted,
                "integrations.libertyrx.client_keys_updated_at": now,
            }
        },
        upsert=False,
    )
    log_event_v2(
        event_type="libertyrx_client_keys_saved",
        domain_uuid=domain_uuid,
        note="Saved encrypted LibertyRx client identifiers",
        actor_component=SYSTEM_ACTOR,
        actor_function="save_client_libertyrx_keys",
        object_type="integrations.libertyrx.client_keys",
        object_operation="write",
        payload={"updated_at": now.isoformat()},
        audit=True,
    )
    return res.modified_count >= 0  # treat upsert False as success if document exists


def get_client_libertyrx_keys(domain_uuid: str) -> Optional[dict]:
    """Return decrypted LibertyRx client identifiers if present."""
    doc = clients.find_one(
        {"domain_uuid": domain_uuid}, {"integrations.libertyrx.encrypted_client_keys": 1}
    )
    if not doc:
        return None
    integrations = doc.get("integrations") or {}
    lib = integrations.get("libertyrx") or {}
    blob = lib.get("encrypted_client_keys")
    if not blob:
        return None
    try:
        return decrypt_blob(domain_uuid, blob)
    except CryptoError:
        return None


# === LibertyRx Device PubKeys ===

def upsert_libertyrx_device_pubkey(
    domain_uuid: str,
    device_id: str,
    pubkey_pem: str,
    thumbprint: str,
    alg: str,
) -> bool:
    """Idempotently upsert a device public key under a client domain.

    Stored at path: integrations.libertyrx.device_pubkeys.{device_id}
    Fields: pubkey_pem, thumbprint, alg, created_at, updated_at
    """
    now = datetime.now(timezone.utc)
    # Fetch existing to preserve created_at if present
    doc = clients.find_one(
        {"domain_uuid": domain_uuid},
        {"integrations.libertyrx.device_pubkeys": 1},
    ) or {}
    created_at = None
    try:
        integrations = doc.get("integrations") or {}
        lib = integrations.get("libertyrx") or {}
        dpk = lib.get("device_pubkeys") or {}
        existing = dpk.get(device_id)
        if isinstance(existing, dict):
            created_at = existing.get("created_at")
    except Exception:
        created_at = None

    if not created_at:
        created_at = now.isoformat()

    field_base = f"integrations.libertyrx.device_pubkeys.{device_id}"
    res = clients.update_one(
        {"domain_uuid": domain_uuid},
        {
            "$set": {
                f"{field_base}.pubkey_pem": pubkey_pem,
                f"{field_base}.thumbprint": (thumbprint or ""),
                f"{field_base}.alg": alg,
                f"{field_base}.created_at": created_at,
                f"{field_base}.updated_at": now.isoformat(),
            }
        },
        upsert=False,
    )

    log_event_v2(
        event_type="libertyrx_device_pubkey_upserted",
        domain_uuid=domain_uuid,
        note="Upserted device public key",
        actor_component=SYSTEM_ACTOR,
        actor_function="upsert_libertyrx_device_pubkey",
        object_type="integrations.libertyrx.device_pubkey",
        object_operation="upsert",
        payload={"device_id": device_id, "alg": alg},
        audit=True,
    )

    return res.modified_count >= 0


def get_libertyrx_device_pubkey(domain_uuid: str, device_id: str) -> Optional[dict]:
    """Return stored device public key record for the given domain/device, or None."""
    doc = clients.find_one(
        {"domain_uuid": domain_uuid},
        {"integrations.libertyrx.device_pubkeys": 1},
    )
    if not doc:
        return None
    try:
        integrations = doc.get("integrations") or {}
        lib = integrations.get("libertyrx") or {}
        dpk = lib.get("device_pubkeys") or {}
        rec = dpk.get(device_id)
        return rec if isinstance(rec, dict) else None
    except Exception:
        return None


# === Download history helpers ===

def add_downloaded_ids(domain_uuid: str, ids: list[str]) -> dict:
    """Idempotently record fax IDs as downloaded for a domain.

    Stores IDs in a single document per domain (doc_type="history"). No legacy
    per-fax fallback is performed.

    Returns dict with counts: {"inserted": int, "total": int}
    """
    if not ids:
        return {"inserted": 0, "total": 0}

    # Normalize and de-duplicate input while preserving order
    norm: list[str] = []
    seen: set[str] = set()
    for fid in ids:
        s = (str(fid) or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        norm.append(s)

    if not norm:
        return {"inserted": 0, "total": 0}

    now = datetime.now(timezone.utc)

    # Single history document per domain
    doc = downloads.find_one({"domain_uuid": domain_uuid, "doc_type": "history"}, {"ids": 1}) or {}
    existing_list = doc.get("ids") if isinstance(doc, dict) else None
    existing_set = set(existing_list or [])
    to_add = [s for s in norm if s not in existing_set]
    if to_add:
        downloads.update_one(
            {"domain_uuid": domain_uuid, "doc_type": "history"},
            {
                "$setOnInsert": {"domain_uuid": domain_uuid, "doc_type": "history", "created_at": now},
                "$push": {"ids": {"$each": to_add}},
                "$set": {"updated_at": now},
            },
            upsert=True,
        )
    else:
        # Ensure the doc exists even if nothing to add (first-time call)
        downloads.update_one(
            {"domain_uuid": domain_uuid, "doc_type": "history"},
            {"$setOnInsert": {"domain_uuid": domain_uuid, "doc_type": "history", "created_at": now}, "$set": {"updated_at": now}},
            upsert=True,
        )
    return {"inserted": len(to_add), "total": len(norm)}


def list_downloaded_ids(domain_uuid: str, skip: int = 0, limit: int = 500) -> list[str]:
    """Return a page (list[str]) of fax IDs for the domain.

    Uses the single history document (doc_type="history"). Paginates the
    in-document array in reverse insertion order (most recent last appended).
    No legacy fallback is performed.
    """
    if skip < 0:
        skip = 0
    if limit <= 0:
        limit = 100
    if limit > 500:
        limit = 500
    try:
        doc = downloads.find_one({"domain_uuid": domain_uuid, "doc_type": "history"}, {"ids": 1})
        if doc and isinstance(doc, dict) and isinstance(doc.get("ids"), list):
            arr = list(doc.get("ids") or [])
            arr.reverse()
            return arr[int(skip): int(skip) + int(limit)]
        return []
    except Exception:
        return []


def count_downloaded_ids(domain_uuid: str) -> int:
    """Return total count of downloaded fax IDs for the domain from the single history document.

    No legacy fallback is performed.
    """
    try:
        doc = downloads.find_one({"domain_uuid": domain_uuid, "doc_type": "history"}, {"ids": 1})
        if doc and isinstance(doc, dict) and isinstance(doc.get("ids"), list):
            return int(len(doc.get("ids") or []))
        return 0
    except Exception:
        return 0
