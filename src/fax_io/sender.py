"""
Handles outbound fax transmission using SkySwitch API.
Builds payload, generates cover/continuation pages for multi-part sends, and sends attachments as multipart/form.
"""

import os
import tempfile
from typing import List, Dict, Any

import requests

from core.app_state import app_state
from core.config_loader import device_config
from utils.document_utils import (
    normalize_pdf,
    generate_cover_pdf_with_multipart_note,
    generate_continuation_pdf,
)
from utils.logging_utils import get_logger

log = get_logger("send_client")

# 10 MiB provider cap (hard)
MAX_SESSION_BYTES = 10 * 1024 * 1024  # 10,485,760 bytes

# Target maximum including estimated multipart overhead (100 KiB headroom)
SESSION_TARGET_BYTES = MAX_SESSION_BYTES - 100 * 1024

# Per-file limit with overhead cushion (business rule)
MAX_FILE_BYTES = int(9.5 * 1024 * 1024)  # 9,953,280 bytes

# Rough multipart overhead estimator (base + per-file)
MULTIPART_BASE_OVERHEAD = 2048  # bytes
MULTIPART_PER_FILE_OVERHEAD = 512  # bytes


def _estimate_overhead(num_files: int) -> int:
    return MULTIPART_BASE_OVERHEAD + num_files * MULTIPART_PER_FILE_OVERHEAD


def plan_sessions(base_dir: str, attachments: list, include_cover: bool) -> int:
    """Estimate the exact number of sessions that will be used to send the fax.

    Runs the same normalization and chunking logic as send_fax (including
    cover-with-note and continuation page insertion) but performs no network calls.
    Returns at least 1 on error to avoid blocking sends due to estimation issues.
    """
    temp_paths: list[str] = []
    try:
        # Normalize inputs similar to send_fax
        normalized_items: List[Dict[str, Any]] = []
        for idx, path in enumerate(attachments or []):
            npath = normalize_pdf(path) if (path and path.lower().endswith(".pdf")) else path
            try:
                if npath != path and npath and npath.startswith(tempfile.gettempdir()):
                    temp_paths.append(npath)
            except Exception:
                pass
            if not npath or not os.path.exists(npath):
                continue
            try:
                size = os.path.getsize(npath)
            except Exception:
                size = 0
            # Enforce single-file policy; if violated, treat as 1 session (UI already warns)
            if size >= MAX_FILE_BYTES:
                return 1
            mime = "application/pdf" if npath.lower().endswith(".pdf") else "application/octet-stream"
            normalized_items.append({
                "path": npath,
                "size": size,
                "mime": mime,
                "is_cover": (idx == 0 and include_cover),
            })
        if not normalized_items:
            return 1
        # Build sessions
        sessions: List[List[Dict[str, Any]]] = []
        curr: List[Dict[str, Any]] = []
        curr_size = _estimate_overhead(0)
        for item in normalized_items:
            projected = curr_size + item["size"] + MULTIPART_PER_FILE_OVERHEAD
            if projected > SESSION_TARGET_BYTES and curr:
                sessions.append(curr)
                curr = []
                curr_size = _estimate_overhead(0)
            curr.append(item)
            curr_size += item["size"] + MULTIPART_PER_FILE_OVERHEAD
        if curr:
            sessions.append(curr)
        N = len(sessions)
        if N <= 0:
            return 1
        # If multi-part, include generated cover/continuation and re-validate like send_fax
        if N > 1:
            try:
                attn = device_config.get("Fax Options", "cover_attn", "")
                memo = device_config.get("Fax Options", "cover_memo", "")
            except Exception:
                attn = ""
                memo = ""
            # Session 1 cover handling
            try:
                if sessions[0] and sessions[0][0].get("is_cover"):
                    rep = generate_cover_pdf_with_multipart_note(attn, memo, session_idx=1, session_total=N, base_dir=base_dir)
                    if rep:
                        sessions[0][0] = {
                            "path": rep,
                            "size": os.path.getsize(rep),
                            "mime": "application/pdf",
                            "is_cover": True,
                        }
                        temp_paths.append(rep)
                else:
                    rep = generate_cover_pdf_with_multipart_note(attn, memo, session_idx=1, session_total=N, base_dir=base_dir)
                    if rep:
                        sessions[0].insert(0, {
                            "path": rep,
                            "size": os.path.getsize(rep),
                            "mime": "application/pdf",
                            "is_cover": True,
                        })
                        temp_paths.append(rep)
            except Exception:
                # If cover gen fails, proceed without it
                pass
            # Continuation pages for sessions 2..N
            for i in range(1, N):
                try:
                    cont = generate_continuation_pdf(session_idx=i+1, session_total=N, base_dir=base_dir)
                    if cont:
                        sessions[i].insert(0, {
                            "path": cont,
                            "size": os.path.getsize(cont),
                            "mime": "application/pdf",
                            "is_cover": False,
                        })
                        temp_paths.append(cont)
                except Exception:
                    pass
            # Re-validate sizes after inserts; shift items if needed
            def session_bytes(part: List[Dict[str, Any]]) -> int:
                return sum(x.get("size", 0) for x in part) + _estimate_overhead(len(part))
            changed = True
            guard = 0
            while changed and guard < 50:
                changed = False
                guard += 1
                for i in range(len(sessions)):
                    part = sessions[i]
                    while session_bytes(part) > SESSION_TARGET_BYTES and len(part) > 1:
                        j = len(part) - 1
                        if j == 0:
                            break
                        item_to_move = part.pop(j)
                        if i + 1 == len(sessions):
                            sessions.append([])
                        sessions[i + 1].insert(0, item_to_move)
                        changed = True
        return max(1, len(sessions))
    except Exception:
        # On any estimation error, default to 1
        try:
            log.exception("Failed to estimate number of sessions; defaulting to 1")
        except Exception:
            pass
        return 1
    finally:
        # Cleanup any temp files created during planning
        for tmp in temp_paths:
            try:
                if tmp and os.path.exists(tmp):
                    os.remove(tmp)
            except Exception:
                pass


class FaxSender:
    @staticmethod
    def send_fax(
        base_dir, recipient: str, attachments: list, include_cover: bool, progress_callback=None
    ) -> bool:
        """
        Sends a fax to the specified recipient with optional cover sheet.

        Args:
            base_dir (str): Application base directory (MEIPASS-aware)
            recipient (str): Phone number of the recipient
            attachments (list): List of file paths (UI may have inserted a cover at index 0 if include_cover)
            include_cover (bool): Whether a cover was included by UI as the first item

        Returns:
            bool: True if successful, False otherwise
        """
        if not app_state.global_cfg.fax_user or not app_state.global_cfg.bearer_token:
            if not app_state.global_cfg.fax_user:
                log.error(
                    "fax_user missing from config; cannot send fax until account is configured."
                )
                return False
            log.error("Missing access_token; cannot send fax.")
            return False

        if not recipient or not attachments:
            log.warning("Fax send aborted: missing recipient or attachments.")
            return False

        # Resolve fax_user for API (prefer full ext@domain if stored)
        fax_user = (
            getattr(app_state.global_cfg, "fax_user", None) or app_state.global_cfg.fax_user
        )

        # Sanitize numbers
        dest_digits = "".join(ch for ch in (recipient or "") if ch.isdigit())
        caller_raw = app_state.device_cfg.selected_fax_number or (
            app_state.global_cfg.all_numbers[0] if app_state.global_cfg.all_numbers else ""
        )
        caller_digits = "".join(ch for ch in (caller_raw or "") if ch.isdigit())

        # Preflight normalize + size, and build normalized item list
        temp_paths: List[str] = []  # for cleanup (normalized PDFs and generated pages)
        temp_handles: List[Any] = []  # for closing
        normalized_items: List[Dict[str, Any]] = []
        try:
            for idx, path in enumerate(attachments):
                npath = normalize_pdf(path) if (path and path.lower().endswith(".pdf")) else path
                try:
                    if npath != path and npath and npath.startswith(tempfile.gettempdir()):
                        temp_paths.append(npath)
                except Exception:
                    pass

                if not npath or not os.path.exists(npath):
                    log.warning(f"Attachment missing: {path}")
                    continue
                size = 0
                try:
                    size = os.path.getsize(npath)
                except Exception:
                    log.warning(f"Unable to stat file size: {npath}")
                if size >= MAX_FILE_BYTES:
                    log.error(
                        f"Single file exceeds 9.5 MiB policy: {os.path.basename(npath)} ({size} bytes)"
                    )
                    return False
                mime = (
                    "application/pdf" if npath.lower().endswith(".pdf") else "application/octet-stream"
                )
                normalized_items.append(
                    {
                        "path": npath,
                        "size": size,
                        "mime": mime,
                        "is_cover": (idx == 0 and include_cover),
                    }
                )

            if not normalized_items:
                log.error("No valid attachments to send after normalization.")
                return False

            # Build sessions (parts) under SESSION_TARGET_BYTES
            sessions: List[List[Dict[str, Any]]] = []
            curr: List[Dict[str, Any]] = []
            curr_size = _estimate_overhead(0)

            for item in normalized_items:
                projected = curr_size + item["size"] + MULTIPART_PER_FILE_OVERHEAD
                if projected > SESSION_TARGET_BYTES and curr:
                    sessions.append(curr)
                    curr = []
                    curr_size = _estimate_overhead(0)
                curr.append(item)
                curr_size += item["size"] + MULTIPART_PER_FILE_OVERHEAD

            if curr:
                sessions.append(curr)

            N = len(sessions)
            if N <= 0:
                log.error("Failed to allocate any session for fax send.")
                return False

            log.info(
                f"Preparing to send fax in {N} session(s). Target max per session: {SESSION_TARGET_BYTES} bytes."
            )

            # Multi-part indicators: cover-with-note for session 1, continuation for sessions 2..N
            if N > 1:
                # Attempt to load Attn/Memo from device settings as saved by UI
                try:
                    attn = device_config.get("Fax Options", "cover_attn", "")
                    memo = device_config.get("Fax Options", "cover_memo", "")
                except Exception:
                    attn = ""
                    memo = ""

                # Session 1 cover handling
                try:
                    if sessions[0] and sessions[0][0].get("is_cover"):
                        rep = generate_cover_pdf_with_multipart_note(
                            attn, memo, session_idx=1, session_total=N, base_dir=base_dir
                        )
                        if rep:
                            sessions[0][0] = {
                                "path": rep,
                                "size": os.path.getsize(rep),
                                "mime": "application/pdf",
                                "is_cover": True,
                            }
                            temp_paths.append(rep)
                        else:
                            log.warning(
                                "ReportLab unavailable or cover-with-note generation failed; proceeding without multi-part note on cover."
                            )
                    else:
                        # Insert generated cover with multipart note at the start of session 1
                        rep = generate_cover_pdf_with_multipart_note(
                            attn, memo, session_idx=1, session_total=N, base_dir=base_dir
                        )
                        if rep:
                            sessions[0].insert(
                                0,
                                {
                                    "path": rep,
                                    "size": os.path.getsize(rep),
                                    "mime": "application/pdf",
                                    "is_cover": True,
                                },
                            )
                            temp_paths.append(rep)
                        else:
                            log.warning(
                                "ReportLab unavailable or cover-with-note generation failed; proceeding without generated cover."
                            )
                except Exception:
                    log.exception("Error while preparing cover-with-note for session 1")

                # Continuation pages for sessions 2..N
                for i in range(1, N):
                    try:
                        cont = generate_continuation_pdf(
                            session_idx=i + 1, session_total=N, base_dir=base_dir
                        )
                        if cont:
                            sessions[i].insert(
                                0,
                                {
                                    "path": cont,
                                    "size": os.path.getsize(cont),
                                    "mime": "application/pdf",
                                    "is_cover": False,
                                },
                            )
                            temp_paths.append(cont)
                        else:
                            log.warning(
                                "ReportLab unavailable or continuation page generation failed; proceeding without continuation page."
                            )
                    except Exception:
                        log.exception("Error while generating continuation page")

                # Re-validate sizes after inserts; if overflow, shift last non-cover item to next session
                def session_bytes(part: List[Dict[str, Any]]) -> int:
                    return sum(x.get("size", 0) for x in part) + _estimate_overhead(len(part))

                changed = True
                guard = 0
                while changed and guard < 50:
                    changed = False
                    guard += 1
                    for i in range(N):
                        if i >= len(sessions):
                            break
                        part = sessions[i]
                        while session_bytes(part) > SESSION_TARGET_BYTES and len(part) > 1:
                            # Move last non-cover (prefer removing from end) to next session
                            j = len(part) - 1
                            # ensure we don't move the first element if it's a cover/continuation marker
                            if j == 0:
                                break
                            item_to_move = part.pop(j)
                            # Ensure next session exists
                            if i + 1 == len(sessions):
                                sessions.append([])
                                N = len(sessions)
                            sessions[i + 1].insert(0, item_to_move)
                            changed = True
                        # Update reference (not strictly needed as list is mutable)
                        sessions[i] = part

            # Send each session
            endpoint = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
            headers = {"Authorization": f"Bearer {app_state.global_cfg.bearer_token}"}

            # Report planned total sessions via callback if provided
            try:
                if progress_callback:
                    progress_callback(0, len(sessions))
            except Exception:
                pass

            for i, part in enumerate(sessions, start=1):
                # Notify progress (current session index, total)
                try:
                    if progress_callback:
                        progress_callback(i, len(sessions))
                except Exception:
                    pass
                # Build files for this part
                files = {}
                handles_this: List[Any] = []
                try:
                    for idx, it in enumerate(part):
                        fh = open(it["path"], "rb")
                        handles_this.append(fh)
                        files[f"filename[{idx}]"] = (
                            os.path.basename(it["path"]),
                            fh,
                            it["mime"],
                        )

                    data = {"caller_id": caller_digits, "destination": dest_digits}

                    est_bytes = sum(x.get("size", 0) for x in part) + _estimate_overhead(
                        len(part)
                    )
                    log.info(
                        f"Sending session {i}/{len(sessions)} with {len(part)} attachment(s); est bytes ≈ {est_bytes}"
                    )
                    resp = requests.post(
                        endpoint, data=data, files=files, headers=headers, timeout=60
                    )

                    if resp.status_code != 200:
                        log.error(
                            f"Session {i}/{len(sessions)} failed: {resp.status_code} {resp.text}"
                        )
                        return False
                    else:
                        log.info(f"Session {i}/{len(sessions)} sent successfully.")
                finally:
                    # Close per-session handles
                    for fh in handles_this:
                        try:
                            fh.close()
                        except Exception:
                            log.debug("Failed to close file handle after session", exc_info=True)

            return True

        except Exception:
            log.exception("Unexpected error sending fax")
            return False
        finally:
            # Cleanup any temp files created/collected during this send (normalized PDFs and generated pages)
            for tmp in temp_paths:
                try:
                    if tmp and os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    log.debug(f"Failed to remove temp file: {tmp}", exc_info=True)
