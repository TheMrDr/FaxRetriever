import requests
from PyQt5.QtCore import QThread, pyqtSignal

from SaveManager import SaveManager
from SystemLog import SystemLog


class RetrieveNumbers(QThread):
    finished = pyqtSignal(str, str)
    numbers_retrieved = pyqtSignal(list)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.save_manager = SaveManager(self.main_window)
        self.log_system = SystemLog()

        self.access_token = self.save_manager.get_config_value('Token', 'access_token')
        self.user_id = self.save_manager.get_config_value('Account', 'fax_user')

    def run(self):
        self.log_system.log_message('info', "Starting fax number retrieval thread.")
        self.retrieve_numbers()

    def retrieve_numbers(self):
        if not self.access_token or not self.user_id:
            self.finished.emit("Failure", "Essential credentials are not properly set.")
            self.log_system.log_message('error', "Essential credentials are not set properly for number retrieval.")
            return

        url = f"https://telco-api.skyswitch.com/users/{self.user_id}/faxes/numberlist"
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.access_token}"
        }

        try:
            response = requests.get(url, headers=headers)
            if response.status_code == 200:
                data = response.json().get('data', [])
                numbers = [item['number'] for item in data]
                self.numbers_retrieved.emit(numbers)
                self.finished.emit("Success", "Successfully retrieved fax numbers.")
                self.log_system.log_message('info', f"Successfully retrieved fax numbers: {numbers}")
                self.main_window.create_central_widget()
            else:
                self.finished.emit("Failure", f"HTTP Error {response.status_code}: {response.text}")
                self.log_system.log_message('error',
                                            f"Failed to retrieve fax numbers. HTTP {response.status_code}: {response.text}")
        except Exception as e:
            self.finished.emit("Failure", str(e))
            self.log_system.log_message('error', f"Failed to retrieve fax numbers: {e}")
