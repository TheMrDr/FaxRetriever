import base64

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from SaveManager import SaveManager
from SystemLog import SystemLog


class LibertyRxIntegration(QThread):
    finished = pyqtSignal(str, str)  # status, message

    def __init__(self, from_number, pdf_path, main_window=None):
        super().__init__()
        self.from_number = from_number
        self.pdf_path = pdf_path
        self.main_window = main_window

        self.save_manager = SaveManager(main_window)
        self.log_system = SystemLog()

    def run(self):
        try:
            # Get credentials and config
            vendor_username = self.save_manager.get_config_value("Liberty", "vendor_username")
            vendor_password = self.save_manager.get_config_value("Liberty", "vendor_password")
            pharmacy_npi = self.save_manager.get_config_value("Liberty", "pharmacy_npi")
            pharmacy_key = self.save_manager.get_config_value("Liberty", "pharmacy_key")

            if not all([vendor_username, vendor_password, pharmacy_npi, pharmacy_key]):
                self.finished.emit("Failure", "Missing Liberty credentials or pharmacy info.")
                return

            # Set endpoint (True = Dev Environment, False = Production Environment)
            use_dev = True
            if use_dev:
                url = "https://devapi.libertysoftware.com/fax"
            else:
                url = "https://api.libertysoftware.com/fax"

            # Build headers
            auth_token = base64.b64encode(f"{vendor_username}:{vendor_password}".encode()).decode()
            customer_token = base64.b64encode(f"{pharmacy_npi}:{pharmacy_key}".encode()).decode()

            headers = {
                "Authorization": f"Basic {auth_token}",
                "Customer": customer_token,
                "Content-Type": "application/json"
            }

            # Encode the PDF
            with open(self.pdf_path, "rb") as f:
                encoded_pdf = base64.b64encode(f.read()).decode("utf-8")

            payload = {
                "FromNumber": int(self.from_number),
                "ContentType": "application/pdf",
                "FileData": encoded_pdf
            }

            # Send the request
            response = requests.post(url, json=payload, headers=headers)

            if response.status_code == 200:
                self.log_system.log_message("info", f"Successfully delivered fax to Liberty Rx from {self.from_number}")
                self.finished.emit("Success", "Fax delivered to Liberty Rx.")
            elif response.status_code == 401:
                self.log_system.log_message("error", f"Unauthorized - Check Liberty credentials or Customer header.")
                self.finished.emit("Failure", "Unauthorized (401) - Check Liberty credentials.")
            else:
                self.log_system.log_message("error", f"Liberty Rx API error {response.status_code}: {response.text}")
                self.finished.emit("Failure", f"API error: {response.status_code} - {response.text}")

        except Exception as e:
            self.log_system.log_message("error", f"Exception in LibertyRxIntegration: {e}")
            self.finished.emit("Failure", str(e))
