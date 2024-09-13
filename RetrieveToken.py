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
        try:
            self.save_manager = SaveManager(self.main_window)
            self.load_credentials()  # Load credentials during initialization
        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize SaveManager or load credentials: {e}")
            self.finished.emit("Failure", "Initialization failed.")

    def load_credentials(self):
        try:
            # Retrieve and decrypt configuration values for use in API call
            self.key_client_id = self.save_manager.get_config_value('Client', 'client_id')
            self.key_client_pass = self.save_manager.get_config_value('Client', 'client_secret')
            self.key_api_username = self.save_manager.get_config_value('API', 'username')
            self.key_api_pass = self.save_manager.get_config_value('API', 'password')
            self.key_token_retrieved = self.save_manager.get_config_value('Token', 'token_retrieved')  # Add this line
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
        # Check if any essential parameter is '--' or None
        essential_params = [self.key_client_id, self.key_client_pass, self.key_api_username, self.key_api_pass]
        if any(param == "None Set" or param is None for param in essential_params):
            self.finished.emit("Failure", "Essential credentials are not properly set.")
            self.log_system.log_message('error', "Essential credentials are not set properly for token retrieval.")
            return  # Skip the rest of the function

        try:
            url = "https://telco-api.skyswitch.com/oauth2/token"
            payload = {
                "grant_type": "password",
                "client_id": self.key_client_id,
                "client_secret": self.key_client_pass,
                "username": self.key_api_username,
                "password": self.key_api_pass,
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

                    token_info = response.json()
                    self.key_access_token = token_info.get('access_token')
                    self.key_token_expiration = token_info.get('expires_in')

                    # Calculate expiration datetime
                    expiration_datetime = datetime.datetime.now() + datetime.timedelta(seconds=int(self.key_token_expiration))
                    formatted_expiration = expiration_datetime.strftime('%Y-%m-%d %H:%M:%S')

                    # Encrypt and save the token and expiration date to config.ini using EncryptionKeyManager
                    self.save_manager.config.set('Token', 'access_token', self.key_access_token)
                    self.save_manager.config.set('Token', 'token_expiration', formatted_expiration)
                    self.save_manager.config.set('Token', 'token_retrieved', datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))  # Add this line
                    self.save_manager.save_changes()
                    self.main_window.reload_ui()

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
                self.log_system.log_message('error', f"Failed to retrieve token. HTTP {response.status_code}: {response.text}")
        except Exception as e:
            if self.main_window.isVisible():
                self.main_window.update_status_bar(f"Token retrieval error: {str(e)}", 5000)
            self.finished.emit("Failure", str(e))
            self.log_system.log_message('error', f"Failed to retrieve access token: {e}")
