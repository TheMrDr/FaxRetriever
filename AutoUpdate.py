import os
import subprocess
import sys

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from Version import __version__


class CheckForUpdate(QThread):
    new_version_available = pyqtSignal(str, str)  # signals with the download URL

    def run(self):
        current_version = __version__
        url = "https://api.github.com/repos/your_username/your_repository/releases/latest"
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            latest_version = data['tag_name']
            if latest_version > current_version:
                download_url = data['assets'][0]['browser_download_url']
                self.new_version_available.emit(latest_version, download_url)


class UpgradeApplication(QThread):
    def __init__(self, download_url):
        super().__init__()
        self.download_url = download_url

    def run(self):
        # Download the new version
        response = requests.get(self.download_url)
        if response.status_code == 200:
            update_file_path = 'update_temp.exe'
            with open(update_file_path, 'wb') as file:
                file.write(response.content)

            # Replace the current executable with the new one
            try:
                current_exe = sys.executable
                os.remove(current_exe + ".bak") # Remove the old backup
                os.rename(current_exe, current_exe + ".bak")  # Rename old executable
                os.rename(update_file_path, current_exe)  # Move new executable to current
            except Exception as e:
                print(f"Failed to update: {e}")
                return

            # Restart the application
            subprocess.Popen(current_exe, close_fds=True)  # Relaunch the application
            sys.exit()  # Close the current instance of the application
        else:
            print("Failed to download the update.")