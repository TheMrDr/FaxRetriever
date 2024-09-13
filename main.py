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
from Customizations import CustomPushButton, SelectInboxDialog, PhoneNumberInputDialog
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
        try:
            self.initialize_attributes()
            self.setup_ui()
            self.connect_signals()
            self.load_initial_data()
            self.finalize_initialization()
        except Exception as e:
            if self.log_system:
                self.log_system.log_message('error', f"Initialization error: {e}")
            print(f"Initialization error: {e}")

    def initialize_attributes(self):
        """Initialize attributes with default values or configurations"""
        try:
            self.status_bar = None
            self.version = __version__
            self.save_manager = SaveManager(self)
            self.log_system = SystemLog()
            self.logging_level = self.save_manager.get_config_value('UserSettings', 'logging_level')
            self.log_system.refresh_logging_level(self.logging_level)
        except Exception as e:
            print(f"Error initializing attributes: {e}")

    def setup_ui(self):
        """Setup the main window UI components"""
        try:
            self.setWindowTitle("FaxRetriever - Cloud Fax")
            self.setFixedWidth(600)
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
            self.initialize_components()
            self.initialize_tray_menu()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up UI: {e}")
            print(f"Failed to set up UI: {e}")

    def initialize_components(self):
        """Initialize UI components that might display or utilize saved data"""
        try:
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
        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize components: {e}")
            print(f"Failed to initialize components: {e}")

    def connect_signals(self):
        try:
            # self.settingsLoaded.connect(self.reload_ui)
            self.retrieve_token.token_retrieved.connect(self.tokenLifespanProgressBar.restart_progress)
            self.retrieve_token.token_retrieved.connect(self.faxPollTimerProgressBar.restart_progress)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to connect signals: {e}")
            print(f"Failed to connect signals: {e}")

    def load_initial_data(self):
        """Load data and setup the initial state of the application"""
        try:
            self.check_for_updates()
            self.validation_status = self.save_manager.get_config_value('Account', 'validation_status')
            if not self.validation_status:
                self.disable_functionality()
            else:
                self.initialize_ui()
                self.setup_periodic_update_check()  # Set up periodic update check
        except Exception as e:
            self.log_system.log_message('error', f"Failed to load initial data: {e}")
            print(f"Failed to load initial data: {e}")

    def disable_functionality(self):
        """Disable the main functionality if the validation status is False"""
        try:
            self.faxPollButton.setEnabled(False)
            self.send_fax_button.setEnabled(False)
            self.tokenLifespanProgressBar.setVisible(False)
            self.faxPollTimerProgressBar.setVisible(False)
            self.log_system.log_message('info', 'Application functionality disabled due to failed validation status')
            self.update_status_bar("Validation failed. Please configure your account in settings.", 10000)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to disable functionality: {e}")
            print(f"Failed to disable functionality: {e}")

    def finalize_initialization(self):
        """Final steps to initialize the UI based on loaded data"""
        try:
            required_height = (self.centralWidget().sizeHint().height() + self.statusBar().sizeHint().height() +
                               self.menuBar().sizeHint().height() + 10)
            self.setFixedSize(600, required_height)  # Set width to 600 and height dynamically
        except Exception as e:
            self.log_system.log_message('error', f"Failed to finalize initialization: {e}")
            print(f"Failed to finalize initialization: {e}")

    def showEvent(self, event):
        super().showEvent(event)
        try:
            self.settingsLoaded.emit()  # Emit signal after dialog is shown
            self.update_status_bar('System Started Successfully', 1000)
        except Exception as e:
            self.log_system.log_message('error', f"Failed during showEvent: {e}")
            print(f"Failed during showEvent: {e}")

    def closeEvent(self, event):
        try:
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
        except Exception as e:
            self.log_system.log_message('error', f"Failed during closeEvent: {e}")
            print(f"Failed during closeEvent: {e}")

    def check_for_updates(self):
        try:
            self.log_system.log_message('info', 'Checking for updates')
            self.update_checker = CheckForUpdate(self)
            self.update_checker.new_version_available.connect(self.upgrade_application)
            self.update_checker.start()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to check for updates: {e}")
            print(f"Failed to check for updates: {e}")

    def setup_periodic_update_check(self):
        """Set up a periodic update check every 24 hours"""
        try:
            self.update_checker_timer = QTimer(self)
            self.update_checker_timer.timeout.connect(self.check_for_updates)
            self.update_checker_timer.start(24 * 60 * 60 * 1000)  # 24 hours in milliseconds
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up periodic update check: {e}")
            print(f"Failed to set up periodic update check: {e}")

    def upgrade_application(self, version, download_url):
        try:
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
        except Exception as e:
            self.log_system.log_message('error', f"Failed during upgrade_application: {e}")
            print(f"Failed during upgrade_application: {e}")

    def start_upgrader(self, download_url):
        """Start the updater thread."""
        try:
            self.upgrader = UpgradeApplication(download_url)
            self.upgrader.start()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to start upgrader: {e}")
            print(f"Failed to start upgrader: {e}")

    def initialize_tray_menu(self):
        try:
            # Tray icon setup should not depend on data loading
            self.tray_icon = QSystemTrayIcon(self)
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
            self.tray_menu = QMenu()
            self.tray_menu.addAction("Open FaxRetriever", self.show)
            self.tray_menu.addAction("Close", self.close)
            self.tray_icon.setIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
            self.tray_icon.setContextMenu(self.tray_menu)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize tray menu: {e}")
            print(f"Failed to initialize tray menu: {e}")

    def initialize_ui(self):
        try:
            self.log_system.log_message('debug', 'UI Initializing')
            self.create_menu()
            self.log_system.log_message('debug', 'Menu Initialized')
            self.create_central_widget()
            self.log_system.log_message('debug', 'Main UI Initialized')
        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize UI: {e}")
            print(f"Failed to initialize UI: {e}")

    def create_menu(self):
        try:
            self.file_menu = self.menuBar().addMenu("&System")
            self.populate_system_menu()
            self.tools_menu = self.menuBar().addMenu("&Tools")
            self.populate_tools_menu()
            self.help_menu = self.menuBar().addMenu("&Help")
            self.populate_help_menu()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to create menu: {e}")
            print(f"Failed to create menu: {e}")

    def populate_system_menu(self):
        try:
            self.options_button = QAction("Options", self)
            self.options_button.triggered.connect(self.show_options_dialog)
            self.file_menu.addAction(self.options_button)
            self.options_button.setEnabled(True)  # Ensure settings are enabled

            self.minimize_app_button = QAction("Minimize", self)
            self.minimize_app_button.triggered.connect(self.minimize_to_tray)
            self.file_menu.addAction(self.minimize_app_button)

            self.close_app_button = QAction("Close", self)
            self.close_app_button.triggered.connect(self.close)
            self.file_menu.addAction(self.close_app_button)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to populate system menu: {e}")
            print(f"Failed to populate system menu: {e}")

    def populate_tools_menu(self):
        try:
            self.fax_status_button = QAction("Fax Status", self)
            self.fax_status_button.triggered.connect(self.show_fax_status_dialog)
            self.tools_menu.addAction(self.fax_status_button)
            self.fax_status_button.setEnabled(True)

            self.retrieve_token_button = QAction("Retrieve Token", self)
            self.retrieve_token_button.triggered.connect(self.startTokenRetrieval)
            self.tools_menu.addAction(self.retrieve_token_button)
            self.retrieve_token_button.setEnabled(True)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to populate tools menu: {e}")
            print(f"Failed to populate tools menu: {e}")

    def populate_help_menu(self):
        try:
            self.about_button = QAction("About", self)
            self.about_button.triggered.connect(self.about)
            self.help_menu.addAction(self.about_button)
            self.about_button.setEnabled(True)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to populate help menu: {e}")
            print(f"Failed to populate help menu: {e}")

    def create_status_bar(self):
        try:
            self.status_bar = self.statusBar()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to create status bar: {e}")
            print(f"Failed to create status bar: {e}")

    def show_options_dialog(self):
        try:
            self.options_dialog.show()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to show options dialog: {e}")
            print(f"Failed to show options dialog: {e}")

    def show_fax_status_dialog(self):
        try:
            self.fax_status_dialog.initiate_fetch()
            self.fax_status_dialog.show()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to show fax status dialog: {e}")
            print(f"Failed to show fax status dialog: {e}")

    def create_central_widget(self):
        try:
            self.centralWidget = QWidget()
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

            self.setCentralWidget(self.centralWidget)
            self.centralWidget.setLayout(layout)

            self.create_status_bar()
            self.log_system.log_message('debug', 'Status Bar Initialized')

            self.reload_ui()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to create central widget: {e}")
            print(f"Failed to create central widget: {e}")

    def about(self):
        try:
            self.about_dialog.show()  # This is a QDialog popup
        except Exception as e:
            self.log_system.log_message('error', f"Failed to show about dialog: {e}")
            print(f"Failed to show about dialog: {e}")

    def open_select_inbox_dialog(self):
        try:
            if not self.retrieve_numbers_thread.isRunning():
                self.retrieve_numbers_thread.start()
            else:
                self.update_status_bar("Retrieval already in progress", 5000)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to open select inbox dialog: {e}")
            self.update_status_bar(f"Failed to open select inbox dialog: {str(e)}", 10000)

    def show_send_fax_dialog(self):
        try:
            self.send_fax_dialog.show()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to show send fax dialog: {e}")
            print(f"Failed to show send fax dialog: {e}")

    def load_data_from_config(self):
        try:
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

            self.validation_status = self.save_manager.get_config_value('Account', 'validation_status')
        except Exception as e:
            self.log_system.log_message('error', f"Failed to load data from config: {e}")
            print(f"Failed to load data from config: {e}")

    def refresh_data_from_config(self):
        try:
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

            self.validation_status = self.save_manager.get_config_value('Account', 'validation_status')

            self.populate_caller_ids(self.fax_caller_id)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to refresh data from config: {e}")
            print(f"Failed to refresh data from config: {e}")

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
            self.log_system.log_message('error', f"Failed to reload UI: {e}")
            QMessageBox.critical(self, "Reload Failed", f"An error occurred while reloading the UI: {str(e)}")

    def select_folder(self):
        try:
            folder_path = QFileDialog.getExistingDirectory(self, "Select Folder")
            self.saveLocationDisplay.setText(folder_path)
            self.save_manager.config.set('UserSettings', 'save_path', folder_path)
            self.save_manager.save_changes()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to select folder: {e}")
            QMessageBox.critical(self, "Error", f"Failed to select folder: {str(e)}")

    def minimize_to_tray(self):
        try:
            self.hide()  # Hide the main window
            self.tray_icon.show()  # Show the tray icon
        except Exception as e:
            self.log_system.log_message('error', f"Failed to minimize to tray: {e}")
            print(f"Failed to minimize to tray: {e}")

    def retrieve_faxes(self):
        try:
            self.update_status_bar("Retrieving Faxes...", 5000)
            self.faxPollTimerProgressBar.retrieveFaxes()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to retrieve faxes: {e}")
            self.update_status_bar(f"Failed to retrieve faxes: {str(e)}", 10000)

    def startTokenRetrieval(self):
        try:
            self.update_status_bar("Retrieving access token...", 5000)
            self.token_thread = RetrieveToken(self)
            self.token_thread.finished.connect(self.handle_token_response)
            self.token_thread.start()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to start token retrieval: {e}")
            self.update_status_bar(f"Failed to start token retrieval: {str(e)}", 10000)

    def handle_token_response(self, status, message):
        try:
            if status == "Success":
                self.update_status_bar("Access token retrieved successfully.", 5000)
                QMessageBox.information(self, "Success", message)
            else:
                self.update_status_bar("Failed to retrieve access token.", 5000)
                QMessageBox.critical(self, "Failure", message)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to handle token response: {e}")
            self.update_status_bar(f"Failed to handle token response: {str(e)}", 10000)

    def update_inbox_selection(self, numbers):
        try:
            formatted_numbers = [self.format_phone_number(num) for num in numbers] if numbers else []

            if not formatted_numbers:
                # No numbers retrieved, prompt for user input
                user_number = self.prompt_for_fax_number()
                if user_number:
                    formatted_numbers = [self.format_phone_number(user_number)]  # Ensure user number is formatted
                else:
                    self.inbox_button.setText("No Inboxes Available")
                    return

            all_numbers = ','.join(formatted_numbers)  # Join all numbers into a single string separated by commas
            self.save_manager.config.set('Account', 'all_numbers', all_numbers)  # Save the numbers immediately

            dialog = SelectInboxDialog(formatted_numbers, self)
            if dialog.exec() == QDialog.Accepted:
                selected_inboxes = dialog.selected_inboxes()

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

                try:
                    self.save_manager.save_changes()  # Save settings
                except Exception as e:
                    QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                    self.update_status_bar(f"Error: {str(e)}", 10000)
            else:
                # If the dialog was rejected, ensure any new numbers are still saved
                try:
                    self.save_manager.save_changes()
                except Exception as e:
                    QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                    self.update_status_bar(f"Error: {str(e)}", 10000)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to update inbox selection: {e}")
            QMessageBox.critical(self, "Error", f"Failed to update inbox selection: {str(e)}")

    def prompt_for_fax_number(self):
        """Prompts the user to enter a formatted USA fax number."""
        dialog = PhoneNumberInputDialog(self)
        if dialog.exec() == QDialog.Accepted:
            phone_number = dialog.get_phone_number()
            if phone_number:
                return phone_number
        return None

    def populate_caller_ids(self, caller_ids):
        try:
            if caller_ids:
                numbers = [self.format_phone_number(num) for num in caller_ids.split(',')]  # Format each number
                if len(numbers) == 1:
                    self.inbox_button.setText(numbers[0])
                elif len(numbers) > 1:
                    self.inbox_button.setText(f"{len(numbers)} Inboxes")
            else:
                self.inbox_button.setText("Choose an Inbox")
        except Exception as e:
            self.log_system.log_message('error', f"Failed to populate caller IDs: {e}")
            print(f"Failed to populate caller IDs: {e}")

    def format_phone_number(self, phone_number):
        """Format a U.S. phone number into the format 1 (NNN) NNN-NNNN."""
        try:
            digits = ''.join(filter(str.isdigit, phone_number))  # Remove all non-digit characters
            if len(digits) == 10:
                return f"1 ({digits[:3]}) {digits[3:6]}-{digits[6:]}"
            elif len(digits) == 11 and digits.startswith('1'):
                return f"1 ({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
            return phone_number  # Return the original if it doesn't meet the criteria
        except Exception as e:
            self.log_system.log_message('error', f"Failed to format phone number: {e}")
            print(f"Failed to format phone number: {e}")
            return phone_number

    def update_status_bar(self, message, timeout):
        try:
            # Display the initial message with the specified timeout
            if self.isVisible():
                self.status_bar.showMessage(message, timeout)

            # Set up a QTimer to reset the status bar to the copyright message after the initial message's timeout
            QTimer.singleShot(timeout, self.reset_status_bar)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to update status bar: {e}")
            print(f"Failed to update status bar: {e}")

    def reset_status_bar(self):
        try:
            # Display the copyright message indefinitely (or with a specific timeout if needed)
            self.status_bar.showMessage(f"Clinic Networking, LLC © 2024 - App Version: {self.version}")
        except Exception as e:
            self.log_system.log_message('error', f"Failed to reset status bar: {e}")
            print(f"Failed to reset status bar: {e}")

if __name__ == '__main__':
    try:
        log_system = SystemLog()
        log_system.log_message('info', 'Application Started')
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        sys.exit(app.exec_())
    except Exception as e:
        if log_system:
            log_system.log_message('error', f"Application failed to start: {e}")
        print(f"Application failed to start: {e}")
