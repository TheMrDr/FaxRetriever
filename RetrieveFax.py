import datetime
import os
import platform
import re
import shutil
import subprocess
import sys

import fitz
import requests
from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal, QRect
from PyQt5.QtGui import QImage, QPainter
from PyQt5.QtPrintSupport import QPrinter, QPrinterInfo
from plyer import notification
import pytz
from tzlocal import get_localzone

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
        self.allowed_caller_ids = self.load_allowed_caller_ids()
        self.file_naming_option = self.encryption_manager.get_config_value('Fax Options', 'file_name_format')

        # Load archival settings
        self.archive_enabled = self.encryption_manager.get_config_value('Fax Options', 'archive_enabled') == "Yes"
        self.archive_duration = int(self.encryption_manager.get_config_value('Fax Options', 'archive_duration') or 30)
        self.archive_path = os.path.join(os.getcwd(), "Archive")

        os.makedirs(self.archive_path, exist_ok=True)

    def add_poppler_to_path(self):
        if platform.system() == "Windows":
            os.environ['PATH'] += os.pathsep + self.poppler_path

    def run(self):
        self.retrieve_faxes()

    def load_allowed_caller_ids(self):
        try:
            caller_ids = self.encryption_manager.get_config_value('Retrieval', 'fax_caller_id')
            formatted_caller_ids = [re.sub(r'\D', '', cid) for cid in caller_ids.split(',')]
            return formatted_caller_ids
        except Exception as e:
            self.log_system.log_message('error', f"Failed to load allowed caller IDs: {str(e)}")
            return []

    def retrieve_faxes(self):
        try:
            if not self.validate_save_path():
                self.log_system.log_message('error', "Invalid save path. Please set a valid save path before downloading faxes.")
                self.finished.emit([])
                return

            base_url = "https://telco-api.skyswitch.com"
            url = f"{base_url}/users/{self.fax_account}/faxes/inbound"
            headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                faxes_response = response.json()

                if 'data' in faxes_response:
                    faxes = faxes_response['data']
                    self.download_fax_pdfs(faxes)
                    while 'next' in faxes_response['links'] and faxes_response['links']['next']:
                        next_page_path = faxes_response['links']['next']
                        next_page_url = url + next_page_path
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
        except Exception as e:
            self.log_system.log_message('error', f"Exception in retrieve_faxes: {str(e)}")
            self.finished.emit([])

    def validate_save_path(self):
        try:
            if not self.save_path:
                return False
            if not os.path.exists(self.save_path):
                try:
                    os.makedirs(self.save_path)
                    self.log_system.log_message('info', f"Created save path: {self.save_path}")
                except Exception as e:
                    self.log_system.log_message('error', f"Failed to create save path: {str(e)}")
                    return False
            return True
        except Exception as e:
            self.log_system.log_message('error', f"Exception in validate_save_path: {str(e)}")
            return False

    def download_fax_pdfs(self, faxes):
        try:
            download_results = []
            all_faxes_downloaded = True
            downloaded_faxes_count = 0

            # Show "Checking for new faxes..." status
            if self.main_window:
                self.main_window.update_status_bar("Checking for new faxes...", 5000)

            for fax in faxes:
                try:
                    fax_id = fax['id']
                    caller_id = fax['caller_id']
                    timestamp = fax['created_at']

                    # Format timestamp as MMDD-HHMM
                    try:
                        dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                        formatted_timestamp = dt.strftime("%m%d-%H%M")
                    except ValueError:
                        self.log_system.log_message('error',
                                                    f"Invalid timestamp format for fax ID {fax_id}: {timestamp}")
                        formatted_timestamp = "unknown"

                    # Determine file names
                    standard_file_name = f"{fax_id}.pdf"
                    custom_file_name = f"{caller_id}-{formatted_timestamp}.pdf" if caller_id else standard_file_name
                    file_name = custom_file_name if self.file_naming_option == "cid-mmdd-hhmm" and caller_id else standard_file_name
                    pdf_path = os.path.join(self.save_path, file_name)
                    jpg_prefix = os.path.join(self.save_path, file_name.replace(".pdf", ""))

                    # **Determine Archive Path (Year > Month > Day > Hour)**
                    dt_utc = datetime.strptime(timestamp,
                                               "%Y-%m-%dT%H:%M:%S.%fZ") if '.' in timestamp else datetime.strptime(
                        timestamp, "%Y-%m-%dT%H:%M:%SZ")
                    archive_dir = os.path.join(
                        self.archive_path,
                        dt_utc.strftime("%Y"),  # Year (2025)
                        dt_utc.strftime("%m"),  # Month (03)
                        dt_utc.strftime("%d"),  # Day (12)
                        dt_utc.strftime("%H")  # Hour (23)
                    )
                    archive_pdf_path = os.path.join(archive_dir, file_name)
                    archive_jpg_prefix = os.path.join(archive_dir, file_name.replace(".pdf", ""))

                    # **Check if fax already exists in the save directory OR archive**
                    standard_file_path = os.path.join(self.save_path, standard_file_name)
                    custom_file_path = os.path.join(self.save_path, custom_file_name)
                    jpg_files = [f for f in os.listdir(self.save_path) if
                                 f.startswith(jpg_prefix) and f.endswith(".jpg")]

                    archive_jpg_files = []
                    if os.path.exists(archive_dir):  # Check archive only if the directory exists
                        archive_jpg_files = [f for f in os.listdir(archive_dir) if
                                             f.startswith(archive_jpg_prefix) and f.endswith(".jpg")]

                    if (
                            os.path.exists(standard_file_path) or
                            os.path.exists(custom_file_path) or
                            os.path.exists(archive_pdf_path) or
                            (self.download_type in ["JPG", "Both"] and (jpg_files or archive_jpg_files))
                    ):
                        self.log_system.log_message('info', f"Skipping fax ID {fax_id}, already downloaded or archived")
                        continue

                    all_faxes_downloaded = False

                    # Show "Downloading fax..." status
                    if self.main_window:
                        self.main_window.update_status_bar(f"Downloading fax {file_name}...", 5000)

                    # **Download the fax PDF**
                    pdf_url = fax['pdf']
                    headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
                    pdf_response = requests.get(pdf_url, headers=headers)

                    if pdf_response.status_code == 200:
                        with open(pdf_path, 'wb') as f:
                            f.write(pdf_response.content)
                        self.log_system.log_message('info', f"Downloaded fax file for ID {fax_id} to {pdf_path}")

                        # **Convert to JPG if needed**
                        if self.download_type in ["JPG", "Both"]:
                            if self.main_window:
                                self.main_window.update_status_bar(f"Converting {file_name} to JPG...", 5000)

                            command = ['pdftoppm', '-jpeg', pdf_path, jpg_prefix]
                            process = subprocess.Popen(command, creationflags=subprocess.CREATE_NO_WINDOW)
                            process.communicate()

                            if self.main_window:
                                self.main_window.update_status_bar(f"Conversion complete for {file_name}", 5000)

                            # **Archive fax if enabled**
                            if self.archive_enabled:
                                self.archive_fax(pdf_path, file_name, fax['created_at'])

                            # Remove original PDF if JPG is the only format
                            if self.download_type == "JPG":
                                os.remove(pdf_path)

                        # **Print fax if enabled**
                        if self.print_faxes:
                            self.print_fax(pdf_path)

                        # Optionally delete the fax record after processing
                        if self.delete_fax_option == 'Yes':
                            self.delete_fax(fax_id)

                        download_results.append(
                            (fax_id, 'Downloaded', pdf_path if self.download_type != 'JPG' else 'Converted to JPG'))
                        downloaded_faxes_count += 1
                    else:
                        download_results.append((fax_id, 'Failed to download'))
                        self.log_system.log_message('error',
                                                    f"Failed to download fax file for ID {fax_id}, HTTP {pdf_response.status_code}")

                except Exception as e:
                    self.log_system.log_message('error', f"Exception in download_fax_pdfs loop: {str(e)}")

            # **Show final status message**
            if all_faxes_downloaded:
                if self.main_window:
                    self.main_window.update_status_bar("All faxes have already been downloaded.", 5000)
                self.log_system.log_message('info', "All faxes have already been downloaded.")
            elif downloaded_faxes_count > 0:
                if self.main_window:
                    self.main_window.update_status_bar(f"{downloaded_faxes_count} new faxes downloaded.", 5000)
                self.log_system.log_message('info', f"{downloaded_faxes_count} faxes downloaded")
                self.notify_user(downloaded_faxes_count)

            self.finished.emit(download_results)

        except Exception as e:
            self.log_system.log_message('error', f"Exception in download_fax_pdfs: {str(e)}")
            self.finished.emit([])

    def archive_fax(self, file_path, file_name, sent_timestamp):
        """Copy the downloaded fax to the archive folder based on when the fax was originally sent."""
        try:
            # **Extract Year, Month, Day, and Hour from sent_timestamp (Already in UTC)**
            try:
                if '.' in sent_timestamp:
                    timestamp = datetime.strptime(sent_timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
                else:
                    timestamp = datetime.strptime(sent_timestamp, "%Y-%m-%dT%H:%M:%SZ")

            except ValueError as e:
                self.log_system.log_message('error', f"Invalid sent timestamp format: {timestamp} - {str(e)}")
                return  # If timestamp parsing fails, do not archive the fax.

            # **Organize by sent date & hour in descending order (Year > Month > Day > Hour)**
            archive_dir = os.path.join(
                self.archive_path,
                timestamp.strftime("%Y"),
                timestamp.strftime("%m"),
                timestamp.strftime("%d"),
                timestamp.strftime("%H")
            )

            os.makedirs(archive_dir, exist_ok=True)  # Ensure archive directory exists
            archive_path = os.path.join(archive_dir, file_name)

            if not os.path.exists(archive_path):  # Prevent duplicate archiving
                shutil.copy(file_path, archive_path)  # Copy file to archive directory
                self.log_system.log_message('info', f"Archived fax to {archive_path}")
            else:
                self.log_system.log_message('info', f"Skipped archiving: Fax already archived at {archive_path}")

        except Exception as e:
            self.log_system.log_message('error', f"Failed to archive fax: {e}")

    def print_fax(self, file_path):
        try:
            if os.path.exists(file_path):
                printer = QPrinter()
                printer.setPrinterName(self.printer_name)
                printer.setOutputFormat(QPrinter.NativeFormat)
                printer.setPageSize(QPrinter.Letter)
                printer.setPageMargins(0, 0, 0, 0, QPrinter.Millimeter)

                available_printers = QPrinterInfo.availablePrinters()
                if any(p.printerName() == self.printer_name for p in available_printers):
                    doc = fitz.open(file_path)
                    painter = QPainter(printer)

                    for page_num in range(len(doc)):
                        page = doc[page_num]
                        pix = page.get_pixmap()
                        img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)

                        target_rect = QRect(0, 0, printer.pageRect().width(), printer.pageRect().height())
                        painter.drawImage(target_rect, img)

                        if page_num < len(doc) - 1:
                            printer.newPage()

                    painter.end()
                    doc.close()

                    if not os.path.exists(self.printed_path):
                        os.makedirs(self.printed_path)
                    shutil.move(file_path, os.path.join(self.printed_path, os.path.basename(file_path)))
                    self.log_system.log_message('info', f"Printed fax {file_path} and moved to 'Printed' directory.")
                else:
                    self.log_system.log_message('error', f"Printer {self.printer_name} not found.")
        except Exception as e:
            self.log_system.log_message('error', f"Exception in print_fax: {str(e)}")

    def delete_fax(self, fax_id):
        try:
            delete_url = f"https://telco-api.skyswitch.com/users/{self.fax_account}/faxes/{fax_id}/delete"
            headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
            delete_response = requests.post(delete_url, headers=headers)
            if delete_response.status_code == 200:
                self.log_system.log_message('info', f"Deleted fax {fax_id} successfully.")
            else:
                self.log_system.log_message('error', f"Failed to delete fax {fax_id}, HTTP {delete_response.status_code}")
        except Exception as e:
            self.log_system.log_message('error', f"Exception in delete_fax: {str(e)}")

    def notify_user(self, fax_count):
        try:
            icon_path = os.path.join(bundle_dir, "images", "fax_thumbnail.ico")
            notification.notify(
                title='New Faxes Received',
                message=f'{fax_count} new faxes have been downloaded.',
                app_name='FaxRetriever',
                timeout=10,
                app_icon=icon_path  # Add the icon path here
            )
            self.log_system.log_message('info', 'Notification sent successfully.')
        except Exception as e:
            self.log_system.log_message('error', f"Failed to send notification: {str(e)}")
            self._log_notification_debug_info()

    def _log_notification_debug_info(self):
        try:
            import plyer.platforms.win.notification
            self.log_system.log_message('debug', 'Windows notification backend is available.')
        except ImportError:
            self.log_system.log_message('debug', 'Windows notification backend is not available.')

        # Additional check to see if the notification function is available
        if hasattr(notification, 'notify'):
            self.log_system.log_message('debug', 'Notification function is available in plyer.')
        else:
            self.log_system.log_message('debug', 'Notification function is NOT available in plyer.')

        # Log the platform-specific backend used by plyer
        from plyer.utils import platform
        self.log_system.log_message('debug', f"Plyer platform: {platform}")
