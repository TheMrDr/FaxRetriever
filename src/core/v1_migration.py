import configparser
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Tuple

try:
    import winreg as reg  # type: ignore
except Exception:  # Non-Windows environments
    reg = None  # type: ignore

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None  # type: ignore

from core.config_loader import device_config, global_config
from utils.logging_utils import get_logger

log = get_logger("v1_migration")

# v1 locations/config
V1_APP_DIR = os.path.join(os.getenv("LOCALAPPDATA") or "", "CN-FaxRetriever")
V1_INI_PATH = os.path.join(V1_APP_DIR, "config.ini")
V1_REG_PATH = r"Software\Clinic Networking, LLC"
V1_REG_VALUE = "FaxRetriever"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_v1_encryption_key() -> str | None:
    if reg is None:
        return None
    try:
        with reg.OpenKey(reg.HKEY_CURRENT_USER, V1_REG_PATH, 0, reg.KEY_READ) as key:
            val, _ = reg.QueryValueEx(key, V1_REG_VALUE)
            if isinstance(val, str) and val:
                return val
    except FileNotFoundError:
        return None
    except Exception as e:
        log.debug(f"Failed to read v1 encryption key: {e}")
    return None


def _decrypt_v1_ini(enc_key: str, ini_path: str) -> Dict[str, Dict[str, str]] | None:
    if Fernet is None:
        log.warning("cryptography.fernet not available; cannot import v1 settings.")
        return None
    try:
        cfg = configparser.ConfigParser()
        if not os.path.exists(ini_path):
            return None
        cfg.read(ini_path)
        fernet = Fernet(enc_key.encode())
        data: Dict[str, Dict[str, str]] = {}
        for section in cfg.sections():
            data[section] = {}
            for option in cfg.options(section):
                try:
                    enc_val = cfg.get(section, option)
                    dec_val = fernet.decrypt(enc_val.encode()).decode()
                except Exception:
                    # Some entries might be stored in plain (rare); fall back
                    try:
                        dec_val = cfg.get(section, option)
                    except Exception:
                        dec_val = ""
                data[section][option] = dec_val
        return data
    except Exception as e:
        log.exception(f"Failed to decrypt v1 INI: {e}")
        return None


def _map_v1_to_v2(
    v1: Dict[str, Dict[str, str]]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns (global_updates, device_updates)
    Sensitive credentials from v1 Account section are intentionally excluded.
    """
    g: Dict[str, Any] = {}
    d: Dict[str, Any] = {}

    # Global: Account
    acc = v1.get("Account", {})
    fax_user = (acc.get("fax_user") or "").strip()
    if fax_user:
        g.setdefault("Account", {})["fax_user"] = fax_user

    # Global: UserSettings.logging_level
    usr = v1.get("UserSettings", {})
    logging_level = (usr.get("logging_level") or "").strip()
    if logging_level:
        g.setdefault("UserSettings", {})["logging_level"] = logging_level

    # Device: Fax Options mapping
    fax = v1.get("Fax Options", {})
    # v1 stored save_path under UserSettings.save_path
    save_path = (usr.get("save_path") or "").strip()
    if save_path:
        d.setdefault("Fax Options", {})["save_path"] = save_path
    # Direct mappings
    for k in [
        "download_method",
        "delete_faxes",
        "print_faxes",
        "printer_name",
        "archive_enabled",
        "archive_duration",
        "file_name_format",
    ]:
        val = (fax.get(k) or "").strip()
        if val != "":
            d.setdefault("Fax Options", {})[k] = val

    # Device: Integrations mapping
    integ = v1.get("Integrations", {})
    integration_enabled = (integ.get("integration_enabled") or "").strip()
    software_integration = (integ.get("software_integration") or "").strip() or "None"
    winrx_path = (integ.get("winrx_path") or "").strip()

    # Normalize to v2 structure: integration_settings dict and winrx_path
    integration_settings = {
        "enable_third_party": (
            "Yes" if integration_enabled.lower() in ("yes", "true", "1") else "No"
        ),
        "integration_software": (
            software_integration if software_integration else "None"
        ),
    }
    d.setdefault("Integrations", {})["integration_settings"] = integration_settings
    if winrx_path:
        d.setdefault("Integrations", {})["winrx_path"] = winrx_path

    # Device: Optional UI preferences (not present in v1 defaults except maybe notifications)
    notif = (fax.get("notifications_enabled") or "").strip()
    if notif:
        d.setdefault("Fax Options", {})["notifications_enabled"] = notif

    return g, d


def _apply_updates(g_updates: Dict[str, Any], d_updates: Dict[str, Any]) -> None:
    # Merge updates into loaders and save
    try:
        for section, kv in g_updates.items():
            for k, v in kv.items():
                global_config.set(section, k, v)
        global_config.save()
    except Exception:
        log.exception("Failed to save global config during migration")
    try:
        for section, kv in d_updates.items():
            for k, v in kv.items():
                device_config.set(section, k, v)
        # Mark migration
        device_config.set("Migration", "v1_migrated", True)
        device_config.set("Migration", "migrated_at", _utc_now_iso())
        device_config.save()
    except Exception:
        log.exception("Failed to save device config during migration")


def _cleanup_v1_artifacts() -> None:
    # Delete v1 registry value and directory; be conservative
    try:
        if reg is not None:
            try:
                with reg.OpenKey(
                    reg.HKEY_CURRENT_USER, V1_REG_PATH, 0, reg.KEY_SET_VALUE
                ) as key:
                    try:
                        reg.DeleteValue(key, V1_REG_VALUE)
                        log.info("Removed v1 registry encryption value.")
                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        log.warning(f"Failed to delete v1 registry value: {e}")
            except FileNotFoundError:
                pass
            except Exception as e:
                log.warning(f"Unable to open registry for cleanup: {e}")
    except Exception:
        log.debug("Registry cleanup skipped.")

    try:
        if os.path.isdir(V1_APP_DIR):
            # Remove only files inside; then attempt to remove dir
            for root, dirs, files in os.walk(V1_APP_DIR, topdown=False):
                for name in files:
                    try:
                        os.remove(os.path.join(root, name))
                    except Exception:
                        pass
                for name in dirs:
                    try:
                        os.rmdir(os.path.join(root, name))
                    except Exception:
                        pass
            try:
                os.rmdir(V1_APP_DIR)
            except Exception:
                pass
            log.info("Removed v1 configuration directory.")
    except Exception as e:
        log.warning(f"Failed to remove v1 app directory: {e}")


def migrate_v1_if_present() -> bool:
    """
    Attempts to migrate v1 settings into v2 JSON configs.
    Returns True if a migration occurred (successfully applied at least some values), False otherwise.
    """
    try:
        if device_config.get("Migration", "v1_migrated", False):
            return False
        # Only on Windows and only if artifacts exist
        if sys.platform != "win32":
            return False
        if not os.path.exists(V1_INI_PATH):
            return False
        enc_key = _read_v1_encryption_key()
        if not enc_key:
            log.warning("v1 encryption key not found; cannot import v1 settings.")
            return False
        v1_data = _decrypt_v1_ini(enc_key, V1_INI_PATH)
        if not v1_data:
            return False
        # Map and apply
        g, d = _map_v1_to_v2(v1_data)
        # Ensure we explicitly drop sensitive credentials by never copying them
        # from v1 Account: api_username, api_password, client_id, client_secret
        _apply_updates(g, d)
        # Cleanup artifacts
        _cleanup_v1_artifacts()
        log.info("v1 settings migration completed.")
        return True
    except Exception as e:
        log.exception(f"v1 migration failed: {e}")
        return False
