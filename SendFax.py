import os
import sys
import requests

from PIL import Image

from PyQt5 import QtGui
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QIntValidator
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
                             QComboBox, QListWidget, QGridLayout, QMessageBox, QMenu, QAction)

from SaveManager import SaveManager
from SystemLog import SystemLog

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory

# Use the bundle_dir to construct paths to bundled files
class SendFax(QDialog):
    finished = pyqtSignal(str, str)  # Signal to indicate the fax send result

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.encryption_manager = SaveManager(self.main_window)
        self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
        self.setWindowTitle("Send Fax")
        self.log_system = SystemLog()
        self.cover_sheet_path = None  # Store the full path to the cover sheet
        self.documents_paths = []  # List to store full paths of attached documents


        self.setWindowTitle('Send Fax')
        self.setup_ui()

    def setup_validators(self):
        validator = QIntValidator(0, 999)
        self.area_code_input.setValidator(validator)
        self.first_three_input.setValidator(validator)
        self.last_four_input.setValidator(QIntValidator(0, 9999))

    def setup_ui(self):

        layout = QVBoxLayout(self)

        # Caller ID selection
        self.caller_id_label = QLabel("Faxing From:")
        self.caller_id_combo = QComboBox()
        self.populate_caller_id_combo_box()
        self.caller_id_combo.currentIndexChanged.connect(self.populate_area_code)
        layout.addWidget(self.caller_id_label)
        layout.addWidget(self.caller_id_combo)

        self.destination_label = QLabel("Destination Number:")
        layout.addWidget(self.destination_label)

        # Setup grid layout for phone number
        grid_layout = QGridLayout()
        layout.addLayout(grid_layout)

        # Destination phone number
        self.phone_label = QLabel("+1 (")
        self.area_code_input = QLineEdit()
        self.area_code_input.setMaxLength(3)
        self.first_three_input = QLineEdit()
        self.first_three_input.setMaxLength(3)
        self.last_four_input = QLineEdit()
        self.last_four_input.setMaxLength(4)

        grid_layout.addWidget(self.phone_label, 0, 0)
        grid_layout.addWidget(self.area_code_input, 0, 1)
        grid_layout.addWidget(QLabel(")"), 0, 2)
        grid_layout.addWidget(self.first_three_input, 0, 3)
        grid_layout.addWidget(QLabel("-"), 0, 4)
        grid_layout.addWidget(self.last_four_input, 0, 5)

        self.populate_area_code()

        # Connect field transitions
        self.area_code_input.textChanged.connect(
            lambda: self.focus_next(self.area_code_input, self.first_three_input))
        self.first_three_input.textChanged.connect(
            lambda: self.focus_next(self.first_three_input, self.last_four_input))

        # Attach Cover Sheet
        self.cover_sheet_label = QLabel("Attached Cover Sheet:")
        self.cover_sheet_list = QListWidget()
        self.cover_sheet_list.setContextMenuPolicy(Qt.CustomContextMenu)  # Enable custom context menu
        self.cover_sheet_list.setMaximumHeight(self.cover_sheet_list.sizeHintForRow(0) + 10 * self.cover_sheet_list.frameWidth())  # Set the max height to fit one row
        self.cover_sheet_button = QPushButton("Add/Change Cover Sheet")
        self.cover_sheet_button.clicked.connect(self.attach_or_change_cover_sheet)
        layout.addWidget(self.cover_sheet_label)
        layout.addWidget(self.cover_sheet_list)
        layout.addWidget(self.cover_sheet_button)

        # Attach Document
        self.document_label = QLabel("Attached Documents:")
        self.document_list = QListWidget()
        self.document_list.setContextMenuPolicy(Qt.CustomContextMenu)  # Enable custom context menu
        self.document_list.customContextMenuRequested.connect(self.show_document_context_menu)  # Connect to context menu event
        self.document_button = QPushButton("Attach Document")
        self.document_button.clicked.connect(self.attach_document)
        layout.addWidget(self.document_label)
        layout.addWidget(self.document_list)
        layout.addWidget(self.document_button)

        # Send Button
        self.send_button = QPushButton("Send Fax")
        self.send_button.clicked.connect(self.send_fax)
        layout.addWidget(self.send_button)

        # Cancel Button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)
        layout.addWidget(self.cancel_button)

    def show_document_context_menu(self, pos):
        document_item = self.document_list.itemAt(pos)
        if document_item:
            menu = QMenu()
            remove_action = QAction("Remove Document", self)
            remove_action.triggered.connect(self.remove_document)
            menu.addAction(remove_action)
            menu.exec_(self.document_list.mapToGlobal(pos))

    # def remove_document(self, item):
    #     index = self.document_list.row(item)
    #     del self.documents_paths[index]  # Remove the corresponding full path
    #     self.document_list.takeItem(index)

    def attach_or_change_cover_sheet(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(self, "Select a cover sheet", "", "Documents (*.pdf *.doc *.docx);;Images (*.jpg *.png *.tiff);;Text Files (*.txt)", options=options)
        if filename:
            self.cover_sheet_path = filename  # Store the full path
            self.cover_sheet_list.clear()
            self.cover_sheet_list.addItem(self.format_display_name(filename))

    def populate_caller_id_combo_box(self):
        # Retrieve all fax numbers stored in the configuration
        all_fax_numbers = self.encryption_manager.get_config_value('Account', 'all_numbers')

        if all_fax_numbers:
            # Split the stored string by commas to get individual numbers
            numbers = all_fax_numbers.split(',')

            # Format each number before adding it to the combo box
            formatted_numbers = [self.main_window.format_phone_number(num) for num in numbers]

            # Add each formatted number to the combo box
            for number in formatted_numbers:
                self.caller_id_combo.addItem(number.strip())  # Ensure to strip any whitespace

            # Automatically select the first number if there's only one
            if len(numbers) == 1:
                self.caller_id_combo.setCurrentIndex(0)

    def populate_area_code(self):
        if self.caller_id_combo.currentIndex() != -1:
            selected_number = self.caller_id_combo.currentText()
            area_code = selected_number[selected_number.find('(') + 1:selected_number.find(
                ')')]  # Extract area code between parentheses
            self.area_code_input.setText(area_code)

    def focus_next(self, current_widget, next_widget):
        if len(current_widget.text()) == current_widget.maxLength():
            next_widget.setFocus()

    def format_display_name(self, filepath):
        """ Format the filename to display only the file name, not the full path,
            and truncate it if too long. """
        base_name = os.path.basename(filepath)
        if len(base_name) > 30:  # Assuming 30 characters as a threshold for too long
            return f"{base_name[:15]}...{base_name[-10:]}"  # Keep the start and end of the filename
        return base_name

    def attach_or_change_cover_sheet(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(self, "Select a cover sheet", "",
                                                  "Documents (*.pdf *.doc *.docx *.jpg *.png *.tif *.tiff *.txt)",
                                                  options=options)
        if filename:
            self.cover_sheet_path = filename  # Store the full path
            self.cover_sheet_list.clear()
            self.cover_sheet_list.addItem(self.format_display_name(filename))

    def remove_cover_sheet(self):
        self.cover_sheet_list.clear()

    def attach_document(self):
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(self, "Select one or more files to fax", "",
                                                "Documents (*.pdf *.doc *.docx *.jpg *.png *.tif *.tiff *.txt)",
                                                options=options)
        if files:
            for file in files:
                self.documents_paths.append(file)  # Store full path
                self.document_list.addItem(self.format_display_name(file))

    def remove_document(self):
        selected_items = self.document_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            index = self.document_list.row(item)
            del self.documents_paths[index]  # Remove the corresponding full path
            self.document_list.takeItem(index)

    def send_fax(self):
        self.fax_user = self.encryption_manager.get_config_value('Account', 'fax_user')
        self.token = self.encryption_manager.get_config_value('Token', 'access_token')
        self.caller_id = self.caller_id_combo.currentText().strip()
        destination = '1' + self.area_code_input.text() + self.first_three_input.text() + self.last_four_input.text()
        url = f"https://telco-api.skyswitch.com/users/{self.fax_user}/faxes/send"

        # Prepare multipart/form-data payload
        headers = {"Authorization": f"Bearer {self.token}"}
        files = {}
        data = {"caller_id": self.caller_id, "destination": destination}

        # Add the cover sheet if selected
        if self.cover_sheet_path:
            files['filename[0]'] = (os.path.basename(self.cover_sheet_path), open(self.cover_sheet_path, 'rb'), 'application/pdf')

        # Add other documents
        for idx, doc_path in enumerate(self.documents_paths):
            file_extension = os.path.splitext(doc_path)[1]
            mime_type = 'application/pdf' if file_extension == '.pdf' else 'image/' + file_extension.strip('.')
            file_key = f'filename[{idx + 1}]' if self.cover_sheet_path else f'filename[{idx}]'
            files[file_key] = (os.path.basename(doc_path), open(doc_path, 'rb'), mime_type)

        # Send the request with files and data
        try:
            response = requests.post(url, files=files, data=data, headers=headers)
            if response.status_code == 200:
                QMessageBox.information(self, "Fax Sent", "Your fax has been queued successfully.")
                self.accept()  # Close the dialog after sending
            else:
                QMessageBox.critical(self, "Sending Failed", f"Failed to send fax: {response.text}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An error occurred: {str(e)}")
            self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
        finally:
            # Make sure to close all files opened for sending
            for _, file_tuple in files.items():
                file_tuple[1].close()

    def convert_tif_to_jpg(self, tif_path):
        # Convert .TIF file to .JPG
        jpg_path = tif_path.replace(".tif", ".jpg").replace(".TIF", ".JPG")
        image = Image.open(tif_path)
        image.convert('RGB').save(jpg_path, 'JPEG')
        return jpg_path