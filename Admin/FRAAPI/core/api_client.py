# Admin/licensing_server/core/api_client.py
# Thin HTTP client used by FRA GUI to talk to FRAAPI. This keeps the GUI from touching MongoDB.

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

DEFAULT_BASE_URL = os.environ.get(
    "FRAAPI_BASE_URL", "https://licensing.clinicnetworking.com"
).rstrip("/")
ADMIN_KEY = os.environ.get("ADMIN_API_KEY")
TIMEOUT = 10


class ApiClient:
    def __init__(self, base_url: Optional[str] = None, admin_key: Optional[str] = None):
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.admin_key = admin_key if admin_key is not None else ADMIN_KEY

    def _headers(self) -> Dict[str, str]:
        headers = {"accept": "application/json"}
        if self.admin_key:
            headers["X-Admin-Key"] = self.admin_key
        return headers

    def ping(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            if r.status_code == 200:
                return True
            return False
        except Exception:
            return False

    # ---- Clients ----
    def list_clients(self) -> List[Dict[str, Any]]:
        r = requests.get(
            f"{self.base_url}/admin/clients", headers=self._headers(), timeout=TIMEOUT
        )
        r.raise_for_status()
        return r.json()

    def save_client(
        self, fax_user: str, authentication_token: str, all_fax_numbers: List[str]
    ) -> str:
        payload = {
            "fax_user": fax_user,
            "authentication_token": authentication_token,
            "all_fax_numbers": all_fax_numbers,
        }
        r = requests.post(
            f"{self.base_url}/admin/clients",
            json=payload,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("domain_uuid", "")

    def toggle_client_active(self, domain_uuid: str) -> bool:
        r = requests.post(
            f"{self.base_url}/admin/clients/{domain_uuid}/toggle_active",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return bool(r.json().get("success"))

    def delete_client(self, domain_uuid: str) -> bool:
        r = requests.delete(
            f"{self.base_url}/admin/clients/{domain_uuid}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return bool(r.json().get("success"))

    def get_known_devices(self, domain_uuid: str) -> List[str]:
        r = requests.get(
            f"{self.base_url}/admin/clients/{domain_uuid}/devices",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("devices", [])

    def get_cached_bearer(self, fax_user: str) -> Dict[str, Any]:
        r = requests.get(
            f"{self.base_url}/admin/clients/{fax_user}/bearer",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json() or {}

    def update_assignments(self, fax_user: str, assignments: Dict[str, Any]) -> bool:
        payload = {"assignments": assignments}
        r = requests.post(
            f"{self.base_url}/admin/clients/{fax_user}/assignments",
            json=payload,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return bool(r.json().get("success"))

    def get_fax_numbers(self, domain_uuid: str) -> List[str]:
        r = requests.get(
            f"{self.base_url}/admin/clients/{domain_uuid}/numbers",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json().get("numbers", [])

    # ---- Resellers ----
    def list_resellers(self) -> List[Dict[str, Any]]:
        r = requests.get(
            f"{self.base_url}/admin/resellers", headers=self._headers(), timeout=TIMEOUT
        )
        r.raise_for_status()
        return r.json()

    def get_reseller_blob(self, reseller_id: str) -> Optional[Dict[str, Any]]:
        r = requests.get(
            f"{self.base_url}/admin/resellers/{reseller_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json().get("encrypted_blob")

    def save_reseller(self, reseller_id: str, data: Dict[str, Any]) -> bool:
        payload = {"reseller_id": reseller_id, "data": data}
        r = requests.post(
            f"{self.base_url}/admin/resellers",
            json=payload,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return bool(r.json().get("success"))

    def delete_reseller(self, reseller_id: str) -> bool:
        r = requests.delete(
            f"{self.base_url}/admin/resellers/{reseller_id}",
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return bool(r.json().get("success"))

    # ---- Logs ----
    def get_log_event_types(self, collection: str = "access_logs") -> List[str]:
        params = {"collection": collection}
        r = requests.get(
            f"{self.base_url}/admin/logs/types",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json() or {}
        return data.get("event_types", [])

    def get_logs(
        self,
        collection: str = "access_logs",
        event_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"collection": collection, "limit": int(limit or 200)}
        if event_type and event_type != "<All>":
            params["event_type"] = event_type
        r = requests.get(
            f"{self.base_url}/admin/logs",
            params=params,
            headers=self._headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        data = r.json() or {}
        return data.get("entries", [])

    # ---- Bulk update helpers for full refreshes ----
    def update_all_clients(self) -> List[Dict[str, Any]]:
        """Return full client records with aggregated extras when supported by server.
        Falls back to list_clients() if the bulk endpoint is unavailable."""
        try:
            r = requests.get(
                f"{self.base_url}/admin/clients/full",
                headers=self._headers(),
                timeout=TIMEOUT,
            )
            if r.status_code == 200:
                return r.json() or []
        except Exception:
            pass
        return self.list_clients()

    def update_all_resellers(self) -> List[Dict[str, Any]]:
        """Return all resellers (wrapper for future flexibility)."""
        return self.list_resellers()

    def update_all_logs(
        self,
        collection: str = "access_logs",
        event_type: Optional[str] = None,
        limit: int = 200,
    ) -> List[Dict[str, Any]]:
        """Return logs (wrapper for future flexibility)."""
        return self.get_logs(collection=collection, event_type=event_type, limit=limit)
