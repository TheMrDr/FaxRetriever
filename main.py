"""
This application was developed by Clinic Networking, LLC and is the property of Clinic Networking, LLC.

The purpose of this application is to retrieve faxes on the SkySwitch platform's Instant Fax API.
"""

import os
import sys

from PyQt5 import QtGui
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QMainWindow, QApplication, QWidget, QAction, QLabel, QLineEdit, QPushButton, QFileDialog,
                             QGridLayout, QSystemTrayIcon, QMenu, QMessageBox, QDialog)

# Import other modules after setting bundle_dir
# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory

from AboutDialog import AboutDialog
from AutoUpdate import CheckForUpdate, UpgradeApplication
from Customizations import CustomPushButton, SelectInboxDialog
from FaxStatusDialog import FaxStatusDialog
from Options import OptionsDialog
from ProgressBars import TokenLifespanProgressBar, FaxPollTimerProgressBar
from RetrieveNumbers import RetrieveNumbers
from RetrieveToken import RetrieveToken
from SaveManager import SaveManager
from SendFax import SendFax
from SystemLog import SystemLog
from Version import __version__


# noinspection PyUnresolvedReferences
class MainWindow(QMainWindow):
    settingsLoaded = pyqtSignal()  # Custom signal to load settings after GUI is shown

    def __init__(self):
        super().__init__()
        self.log_system = None
        self.save_manager = None
        self.version = None
        self.status_bar = None
        self.update_checker_timer = None
        self.initialize_attributes()
        self.setup_ui()
        self.connect_signals()
        self.load_initial_data()
        self.finalize_initialization()

    def initialize_attributes(self):
        """Initialize attributes with default values or configurations"""
        self.status_bar = None
        self.version = __version__
        self.save_manager = SaveManager(self)
        self.log_system = SystemLog()
        self.logging_level = self.save_manager.get_config_value('UserSettings', 'logging_level')
        self.log_system.refresh_logging_level(self.logging_level)

    def setup_ui(self):
        """Setup the main window UI components"""
        self.setWindowTitle("Clinic Voice Instant Fax")
        self.setFixedWidth(600)
        self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
        self.initialize_components()
        self.initialize_tray_menu()

    def initialize_components(self):
        """Initialize UI components that might display or utilize saved data"""
        self.retrieve_numbers = RetrieveNumbers(self)
        self.retrieve_token = RetrieveToken(self)  # Pass self as main_window
        self.send_fax_dialog = SendFax(self)
        self.about_dialog = AboutDialog()
        self.fax_status_dialog = FaxStatusDialog(self)
        self.faxPollButton = CustomPushButton("Check for New Faxes")
        self.send_fax_button = CustomPushButton("Send a Fax")
        self.tokenLifespanProgressBar = TokenLifespanProgressBar(main_window=self)  # Pass self as main_window
        self.faxPollTimerProgressBar = FaxPollTimerProgressBar(main_window=self,
                                                               token_progress_bar=self.tokenLifespanProgressBar)
        self.options_dialog = OptionsDialog(main_window=self, token_progress_bar=self.tokenLifespanProgressBar)

    def connect_signals(self):
        self.settingsLoaded.connect(self.reload_ui)  # Connect signal to slot
        self.retrieve_token.token_retrieved.connect(self.tokenLifespanProgressBar.restart_progress)
        self.retrieve_token.token_retrieved.connect(self.faxPollTimerProgressBar.restart_progress)

    def load_initial_data(self):
        """Load data and setup initial state of the application"""
        self.check_for_updates()
        self.initialize_ui()
        self.setup_periodic_update_check()  # Set up periodic update check

    def finalize_initialization(self):
        """Final steps to initialize the UI based on loaded data"""
        required_height = (self.centralWidget.sizeHint().height() + self.statusBar().sizeHint().height() +
                           self.menuBar().sizeHint().height() + 10)
        self.setFixedSize(600, required_height)  # Set width to 600 and height dynamically

    def showEvent(self, event):
        super().showEvent(event)
        self.settingsLoaded.emit()  # Emit signal after dialog is shown
        self.update_status_bar('System Started Successfully', 1000)

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

    def check_for_updates(self):
        self.log_system.log_message('info', 'Checking for updates')
        self.update_checker = CheckForUpdate(self)
        self.update_checker.new_version_available.connect(self.upgrade_application)
        self.update_checker.start()

    def setup_periodic_update_check(self):
        """Set up a periodic update check every 24 hours"""
        self.update_checker_timer = QTimer(self)
        self.update_checker_timer.timeout.connect(self.check_for_updates)
        self.update_checker_timer.start(24 * 60 * 60 * 1000)  # 24 hours in milliseconds

    def upgrade_application(self, version, download_url):
        msgBox = QMessageBox(self)
        msgBox.setWindowTitle('Update Available')
        msgBox.setText(
            f"An update to version {version} is available. The application will now restart to apply this update.")

        # Define the OK button with a countdown and add it to the message box
        okButton = msgBox.addButton("OK (10)", QMessageBox.AcceptRole)
        msgBox.setDefaultButton(okButton)

        # Setup a timer for updating the button text with a countdown
        self.timer = QTimer(self)
        self.countdown = 10  # Start countdown from 10 seconds

        def update_button_text():
            """Update the text of the button showing the countdown and check for countdown end."""
            self.countdown -= 1
            if self.countdown > 0:
                okButton.setText(f"OK ({self.countdown})")
            else:
                self.timer.stop()  # Stop the timer
                okButton.setText("OK")
                msgBox.accept()  # Programmatically accept the dialog

        self.timer.timeout.connect(update_button_text)
        self.timer.start(1000)  # Trigger every second

        # Display the message box
        msgBox.exec_()  # Block execution here until the dialog is dismissed

        # After the dialog is closed
        self.timer.stop()  # Ensure timer is stopped

        # Handle user interaction or auto-accept
        if msgBox.clickedButton() == okButton or self.countdown <= 0:
            self.start_upgrader(download_url)
        else:
            QApplication.quit()  # Quit the application if the message box is closed without clicking OK

    def start_upgrader(self, download_url):
        """Start the updater thread."""
        self.upgrader = UpgradeApplication(download_url)
        self.upgrader.start()

    def initialize_tray_menu(self):
        # Tray icon setup should not depend on data loading
        self.tray_icon = QSystemTrayIcon(self)
        self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
        self.tray_menu = QMenu()
        self.tray_menu.addAction("Open Fax Manager", self.show)
        self.tray_menu.addAction("Close", self.close)
        self.tray_icon.setIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
        self.tray_icon.setContextMenu(self.tray_menu)

    def initialize_ui(self):
        self.log_system.log_message('debug', 'UI Initializing')
        self.create_menu()
        self.log_system.log_message('debug', 'Menu Initialized')
        self.create_central_widget()
        self.log_system.log_message('debug', 'Main UI Initialized')

    def create_menu(self):
        self.file_menu = self.menuBar().addMenu("&System")
        self.populate_system_menu()
        self.tools_menu = self.menuBar().addMenu("&Tools")
        self.populate_tools_menu()
        self.help_menu = self.menuBar().addMenu("&Help")
        self.populate_help_menu()

    def populate_system_menu(self):
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
        self.fax_status_button = QAction("Fax Status", self)
        self.fax_status_button.triggered.connect(self.show_fax_status_dialog)
        self.tools_menu.addAction(self.fax_status_button)
        self.fax_status_button.setEnabled(True)

        self.retrieve_token_button = QAction("Retrieve Token", self)
        self.retrieve_token_button.triggered.connect(self.startTokenRetrieval)
        self.tools_menu.addAction(self.retrieve_token_button)
        self.retrieve_token_button.setEnabled(True)

    def populate_help_menu(self):
        self.about_button = QAction("About", self)
        self.about_button.triggered.connect(self.about)
        self.help_menu.addAction(self.about_button)
        self.about_button.setEnabled(True)

    def create_status_bar(self):
        self.status_bar = self.statusBar()

    def show_options_dialog(self):
        self.options_dialog.show()

    def show_fax_status_dialog(self):
        self.fax_status_dialog.initiate_fetch()
        self.fax_status_dialog.show()

    def create_central_widget(self):
        self.centralWidget = QWidget()

        # Main layout
        layout = QGridLayout(self.centralWidget)

        self.load_data_from_config()

        # Placeholder for a logo
        banner = QLabel()
        pixmap = QPixmap(os.path.join(bundle_dir, "images", "banner_small.png"))  # Update the path as needed
        banner.setPixmap(pixmap)
        banner.setAlignment(Qt.AlignCenter)
        banner.setFixedHeight(150)
        banner.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(banner, 0, 0, 2, 2)

        # Save Location
        saveLocationLayout = QGridLayout()
        self.saveLocationDisplay = QLineEdit()
        self.saveLocationDisplay.setPlaceholderText("No folder selected...")
        auto_retrieve_enabled = self.save_manager.get_config_value('Retrieval', 'auto_retrieve')

        select_folder_button = QPushButton("Select Save Location")
        select_folder_button.clicked.connect(self.select_folder)
        saveLocationLayout.addWidget(self.saveLocationDisplay, 0, 0)
        saveLocationLayout.addWidget(select_folder_button, 0, 1)
        layout.addLayout(saveLocationLayout, 2, 0, 1, 2)

        self.caller_id_label = QLabel("Fax Inbox:")
        self.inbox_button = QPushButton("Choose an Inbox")
        self.inbox_button.clicked.connect(self.open_select_inbox_dialog)
        self.retrieve_numbers_thread = RetrieveNumbers(self)
        self.retrieve_numbers_thread.numbers_retrieved.connect(self.update_inbox_selection)
        layout.addWidget(self.caller_id_label, 3, 0)
        layout.addWidget(self.inbox_button, 3, 1)

        layout.addWidget(self.faxPollTimerProgressBar, 4, 0, 1, 2)
        layout.addWidget(self.tokenLifespanProgressBar, 5, 0, 1, 2)

        self.faxPollButton.clicked.connect(self.retrieve_faxes)
        layout.addWidget(self.faxPollButton, 6, 0, 1, 2)
        self.faxPollButton.setVisible(auto_retrieve_enabled == "Enabled")
        self.faxPollButton.setEnabled(True)

        self.send_fax_button.clicked.connect(self.show_send_fax_dialog)
        layout.addWidget(self.send_fax_button, 7, 0, 1, 2)
        self.send_fax_button.setEnabled(False)

        if self.isVisible():
            self.update_status_bar('System Started', 1000)

        # Set central widget and layout
        self.setCentralWidget(self.centralWidget)
        self.centralWidget.setLayout(layout)

        self.create_status_bar()
        self.log_system.log_message('debug', 'Status Bar Initialized')

        self.reload_ui()

    def about(self):
        self.about_dialog.show()  # This is a QDialog popup

    def show_send_fax_dialog(self):
        self.send_fax_dialog.show()

    def load_data_from_config(self):
        self.access_token = self.save_manager.get_config_value('Token', 'access_token')
        self.token_retrieved = self.save_manager.get_config_value('Token', 'token_retrieved')
        self.token_expiration = self.save_manager.get_config_value('Token', 'token_expiration')

        self.fax_user = self.save_manager.get_config_value('Account', 'fax_user')
        self.all_numbers = self.save_manager.get_config_value('Account', 'all_numbers')

        self.client_id = self.save_manager.get_config_value('Client', 'client_id')
        self.client_pass = self.save_manager.get_config_value('Client', 'client_secret')

        self.api_username = self.save_manager.get_config_value('API', 'username')
        self.api_pass = self.save_manager.get_config_value('API', 'password')

        self.log_level = self.save_manager.get_config_value('UserSettings', 'logging_level')

        self.auto_retrieve_enabled = self.save_manager.get_config_value('Retrieval', 'auto_retrieve')
        self.fax_caller_id = self.save_manager.get_config_value('Retrieval', 'fax_caller_id')

        self.download_method = self.save_manager.get_config_value('Fax Options', 'download_method')
        self.delete_faxes = self.save_manager.get_config_value('Fax Options', 'delete_faxes')

        self.save_path = self.save_manager.get_config_value('UserSettings', 'save_path')

    def refresh_data_from_config(self):
        self.access_token = self.save_manager.get_config_value('Token', 'access_token')
        self.token_retrieved = self.save_manager.get_config_value('Token', 'token_retrieved')
        self.token_expiration = self.save_manager.get_config_value('Token', 'token_expiration')

        self.fax_user = self.save_manager.get_config_value('Account', 'fax_user')
        self.all_numbers = self.save_manager.get_config_value('Account', 'all_numbers')

        self.client_id = self.save_manager.get_config_value('Client', 'client_id')
        self.client_pass = self.save_manager.get_config_value('Client', 'client_secret')

        self.api_username = self.save_manager.get_config_value('API', 'username')
        self.api_pass = self.save_manager.get_config_value('API', 'password')

        self.log_level = self.save_manager.get_config_value('UserSettings', 'logging_level')

        self.auto_retrieve_enabled = self.save_manager.get_config_value('Retrieval', 'auto_retrieve')
        self.fax_caller_id = self.save_manager.get_config_value('Retrieval', 'fax_caller_id')

        self.download_method = self.save_manager.get_config_value('Fax Options', 'download_method')
        self.delete_faxes = self.save_manager.get_config_value('Fax Options', 'delete_faxes')

        self.save_path = self.save_manager.get_config_value('UserSettings', 'save_path')

        self.populate_caller_ids(self.fax_caller_id)

    def reload_ui(self):
        """
        Reloads all widgets and their data in the application.
        """
        try:
            # Refresh data configurations and UI components
            self.refresh_data_from_config()

            # Restart progress bars
            self.tokenLifespanProgressBar.restart_progress()
            self.faxPollTimerProgressBar.restart_progress()

            # Load content into dynamic fields and buttons
            self.saveLocationDisplay.setText(self.save_path)

            # Update the status bar to indicate successful reloading
            self.update_status_bar("UI and data reloaded successfully.", 5000)
        except Exception as e:
            self.update_status_bar(f"Failed to reload UI: {str(e)}", 10000)
            QMessageBox.critical(self, "Reload Failed", f"An error occurred while reloading the UI: {str(e)}")

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
        self.saveLocationDisplay.setText(folder_path)
        self.save_manager.config.set('UserSettings', 'save_path', folder_path)
        self.save_manager.save_changes()

    def minimize_to_tray(self):
        self.hide()  # Hide the main window
        self.tray_icon.show()  # Show the tray icon

    def retrieve_faxes(self):
        self.update_status_bar("Retrieving Faxes...", 5000)
        self.faxPollTimerProgressBar.retrieveFaxes()

    def startTokenRetrieval(self):
        self.update_status_bar("Retrieving access token...", 5000)
        self.token_thread = RetrieveToken(self)
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
            self.update_status_bar("Retrieval already in progress", 5000)

    def update_inbox_selection(self, numbers):
        formatted_numbers = [self.format_phone_number(num) for num in numbers]
        dialog = SelectInboxDialog(formatted_numbers, self)
        if dialog.exec() == QDialog.Accepted:
            selected_inboxes = dialog.selected_inboxes()
            all_numbers = ','.join(numbers)  # Join all numbers into a single string separated by commas

            if selected_inboxes:
                if len(selected_inboxes) == 1:
                    button_text = self.format_phone_number(selected_inboxes[0])
                else:
                    button_text = f"{len(selected_inboxes)} Inboxes"
                inbox_ids = ','.join(selected_inboxes)
                self.save_manager.config.set('Retrieval', 'fax_caller_id', inbox_ids)
            else:
                button_text = "Choose an Inbox"
                self.save_manager.config.set('Retrieval', 'fax_caller_id', '')

            self.inbox_button.setText(button_text)
            self.save_manager.config.set('Account', 'all_numbers', all_numbers)
            try:
                self.save_manager.save_changes()
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

        if len(numbers) == 1:
            self.inbox_button.setText(self.format_phone_number(numbers[0]))
            self.save_manager.config.set('Retrieval', 'fax_caller_id', numbers[0])
            try:
                self.save_manager.save_changes()
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def populate_caller_ids(self, caller_ids):
        if caller_ids:
            numbers = [self.format_phone_number(num) for num in caller_ids.split(',')]  # Format each number
            if len(numbers) == 1:
                self.inbox_button.setText(numbers[0])
            elif len(numbers) > 1:
                self.inbox_button.setText(f"{len(numbers)} Inboxes")
        else:
            self.inbox_button.setText("Choose an Inbox")

    def format_phone_number(self, phone_number):
        """Format a U.S. phone number into the format 1 (NNN) NNN-NNNN."""
        if len(phone_number) == 10 and phone_number.isdigit():
            return f"1 ({phone_number[:3]}) {phone_number[3:6]}-{phone_number[6:]}"
        elif len(phone_number) == 11 and phone_number.isdigit() and phone_number.startswith('1'):
            return f"1 ({phone_number[1:4]}) {phone_number[4:7]}-{phone_number[7:]}"
        return phone_number  # Return the original if it doesn't meet the criteria

    from PyQt5.QtCore import QTimer

    def update_status_bar(self, message, timeout):
        # Display the initial message with the specified timeout
        if self.isVisible():
            self.status_bar.showMessage(message, timeout)

        # Set up a QTimer to reset the status bar to the copyright message after the initial message's timeout
        QTimer.singleShot(timeout, self.reset_status_bar)

    def reset_status_bar(self):
        # Display the copyright message indefinitely (or with a specific timeout if needed)
        self.status_bar.showMessage(f"Clinic Networking, LLC © 2024 - App Version: {self.version}")


if __name__ == '__main__':
    log_system = SystemLog()
    log_system.log_message('info', 'Application Started')
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())
