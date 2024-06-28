import json
import os
import platform
import re
import requests
import subprocess
import sys
import shutil

import fitz  # PyMuPDF

from PyQt5.QtCore import QThread, pyqtSignal, QRect
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo
from PyQt5.QtGui import QImage, QPainter

from SaveManager import SaveManager
from SystemLog import SystemLog

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


# noinspection PyUnresolvedReferences
class RetrieveFaxes(QThread):
    finished = pyqtSignal(list)

    def __init__(self, main_window=None):
        super().__init__()
        self.log_system = SystemLog()
        self.main_window = main_window
        self.poppler_path = os.path.join(bundle_dir, "poppler", "bin")
        self.add_poppler_to_path()
        self.encryption_manager = SaveManager(self.main_window)
        self.token = self.encryption_manager.get_config_value('Token', 'access_token')
        self.fax_account = self.encryption_manager.get_config_value('Account', 'fax_user')
        self.save_path = self.encryption_manager.get_config_value('UserSettings', 'save_path')
        self.printed_path = os.path.join(self.save_path, "Printed")
        self.download_type = self.encryption_manager.get_config_value('Fax Options', 'download_method')
        self.delete_fax_option = self.encryption_manager.get_config_value('Fax Options', 'delete_faxes')
        self.print_faxes = self.encryption_manager.get_config_value('Fax Options', 'print_faxes') == 'Yes'
        self.printer_name = self.encryption_manager.get_config_value('Fax Options', 'printer_full_name')
        # self.mark_read = self.encryption_manager.get_config_value('Fax Options', 'mark_read')
        self.allowed_caller_ids = self.load_allowed_caller_ids()

    def add_poppler_to_path(self):
        if platform.system() == "Windows":
            os.environ['PATH'] += os.pathsep + self.poppler_path

    def run(self):
        self.retrieve_faxes()

    def load_allowed_caller_ids(self):
        # Retrieve the caller IDs from the configuration
        caller_ids = self.encryption_manager.get_config_value('Retrieval', 'fax_caller_id')
        # Split by comma and reformat to numbers only
        formatted_caller_ids = [re.sub(r'\D', '', cid) for cid in caller_ids.split(',')]
        return formatted_caller_ids

    def retrieve_faxes(self):
        base_url = "https://telco-api.skyswitch.com"
        url = f"{base_url}/users/{self.fax_account}/faxes/inbound"
        headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            faxes_response = response.json()
            with open('faxes_response.txt', 'w') as outfile:
                json.dump(faxes_response, outfile, indent=4)  # Write the JSON response to a .txt file with indentation
            if 'data' in faxes_response:
                faxes = faxes_response['data']
                self.download_fax_pdfs(faxes)
                # Check if there are more pages and retrieve them if necessary
                while 'next' in faxes_response['links'] and faxes_response['links']['next']:
                    next_page_path = faxes_response['links']['next']  # Get the path for the next page
                    next_page_url = url + next_page_path  # Construct the complete URL
                    response = requests.get(next_page_url, headers=headers)
                    if response.status_code == 200:
                        faxes_response = response.json()
                        faxes = faxes_response['data']
                        self.download_fax_pdfs(faxes)
                    else:
                        self.log_system.log_message('error', f"Failed to retrieve next page of faxes. Status code: {response.status_code}")
                        break
            else:
                self.log_system.log_message('error', 'No fax data available')
                self.finished.emit([])
        else:
            self.log_system.log_message('error', f"Failed to retrieve faxes. Status code: {response.status_code}")
            self.finished.emit([])

    def download_fax_pdfs(self, faxes):
        download_results = []
        all_faxes_downloaded = True  # Flag to check if all faxes have been downloaded
        downloaded_faxes_count = 0  # Counter for downloaded faxes

        for fax in faxes:
            destination_number = str(fax['destination'])

            if destination_number not in self.allowed_caller_ids:
                self.log_system.log_message('info', f'Destination number {destination_number} not in allowed caller IDs')
                continue  # Skip downloading the fax

            fax_id = fax['id']
            pdf_path = os.path.join(self.save_path, f"{fax_id}.pdf")
            printed_pdf_path = os.path.join(self.printed_path, f"{fax_id}.pdf")

            # Determine the appropriate file name and extension based on the download type
            if self.download_type == 'PDF':
                file_path = pdf_path
            elif self.download_type == 'JPG':
                # Check if any JPG file exists for the fax ID
                jpg_files = [file for file in os.listdir(self.save_path) if file.startswith(f"{fax_id}_") and file.endswith(".jpg")]
                if jpg_files:
                    # Skip downloading if a JPG file already exists
                    if self.main_window.isVisible():
                        self.main_window.update_status_bar(f"Fax PDF for ID {fax_id} already converted to JPG", 5000)
                    self.log_system.log_message('info', f"Fax PDF for ID {fax_id} already converted to JPG")
                    continue
                file_path = os.path.join(self.save_path, f"{fax_id}_0.jpg")  # Assuming the first page is named as <fax_id>_0.jpg
            elif self.download_type == 'Both':
                # Check if any PDF or JPG file exists for the fax ID
                if os.path.exists(pdf_path) or os.path.exists(printed_pdf_path):
                    # Skip downloading if a PDF file already exists
                    if self.main_window.isVisible():
                        self.main_window.update_status_bar(f"Fax PDF for ID {fax_id} already downloaded", 5000)
                    self.log_system.log_message('info', f"Fax PDF for ID {fax_id} already downloaded")
                    continue
                jpg_files = [file for file in os.listdir(self.save_path) if file.startswith(f"{fax_id}_") and file.endswith(".jpg")]
                if jpg_files:
                    # Skip downloading if any JPG file already exists
                    if self.main_window.isVisible():
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
            if not os.path.exists(file_path) and not os.path.exists(printed_pdf_path):
                pdf_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/pdf"
                headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
                pdf_response = requests.get(pdf_url, headers=headers)

                if pdf_response.status_code == 200:
                    with open(file_path, 'wb') as f:
                        f.write(pdf_response.content)
                    if self.main_window.isVisible():
                        self.main_window.update_status_bar(f"Downloaded fax file for ID {fax_id}", 5000)
                    self.log_system.log_message('info', f"Downloaded fax file for ID {fax_id} to {file_path}")

                    # Convert PDF to JPG if required
                    if self.download_type in ['JPG', 'Both']:
                        command = ['pdftoppm', '-jpeg', file_path, os.path.join(self.save_path, f"{fax_id}")]
                        process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
                        process.communicate()  # Wait for the process to finish
                        if self.main_window.isVisible():
                            self.main_window.update_status_bar(f"Converted fax PDF to JPG for ID {fax_id}", 5000)
                        self.log_system.log_message('info', f"Converted fax PDF to JPG for ID {fax_id}")

                    # Remove the PDF if only JPG is required
                    if self.download_type == 'JPG':
                        os.remove(file_path)
                        self.log_system.log_message('info', f"Removed original fax PDF for ID {fax_id} after conversion to JPG")

                    # Print the fax if the option is enabled
                    if self.print_faxes:
                        self.print_fax(file_path)

                    download_results.append((fax_id, 'Downloaded', file_path if self.download_type != 'JPG' else 'Converted to JPG'))
                    downloaded_faxes_count += 1  # Increment the counter for downloaded faxes
                else:
                    download_results.append((fax_id, 'Failed to download'))
                    if self.main_window.isVisible():
                        self.main_window.update_status_bar(f"Failed to download fax file for ID {fax_id}", 5000)
                    self.log_system.log_message('error', f"Failed to download fax file for ID {fax_id}, HTTP {pdf_response.status_code}")

            # Optionally delete the fax record after processing
            if self.delete_fax_option == 'Yes':
                self.delete_fax(fax_id)

        # Check if all faxes have been downloaded and provide appropriate status messages
        if all_faxes_downloaded:
            if self.download_type == 'PDF':
                if self.main_window.isVisible():
                    self.main_window.update_status_bar("All faxes have already been downloaded as PDFs", 5000)
                self.log_system.log_message('info', "All faxes have already been downloaded as PDFs")
            elif self.download_type == 'JPG':
                if self.main_window.isVisible():
                    self.main_window.update_status_bar("All faxes have already been converted to JPG", 5000)
                self.log_system.log_message('info', "All faxes have already been converted to JPG")
            elif self.download_type == 'Both':
                if self.main_window.isVisible():
                    self.main_window.update_status_bar("All faxes have already been downloaded and converted", 5000)
                self.log_system.log_message('info', "All faxes have already been downloaded and converted")
        elif downloaded_faxes_count > 1:  # If more than one fax is downloaded
            if self.main_window.isVisible():
                self.main_window.update_status_bar(f"{downloaded_faxes_count} faxes downloaded", 5000)
            self.log_system.log_message('info', f"{downloaded_faxes_count} faxes downloaded")

        self.finished.emit(download_results)  # Emit results of downloads

    def print_fax(self, file_path):
        if os.path.exists(file_path):
            printer = QPrinter()
            printer.setPrinterName(self.printer_name)
            printer.setOutputFormat(QPrinter.NativeFormat)
            printer.setPageSize(QPrinter.Letter)
            printer.setPageMargins(0, 0, 0, 0, QPrinter.Millimeter)

            # Check if the printer is valid
            available_printers = QPrinterInfo.availablePrinters()
            if any(p.printerName() == self.printer_name for p in available_printers):
                doc = fitz.open(file_path)  # Open the PDF file using PyMuPDF
                painter = QPainter(printer)

                for page_num in range(len(doc)):
                    page = doc[page_num]
                    pix = page.get_pixmap()
                    img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

                    # Calculate the target rectangle for the image
                    target_rect = QRect(0, 0, printer.pageRect().width(), printer.pageRect().height())
                    painter.drawImage(target_rect, img)

                    if page_num < len(doc) - 1:
                        printer.newPage()

                painter.end()
                doc.close()

                # Move the file to the "Printed" directory
                if not os.path.exists(self.printed_path):
                    os.makedirs(self.printed_path)
                shutil.move(file_path, os.path.join(self.printed_path, os.path.basename(file_path)))
                self.log_system.log_message('info', f"Printed fax {file_path} and moved to 'Printed' directory.")
            else:
                self.log_system.log_message('error', f"Printer {self.printer_name} not found.")

    def delete_fax(self, fax_id):
        delete_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/delete"
        headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
        delete_response = requests.post(delete_url, headers=headers)
        if delete_response.status_code == 200:
            self.log_system.log_message('info', f"Deleted fax {fax_id} successfully.")
        else:
            self.log_system.log_message('error', f"Failed to delete fax {fax_id}, HTTP {delete_response.status_code}")
