import requests
from PyQt5.QtCore import QThread, pyqtSignal


class RetrieveFaxesThread(QThread):
    finished = pyqtSignal(list)

    def __init__(self, fax_user, bearer_token, inbound_page: int = 1, outbound_page: int = 1):
        super().__init__()
        self.fax_user = fax_user
        self.bearer_token = bearer_token
        self.inbound_page = inbound_page
        self.outbound_page = outbound_page
        # Exposed after run to support lazy-loading
        self.next_inbound_page = None
        self.next_outbound_page = None

    def run(self):
        if not self.fax_user or not self.bearer_token:
            self.finished.emit([])
            return

        try:
            base_url = "https://telco-api.skyswitch.com"
            inbound_url = f"{base_url}/users/{self.fax_user}/faxes/inbound"
            outbound_url = f"{base_url}/users/{self.fax_user}/faxes/outbound"
            # Append page parameters for lazy loading
            if self.inbound_page and self.inbound_page > 1:
                inbound_url += f"?page={self.inbound_page}"
            if self.outbound_page and self.outbound_page > 1:
                outbound_url += f"?page={self.outbound_page}"
            headers = {"accept": "application/json", "Authorization": f"Bearer {self.bearer_token}"}
            faxes = []

            inbound_json = None
            outbound_json = None

            inbound_response = requests.get(inbound_url, headers=headers, timeout=10)
            if inbound_response.status_code == 200:
                try:
                    inbound_json = inbound_response.json()
                except Exception:
                    inbound_json = {"error": "invalid_json", "text": inbound_response.text}
                inbound_faxes = (inbound_json or {}).get("data", [])
                for fax in inbound_faxes:
                    fax["direction"] = "Inbound"
                faxes.extend(inbound_faxes)
                # Next page calc
                try:
                    meta = (inbound_json or {}).get("meta") or {}
                    cur = int(meta.get("current_page") or self.inbound_page or 1)
                    last = int(meta.get("last_page") or cur)
                    self.next_inbound_page = (cur + 1) if cur < last else None
                except Exception:
                    self.next_inbound_page = None

            outbound_response = requests.get(outbound_url, headers=headers, timeout=10)
            if outbound_response.status_code == 200:
                try:
                    outbound_json = outbound_response.json()
                except Exception:
                    outbound_json = {"error": "invalid_json", "text": outbound_response.text}
                outbound_faxes = (outbound_json or {}).get("data", [])
                for fax in outbound_faxes:
                    fax["direction"] = "Outbound"
                faxes.extend(outbound_faxes)
                # Next page calc
                try:
                    meta = (outbound_json or {}).get("meta") or {}
                    cur = int(meta.get("current_page") or self.outbound_page or 1)
                    last = int(meta.get("last_page") or cur)
                    self.next_outbound_page = (cur + 1) if cur < last else None
                except Exception:
                    self.next_outbound_page = None

            # Sort newest-first by created_at
            try:
                faxes.sort(key=lambda x: x.get("created_at", ""), reverse=True)
            except Exception:
                pass

            self.finished.emit(faxes)
        except Exception as e:
            print(f"Error retrieving faxes: {str(e)}")
            self.finished.emit([])
