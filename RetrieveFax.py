import os

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from SaveManager import EncryptionKeyManager
from SystemLog import SystemLog


# noinspection PyUnresolvedReferences
class RetrieveFaxes(QThread):
    finished = pyqtSignal(list)  # Signal to send the list of fax processing results

    def __init__(self):
        super().__init__()
        self.log_system = SystemLog()
        self.encryption_manager = EncryptionKeyManager()
        self.token = self.encryption_manager.get_config_value('Token', 'access_token')
        self.fax_account = self.encryption_manager.get_config_value('Account', 'fax_user')
        self.save_path = self.encryption_manager.get_config_value('Path', 'save_path')
        # self.mark_read = self.encryption_manager.get_config_value('Fax Options', 'mark_read')
        self.delete_fax_option = self.encryption_manager.get_config_value('Fax Options', 'delete_faxes')

    def run(self):
        self.retrieve_faxes()

    def retrieve_faxes(self):
        url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/inbound"
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.token}"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            faxes_response = response.json()
            if 'data' in faxes_response:
                faxes = faxes_response['data']
                self.download_fax_pdfs(faxes)
            else:
                self.log_system.log_message('error', 'No fax data available')
                self.finished.emit([])  # Emit empty list if no data is found
        else:
            self.log_system.log_message('error', f"Failed to retrieve faxes. Status code: {response.status_code}")
            self.finished.emit([])  # Emit an empty list in case of failure

    def download_fax_pdfs(self, faxes):
        download_results = []
        for fax in faxes:
            fax_id = fax['id']
            pdf_path = f"{self.save_path}\\{fax_id}.pdf"
            if not os.path.exists(pdf_path):  # Check if the file already exists
                pdf_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/pdf"
                headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
                pdf_response = requests.get(pdf_url, headers=headers)
                if pdf_response.status_code == 200:
                    try:
                        with open(pdf_path, 'wb') as f:
                            f.write(pdf_response.content)
                        self.log_system.log_message('info', f"Downloaded fax PDF for ID {fax_id} to {pdf_path}")
                        # if self.mark_read == 'Yes':
                        #     self.mark_fax_as_read(fax_id)
                        if self.delete_fax_option == 'Yes':
                            self.delete_fax(fax_id)
                        download_results.append((fax_id, 'Downloaded', pdf_path))
                    except Exception as e:
                        download_results.append((fax_id, 'Failed', str(e)))
                        self.log_system.log_message('error', f"Failed to save fax PDF for ID {fax_id}: {str(e)}")
                else:
                    download_results.append((fax_id, 'Failed to download'))
                    self.log_system.log_message('error', f"Failed to download fax PDF for ID {fax_id}, HTTP {pdf_response.status_code}")
            else:
                download_results.append((fax_id, 'Already downloaded', pdf_path))
                self.log_system.log_message('info', f"Fax PDF for ID {fax_id} already exists at {pdf_path}")

        self.finished.emit(download_results)  # Emit results of downloads


    # def mark_fax_as_read(self, fax_id):
    #     read_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/read"
    #     headers = {
    #         "accept": "application/json",
    #         "authorization": f"Bearer {self.token}"
    #     }
    #     read_response = requests.get(read_url, headers=headers)
    #     if read_response.status_code == 200:
    #         self.log_system.log_message('info', f"Marked fax {fax_id} as read successfully.")
    #     else:
    #         self.log_system.log_message('error', f"Failed to mark fax {fax_id} as read, HTTP {read_response.status_code}")

    def delete_fax(self, fax_id):
        delete_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/delete"
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {self.token}"
        }
        delete_response = requests.post(delete_url, headers=headers)
        if delete_response.status_code == 200:
            self.log_system.log_message('info', f"Deleted fax {fax_id} successfully.")
        else:
            self.log_system.log_message('error', f"Failed to delete fax {fax_id}, HTTP {delete_response.status_code}")