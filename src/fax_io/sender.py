"""
Handles outbound fax transmission using SkySwitch API.
Builds payload, generates cover sheet, and sends attachments as multipart/form.
"""

import os
import tempfile

import requests

from core.app_state import app_state
from utils.document_utils import generate_cover_sheet_pdf, normalize_pdf
from utils.logging_utils import get_logger

log = get_logger("send_client")


class FaxSender:
    @staticmethod
    def send_fax(
        base_dir, recipient: str, attachments: list, include_cover: bool
    ) -> bool:
        """
        Sends a fax to the specified recipient with optional cover sheet.

        Args:
            base_dir (str): Application base directory (MEIPASS-aware)
            recipient (str): Phone number of the recipient
            attachments (list): List of file paths
            include_cover (bool): Whether to prepend a generated cover sheet

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

        temp_handles = []
        temp_paths = []
        try:
            # Build multipart "filename[i]" parts expected by v1 API
            files = {}
            working_dir = tempfile.gettempdir()

            # Resolve fax_user for API (prefer full ext@domain if stored)
            fax_user = (
                getattr(app_state.global_cfg, "fax_user", None)
                or app_state.global_cfg.fax_user
            )

            # Sanitize numbers
            dest_digits = "".join(ch for ch in (recipient or "") if ch.isdigit())
            caller_raw = app_state.device_cfg.selected_fax_number or (
                app_state.global_cfg.all_numbers[0]
                if app_state.global_cfg.all_numbers
                else ""
            )
            caller_digits = "".join(ch for ch in (caller_raw or "") if ch.isdigit())

            # Attachments are provided by UI (SendFaxPanel), which has already
            # inserted the user-designed cover sheet at index 0 when enabled.
            # Do not auto-generate any cover here.
            file_index = 0

            # Add attachments (normalize PDFs)
            for path in attachments:
                normalized = normalize_pdf(path)
                if os.path.exists(normalized):
                    # Track temp normalized PDFs for cleanup (only if different from original and in temp dir)
                    try:
                        if normalized != path and normalized.startswith(
                            tempfile.gettempdir()
                        ):
                            temp_paths.append(normalized)
                    except Exception:
                        pass

                    mime = (
                        "application/pdf"
                        if normalized.lower().endswith(".pdf")
                        else "application/octet-stream"
                    )
                    fh = open(normalized, "rb")
                    files[f"filename[{file_index}]"] = (
                        os.path.basename(normalized),
                        fh,
                        mime,
                    )
                    temp_handles.append(fh)
                    file_index += 1
                else:
                    log.warning(f"Attachment missing: {path}")

            # v1 endpoint and payload
            endpoint = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
            headers = {"Authorization": f"Bearer {app_state.global_cfg.bearer_token}"}
            data = {"caller_id": caller_digits, "destination": dest_digits}

            log.info(
                f"Sending fax to {dest_digits} from {caller_digits} with {len(files)} attachment(s) -> {endpoint}"
            )
            response = requests.post(
                endpoint, data=data, files=files, headers=headers, timeout=60
            )

            if response.status_code == 200:
                log.info("Fax sent successfully.")
                return True
            else:
                log.error(f"Fax send failed: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            log.exception("Unexpected error sending fax")
            return False
        finally:
            # Close all opened file handles and delete temporary normalized files
            try:
                for fh in temp_handles:
                    try:
                        fh.close()
                    except Exception:
                        log.debug("Failed to close temporary file handle", exc_info=True)
            except Exception:
                log.debug("Error while closing temporary file handles", exc_info=True)

            for tmp in temp_paths:
                try:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                except Exception:
                    # Do not raise; log at debug level to avoid noise, but record details
                    log.debug(f"Failed to remove temp file: {tmp}", exc_info=True)
