import json
import os
import subprocess
import sys
import webbrowser

import requests
from PyQt5.QtCore import QThread, pyqtSignal

from Version import __version__


class CheckForUpdate(QThread):
    new_version_available = pyqtSignal(str, str)  # signals with the download URL


    def run(self):
        current_version = __version__
        # Correct URL to fetch the latest release
        url = "https://api.github.com/repos/TheMrDr/FaxRetriever/Version.py"
        response = requests.get(url)
        # self.save_full_response(response)  # Save the full response for troubleshooting

        if response.status_code == 200:
            data = response.json()
            # Check if 'tag_name' exists in the data
            if 'tag_name' in data:
                latest_version = data['tag_name']
                if latest_version > current_version:
                    # Check for assets and download URL
                    if data['assets']:
                        download_url = data['assets'][0]['browser_download_url']
                        self.new_version_available.emit(latest_version, download_url)
                    else:
                        print("No assets found for the latest release.")
            else:
                print("No tag name found in the latest release.")
        else:
            print(f"Failed to fetch update data from GitHub. Status Code: {response.status_code}")

    def save_full_response(self, response):
        """Save the full raw HTTP response to a file for debugging purposes."""
        response_details = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.json() if response.text else "No content"
        }
        with open("full_github_response.json", "w") as file:
            json.dump(response_details, file, indent=4)
            print("Saved full GitHub API response to 'full_github_response.json'")


class UpgradeApplication(QThread):
    def __init__(self, download_url, fallback_url):
        super().__init__()
        self.download_url = download_url
        self.fallback_url = fallback_url  # URL to open in browser for manual download

    def run(self):
        # Attempt to download the new version
        response = requests.get(self.download_url)
        if response.status_code == 200:
            update_file_path = 'update_temp.exe'
            with open(update_file_path, 'wb') as file:
                file.write(response.content)

            # Try to replace the current executable with the new one
            try:
                current_exe = sys.executable
                os.remove(current_exe + ".bak")  # Ensure there is no previous backup
                os.rename(current_exe, current_exe + ".bak")  # Backup the current executable
                os.rename(update_file_path, current_exe)  # Replace with the new file
                # Restart the application
                subprocess.Popen(current_exe, close_fds=True)
                sys.exit()  # Close the current instance
            except Exception as e:
                print(f"Failed to update: {e}")
                self.open_fallback_url()  # Open the fallback URL on failure
        else:
            print("Failed to download the update.")
            self.open_fallback_url()

    def open_fallback_url(self):
        """Open a web browser to allow manual download of the update."""
        webbrowser.open(self.fallback_url)