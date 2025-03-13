import json
import os
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QTableWidget,
                             QTableWidgetItem, QHeaderView, QFileDialog, QComboBox, QGridLayout, QListWidget, QWidget)
from PyQt5.QtGui import QIcon, QFont, QRegExpValidator
from PyQt5.QtCore import Qt, QRegExp

import sys, os

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory

class AddressBookManager:
    def __init__(self, filename="address_book.json"):
        self.filename = filename
        self.contacts = self.load_contacts()

    def load_contacts(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, "r") as file:
                    return sorted(json.load(file), key=lambda x: x['name'].lower())
            except json.JSONDecodeError:
                return []
        return []

    def save_contacts(self):
        self.contacts.sort(key=lambda x: x['name'].lower())
        with open(self.filename, "w") as file:
            json.dump(self.contacts, file, indent=4)

    def add_contact(self, name, phone):
        self.contacts.append({"name": name, "phone": phone})
        self.save_contacts()

    def delete_contact(self, index):
        if 0 <= index < len(self.contacts):
            del self.contacts[index]
            self.save_contacts()

    def export_contacts(self, filepath):
        with open(filepath, "w") as file:
            json.dump(self.contacts, file, indent=4)

    def import_contacts(self, filepath):
        try:
            with open(filepath, "r") as file:
                imported_contacts = json.load(file)
                if isinstance(imported_contacts, list):
                    self.contacts.extend(imported_contacts)
                    self.save_contacts()
        except json.JSONDecodeError:
            pass  # Handle import error


class AddressBookDialog(QDialog):
    def __init__(self, address_book_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Address Book")
        self.setFixedSize(650, 400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove help '?' button
        self.address_book_manager = address_book_manager

        self.layout = QVBoxLayout()
        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Name", "Phone Number", "Actions"])
        self.table.verticalHeader().setVisible(False)  # Remove row numbers
        self.table.setStyleSheet("QTableWidget { font-size: 12pt; }")  # Improve aesthetics
        self.populate_table()

        # Adjust column sizes and center align content
        self.adjust_table_styling()

        self.layout.addWidget(self.table)

        # Import and Export Buttons
        button_layout = QHBoxLayout()
        self.import_button = QPushButton("Import Contact File")
        self.export_button = QPushButton("Export All Contacts")
        self.import_button.setFont(QFont("Arial", 12))
        self.export_button.setFont(QFont("Arial", 12))
        self.import_button.clicked.connect(self.import_contacts)
        self.export_button.clicked.connect(self.export_contacts)

        button_layout.addWidget(self.import_button)
        button_layout.addWidget(self.export_button)
        self.layout.addLayout(button_layout)

        self.setLayout(self.layout)

    def populate_table(self):
        self.address_book_manager.contacts.sort(key=lambda x: x['name'].lower())  # Ensure contacts are sorted
        self.table.setRowCount(len(self.address_book_manager.contacts))
        for row, contact in enumerate(self.address_book_manager.contacts):
            name_item = QTableWidgetItem(contact['name'])
            phone_item = QTableWidgetItem(contact['phone'])
            name_item.setTextAlignment(Qt.AlignCenter)
            phone_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 0, name_item)
            self.table.setItem(row, 1, phone_item)

            action_layout = QHBoxLayout()
            action_layout.setContentsMargins(2, 2, 2, 2)
            action_layout.setSpacing(4)

            select_button = QPushButton()
            select_button.setIcon(QIcon(os.path.join(bundle_dir, "images", "CheckMark.png")))
            # select_button.setFixedSize(35, 35)
            select_button.setToolTip("Select Contact")
            select_button.clicked.connect(lambda _, r=row: self.select_contact(r))

            delete_button = QPushButton()
            delete_button.setIcon(QIcon(os.path.join(bundle_dir, "images", "TrashCan.png")))
            # delete_button.setFixedSize(35, 35)
            delete_button.setToolTip("Delete Contact")
            delete_button.clicked.connect(lambda _, r=row: self.delete_contact(r))

            action_widget = QWidget()
            action_container = QHBoxLayout(action_widget)
            action_container.addWidget(select_button)
            action_container.addWidget(delete_button)
            action_container.setContentsMargins(2, 2, 2, 2)
            action_container.setSpacing(4)
            action_widget.setLayout(action_container)

            self.table.setCellWidget(row, 2, action_widget)

        self.adjust_table_styling()

    def adjust_table_styling(self):
        self.table.setColumnWidth(1, 200)  # Phone Number Column
        self.table.setColumnWidth(2, 100)  # Actions Column
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)  # Expand Name column

        for col in range(3):
            self.table.horizontalHeaderItem(col).setTextAlignment(Qt.AlignCenter)

        for row in range(self.table.rowCount()):
            for col in range(3):
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)

    def select_contact(self, row):
        selected_phone = self.address_book_manager.contacts[row]['phone']
        self.parent().populate_phone_fields(selected_phone)
        self.accept()

    def delete_contact(self, row):
        self.address_book_manager.delete_contact(row)
        self.populate_table()

    def import_contacts(self):
        filepath, _ = QFileDialog.getOpenFileName(self, "Import Contacts", "", "JSON Files (*.json)")
        if filepath:
            self.address_book_manager.import_contacts(filepath)
            self.populate_table()

    def export_contacts(self):
        filepath, _ = QFileDialog.getSaveFileName(self, "Export Contacts", "", "JSON Files (*.json)")
        if filepath:
            self.address_book_manager.export_contacts(filepath)


class AddContactDialog(QDialog):
    def __init__(self, address_book_manager, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Contact")
        self.setFixedSize(350, 200)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove '?' button
        self.address_book_manager = address_book_manager

        layout = QVBoxLayout()
        self.name_input = QLineEdit()
        self.name_input.setFont(QFont("Arial", 14))  # Increase font size for readability

        phone_layout = QHBoxLayout()
        self.phone_label = QLabel("+1 ")  # Display +1 as a static label
        self.phone_label.setFont(QFont("Arial", 14))

        self.phone_input = QLineEdit()
        self.phone_input.setPlaceholderText("Enter 10-digit phone number")
        self.phone_input.setFont(QFont("Arial", 14))  # Increase font size
        self.phone_input.setMaxLength(10)  # Limit to 10 digits
        self.phone_input.setValidator(QRegExpValidator(QRegExp("\\d{10}")))  # Ensure only digits
        self.phone_input.textChanged.connect(self.validate_phone_number)  # Validate on change

        phone_layout.addWidget(self.phone_label)
        phone_layout.addWidget(self.phone_input)

        self.add_button = QPushButton("Add Contact")
        self.add_button.setFont(QFont("Arial", 12))
        self.add_button.setFixedHeight(40)
        self.add_button.setEnabled(False)  # Disabled initially
        self.add_button.clicked.connect(self.add_contact)

        layout.addWidget(QLabel("Contact Name:"))
        layout.addWidget(self.name_input)
        layout.addWidget(QLabel("Phone Number:"))
        layout.addLayout(phone_layout)  # Add the new phone layout
        layout.addWidget(self.add_button)
        self.setLayout(layout)

    def validate_phone_number(self):
        phone = self.phone_input.text().strip()
        if len(phone) == 10 and phone.isdigit():
            self.add_button.setEnabled(True)
        else:
            self.add_button.setEnabled(False)

    def add_contact(self):
        name = self.name_input.text().strip()
        phone = self.phone_input.text().strip()
        if name and phone:
            self.address_book_manager.add_contact(name, phone)
            self.accept()
