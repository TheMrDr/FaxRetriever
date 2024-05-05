import os
import platform

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from pdf2image import convert_from_path

from SaveManager import SaveManager
from SystemLog import SystemLog


# noinspection PyUnresolvedReferences
class RetrieveFaxes(QThread):
    finished = pyqtSignal(list)


    def __init__(self, main_window=None):
        super().__init__()
        self.log_system = SystemLog()
        self.main_window = main_window
        self.poppler_path = os.path.join(sys._MEIPASS, "poppler", "bin")
        self.add_poppler_to_path()
        self.encryption_manager = SaveManager(self.main_window)
        self.token = self.encryption_manager.get_config_value('Token', 'access_token')
        self.fax_account = self.encryption_manager.get_config_value('Account', 'fax_user')
        self.save_path = self.encryption_manager.get_config_value('Path', 'save_path')
        self.download_type = self.encryption_manager.get_config_value('Fax Options', 'download_method')
        self.delete_fax_option = self.encryption_manager.get_config_value('Fax Options', 'delete_faxes')
        # self.mark_read = self.encryption_manager.get_config_value('Fax Options', 'mark_read')


    def add_poppler_to_path(self):
        if platform.system() == "Windows":
            os.environ['PATH'] += os.pathsep + self.poppler_path

    def run(self):
        self.retrieve_faxes()

    def retrieve_faxes(self):
        url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/inbound"
        headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            faxes_response = response.json()
            if 'data' in faxes_response:
                faxes = faxes_response['data']
                self.download_fax_pdfs(faxes)
            else:
                self.log_system.log_message('error', 'No fax data available')
                self.finished.emit([])
        else:
            self.log_system.log_message('error', f"Failed to retrieve faxes. Status code: {response.status_code}")
            self.finished.emit([])

    def download_fax_pdfs(self, faxes):
        download_results = []
        all_faxes_downloaded = True  # Flag to check if all faxes have been downloaded
        for fax in faxes:
            fax_id = fax['id']
            pdf_path = os.path.join(self.save_path, f"{fax_id}.pdf")

            # Determine the appropriate file name and extension based on the download type
            if self.download_type == 'PDF':
                file_path = pdf_path
            elif self.download_type == 'JPG':
                # Check if any JPG file exists for the fax ID
                jpg_files = [file for file in os.listdir(self.save_path) if
                             file.startswith(f"{fax_id}_") and file.endswith(".jpg")]
                if jpg_files:
                    # Skip downloading if a JPG file already exists
                    self.main_window.update_status_bar(f"Fax PDF for ID {fax_id} already converted to JPG", 5000)
                    self.log_system.log_message('info', f"Fax PDF for ID {fax_id} already converted to JPG")
                    continue
                file_path = os.path.join(self.save_path,
                                         f"{fax_id}_0.jpg")  # Assuming the first page is named as <fax_id>_0.jpg
            elif self.download_type == 'Both':
                # Check if any PDF or JPG file exists for the fax ID
                if os.path.exists(pdf_path):
                    # Skip downloading if a PDF file already exists
                    self.main_window.update_status_bar(f"Fax PDF for ID {fax_id} already downloaded", 5000)
                    self.log_system.log_message('info', f"Fax PDF for ID {fax_id} already downloaded")
                    continue
                jpg_files = [file for file in os.listdir(self.save_path) if
                             file.startswith(f"{fax_id}_") and file.endswith(".jpg")]
                if jpg_files:
                    # Skip downloading if any JPG file already exists
                    self.main_window.update_status_bar(f"Fax PDF for ID {fax_id} already converted to JPG", 5000)
                    self.log_system.log_message('info', f"Fax PDF for ID {fax_id} already converted to JPG")
                    continue
                file_path = pdf_path
            else:
                # Invalid download type
                continue

            # Set the flag to False if any fax file needs to be downloaded
            all_faxes_downloaded = False

            # Download the file if it doesn't already exist
            if not os.path.exists(file_path):
                pdf_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/pdf"
                headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
                pdf_response = requests.get(pdf_url, headers=headers)

                if pdf_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(pdf_response.content)
                    self.main_window.update_status_bar(f"Downloaded fax file for ID {fax_id}", 5000)
                    self.log_system.log_message('info', f"Downloaded fax file for ID {fax_id} to {file_path}")

                    # Convert PDF to JPG if required
                    if self.download_type in ['JPG', 'Both']:
                        images = convert_from_path(file_path)
                        for i, image in enumerate(images):
                            image.save(os.path.join(self.save_path, f"{fax_id}_{i}.jpg"), 'JPEG')
                        self.main_window.update_status_bar(f"Converted fax PDF to JPG for ID {fax_id}", 5000)
                        self.log_system.log_message('info', f"Converted fax PDF to JPG for ID {fax_id}")

                    # Remove the PDF if only JPG is required
                    if self.download_type == 'JPG':
                        os.remove(file_path)
                        self.log_system.log_message('info',
                                                    f"Removed original fax PDF for ID {fax_id} after conversion to JPG")

                    download_results.append(
                        (fax_id, 'Downloaded', file_path if self.download_type != 'JPG' else 'Converted to JPG'))
                else:
                    download_results.append((fax_id, 'Failed to download'))
                    self.main_window.update_status_bar(f"Failed to download fax file for ID {fax_id}", 5000)
                    self.log_system.log_message('error',
                                                f"Failed to download fax file for ID {fax_id}, HTTP {pdf_response.status_code}")

            # Optionally delete the fax record after processing
            if self.delete_fax_option == 'Yes':
                self.delete_fax(fax_id)

        # Check if all faxes have been downloaded and provide appropriate status messages
        if all_faxes_downloaded:
            if self.download_type == 'PDF':
                self.main_window.update_status_bar("All faxes have already been downloaded as PDFs", 5000)
                self.log_system.log_message('info', "All faxes have already been downloaded as PDFs")
            elif self.download_type == 'JPG':
                self.main_window.update_status_bar("All faxes have already been converted to JPG", 5000)
                self.log_system.log_message('info', "All faxes have already been converted to JPG")
            elif self.download_type == 'Both':
                self.main_window.update_status_bar("All faxes have already been downloaded and converted", 5000)
                self.log_system.log_message('info', "All faxes have already been downloaded and converted")

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
        headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
        delete_response = requests.post(delete_url, headers=headers)
        if delete_response.status_code == 200:
            self.log_system.log_message('info', f"Deleted fax {fax_id} successfully.")
        else:
            self.log_system.log_message('error', f"Failed to delete fax {fax_id}, HTTP {delete_response.status_code}")