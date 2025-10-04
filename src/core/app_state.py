# app_state.py — Runtime memory cache for all operational config/state

from datetime import datetime, timezone
from typing import List, Optional

from core.config_loader import device_config, global_config
from utils.logging_utils import get_logger


class GlobalState:
    def __init__(self):
        self.fax_user: Optional[str] = None
        self.authentication_token: Optional[str] = None
        self.domain_uuid: Optional[str] = None
        self.validation_status: bool = False

        self.jwt_token: Optional[str] = None
        self.bearer_token: Optional[str] = None
        self.bearer_token_retrieved: Optional[str] = None
        self.bearer_token_expiration: Optional[str] = None

        self.all_numbers: List[str] = []
        self.integration_settings: dict = {}
        self.logging_level: Optional[str] = None

    def load_from(self, cfg):
        self.fax_user = cfg.get("Account", "fax_user")
        self.authentication_token = cfg.get("Account", "authentication_token")
        self.domain_uuid = cfg.get("Account", "domain_uuid")
        self.validation_status = cfg.get("Account", "validation_status", False)

        self.jwt_token = cfg.get("Token", "jwt_token")
        self.bearer_token = cfg.get("Token", "bearer_token")
        self.bearer_token_retrieved = cfg.get("Token", "bearer_token_retrieved")
        self.bearer_token_expiration = cfg.get("Token", "bearer_token_expires_at")

        numbers_raw = cfg.get("Account", "all_fax_numbers", [])
        if isinstance(numbers_raw, str):
            self.all_numbers = [n.strip() for n in numbers_raw.split(",") if n.strip()]
        elif isinstance(numbers_raw, list):
            self.all_numbers = numbers_raw

        self.integration_settings = cfg.get("Integrations", "integration_settings", {})
        self.logging_level = cfg.get("UserSettings", "logging_level")


class DeviceState:
    def __init__(self):
        self.retriever_status: Optional[str] = None
        self.retriever_mode: Optional[str] = None
        self.selected_fax_number: Optional[str] = None
        self.selected_fax_numbers: list[str] = []

        # Only loaded if retriever_mode == sender_receiver
        self.save_path: Optional[str] = None
        self.download_method: Optional[str] = None
        self.file_name_format: Optional[str] = None
        self.polling_frequency: Optional[int] = None
        self.print_faxes: Optional[str] = None
        self.printer_name: Optional[str] = None
        self.delete_faxes: Optional[str] = None
        self.archive_enabled: Optional[str] = None
        self.archive_duration: Optional[str] = None
        self.notifications_enabled: Optional[str] = None
        self.close_to_tray: Optional[str] = None
        self.start_with_system: Optional[str] = None
        # Integrations
        self.integration_settings: dict = {}
        self.winrx_path: Optional[str] = None

    def load_from(self, cfg):
        self.retriever_status = cfg.get("Token", "retriever_status", "denied")
        self.retriever_mode = cfg.get("Account", "retriever_mode", "sender")
        self.selected_fax_number = cfg.get("Account", "selected_fax_number")
        nums = cfg.get("Account", "selected_fax_numbers", [])
        if isinstance(nums, list):
            self.selected_fax_numbers = [str(n).strip() for n in nums if str(n).strip()]
        elif isinstance(nums, str) and nums.strip():
            # tolerate old stray string values
            self.selected_fax_numbers = [nums.strip()]
        else:
            self.selected_fax_numbers = (
                [self.selected_fax_number] if self.selected_fax_number else []
            )

        # Always hydrate fax options so OptionsDialog and runtime have full config after restart
        self.save_path = cfg.get("Fax Options", "save_path", "")
        self.download_method = cfg.get("Fax Options", "download_method", "PDF")
        self.file_name_format = cfg.get("Fax Options", "file_name_format")
        self.polling_frequency = int(
            cfg.get("Fax Options", "polling_frequency", 15) or 15
        )
        self.print_faxes = cfg.get("Fax Options", "print_faxes", "No")
        self.delete_faxes = cfg.get("Fax Options", "delete_faxes", "No")
        # With archival checkbox removed, default to Yes to keep consistent behavior
        self.archive_enabled = cfg.get("Fax Options", "archive_enabled", "Yes")
        self.archive_duration = cfg.get("Fax Options", "archive_duration", "30")
        self.printer_name = cfg.get("Fax Options", "printer_name", "")
        self.notifications_enabled = cfg.get(
            "Fax Options", "notifications_enabled", "Yes"
        )
        self.close_to_tray = cfg.get("Fax Options", "close_to_tray", "No")
        self.start_with_system = cfg.get("Fax Options", "start_with_system", "No")
        # Integrations
        self.integration_settings = (
            cfg.get("Integrations", "integration_settings", {}) or {}
        )
        self.winrx_path = cfg.get("Integrations", "winrx_path", "") or ""


class AppState:
    def __init__(self):
        self.log = get_logger("state")
        self.global_cfg = GlobalState()
        self.device_cfg = DeviceState()
        self.sync_from_config()

    def sync_from_config(self):
        self.global_cfg.load_from(global_config)
        self.device_cfg.load_from(device_config)
        self.log.info("App state hydrated from global and device configs.")
        self.log.debug(
            f"User: {self.global_cfg.fax_user} | Mode: {self.device_cfg.retriever_mode} | Status: {self.device_cfg.retriever_status}"
        )

    def update_token_state(
        self, bearer_token: str, expires_at: str, fax_numbers: list[str]
    ):
        now = datetime.now(timezone.utc).isoformat()

        self.global_cfg.bearer_token = bearer_token
        self.global_cfg.bearer_token_expiration = expires_at
        self.global_cfg.bearer_token_retrieved = now
        self.global_cfg.all_numbers = fax_numbers

        global_config.set("Token", "bearer_token", bearer_token)
        global_config.set("Token", "bearer_token_expires_at", expires_at)
        global_config.set("Token", "bearer_token_retrieved", now)
        global_config.set("Account", "all_fax_numbers", fax_numbers)
        global_config.save()

    def update_save_path(self, new_path: str):
        self.device_cfg.save_path = new_path
        device_config.set("Fax Options", "save_path", new_path)
        device_config.save()


# Global instance
app_state = AppState()
