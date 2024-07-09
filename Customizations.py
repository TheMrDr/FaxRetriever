from PyQt5.QtCore import Qt
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtWidgets import (QPushButton, QDialog, QVBoxLayout, QListView, QDialogButtonBox, QProgressBar, QMessageBox)

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


class SelectInboxDialog(QDialog):
    def __init__(self, inboxes, parent=None):
        super().__init__(parent)
        self.save_manager = SaveManager(self)
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
            super().accept()  # Close the dialog only if save succeeds
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to save selected inboxes: " + str(e))
            if hasattr(self, 'main_window') and self.main_window.isVisible():
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
