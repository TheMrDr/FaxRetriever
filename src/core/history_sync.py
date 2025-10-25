from __future__ import annotations

import json
import os
from typing import Iterable, List, Set

from utils.logging_utils import get_logger
from utils.history_index import load_index, save_index
from core.sync_client import list_page, post_ids, MAX_PAGE

log = get_logger("history_sync")

_QUEUE_FILE = os.path.join("cache", "history_sync_queue.json")


def _ensure_cache_dir(base_dir: str) -> str:
    path = os.path.join(base_dir, "cache")
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _queue_path(base_dir: str) -> str:
    _ensure_cache_dir(base_dir)
    return os.path.join(base_dir, _QUEUE_FILE)


def _read_queue(base_dir: str) -> List[str]:
    path = _queue_path(base_dir)
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return [str(x) for x in data if str(x).strip()]
    except Exception:
        pass
    return []


def _write_queue(base_dir: str, ids: Iterable[str]) -> None:
    path = _queue_path(base_dir)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(list(dict.fromkeys([str(x).strip() for x in ids if str(x).strip()])), f)
    except Exception:
        pass


# --- Public helpers ---

def pull_if_missing(base_dir: str) -> None:
    """If local history is absent/empty, pull from FRAAPI to rebuild the cache."""
    try:
        local_map = load_index(base_dir)
        if local_map:
            return
        log.info("Local history empty; pulling from FRAAPI…")
        # Pull all pages of 500
        offset = 0
        all_ids: List[str] = []
        while True:
            ids, next_offset, total = list_page(offset=offset, limit=MAX_PAGE)
            if not ids:
                break
            all_ids.extend(ids)
            if next_offset is None:
                break
            offset = int(next_offset)
        if all_ids:
            save_index(base_dir, {fid: True for fid in all_ids})
            log.info(f"Rebuilt local history with {len(all_ids)} entries")
    except Exception:
        log.exception("pull_if_missing failed")


def flush_queue(base_dir: str) -> None:
    """Attempt to POST queued IDs in batches of 500 until delivered."""
    try:
        pending = _read_queue(base_dir)
        if not pending:
            return
        sent_any = False
        while pending:
            batch = pending[:MAX_PAGE]
            res = post_ids(batch)
            if res.get("error"):
                # stop on first failure; keep queue
                break
            # success — drop batch
            pending = pending[MAX_PAGE:]
            sent_any = True
        if sent_any:
            _write_queue(base_dir, pending)
            log.info("Flushed some queued history IDs; remaining=%d", len(pending))
    except Exception:
        log.exception("flush_queue failed")


def queue_post(base_dir: str, fax_id: str) -> None:
    """Post a single fax_id; on failure, queue it locally for later flush."""
    s = (str(fax_id) or "").strip()
    if not s:
        return
    try:
        res = post_ids([s])
        if res.get("error"):
            # Enqueue
            q = _read_queue(base_dir)
            q.append(s)
            _write_queue(base_dir, q)
            log.warning("Queued fax_id for later sync: %s", s)
    except Exception:
        # On any exception, enqueue
        try:
            q = _read_queue(base_dir)
            q.append(s)
            _write_queue(base_dir, q)
        except Exception:
            pass


def reconcile(base_dir: str) -> None:
    """Bidirectional sync: push local-only and pull server-only entries.
    - Pull remote list (paged) and build a set
    - Compare to local set; push missing (in 500 batches); add missing local entries
    """
    try:
        # Build local set
        local_map = load_index(base_dir)
        local_ids: Set[str] = {k for k, v in local_map.items() if v}

        # Pull all remote IDs
        remote_ids: List[str] = []
        offset = 0
        while True:
            ids, next_offset, total = list_page(offset=offset, limit=MAX_PAGE)
            if not ids:
                break
            remote_ids.extend(ids)
            if next_offset is None:
                break
            offset = int(next_offset)
        remote_set: Set[str] = set(remote_ids)

        # Determine differences
        to_push = list(local_ids - remote_set)
        to_pull = list(remote_set - local_ids)

        # Push in batches of 500
        if to_push:
            log.info("Pushing %d local-only IDs to FRAAPI…", len(to_push))
        i = 0
        while i < len(to_push):
            batch = to_push[i:i + MAX_PAGE]
            res = post_ids(batch)
            if res.get("error"):
                log.warning("Push batch failed; will queue remaining. error=%s", res.get("error"))
                # queue remaining locally
                q = _read_queue(base_dir)
                q.extend(to_push[i:])
                _write_queue(base_dir, q)
                break
            i += MAX_PAGE

        # Pull: add to local index
        if to_pull:
            log.info("Pulling %d remote-only IDs into local cache…", len(to_pull))
            save_index(base_dir, {fid: True for fid in to_pull})

    except Exception:
        log.exception("reconcile failed")
