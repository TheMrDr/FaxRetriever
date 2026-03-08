"""Config RPC handlers: read/write device_config and global_config."""

from registry import register

# Import the actual config loaders from the existing codebase
try:
    from core.config_loader import device_config, global_config
    _CONFIG_AVAILABLE = True
except ImportError:
    _CONFIG_AVAILABLE = False


@register("get_config")
def get_config(params: dict) -> dict:
    """Read a config value. params: {source, section, key, fallback?}"""
    if not _CONFIG_AVAILABLE:
        return {"error": "Config not available in development mode"}

    source = params.get("source", "device")
    section = params.get("section", "")
    key = params.get("key", "")
    fallback = params.get("fallback")

    cfg = device_config if source == "device" else global_config
    value = cfg.get(section, key, fallback)
    return {"value": value}


@register("set_config")
def set_config(params: dict) -> dict:
    """Write a config value. params: {source, section, key, value}"""
    if not _CONFIG_AVAILABLE:
        return {"error": "Config not available in development mode"}

    source = params.get("source", "device")
    section = params.get("section", "")
    key = params.get("key", "")
    value = params.get("value")

    cfg = device_config if source == "device" else global_config
    cfg.set(section, key, value)
    cfg.save()
    return {"ok": True}


@register("get_settings")
def get_settings(params: dict) -> dict:
    """Return all user-facing settings for the Options dialog."""
    if not _CONFIG_AVAILABLE:
        return {"error": "Config not available in development mode"}

    return {
        "fax_user": global_config.get("Account", "fax_user", ""),
        "polling_frequency": int(device_config.get("Fax Options", "polling_frequency", 5) or 5),
        "download_method": device_config.get("Fax Options", "download_method", "PDF"),
        "file_name_format": device_config.get("Fax Options", "file_name_format", "cid"),
        "save_path": device_config.get("Fax Options", "save_path", ""),
        "print_faxes": device_config.get("Fax Options", "print_faxes", "No") == "Yes",
        "printer_name": device_config.get("Fax Options", "printer_name", ""),
        "notifications_enabled": device_config.get("Fax Options", "notifications_enabled", "Yes") == "Yes",
        "close_to_tray": device_config.get("Fax Options", "close_to_tray", "No") == "Yes",
        "theme": device_config.get("UserSettings", "theme", "light"),
        "logging_level": global_config.get("UserSettings", "logging_level", "Debug"),
        "integration_enabled": bool(
            (global_config.get("Integrations", "integration_settings") or {}).get("enable_third_party")
        ),
        "integration_software": (global_config.get("Integrations", "integration_settings") or {}).get(
            "integration_software", ""
        ),
        "libertyrx_enabled": device_config.get("Integrations", "libertyrx_enabled", "No") == "Yes",
        "libertyrx_port": int(device_config.get("Integrations", "libertyrx_port", 18761) or 18761),
    }


@register("save_settings")
def save_settings(params: dict) -> dict:
    """Save user settings from the Options dialog."""
    if not _CONFIG_AVAILABLE:
        return {"error": "Config not available in development mode"}

    settings = params.get("settings", {})

    # Device config
    for key, cfg_key in [
        ("polling_frequency", ("Fax Options", "polling_frequency")),
        ("download_method", ("Fax Options", "download_method")),
        ("file_name_format", ("Fax Options", "file_name_format")),
        ("printer_name", ("Fax Options", "printer_name")),
    ]:
        if key in settings:
            device_config.set(cfg_key[0], cfg_key[1], str(settings[key]))

    # Boolean settings
    for key, cfg_key in [
        ("print_faxes", ("Fax Options", "print_faxes")),
        ("notifications_enabled", ("Fax Options", "notifications_enabled")),
        ("close_to_tray", ("Fax Options", "close_to_tray")),
    ]:
        if key in settings:
            device_config.set(cfg_key[0], cfg_key[1], "Yes" if settings[key] else "No")

    if "theme" in settings:
        device_config.set("UserSettings", "theme", settings["theme"])

    if "logging_level" in settings:
        global_config.set("UserSettings", "logging_level", settings["logging_level"])
        global_config.save()

    device_config.save()
    return {"ok": True}
