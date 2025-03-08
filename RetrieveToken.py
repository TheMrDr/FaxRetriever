import datetime

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from SaveManager import SaveManager
from SystemLog import SystemLog  # Assuming this is correctly imported


class RetrieveToken(QThread):
    finished = pyqtSignal(str, str)
    token_retrieved = pyqtSignal()  # Signal to indicate token was successfully retrieved

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.log_system = SystemLog()  # Initialize the log system
        self.credentials = {}
        try:
            self.save_manager = SaveManager(self.main_window)
            self.load_credentials()  # Load credentials during initialization
        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize SaveManager or load credentials: {e}")
            self.finished.emit("Failure", "Initialization failed.")

    def load_credentials(self):
        try:
            self.credentials = {
                "client_id": self.save_manager.get_config_value('Client', 'client_id'),
                "client_secret": self.save_manager.get_config_value('Client', 'client_secret'),
                "username": self.save_manager.get_config_value('API', 'username'),
                "password": self.save_manager.get_config_value('API', 'password'),
                "token_retrieved": self.save_manager.get_config_value('Token', 'token_retrieved')
            }
            self.log_system.log_message('info', "Credentials loaded for token retrieval.")
        except Exception as e:
            self.log_system.log_message('error', f"Failed to load credentials: {e}")
            self.finished.emit("Failure", "Failed to load credentials.")

    def run(self):
        try:
            self.log_system.log_message('info', "Starting token retrieval thread.")
            self.retrieve_token()
        except Exception as e:
            self.log_system.log_message('error', f"Exception in run method: {e}")
            self.finished.emit("Failure", str(e))

    # noinspection PyUnresolvedReferences
    def retrieve_token(self):
        # Check if any essential credentials are missing
        missing_keys = [key for key, value in self.credentials.items() if
                        key in ["client_id", "client_secret", "username", "password"] and (
                                    value is None or value == "None Set")]

        if missing_keys:
            self.log_system.log_message('error', f"Missing credentials: {', '.join(missing_keys)}")
            self.finished.emit("Failure", f"Missing credentials: {', '.join(missing_keys)}")
            return

        try:
            url = "https://telco-api.skyswitch.com/oauth2/token"
            payload = {
                "grant_type": "password",
                "client_id": self.credentials["client_id"],
                "client_secret": self.credentials["client_secret"],
                "username": self.credentials["username"],
                "password": self.credentials["password"],
                "scope": "*"
            }
            headers = {
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded"
            }
            response = requests.post(url, data=payload, headers=headers)
            if response.status_code == 200:
                try:
                    if self.main_window.isVisible():
                        self.main_window.update_status_bar("Token retrieved successfully.", 5000)
                    self.token_retrieved.emit()  # Emit signal when new token is retrieved

                    try:
                        token_info = response.json()
                        self.save_manager.config.set('Token', 'access_token', token_info.get('access_token'))
                        expiration_datetime = (datetime.datetime.now() + datetime.timedelta(
                            seconds=int(token_info.get('expires_in')))).strftime('%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        self.log_system.log_message('error', f"Invalid JSON response from API: {response.text}")
                        self.finished.emit("Failure", f"Invalid API response: {response.text}")
                        return

                    # Encrypt and save the token and expiration date to config.ini using EncryptionKeyManager
                    self.save_manager.config.set('Token', 'token_expiration', expiration_datetime)
                    self.save_manager.config.set('Token', 'token_retrieved',
                                                 datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))  # Add this line
                    self.save_manager.save_changes()

                    self.finished.emit("Success", "Token retrieved and saved successfully.")
                    self.log_system.log_message('info', "Token retrieved and saved successfully.")
                    self.main_window.reload_ui()
                except Exception as e:
                    self.log_system.log_message('error', f"Failed to save token or update UI: {e}")
                    self.finished.emit("Failure", f"Token retrieval succeeded but saving failed: {e}")
            else:
                if self.main_window.isVisible():
                    self.main_window.update_status_bar("Failed to retrieve token.", 5000)
                self.finished.emit("Failure", f"HTTP Error {response.status_code}: {response.text}")
                self.log_system.log_message('error',
                                            f"Failed to retrieve token. HTTP {response.status_code}: {response.text}")
        except Exception as e:
            if self.main_window.isVisible():
                self.main_window.update_status_bar(f"Token retrieval error: {str(e)}", 5000)
            self.finished.emit("Failure", str(e))
            self.log_system.log_message('error', f"Failed to retrieve access token: {e}")
