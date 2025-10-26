import inspect
import traceback
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config import COL_AUDIT_LOGS, COL_LOGS, DB_NAME, MONGO_URI
from pymongo import MongoClient

# MongoDB clients and collections (keep server selection fast to avoid startup stalls)
mongo_client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=1500)
log_db = mongo_client[DB_NAME]
log_collection = log_db[COL_LOGS]
audit_collection = log_db[COL_AUDIT_LOGS]

# def log_event(
#     event_type: str,
#     *,
#     domain_uuid: str = None,
#     device_id: str = None,
#     ip: str = None,
#     note: str = ""
# ):
#     """
#     Baseline event logger (compatibility layer).
#     """
#     entry = {
#         "timestamp": datetime.now(timezone.utc).isoformat(),
#         "event_type": event_type,
#         "domain_uuid": domain_uuid,
#         "device_id": device_id,
#         "source_ip": ip,
#         "note": note
#     }
#     log_collection.insert_one(entry)


def log_event_v2(
    event_type: str,
    *,
    domain_uuid: str = None,
    device_id: str = None,
    ip: str = None,
    note: str = "",
    actor_component: str = None,
    actor_function: str = None,
    object_type: str = None,
    object_operation: str = None,
    payload: dict = None,
    request_id: str = None,
    audit: bool = False,
):
    """
    High-fidelity structured logger for operational and audit logs.
    """
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event_type": event_type,
        "domain_uuid": domain_uuid,
        "device_id": device_id,
        "source_ip": ip,
        "note": note,
    }

    if actor_component or actor_function or request_id:
        event["actor"] = {
            "component": actor_component,
            "function": actor_function,
            "request_id": request_id or str(uuid4()),
        }

    if object_type or object_operation or payload:
        event["object"] = {
            "type": object_type,
            "operation": object_operation,
            "payload": payload or {},
        }

    collection = audit_collection if audit else log_collection
    collection.insert_one(event)


def summarize_log(event_type: str, limit: int = 100):
    return list(
        log_collection.find({"event_type": event_type})
        .sort("timestamp", -1)
        .limit(limit)
    )


def recent_events(domain_uuid: str, limit: int = 50):
    return list(
        log_collection.find({"domain_uuid": domain_uuid})
        .sort("timestamp", -1)
        .limit(limit)
    )


def delete_events_older_than(days: int = 365):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    log_collection.delete_many({"timestamp": {"$lt": cutoff.isoformat()}})
    audit_collection.delete_many({"timestamp": {"$lt": cutoff.isoformat()}})


def auto_log_event(
    event_type: str,
    *,
    domain_uuid: str = None,
    note: str = "",
    object_type: str = None,
    object_operation: str = None,
    payload: dict = None,
    audit: bool = False,
):
    """
    Decorator to auto-log entry and exit from functions with full traceability.
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            frame = inspect.currentframe().f_back
            module = frame.f_globals.get("__name__", "unknown")
            function = func.__name__
            request_id = str(uuid4())

            log_event_v2(
                event_type=event_type,
                domain_uuid=domain_uuid,
                note=f"ENTRY: {note}",
                actor_component=module,
                actor_function=function,
                object_type=object_type,
                object_operation=object_operation,
                payload=payload,
                request_id=request_id,
                audit=audit,
            )

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                log_event_v2(
                    event_type=f"{event_type}_error",
                    domain_uuid=domain_uuid,
                    note=f"ERROR: {str(e)}",
                    actor_component=module,
                    actor_function=function,
                    object_type=object_type,
                    object_operation="exception",
                    payload={"traceback": traceback.format_exc()},
                    request_id=request_id,
                    audit=True,
                )
                raise

            log_event_v2(
                event_type=event_type,
                domain_uuid=domain_uuid,
                note=f"EXIT: {note}",
                actor_component=module,
                actor_function=function,
                object_type=object_type,
                object_operation=object_operation,
                payload=payload,
                request_id=request_id,
                audit=audit,
            )
            return result

        return wrapper

    return decorator
