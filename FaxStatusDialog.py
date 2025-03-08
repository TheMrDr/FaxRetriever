import os
import re
import sys
from datetime import datetime, timezone

import pytz
import requests
from PyQt5.QtCore import pyqtSignal, QThread, QTimer, Qt, QUrl
from PyQt5.QtGui import QPixmap
from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt5.QtWidgets import (QDialog, QTableWidget, QTableWidgetItem, QVBoxLayout, QLineEdit, QWidget,
                             QLabel, QMessageBox)

from SaveManager import SaveManager

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


def format_phone_number(number):
    clean_number = re.sub(r'\D', '', str(number))
    formatted = f"1 ({clean_number[1:4]}) {clean_number[4:7]}-{clean_number[7:11]}"
    return formatted


class HoverLabel(QLabel):
    hovered = pyqtSignal(QPixmap)
    unhovered = pyqtSignal()

    def __init__(self, thumbnail_url, token, parent=None):
        super().__init__(parent)
        self.thumbnail_url = thumbnail_url
        self.token = token
        self.setMouseTracking(True)
        self.network_manager = QNetworkAccessManager(self)
        self.network_manager.finished.connect(self.handle_network_response)

        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(500)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.timeout.connect(self.fetch_thumbnail)

    def handle_network_response(self, reply):
        if reply.error() == QNetworkReply.AuthenticationRequiredError:
            print("Authentication failed. Check token.")
        elif reply.error() != QNetworkReply.NoError:
            print("Failed to fetch thumbnail:", reply.errorString())
        else:
            image_data = reply.readAll()
            pixmap = QPixmap()
            pixmap.loadFromData(image_data)
            self.hovered.emit(pixmap)

    def fetch_thumbnail(self):
        request = QNetworkRequest(QUrl(self.thumbnail_url))
        token_header = f"Bearer {self.token}".encode('utf-8')
        request.setRawHeader(b"Authorization", token_header)
        self.network_manager.get(request)


class ThumbnailPopup(QWidget):
    def __init__(self, image_path, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.WindowDoesNotAcceptFocus)
        self.setLayout(QVBoxLayout())
        self.label = QLabel()
        pixmap = QPixmap(image_path)
        self.label.setPixmap(pixmap)
        self.layout().addWidget(self.label)
        self.adjustSize()

    def showAt(self, pos):
        self.move(pos)
        self.show()


class CustomFaxTable(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setColumnCount(7)  # Reduced number of columns
        self.setHorizontalHeaderLabels(["Fax ID", "Direction", "Fax Source", "Fax Destination", "Status", "Pages", "Timestamp"])
        self.setRowCount(0)
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText("Search...")
        self.search_box.textChanged.connect(self.filter_table)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setSelectionMode(QTableWidget.SingleSelection)
        self.setEditTriggers(QTableWidget.NoEditTriggers)

    def add_fax(self, fax):
        try:
            row = self.rowCount()
            self.insertRow(row)
            self.setItem(row, 0, QTableWidgetItem(str(fax['id'])))
            self.setItem(row, 1, QTableWidgetItem(fax.get('direction', 'N/A')))
            self.setItem(row, 2, QTableWidgetItem(format_phone_number(fax.get('caller_id', 'N/A'))))
            self.setItem(row, 3, QTableWidgetItem(format_phone_number(fax.get('destination', 'N/A'))))
            self.setItem(row, 4, QTableWidgetItem(fax.get('status', 'N/A')))
            self.setItem(row, 5, QTableWidgetItem(str(fax.get('pages', 'N/A'))))
            self.setItem(row, 6, QTableWidgetItem(self.format_timestamp(fax.get('created_at', 'N/A'))))
            self.setRowHeight(row, 40)  # Ensuring all rows have a consistent height
        except Exception as e:
            print(f"Error adding fax to table: {str(e)}")

    @staticmethod
    def format_phone_number(number):
        clean_number = re.sub(r'\D', '', str(number))
        return f"1 ({clean_number[1:4]}) {clean_number[4:7]}-{clean_number[7:11]}"

    def format_timestamp(self, timestamp):
        try:
            if timestamp == 'N/A':
                return 'N/A'
            dt = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%S.%fZ")
            local_timezone = pytz.timezone('America/New_York')  # Replace with your local timezone
            dt = dt.replace(tzinfo=timezone.utc).astimezone(local_timezone)
            return dt.strftime('%Y-%m-%d %H:%M:%S %Z')
        except Exception as e:
            print(f"Error formatting timestamp: {str(e)}")
            return 'N/A'

    def filter_table(self):
        try:
            filter_text = self.search_box.text().lower()
            for i in range(self.rowCount()):
                row_visible = any(filter_text in self.item(i, j).text().lower() for j in range(self.columnCount()))
                self.setRowHidden(i, not row_visible)
        except Exception as e:
            print(f"Error filtering table: {str(e)}")

    def enable_sorting_and_refresh(self):
        try:
            self.adjust_column_sizes()
            self.setSortingEnabled(True)
            self.sortByColumn(6, Qt.DescendingOrder)  # Default sorting by the 'Timestamp' column
        except Exception as e:
            print(f"Error enabling sorting and refresh: {str(e)}")

    def adjust_column_sizes(self):
        try:
            for column in range(self.columnCount()):
                self.resizeColumnToContents(column)  # Dynamically resize each column based on its content
        except Exception as e:
            print(f"Error adjusting column sizes: {str(e)}")


class RetrieveFaxesThread(QThread):
    finished = pyqtSignal(list)

    def __init__(self, fax_account, token):
        super().__init__()
        self.fax_account = fax_account
        self.token = token

    def run(self):
        try:
            base_url = "https://telco-api.skyswitch.com"
            inbound_url = f"{base_url}/users/{self.fax_account}/faxes/inbound"
            outbound_url = f"{base_url}/users/{self.fax_account}/faxes/outbound"
            headers = {"accept": "application/json", "authorization": f"Bearer {self.token}"}
            faxes = []

            # Handle inbound faxes
            inbound_response = requests.get(inbound_url, headers=headers)
            if inbound_response.status_code == 200:
                inbound_faxes = inbound_response.json().get('data', [])
                # Add 'direction' field to each inbound fax
                for fax in inbound_faxes:
                    fax['direction'] = 'Inbound'
                faxes.extend(inbound_faxes)

            # Handle outbound faxes
            outbound_response = requests.get(outbound_url, headers=headers)
            if outbound_response.status_code == 200:
                outbound_faxes = outbound_response.json().get('data', [])
                # Add 'direction' field to each outbound fax
                for fax in outbound_faxes:
                    fax['direction'] = 'Outbound'
                faxes.extend(outbound_faxes)

            self.finished.emit(faxes)
        except Exception as e:
            print(f"Error retrieving faxes: {str(e)}")
            self.finished.emit([])


class FaxStatusDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fax Status")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove Help (?) Button
        self.setFixedSize(800, 600)
        self.layout = QVBoxLayout(self)
        self.fax_result_table = CustomFaxTable()
        self.layout.addWidget(self.fax_result_table.search_box)
        self.layout.addWidget(self.fax_result_table)

        self.save_manager = SaveManager()
        try:
            self.fax_account = self.save_manager.get_config_value('Account', 'fax_user')
            self.token = self.save_manager.get_config_value('Token', 'access_token')
            self.retrieve_thread = RetrieveFaxesThread(self.fax_account, self.token)
        except Exception as e:
            print(f"Error initializing FaxStatusDialog: {str(e)}")
            QMessageBox.critical(self, "Error", f"Initialization failed: {str(e)}")
            self.close()

    def initiate_fetch(self):
        print("Starting to fetch faxes...")
        # Disconnect any existing connections to avoid duplicating slots execution
        try:
            self.retrieve_thread.finished.disconnect()
        except TypeError:
            # No connection exists yet; ignore the exception
            pass
        try:
            self.retrieve_thread.finished.connect(self.populate_table)
            self.retrieve_thread.start()
        except Exception as e:
            print(f"Error initiating fetch: {str(e)}")

    def populate_table(self, faxes):
        try:
            print(f"Populating table with {len(faxes)} faxes")
            self.fax_result_table.clearContents()
            self.fax_result_table.setRowCount(0)
            if not faxes:
                print("No faxes to display.")
                return

            for fax in faxes:
                self.fax_result_table.add_fax(fax)

            # Delay sorting to ensure all widgets are loaded
            QTimer.singleShot(100, self.fax_result_table.enable_sorting_and_refresh)
        except Exception as e:
            print(f"Error populating table: {str(e)}")

    def closeEvent(self, event):
        # Clear the table when the dialog is about to close
        try:
            self.fax_result_table.clearContents()
            self.fax_result_table.setRowCount(0)
        except Exception as e:
            print(f"Error during closeEvent: {str(e)}")
        super().closeEvent(event)
