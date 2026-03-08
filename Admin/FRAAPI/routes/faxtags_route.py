# routes/faxtags_route.py
"""
Fax source tags — records which integration (CRx, LRx) sent a given fax.

Endpoints:
  POST /faxtags/tag    — Upsert tags for fax IDs (called by sidecar after send)
  POST /faxtags/lookup  — Bulk lookup tags by fax IDs (called by sidecar on history load)
"""
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, validator
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_401_UNAUTHORIZED

from auth.token_utils import TokenError, decode_jwt_token, require_scopes
from config import SYSTEM_ACTOR
from core.logger import log_event_v2
from db.mongo_interface import upsert_fax_tags, get_fax_tags

router = APIRouter()


class TagEntry(BaseModel):
    fax_id: str
    source: str  # "crx", "lrx"
    device_id: Optional[str] = None
    record_id: Optional[str] = None  # CRx record ID if applicable

    @validator("fax_id", pre=True)
    def _strip_fax_id(cls, v):
        return str(v).strip() if v else ""

    @validator("source", pre=True)
    def _normalize_source(cls, v):
        return str(v).strip().lower() if v else ""


class TagBody(BaseModel):
    tags: List[TagEntry]


class LookupBody(BaseModel):
    fax_ids: List[str]

    @validator("fax_ids", pre=True)
    def _normalize_ids(cls, v):
        if v is None:
            return []
        if isinstance(v, str):
            v = [v]
        return [str(x).strip() for x in v if x]


def _extract_jwt(authorization: Optional[str]):
    """Extract and validate JWT from Authorization header."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["history.sync"])
    except TokenError as e:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(e))
    return payload


@router.post("/tag")
async def tag_faxes(request: Request, body: TagBody, authorization: str = Header(None)):
    """Tag fax IDs with integration source metadata."""
    payload = _extract_jwt(authorization)
    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    if not body.tags:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No tags provided")

    tag_dicts = []
    for t in body.tags:
        d = {"fax_id": t.fax_id, "source": t.source, "device_id": t.device_id or device_id}
        if t.record_id:
            d["record_id"] = t.record_id
        tag_dicts.append(d)

    result = upsert_fax_tags(domain_uuid, tag_dicts)

    log_event_v2(
        event_type="fax_tags_upsert",
        domain_uuid=domain_uuid,
        device_id=device_id,
        note=f"Tagged {result.get('upserted', 0)} fax(es)",
        actor_component=SYSTEM_ACTOR,
        actor_function="tag_faxes",
        object_type="fax_tags",
        object_operation="upsert",
        payload={"count": len(tag_dicts), "upserted": result.get("upserted", 0)},
        audit=False,
    )

    return {"ok": True, **result}


@router.post("/lookup")
async def lookup_fax_tags(request: Request, body: LookupBody, authorization: str = Header(None)):
    """Look up integration source tags for fax IDs."""
    payload = _extract_jwt(authorization)
    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    fax_ids = list(dict.fromkeys([s for s in body.fax_ids if s]))
    if not fax_ids:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No fax_ids provided")

    tags = get_fax_tags(domain_uuid, fax_ids)

    log_event_v2(
        event_type="fax_tags_lookup",
        domain_uuid=domain_uuid,
        device_id=device_id,
        note=f"Looked up {len(fax_ids)} fax IDs, found {len(tags)} tags",
        actor_component=SYSTEM_ACTOR,
        actor_function="lookup_fax_tags",
        object_type="fax_tags",
        object_operation="read",
        payload={"requested": len(fax_ids), "found": len(tags)},
        audit=False,
    )

    return {"tags": tags}
