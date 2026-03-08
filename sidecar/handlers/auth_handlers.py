"""Auth/license RPC handlers."""

from registry import register, emit_event

# Import existing auth modules
try:
    from core.app_state import app_state
    from core.license_client import initialize_session, retrieve_skyswitch_token
    from core.config_loader import device_config, global_config
    _AUTH_AVAILABLE = True
except ImportError:
    _AUTH_AVAILABLE = False


@register("get_app_state")
def get_app_state_handler(params: dict) -> dict:
    """Return current app state for the frontend to render."""
    if not _AUTH_AVAILABLE:
        return {
            "ready": False,
            "fax_user": "",
            "retriever_mode": "limited",
            "validation_status": False,
            "has_bearer_token": False,
            "selected_fax_numbers": [],
            "all_fax_numbers": [],
            "save_path": "",
        }

    return {
        "ready": True,
        "fax_user": app_state.global_cfg.fax_user or "",
        "retriever_mode": app_state.device_cfg.retriever_mode or "limited",
        "validation_status": app_state.global_cfg.validation_status,
        "has_bearer_token": bool(app_state.global_cfg.bearer_token),
        "bearer_token_expires": app_state.global_cfg.bearer_token_expires_at or "",
        "selected_fax_numbers": app_state.device_cfg.selected_fax_numbers or [],
        "all_fax_numbers": app_state.global_cfg.all_fax_numbers or [],
        "save_path": app_state.device_cfg.save_path or "",
    }


@register("initialize_session")
def handle_initialize_session(params: dict) -> dict:
    """Initialize a new session with the licensing server."""
    if not _AUTH_AVAILABLE:
        return {"error": "Auth modules not available"}

    try:
        domain = params.get("domain", "")
        token = params.get("token", "")
        result = initialize_session(app_state, domain, token)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@register("retrieve_token")
def handle_retrieve_token(params: dict) -> dict:
    """Retrieve a fresh SkySwitch bearer token."""
    if not _AUTH_AVAILABLE:
        return {"error": "Auth modules not available"}

    try:
        result = retrieve_skyswitch_token(app_state)
        if result:
            emit_event("token_refreshed", {
                "bearer_token_expires": app_state.global_cfg.bearer_token_expires_at,
            })
            return {"ok": True}
        return {"ok": False, "error": "Token retrieval returned no result"}
    except Exception as e:
        return {"ok": False, "error": str(e)}
