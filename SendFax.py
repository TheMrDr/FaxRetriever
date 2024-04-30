import os

import requests

from PyQt5 import QtGui
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
                             QMessageBox, QComboBox, QListWidget, QGridLayout)
from PyQt5.QtGui import QIntValidator

from SaveManager import EncryptionKeyManager
from SystemLog import SystemLog


# noinspection PyUnresolvedReferences
class SendFax(QDialog):
    finished = pyqtSignal(str, str)  # Signal to indicate the fax send result

    def __init__(self, parent=None):
        super().__init__(parent)
        self.encryption_manager = EncryptionKeyManager()
        self.setWindowIcon(QtGui.QIcon(".\\images\\logo.ico"))
        self.setWindowTitle("Send Fax")
        self.log_system = SystemLog()
        self.cover_sheet = None
        self.documents = []

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
        self.area_code_input.editingFinished.connect(
            lambda: self.focus_next(self.area_code_input, self.first_three_input))
        self.first_three_input.editingFinished.connect(
            lambda: self.focus_next(self.first_three_input, self.last_four_input))

        # Attach Cover Sheet
        self.cover_sheet_label = QLabel("Attached Cover Sheet:")
        self.cover_sheet_list = QListWidget()
        self.cover_sheet_list.setMaximumHeight(self.cover_sheet_list.sizeHintForRow(0) + 10 * self.cover_sheet_list.frameWidth())  # Set the max height to fit one row
        self.cover_sheet_button = QPushButton("Attach Cover Sheet")
        self.cover_sheet_button.clicked.connect(self.attach_cover_sheet)
        self.remove_cover_button = QPushButton("Remove Cover Sheet")
        self.remove_cover_button.clicked.connect(self.remove_cover_sheet)
        layout.addWidget(self.cover_sheet_label)
        layout.addWidget(self.cover_sheet_list)
        layout.addWidget(self.cover_sheet_button)
        layout.addWidget(self.remove_cover_button)

        # Attach Document
        self.document_label = QLabel("Attached Documents:")
        self.document_list = QListWidget()
        self.document_button = QPushButton("Attach Document")
        self.document_button.clicked.connect(self.attach_document)
        self.remove_document_button = QPushButton("Remove Selected Document")
        self.remove_document_button.clicked.connect(self.remove_document)
        layout.addWidget(self.document_label)
        layout.addWidget(self.document_list)
        layout.addWidget(self.document_button)
        layout.addWidget(self.remove_document_button)

        # Send Button
        self.send_button = QPushButton("Send Fax")
        self.send_button.clicked.connect(self.send_fax)
        layout.addWidget(self.send_button)

        # Cancel Button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)
        layout.addWidget(self.cancel_button)

    def populate_caller_id_combo_box(self):
        # Retrieve all fax numbers stored in the configuration
        all_fax_numbers = self.encryption_manager.get_config_value('Account', 'all_numbers')

        if all_fax_numbers:
            # Split the stored string by commas to get individual numbers
            numbers = all_fax_numbers.split(',')

            # Add each number to the combo box
            for number in numbers:
                self.caller_id_combo.addItem(number.strip())  # Ensure to strip any whitespace

            # Automatically select the first number if there's only one
            if len(numbers) == 1:
                self.caller_id_combo.setCurrentIndex(0)

    def populate_area_code(self):
        if self.caller_id_combo.currentIndex() != -1:
            selected_number = self.caller_id_combo.currentText()
            area_code = selected_number[1:4]  # Assuming the format +1XXXYYYZZZZ
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

    def attach_cover_sheet(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(self, "Select a cover sheet", "", "Documents (*.pdf *.doc *.docx);;Images (*.jpg *.png *.tiff);;Text Files (*.txt)", options=options)
        if filename:
            self.cover_sheet_list.clear()
            self.cover_sheet_list.addItem(self.format_display_name(filename))

    def remove_cover_sheet(self):
        self.cover_sheet_list.clear()

    def attach_document(self):
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(self, "Select one or more files to fax", "", "Documents (*.pdf *.doc *.docx);;Images (*.jpg *.png *.tiff);;Text Files (*.txt)", options=options)
        if files:
            for file in files:
                self.document_list.addItem(self.format_display_name(file))

    def remove_document(self):
        selected_items = self.document_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            self.document_list.takeItem(self.document_list.row(item))

    def send_fax(self):
        self.fax_user = self.encryption_manager.get_config_value('Account', 'fax_user')
        self.token = self.encryption_manager.get_config_value('Token', 'access_token')
        self.caller_id = self.caller_id_combo.currentText().strip()
        destination = '1' + self.area_code_input.text() + self.first_three_input.text() + self.last_four_input.text()

        # Prepare headers
        headers = {
            "authorization": f"Bearer {self.token}"
        }
        url = f"https://telco-api.skyswitch.com/users/{self.fax_user}/faxes/send"

        # Prepare multipart/form-data payload
        files = {}
        data = {
            "caller_id": self.caller_id,
            "destination": destination
        }

        # Adding the cover sheet if selected
        if self.cover_sheet:
            files['raw_files'] = ('cover_sheet', open(self.cover_sheet, 'rb'), 'application/pdf')

        # Adding other documents
        for idx, doc in enumerate(self.documents):
            file_extension = os.path.splitext(doc)[1]
            mime_type = 'application/pdf' if file_extension == '.pdf' else 'image/' + file_extension.strip('.')
            file_key = f'raw_files_{idx + 1}'
            files[file_key] = (os.path.basename(doc), open(doc, 'rb'), mime_type)

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
        finally:
            # Make sure to close all files opened for sending
            for file in files.values():
                file[1].close()

# if __name__ == '__main__':
#     app = QApplication(sys.argv)
#     ex = SendFax()
#     ex.exec()  # Use exec_ to open the QDialog modally
#     sys.exit(app.exec_())
