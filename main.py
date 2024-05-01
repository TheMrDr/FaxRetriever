"""
This application was developed by Clinic Networking, LLC and is the property of Clinic Networking, LLC.

The purpose of this application is to retrieve faxes on the SkySwitch platform's Instant Fax API.
"""

import sys

from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QAction, QLabel, QLineEdit, QPushButton, QFileDialog,
                             QGridLayout, QSystemTrayIcon, QMenu, QMessageBox, QDialog)

from Customizations import CustomPushButton, SelectInboxDialog
from Options import OptionsDialog
from ProgressBars import TokenLifespanProgressBar, FaxPollTimerProgressBar
from RetrieveToken import RetrieveToken
from SaveManager import SaveManager
from SendFax import SendFax
from SystemLog import SystemLog
from RetrieveNumbers import RetrieveNumbers
from Version import __version__


# noinspection PyUnresolvedReferences
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.version = __version__
        self.save_manager = SaveManager()
        self.retrieve_numbers = RetrieveNumbers()
        self.retrieve_token = RetrieveToken()
        self.send_fax_dialog = SendFax()
        self.sendFaxButton = CustomPushButton()
        self.options_dialog = OptionsDialog(self)

        # Load the app log services and set logging level.
        self.log_system = SystemLog()
        self.logging_level = self.save_manager.get_config_value('Log', 'logging_level')
        self.log_system.refresh_logging_level(self.logging_level)

        # Title the app window, set width, and set the app icon.
        self.setWindowTitle("Clinic Voice Instant Fax")
        self.setFixedWidth(600)
        self.setWindowIcon(QtGui.QIcon(".\\images\\logo.ico"))

        # Initialize UI components that might display or utilize the data
        self.tokenLifespanProgressBar = TokenLifespanProgressBar(main_window=self)
        self.faxPollTimerProgressBar = FaxPollTimerProgressBar(main_window=self,
                                                               token_progress_bar=self.tokenLifespanProgressBar)

        # Initialize signals and slots
        self.retrieve_token.token_retrieved.connect(self.tokenLifespanProgressBar.restart_progress)
        self.retrieve_token.token_retrieved.connect(self.faxPollTimerProgressBar.restart_progress)

        # Tray icon setup should ideally not depend on data loading
        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setIcon(QIcon(".\\images\\logo.ico"))
        self.initialize_tray_menu()

        self.initialize_ui()

        # Refresh data from configuration before initializing components that might depend on this data
        self.refresh_data_from_config()

        required_height = (self.centralWidget.sizeHint().height() + self.statusBar().sizeHint().height() +
                           self.menuBar().sizeHint().height() + 10)
        self.setFixedSize(600, required_height)  # Set width to 600 and height dynamically

    def closeEvent(self, event):
        messageBox = QMessageBox(self)
        messageBox.setIcon(QMessageBox.Question)
        messageBox.setWindowTitle('Close Confirmation')
        messageBox.setText(
            "Closing this application will prevent faxes from being automatically downloaded.\n"
            "Are you sure you wish to close the program?")
        yesButton = messageBox.addButton("Close Application", QMessageBox.AcceptRole)
        minimizeButton = messageBox.addButton("Minimize to Tray", QMessageBox.ActionRole)
        noButton = messageBox.addButton("Cancel", QMessageBox.RejectRole)
        messageBox.setDefaultButton(noButton)
        messageBox.exec_()

        if messageBox.clickedButton() == yesButton:
            self.log_system.log_message('info', 'Application Closed')
            event.accept()  # Proceed with the closure of the application
        elif messageBox.clickedButton() == minimizeButton:
            self.minimize_to_tray()
            event.ignore()  # Ignore the close event, keep the application running in tray
        else:
            event.ignore()  # Ignore the close event, the application remains fully open

    def initialize_tray_menu(self):
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Open Fax Manager", self.show)
        self.tray_menu.addAction("Close", self.close)
        self.tray_icon.setContextMenu(self.tray_menu)


    def initialize_ui(self):
        self.log_system.log_message('debug', 'UI Initializing')
        self.create_menu()
        self.log_system.log_message('debug', 'Menu Initialized')
        self.create_status_bar()
        self.log_system.log_message('debug', 'Status Bar Initialized')
        self.create_central_widget()
        self.log_system.log_message('debug', 'Main UI Initialized')
        self.update_status_bar(f"App Version: {self.version}", 30000)

    def create_menu(self):
        self.file_menu = self.menuBar().addMenu("&File")
        self.populate_file_menu()
        self.tools_menu = self.menuBar().addMenu("&Tools")
        self.populate_tools_menu()
        self.help_menu = self.menuBar().addMenu("&Help")
        self.populate_help_menu()

    def populate_file_menu(self):
        self.options_button = QAction("Options", self)
        self.options_button.triggered.connect(self.show_options_dialog)
        self.file_menu.addAction(self.options_button)
        self.options_button.setEnabled(True)

        self.minimize_app_button = QAction("Minimize", self)
        self.minimize_app_button.triggered.connect(self.minimize_to_tray)
        self.file_menu.addAction(self.minimize_app_button)

        self.close_app_button = QAction("Close", self)
        self.close_app_button.triggered.connect(self.close)
        self.file_menu.addAction(self.close_app_button)

    def populate_tools_menu(self):
        self.retrieve_token_button = QAction("Retrieve Token", self)
        self.retrieve_token_button.triggered.connect(self.startTokenRetrieval)
        self.tools_menu.addAction(self.retrieve_token_button)
        self.retrieve_token_button.setEnabled(True)

    def populate_help_menu(self):
        self.about_button = QAction("About", self)
        self.help_menu.addAction(self.about_button)

    def create_status_bar(self):
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("")

    def show_options_dialog(self):
        self.options_dialog.show()

    def create_central_widget(self):
        self.centralWidget = QWidget()
        self.setCentralWidget(self.centralWidget)

        # Main layout
        layout = QGridLayout()

        # Placeholder for a logo
        banner = QLabel()
        pixmap = QPixmap(".\\images\\banner_small.png")  # Set the path to your logo image
        banner.setPixmap(pixmap)
        banner.setAlignment(Qt.AlignCenter)
        banner.setFixedHeight(150)
        banner.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(banner, 0, 0, 2, 2)

        # Save Location
        saveLocationLayout = QGridLayout()
        self.saveLocationDisplay = QLineEdit()
        self.saveLocationDisplay.setPlaceholderText("No folder selected...")
        auto_retrieve_enabled = self.save_manager.get_config_value('Retrieval', 'autoretrieve')

        select_folder_button = QPushButton("Select Save Location")
        select_folder_button.clicked.connect(self.select_folder)
        saveLocationLayout.addWidget(self.saveLocationDisplay, 0, 0, 1, 1)
        saveLocationLayout.addWidget(select_folder_button, 0, 1, 1, 1)
        layout.addLayout(saveLocationLayout, 2, 0, 1, 2)

        self.caller_id_label = QLabel("Fax Inbox:")
        self.inbox_button = QPushButton("Choose an Inbox", self)
        self.inbox_button.clicked.connect(self.open_select_inbox_dialog)
        self.retrieve_numbers_thread = RetrieveNumbers()
        self.retrieve_numbers_thread.numbers_retrieved.connect(self.update_inbox_selection)
        layout.addWidget(self.caller_id_label, 3, 0, 1, 1)
        layout.addWidget(self.inbox_button, 3, 1, 1, 1)

        layout.addWidget(self.faxPollTimerProgressBar, 4, 0, 1, 2)
        layout.addWidget(self.tokenLifespanProgressBar, 5, 0, 1, 2)

        self.faxPollButton = CustomPushButton("Check for New Faxes")
        self.faxPollButton.clicked.connect(self.retrieve_faxes)
        layout.addWidget(self.faxPollButton, 6, 0, 1, 2)
        if auto_retrieve_enabled == "Enabled":
            self.faxPollButton.setVisible(True)
        elif auto_retrieve_enabled == "Disabled":
            self.faxPollButton.setVisible(False)

        self.sendFaxButton = CustomPushButton("Send a Fax")
        self.sendFaxButton.clicked.connect(self.show_send_fax_dialog)
        layout.addWidget(self.sendFaxButton, 7, 0, 1, 2)

        self.centralWidget.setLayout(layout)
        self.populate_data()

    def show_send_fax_dialog(self):
        self.send_fax_dialog.show()

    def refresh_data_from_config(self):
        self.api_username = self.save_manager.get_config_value('API', 'username')
        self.api_pass = self.save_manager.get_config_value('API', 'password')
        self.client_id = self.save_manager.get_config_value('Client', 'client_id')
        self.client_pass = self.save_manager.get_config_value('Client', 'client_secret')
        self.fax_user_info = self.save_manager.get_config_value('Account', 'account_id')
        self.fax_extension = self.save_manager.get_config_value('Fax', 'fax_extension')
        self.access_token = self.save_manager.get_config_value('Token', 'access_token')
        self.token_expiration = self.save_manager.get_config_value('Token', 'token_expiration')
        self.save_path = self.save_manager.get_config_value('Path', 'save_path')
        self.account_uuid = self.save_manager.get_config_value('Account', 'account_uuid')
        caller_ids = self.save_manager.get_config_value('Retrieval', 'fax_caller_id')
        self.populate_caller_ids(caller_ids)

    def populate_data(self):
        self.refresh_data_from_config()
        # Update the QLabel texts with the current values of the variables
        self.saveLocationDisplay.setText(self.save_path if self.save_path is not None else "Not Set")


    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        self.saveLocationDisplay.setText(folder_path)
        self.save_manager.config.set('Path', 'save_path', folder_path)

    def minimize_to_tray(self):
        self.hide()  # Hide the main window
        self.tray_icon.show()  # Show the tray icon

    def retrieve_faxes(self):
        self.update_status_bar("Retrieving Faxes...", 5000)
        self.faxPollTimerProgressBar.retrieveFaxes()

    def startTokenRetrieval(self):
        self.update_status_bar("Retrieving access token...", 5000)
        self.token_thread = RetrieveToken()
        self.token_thread.finished.connect(self.handle_token_response)
        self.token_thread.start()

    def handle_token_response(self, status, message):
        if status == "Success":
            self.update_status_bar("Access token retrieved successfully.", 5000)
            QMessageBox.information(self, "Success", message)
        else:
            self.update_status_bar("Failed to retrieve access token.", 5000)
            QMessageBox.critical(self, "Failure", message)

    def open_select_inbox_dialog(self):
        if not self.retrieve_numbers_thread.isRunning():
            self.retrieve_numbers_thread.start()
        else:
            print("Retrieval already in progress")

    def update_inbox_selection(self, numbers):
        dialog = SelectInboxDialog(numbers, self)
        if dialog.exec() == QDialog.Accepted:
            selected_inboxes = dialog.selected_inboxes()
            all_numbers = ','.join(numbers)  # Join all numbers into a single string separated by commas

            # Determine the button text and save the appropriate settings
            if selected_inboxes:
                if len(selected_inboxes) == 1:
                    button_text = selected_inboxes[0]
                else:
                    button_text = f"{len(selected_inboxes)} Inboxes"
                inbox_ids = ','.join(selected_inboxes)
                self.save_manager.config.set('Retrieval', 'fax_caller_id', inbox_ids)
            else:
                button_text = "Choose an Inbox"
                self.save_manager.config.set('Retrieval', 'fax_caller_id',
                                             '')  # Clear the setting if no inboxes selected

            # Update the button text
            self.inbox_button.setText(button_text)

            # Save all available numbers to the config, regardless of selection
            self.save_manager.config.set('Account', 'all_numbers', all_numbers)

            # Attempt to save the changes using the save manager
            try:
                self.save_manager.save_changes()
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

        # Auto-select if only one inbox is available
        if len(numbers) == 1:
            self.inbox_button.setText(numbers[0])
            self.save_manager.config.set('Retrieval', 'fax_caller_id', numbers[0])
            try:
                self.save_manager.save_changes()
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def populate_caller_ids(self, caller_ids):
        if caller_ids:
            numbers = caller_ids.split(',')  # Assuming numbers are saved delimited by commas
            if len(numbers) == 1:
                self.inbox_button.setText(numbers[0])
            elif len(numbers) > 1:
                self.inbox_button.setText(f"{len(numbers)} Inboxes")
        else:
            self.inbox_button.setText("Choose an Inbox")

    def update_status_bar(self, message, timeout):
        self.timeout = int(timeout)
        self.message = message
        self.status_bar.showMessage(f"{self.message}", self.timeout)


    def restart_application(self):
        """Restart the current application."""
        QApplication.quit()  # Close the application
        # executable = sys.executable  # Get the executable for the current application
        # subprocess.Popen([executable] + sys.argv)  # Start a new instance with the same arguments


if __name__ == '__main__':
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)

    log_system = SystemLog()
    log_system.log_message('info', 'Application Started')
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())