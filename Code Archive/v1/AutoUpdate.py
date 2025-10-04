import os
import shutil
import subprocess
import sys

import requests
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QApplication
from SystemLog import SystemLog
from Version import __version__


# noinspection PyUnresolvedReferences
class CheckForUpdate(QThread):
    new_version_available = pyqtSignal(str, str)  # signals with the download URL

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window

    def run(self):
        try:
            if self.main_window:
                current_version = __version__
                url = "https://api.github.com/repos/TheMrDr/FaxRetriever/releases/latest"  # Use this for deployment of the software.
                # url = "https://api.github.com/repos/test/test/test"  # Use this for development to test the application
                response = requests.get(url)
                # self.save_full_response(response)  # Save the full response for troubleshooting

                if response.status_code == 200:
                    data = response.json()
                    if 'tag_name' in data:  # Ensure 'tag_name' exists in the data
                        latest_version = data['tag_name']
                        if latest_version > current_version:
                            # Check if there are any assets available for download
                            if 'assets' in data and data['assets']:
                                download_url = data['assets'][0]['browser_download_url']
                                if self.main_window.isVisible():
                                    self.main_window.update_status_bar(f"Updating app to latest version: {latest_version}. Please wait...", 5000)
                                self.new_version_available.emit(latest_version, download_url)
                            else:
                                if self.main_window.isVisible():
                                    self.main_window.update_status_bar("No assets found for the latest release.", 5000)
                        else:
                            if self.main_window.isVisible():
                                self.main_window.update_status_bar("No tag name found in the latest release.", 5000)
                else:
                    if self.main_window.isVisible():
                        self.main_window.update_status_bar(
                            f"Failed to fetch update data from GitHub. Status Code: {response.status_code}", 5000)
        except Exception as e:
            if self.main_window.isVisible():
                self.main_window.update_status_bar(f"Exception occurred while checking for updates: {str(e)}", 5000)


class UpgradeApplication(QThread):
    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url
        self.log_system = SystemLog()

    def run(self):
        try:
            # Download the update
            response = requests.get(self.download_url)
            if response.status_code == 200:
                update_file_path = 'update_temp.exe'
                with open(update_file_path, 'wb') as file:
                    file.write(response.content)

                current_exe = sys.executable
                backup_exe = current_exe + ".bak"

                # Create a backup of the current executable
                if os.path.exists(backup_exe):
                    os.remove(backup_exe)
                shutil.copy(current_exe, backup_exe)

                # Create a batch script to handle the executable update
                batch_script_path = 'update_script.bat'
                with open(batch_script_path, 'w') as bat_file:
                    bat_file.write(f"""
@echo off
taskkill /f /im FaxRetriever.exe >nul 2>&1

:loop
timeout /t 1
tasklist /fi "IMAGENAME eq {os.path.basename(current_exe)}" | find /i "{os.path.basename(current_exe)}" >nul
if errorlevel 1 (
    echo Updating...
    if exist "{current_exe}" (
        copy /y "{current_exe}" "{backup_exe}"
    )
    move /y "{update_file_path}" "{current_exe}"
    if not errorlevel 1 (
        echo Update successful, restarting...
        start "" "{current_exe}"
        del "{backup_exe}"  # Cleanup backup file
        del "*.txt" # Delete all .txt files in the same dir as FaxRetriever
    ) else (
        echo Failed to update, restoring backup...
        move /y "{backup_exe}" "{current_exe}"
    )
    del "{batch_script_path}"  # Cleanup the script itself
    exit
) else (
    goto loop
)
""")
                # Execute the batch file to perform the update
                subprocess.Popen(['cmd.exe', '/c', batch_script_path], close_fds=True)
                QApplication.instance().quit()  # Ensure the Qt application quits properly
            else:
                self.log_system.log_message("error", f"Failed to download the update. Status Code: {response.status_code}")
        except Exception as e:
            self.log_system.log_message("error", f"Exception occurred during upgrade: {str(e)}")