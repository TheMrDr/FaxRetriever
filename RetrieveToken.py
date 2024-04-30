import datetime
import json

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from SaveManager import EncryptionKeyManager
from SystemLog import SystemLog  # Assuming this is correctly imported


class RetrieveToken(QThread):
    finished = pyqtSignal(str, str)
    token_retrieved = pyqtSignal()  # Signal to indicate token was successfully retrieved

    def __init__(self):
        super().__init__()
        self.log_system = SystemLog()  # Initialize the log system
        self.encryption_manager = EncryptionKeyManager()
        self.load_credentials()  # Load credentials during initialization

    def load_credentials(self):
        # Retrieve and decrypt configuration values for use in API call
        self.key_client_id = self.encryption_manager.get_config_value('Client', 'client_id')
        self.key_client_pass = self.encryption_manager.get_config_value('Client', 'client_secret')
        self.key_api_username = self.encryption_manager.get_config_value('API', 'username')
        self.key_api_pass = self.encryption_manager.get_config_value('API', 'password')
        self.log_system.log_message('info', "Credentials loaded for token retrieval.")

    def run(self):
        self.log_system.log_message('info', "Starting token retrieval thread.")
        self.retrieve_token()

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
                self.token_retrieved.emit()  # Emit signal when new token is retrieved

                token_info = response.json()
                self.key_access_token = token_info.get('access_token')
                self.key_token_expiration = token_info.get('expires_in')

                # Calculate expiration datetime
                expiration_datetime = datetime.datetime.now() + datetime.timedelta(seconds=int(self.key_token_expiration))
                formatted_expiration = expiration_datetime.strftime('%Y-%m-%d %H:%M:%S')

                # Encrypt and save the token and expiration date to config.ini using EncryptionKeyManager
                self.encryption_manager.write_encrypted_ini('Token', 'access_token', self.key_access_token)
                self.encryption_manager.write_encrypted_ini('Token', 'token_expiration', formatted_expiration)

                # Save token_info as a .json file
                with open('token_info.json', 'w') as json_file:
                    json.dump(token_info, json_file)
                    self.log_system.log_message('info', "Token info saved to JSON.")

                self.finished.emit("Success", "Token retrieved and saved successfully.")
                self.log_system.log_message('info', "Token retrieved and saved successfully.")
            else:
                self.finished.emit("Failure", f"Failed to retrieve token. Status code: {response.status_code}, Response: {response.text}")
                self.log_system.log_message('error', f"Failed to retrieve token. HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.finished.emit("Failure", f"Failed to retrieve access token. Error: {e}")
            self.log_system.log_message('error', f"Failed to retrieve access token: {e}")


class RenewToken(QThread):
    pass
