# routes/sync_route.py
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, validator
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
)

from auth.token_utils import TokenError, decode_jwt_token, require_scopes
from core.logger import log_event_v2
from config import SYSTEM_ACTOR
from db.mongo_interface import (
    add_downloaded_ids,
    list_downloaded_ids,
    count_downloaded_ids,
)

router = APIRouter()


class PostBody(BaseModel):
    fax_id: Optional[str] = None
    ids: Optional[List[str]] = None

    @validator("fax_id", pre=True)
    def _strip_fax_id(cls, v):
        if v is None:
            return v
        s = str(v).strip()
        return s or None

    @validator("ids", pre=True)
    def _normalize_ids(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            v = [v]
        try:
            out = []
            for x in v:
                s = (str(x) or "").strip()
                if s:
                    out.append(s)
            return out or None
        except Exception:
            return None


class ListBody(BaseModel):
    offset: int = 0
    limit: int = 500  # server will cap to 500

    @validator("offset")
    def _offset_nonneg(cls, v: int) -> int:
        return max(0, int(v or 0))

    @validator("limit")
    def _limit_bounds(cls, v: int) -> int:
        try:
            n = int(v)
        except Exception:
            n = 100
        if n <= 0:
            n = 100
        if n > 500:
            n = 500
        return n


@router.post("/post")
async def post_downloaded(request: Request, body: PostBody, authorization: str = Header(None)):
    ip = request.client.host
    # Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["history.sync"])  # new scope for history sync
    except TokenError as e:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(e))

    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    # Collect IDs
    ids: List[str] = []
    if body.ids:
        ids.extend(body.ids)
    if body.fax_id:
        ids.append(body.fax_id)
    # De-dup
    ids = list(dict.fromkeys([s for s in ids if s]))

    if not ids:
        raise HTTPException(status_code=HTTP_400_BAD_REQUEST, detail="No fax_id(s) provided")

    res = add_downloaded_ids(domain_uuid, ids)

    log_event_v2(
        event_type="history_post",
        domain_uuid=domain_uuid,
        device_id=device_id,
        note=f"Posted {len(ids)} ids (inserted={res.get('inserted')})",
        actor_component=SYSTEM_ACTOR,
        actor_function="post_downloaded",
        object_type="download_history",
        object_operation="upsert",
        payload={"count": len(ids), "inserted": res.get("inserted")},
        audit=False,
    )

    return {"ok": True, **res}


@router.post("/list")
async def list_downloaded(request: Request, body: ListBody, authorization: str = Header(None)):
    ip = request.client.host
    # Authorization header
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_jwt_token(token)
        require_scopes(payload, ["history.sync"])  # same scope
    except TokenError as e:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail=str(e))

    domain_uuid = payload.get("sub")
    device_id = payload.get("device_id")

    total = count_downloaded_ids(domain_uuid)
    ids = list_downloaded_ids(domain_uuid, skip=body.offset, limit=body.limit)
    next_offset = body.offset + len(ids)
    if next_offset >= total:
        next_offset = None

    log_event_v2(
        event_type="history_list",
        domain_uuid=domain_uuid,
        device_id=device_id,
        note=f"Listed {len(ids)} ids (offset={body.offset}, limit={body.limit}, total={total})",
        actor_component=SYSTEM_ACTOR,
        actor_function="list_downloaded",
        object_type="download_history",
        object_operation="list",
        payload={"offset": body.offset, "limit": body.limit, "returned": len(ids), "total": total},
        audit=False,
    )

    return {"ids": ids, "offset": body.offset, "limit": body.limit, "total": total, "next_offset": next_offset}
