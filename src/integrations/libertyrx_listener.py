"""
libertyrx_listener.py

Embedded HTTP listener for Liberty Software outbound fax POSTs.
- POST /liberty/fax -> { id }
- GET  /liberty/faxstatus/{id} or /liberty/faxstatus?id=...

Security (MVP per spec):
- No auth; restrict by source IP allowlist (single Liberty server IP).
- Bind on configurable host/port; default host '0.0.0.0', port 18761.

Persistence:
- PDF saved to Outbox; job is inserted into SQLite via LibertyStore.

This module avoids UI; start/stop is managed by MainWindow lifecycle.
"""
from __future__ import annotations

import base64
import json
import re
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from typing import Optional

from utils.logging_utils import get_logger
from integrations.libertyrx_store import LibertyStore

log = get_logger("libertyrx.listener")

DIGITS_RE = re.compile(r"\D+")


class _LibertyHandler(BaseHTTPRequestHandler):
    server_version = "FaxRetrieverLiberty/1.0"

    # type hints for attributes we attach on server
    store: LibertyStore  # type: ignore[assignment]
    max_pdf_bytes: int  # type: ignore[assignment]

    def _send_json(self, status: int, payload: dict):
        try:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            try:
                log.exception("Failed to send HTTP response")
            except Exception:
                pass

    def _read_json(self) -> Optional[dict]:
        try:
            length = int(self.headers.get("Content-Length") or "0")
            if length <= 0:
                return None
            data = self.rfile.read(length)
            return json.loads(data.decode("utf-8"))
        except Exception:
            return None

    def do_POST(self):  # noqa: N802
        log.debug(f"Liberty POST request: {self.path} from {self.address_string()}")
        path = self.path or ""
        clean_path = path.split("?")[0].strip("/")
        
        if clean_path.startswith("liberty/faxstatus"):
            log.warning(f"Liberty POST: method not allowed on '{path}' from {self.address_string()}")
            self._send_json(405, {"error": "method_not_allowed", "message": "Use GET to check status"})
            return

        if clean_path != "liberty/fax":
            log.warning(f"Liberty POST: invalid path '{self.path}' from {self.address_string()}")
            self._send_json(404, {"error": "not_found"})
            return
        body = self._read_json()
        if not isinstance(body, dict):
            log.warning(f"Liberty POST: invalid or empty JSON from {self.address_string()}")
            self._send_json(400, {"error": "invalid_json"})
            return

        # Liberty spec says camelCase (faxNumber, contentType, fileData),
        # but logs show they sometimes send PascalCase (FaxNumber, ContentType, FileData).
        # We'll normalize keys to lowercase for internal lookup.
        norm_body = {k.lower(): v for k, v in body.items()}
        
        fax_number = str(norm_body.get("faxnumber") or "").strip()
        content_type = str(norm_body.get("contenttype") or "").strip().lower()
        file_data = norm_body.get("filedata")

        # Spec says contentType should be application/pdf. 
        # If it's missing or empty, we'll assume it's a PDF to be lenient with Liberty.
        if not content_type and file_data:
            log.debug(f"Liberty POST: contentType missing/empty, defaulting to application/pdf")
            content_type = "application/pdf"

        if content_type != "application/pdf":
            log.warning(f"Liberty POST: unsupported contentType '{content_type}' from {self.address_string()}. Keys: {list(body.keys())}")
            self._send_json(415, {"error": "unsupported_media_type"})
            return
        digits = re.sub(DIGITS_RE, "", fax_number)
        if not digits:
            log.warning(f"Liberty POST: missing or invalid faxNumber from {self.address_string()}. Keys: {list(body.keys())}")
            self._send_json(400, {"error": "invalid_number"})
            return
        if not isinstance(file_data, str) or not file_data:
            log.warning(f"Liberty POST: missing fileData from {self.address_string()}. Keys: {list(body.keys())}")
            self._send_json(400, {"error": "invalid_base64"})
            return
        try:
            pdf_bytes = base64.b64decode(file_data, validate=True)
        except Exception:
            log.warning(f"Liberty POST: invalid base64 fileData from {self.address_string()}")
            self._send_json(400, {"error": "invalid_base64"})
            return
        max_bytes = int(getattr(self.server, "max_pdf_bytes", 25 * 1024 * 1024))  # type: ignore[attr-defined]
        if len(pdf_bytes) > max_bytes:
            log.warning(f"Liberty POST: payload too large ({len(pdf_bytes)} bytes) from {self.address_string()}")
            self._send_json(413, {"error": "payload_too_large"})
            return
        job_id = str(uuid.uuid4())
        try:
            store: LibertyStore = getattr(self.server, "store")  # type: ignore[assignment]
            sha = store.compute_sha256(pdf_bytes)
            pdf_path = store.build_pdf_filename(job_id, digits)
            # Write file
            with open(pdf_path, "wb") as f:
                f.write(pdf_bytes)
            store.add_job(job_id, digits, pdf_path, len(pdf_bytes), sha, retention_hours=getattr(self.server, "retention_hours", 72))  # type: ignore[attr-defined]
            log.info(f"Liberty POST accepted id={job_id} to={digits} len={len(pdf_bytes)} sha256={sha[:10]}...")
            self._send_json(200, {"id": job_id})
        except Exception as e:
            try:
                log.exception(f"Failed to accept Liberty fax: {e}")
            except Exception:
                pass
            self._send_json(500, {"error": "server_error"})

    def do_GET(self):  # noqa: N802
        log.debug(f"Liberty GET request: {self.path} from {self.address_string()}")
        path = self.path or ""
        # Normalize path for matching: remove leading/trailing slashes and query string
        parsed_url = urlparse(path)
        clean_path = parsed_url.path.strip("/")
        
        if clean_path == "liberty/fax":
            log.warning(f"Liberty GET: method not allowed on '{path}' from {self.address_string()}")
            self._send_json(405, {"error": "method_not_allowed", "message": "Use POST to send faxes"})
            return

        job_id = ""
        # Handle /liberty/faxstatus/12345
        if clean_path.startswith("liberty/faxstatus/"):
            job_id = clean_path[len("liberty/faxstatus/") :].strip()
        # Handle /liberty/faxstatus?id=12345
        elif clean_path == "liberty/faxstatus":
            try:
                qs = parse_qs(parsed_url.query or "")
                # Case-insensitive query parameter lookup
                norm_qs = {k.lower(): v for k, v in qs.items()}
                job_id = (norm_qs.get("id") or [""])[0].strip()
            except Exception:
                job_id = ""
        
        if not clean_path.startswith("liberty/faxstatus"):
            log.warning(f"Liberty GET: invalid path '{path}' from {self.address_string()}")
            self._send_json(404, {"error": "not_found"})
            return
        if not job_id:
            log.warning(f"Liberty GET: missing id in query from {self.address_string()}")
            self._send_json(400, {"error": "missing_id"})
            return
        try:
            store: LibertyStore = getattr(self.server, "store")  # type: ignore[assignment]
            job = store.get_job(job_id)
            if not job:
                log.warning(f"Liberty GET: job {job_id} not found for {self.address_string()}")
                self._send_json(404, {"error": "not_found"})
                return
            payload = {"status": job.status}
            if job.message:
                payload["message"] = job.message
            self._send_json(200, payload)
        except Exception as e:
            try:
                log.exception(f"Status lookup failed for {job_id} from {self.address_string()}: {e}")
            except Exception:
                pass
            self._send_json(500, {"error": "server_error"})

    # Silence default logging to stderr
    def log_message(self, format: str, *args):  # noqa: A003
        try:
            log.debug("HTTP %s - %s", self.address_string(), format % args)
        except Exception:
            pass


class LibertyRxListener:
    def __init__(self, host: str, port: int, store: LibertyStore, max_pdf_bytes: int = 25 * 1024 * 1024, retention_hours: int = 72):
        self.host = host
        self.port = port
        self.store = store
        self.max_pdf_bytes = max_pdf_bytes
        self.retention_hours = retention_hours
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._server:
            return
        server = ThreadingHTTPServer((self.host, self.port), _LibertyHandler)
        # Attach shared state
        setattr(server, "store", self.store)
        setattr(server, "max_pdf_bytes", int(self.max_pdf_bytes))
        setattr(server, "retention_hours", int(self.retention_hours))
        self._server = server
        self._thread = threading.Thread(target=server.serve_forever, name=f"LibertyRxListener:{self.port}", daemon=True)
        self._thread.start()
        log.info(f"LibertyRx listener started on {self.host}:{self.port}")

    def stop(self):
        try:
            if self._server:
                self._server.shutdown()
                self._server.server_close()
        except Exception:
            pass
        finally:
            self._server = None
            self._thread = None
            log.info("LibertyRx listener stopped")
