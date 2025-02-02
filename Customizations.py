from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem, QFont
from PyQt5.QtWidgets import (QPushButton, QDialog, QListView, QDialogButtonBox, QProgressBar, QMessageBox, QVBoxLayout,
                             QLabel, QHBoxLayout, QLineEdit)

from SaveManager import SaveManager


class CustomPushButton(QPushButton):
    def __init__(self, text='', parent=None):  # Ensure the text parameter is handled
        super().__init__(text, parent)  # Pass text to the QPushButton constructor
        self.setStyleSheet("""
            QPushButton {
                # background-color: #243954;
                # color: white;
                font-size: 24px;  /* Make the font large and white for easy identification */
                font-weight: bold;
                border: none;
                # padding: 8px;
            }
            # QPushButton:hover {
                # background-color: #2d5066;  /* Lighter shade on hover */
            }
        """)


# noinspection PyUnresolvedReferences
class SelectInboxDialog(QDialog):
    def __init__(self, inboxes, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.save_manager = self.main_window.save_manager if self.main_window else SaveManager(self)
        self.setWindowTitle("Select Inboxes")
        self.layout = QVBoxLayout(self)

        # ListView setup
        self.listView = QListView(self)
        self.model = QStandardItemModel(self.listView)
        for inbox in inboxes:
            item = QStandardItem(inbox)
            item.setCheckable(True)
            self.model.appendRow(item)
        self.listView.setModel(self.model)
        self.layout.addWidget(self.listView)

        # ButtonBox for OK and Cancel
        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, self)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)
        self.layout.addWidget(self.buttonBox)

    def selected_inboxes(self):
        selected = []
        for index in range(self.model.rowCount()):
            item = self.model.item(index)
            if item.checkState() == Qt.Checked:
                selected.append(item.text())
        return selected

    def accept(self):
        try:
            # Get the list of selected inboxes
            selected_inboxes = self.selected_inboxes()
            # Convert list to a string for storage
            selected_inboxes_str = ','.join(selected_inboxes)

            # Check the current settings before saving
            self.save_manager.get_config_value('UserSettings', 'selected_inboxes')
            # Save the selected inboxes using SaveManager
            self.save_manager.config.set('UserSettings', 'selected_inboxes', selected_inboxes_str)

            self.save_manager.save_changes()

            if self.main_window:
                self.main_window.reload_ui()

            super().accept()  # Close the dialog only if save succeeds
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to save selected inboxes: " + str(e))
            if self.main_window and self.main_window.isVisible():
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)



class HomescreenProgressBar(QProgressBar):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("QProgressBar::chunk { background-color: #2a81dc; margin: 1px; } "
                           "QProgressBar { border: 1px solid transparent; border-radius: 5px; } "
                           "QProgressBar::chunk:indeterminate { border-radius: 5px; } "
                           "QProgressBar::chunk:indeterminate { "
                           "    animation: pulse 1.5s ease-in-out infinite; "
                           "} "
                           "@keyframes pulse { "
                           "    0% { background-color: #2a81dc; } "
                           "    10% { background-color: #508ed8; } "
                           "    20% { background-color: #2a81dc; } "
                           "    30% { background-color: #508ed8; } "
                           "    40% { background-color: #2a81dc; } "
                           "    50% { background-color: #508ed8; } "
                           "    60% { background-color: #2a81dc; } "
                           "    70% { background-color: #508ed8; } "
                           "    80% { background-color: #2a81dc; } "
                           "    90% { background-color: #508ed8; } "
                           "    100% { background-color: #2a81dc; } }")


# noinspection PyUnresolvedReferences
class PhoneNumberInputDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Enter Fax Number")

        # Create the main layout
        self.layout = QVBoxLayout()

        # Create a message label with enhanced styling
        message_label = QLabel("No fax numbers retrieved.\nPlease enter your fax number:")
        message_label.setAlignment(Qt.AlignCenter)
        message_label.setFont(QFont("Arial", 10))
        self.layout.addWidget(message_label)

        # Create a phone number layout
        self.phone_layout = QHBoxLayout()

        # "+1" label
        self.plus_one_label = QLabel("+1")
        self.plus_one_label.setFont(QFont("Arial", 12, QFont.Bold))
        self.phone_layout.addWidget(self.plus_one_label)

        # Area code input
        self.area_code_input = QLineEdit()
        self.area_code_input.setMaxLength(3)
        self.area_code_input.setFixedWidth(40)
        self.area_code_input.setAlignment(Qt.AlignCenter)
        self.area_code_input.setFont(QFont("Arial", 12, QFont.Bold))
        self.phone_layout.addWidget(QLabel("("))
        self.phone_layout.addWidget(self.area_code_input)
        self.phone_layout.addWidget(QLabel(")"))

        # First 3 digits input
        self.first_three_input = QLineEdit()
        self.first_three_input.setMaxLength(3)
        self.first_three_input.setFixedWidth(40)
        self.first_three_input.setAlignment(Qt.AlignCenter)
        self.first_three_input.setFont(QFont("Arial", 12, QFont.Bold))
        self.phone_layout.addWidget(self.first_three_input)
        self.phone_layout.addWidget(QLabel("-"))

        # Last 4 digits input
        self.last_four_input = QLineEdit()
        self.last_four_input.setMaxLength(4)
        self.last_four_input.setFixedWidth(50)
        self.last_four_input.setAlignment(Qt.AlignCenter)
        self.last_four_input.setFont(QFont("Arial", 12, QFont.Bold))
        self.phone_layout.addWidget(self.last_four_input)

        self.layout.addLayout(self.phone_layout)

        # Button layout
        self.button_layout = QHBoxLayout()

        # OK button
        self.ok_button = QPushButton("OK")
        self.ok_button.setFixedHeight(30)
        self.ok_button.setFont(QFont("Arial", 10, QFont.Bold))
        self.ok_button.setStyleSheet("background-color: #2a81dc; padding: 6px 12px;")
        self.ok_button.clicked.connect(self.accept)

        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedHeight(30)
        self.cancel_button.setFont(QFont("Arial", 10, QFont.Bold))
        self.cancel_button.setStyleSheet("background-color: lightcoral; padding: 6px 12px;")
        self.cancel_button.clicked.connect(self.reject)

        self.button_layout.addWidget(self.ok_button)
        self.button_layout.addWidget(self.cancel_button)

        self.layout.addLayout(self.button_layout)

        # Set layout for the dialog
        self.setLayout(self.layout)

        # Connect input fields for auto-move
        self.area_code_input.textChanged.connect(self.move_cursor_to_next_field)
        self.first_three_input.textChanged.connect(self.move_cursor_to_next_field)

    def move_cursor_to_next_field(self):
        if len(self.area_code_input.text()) == 3:
            self.first_three_input.setFocus()
        elif len(self.first_three_input.text()) == 3:
            self.last_four_input.setFocus()

    def get_phone_number(self):
        area_code = self.area_code_input.text()
        first_three = self.first_three_input.text()
        last_four = self.last_four_input.text()

        if len(area_code) == 3 and len(first_three) == 3 and len(last_four) == 4:
            return f"1 ({area_code}) {first_three}-{last_four}"
        else:
            QMessageBox.warning(self, "Input Error", "Please enter a valid fax number.")
            return None