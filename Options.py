import os
import re
import sys

from PyQt5.QtCore import Qt, QStandardPaths
from PyQt5 import QtGui
from PyQt5.QtPrintSupport import QPrintDialog
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QCheckBox, QMessageBox,
                             QRadioButton, QGroupBox, QHBoxLayout, QComboBox, QWidget, QFileDialog)

from Customizations import IntegrationAcknowledgement
from ProgressBars import FaxPollTimerProgressBar
from RetrieveToken import RetrieveToken
from SaveManager import SaveManager
from SystemLog import SystemLog
from Validation import validate_fax_user


# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


# noinspection PyUnresolvedReferences
class OptionsDialog(QDialog):
    def __init__(self, main_window, token_progress_bar=None, parent=None):
        super().__init__(main_window or parent)
        self.log_system = SystemLog()
        self.retrieve_token = RetrieveToken(main_window)
        self.main_window = main_window
        self.selected_printer_full_name = None
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove help button

        try:
            self.save_manager = SaveManager(self.main_window)
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))

            self.setWindowTitle("Options")
            self.setFixedWidth(700)
            # self.setMinimumHeight(800)

            self.layout = QGridLayout()
            self.setup_ui()
            self.populate_settings()
            self.fax_timer_progress_bar = FaxPollTimerProgressBar(self.main_window, token_progress_bar)

            # Initialize to store the previous fax_user value
            self.previous_fax_user = self.save_manager.get_config_value('Account', 'fax_user')
            self._license_valid = self.save_manager.get_config_value('Account', 'validation_status') == 'True'

        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize OptionsDialog: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_ui(self):
        try:
            # Initialize Window Layout
            self.layout = QGridLayout()

            # Create the section layouts
            left_layout = QVBoxLayout()
            right_layout = QVBoxLayout()

            # Fax Retrieval Settings
            self.fax_retrieval_group = QGroupBox("Fax Retrieval Settings")
            fax_retrieval_group_layout = QVBoxLayout()
            self.setup_fax_retrieval_options(fax_retrieval_group_layout)
            self.fax_retrieval_group.setLayout(fax_retrieval_group_layout)

            # Logging Level
            self.logging_level_group = QGroupBox("Logging Level")
            self.setup_logging_level_group(self.logging_level_group)

            # Account Settings
            self.account_info_group = QGroupBox("Account Settings")
            account_settings_layout = QVBoxLayout()
            self.setup_account_settings_group(account_settings_layout)
            self.account_info_group.setLayout(account_settings_layout)

            # Integrations (Moved to Right Column Above Account Settings)
            self.integrations_group = QGroupBox("Integrations")
            integrations_group_layout = QVBoxLayout()
            self.setup_integrations_group(integrations_group_layout)
            self.integrations_group.setLayout(integrations_group_layout)

            # Add widgets to layouts
            left_layout.addWidget(self.fax_retrieval_group)
            left_layout.addWidget(self.logging_level_group)
            left_layout.addStretch()

            right_layout.addWidget(self.integrations_group)
            right_layout.addWidget(self.account_info_group)
            right_layout.addStretch()

            # Wrap layouts in QWidget objects (fixes missing UI issue)
            left_widget = QWidget()
            left_widget.setLayout(left_layout)
            left_widget.setFixedWidth(350)

            right_widget = QWidget()
            right_widget.setLayout(right_layout)
            right_widget.setFixedWidth(350)

            # Add widgets to the grid layout
            self.layout.addWidget(left_widget, 0, 0)
            self.layout.addWidget(right_widget, 0, 1)

            # Save & Cancel buttons
            button_layout = QHBoxLayout()
            self.save_button = QPushButton("Save")
            self.save_button.clicked.connect(self.save_settings)
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.clicked.connect(self.close)
            button_layout.addWidget(self.save_button)
            button_layout.addWidget(self.cancel_button)

            self.layout.addLayout(button_layout, 1, 0, 1, 2)
            self.setLayout(self.layout)
            self.toggle_sensitive_settings(False)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up UI: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_fax_retrieval_options(self, parent_layout):
        try:
            # Create Fax Retrieval Group
            self.fax_retrieval_group = QGroupBox("Fax Retrieval Settings")
            fax_retrieval_layout = QVBoxLayout()

            # Disable Fax Retrieval Checkbox (This should remain interactive)
            self.disable_fax_retrieval_checkbox = QCheckBox("Disable Fax Retrieval")
            self.disable_fax_retrieval_checkbox.setChecked(True)
            self.disable_fax_retrieval_checkbox.toggled.connect(self.toggle_retrieval_settings)
            fax_retrieval_layout.addWidget(self.disable_fax_retrieval_checkbox)

            # Download Method Group
            self.download_options_group = QGroupBox("Download Method")
            download_options_layout = QVBoxLayout()
            self.download_method_combo = QComboBox()
            self.download_method_combo.addItems(["PDF", "JPG", "Both"])
            self.download_method_combo.setCurrentText("PDF")
            download_options_layout.addWidget(self.download_method_combo)
            self.download_options_group.setLayout(download_options_layout)
            fax_retrieval_layout.addWidget(self.download_options_group)

            # Fax Naming Group
            self.fax_name_group = QGroupBox("File Name Options")
            fax_name_layout = QGridLayout()  # Use QGridLayout for alignment

            # Fax ID Option
            self.fax_id_radio = QRadioButton("Use Fax ID")
            fax_id_example = QLabel("Example: 1234567890.pdf")  # Example label
            fax_id_example.setStyleSheet("font-size: 10px; color: gray;")  # Optional styling

            # CID-MMDD-HHMM Option
            self.cid_mmdd_hhmm_radio = QRadioButton("Use CID-MMDD-HHMM")
            cid_example = QLabel("Example: 1231231234-0206-1645.pdf")
            cid_example.setStyleSheet("font-size: 10px; color: gray;")

            # Adjust row/column positioning with vertical padding
            fax_name_layout.addWidget(self.fax_id_radio, 0, 0, Qt.AlignLeft)
            fax_name_layout.addWidget(fax_id_example, 1, 0, Qt.AlignLeft)

            fax_name_layout.addWidget(self.cid_mmdd_hhmm_radio, 0, 1, Qt.AlignRight)
            fax_name_layout.addWidget(cid_example, 1, 1, Qt.AlignRight)

            # Add spacing to prevent squishing
            fax_name_layout.setRowMinimumHeight(0, 25)
            fax_name_layout.setRowMinimumHeight(1, 20)

            # Set layout before adding to parent
            self.fax_name_group.setLayout(fax_name_layout)
            fax_retrieval_layout.addWidget(self.fax_name_group)

            # Print Faxes Group
            self.print_options_group = QGroupBox("Print Faxes")
            print_options_layout = QHBoxLayout()

            self.print_faxes_checkbox = QCheckBox("Print Faxes")
            self.print_faxes_checkbox.toggled.connect(self.toggle_print_options)

            self.select_printer_button = QPushButton("Select Printer")
            self.select_printer_button.clicked.connect(self.select_printer)
            self.select_printer_button.setVisible(False)  # Start hidden

            print_options_layout.addWidget(self.print_faxes_checkbox)
            print_options_layout.addWidget(self.select_printer_button)
            self.print_options_group.setLayout(print_options_layout)
            fax_retrieval_layout.addWidget(self.print_options_group)

            # Archival Settings Group
            # self.setup_archival_group(fax_retrieval_layout)
            self.archival_group = QGroupBox("Fax Archival Settings")
            archival_layout = QHBoxLayout()

            # Archive Faxes Checkbox
            self.archive_enabled_checkbox = QCheckBox("Archive Incoming Faxes")
            self.archive_enabled_checkbox.setChecked(False)
            self.archive_enabled_checkbox.toggled.connect(self.toggle_archive_duration)

            # Archive Duration Dropdown
            self.archive_duration_label = QLabel("Archive Incoming Faxes For:")
            self.archive_duration_combo = QComboBox()
            self.archive_duration_combo.addItems(["30", "60", "90", "120", "365"])
            self.archive_duration_combo.setCurrentText("30")
            self.archive_duration_combo.setEnabled(False)

            # Add widgets to the layout
            archival_layout.addWidget(self.archive_enabled_checkbox)
            archival_layout.addWidget(self.archive_duration_combo)
            archival_layout.addWidget(QLabel("Days"))
            self.archival_group.setLayout(archival_layout)
            fax_retrieval_layout.addWidget(self.archival_group)

            # Delete Faxes Group
            self.delete_faxes_group = QGroupBox("Delete Faxes After Download")
            delete_faxes_layout = QHBoxLayout()
            self.delete_faxes_checkbox = QCheckBox("Delete Faxes")
            delete_faxes_layout.addWidget(self.delete_faxes_checkbox)
            self.delete_faxes_group.setLayout(delete_faxes_layout)
            fax_retrieval_layout.addWidget(self.delete_faxes_group)

            # Apply layout to Fax Retrieval Group
            self.fax_retrieval_group.setLayout(fax_retrieval_layout)
            parent_layout.addWidget(self.fax_retrieval_group)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up disable fax options: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_integrations_group(self, parent_layout):
        """Sets up the integrations section with software dropdown."""

        # Master Enable Checkbox
        self.enable_integrations_checkbox = QCheckBox("Enable 3rd Party Integrations")
        self.enable_integrations_checkbox.toggled.connect(self.toggle_integrations_group)
        parent_layout.addWidget(self.enable_integrations_checkbox)

        # Software Selection Dropdown (Dynamically Updated)
        self.software_group = QGroupBox("Select Software Integration")
        software_layout = QVBoxLayout()

        self.software_selector = QComboBox()
        self.software_selector.addItems(["None"])  # Placeholder, will update dynamically
        self.software_selector.currentIndexChanged.connect(self.handle_software_selection)

        software_layout.addWidget(self.software_selector)
        self.software_group.setLayout(software_layout)
        parent_layout.addWidget(self.software_group)

        # Locate Program Button (Hidden by default)
        self.locate_program_button = QPushButton("Locate Program")
        self.locate_program_button.clicked.connect(self.prompt_for_winrx_path)
        self.locate_program_button.setVisible(False)
        parent_layout.addWidget(self.locate_program_button)

        # Initially hide software selectors
        self.software_group.setVisible(False)

    def toggle_integrations_group(self, checked):
        """Show/hide integration settings based on master checkbox and display warning message."""
        self.software_group.setVisible(checked)

        if not checked:
            self.software_selector.setCurrentIndex(0)

        if checked:
            acknowledgement_setting = self.save_manager.get_config_value('Integrations', 'acknowledgement')
            if acknowledgement_setting != "True":
                dialog = IntegrationAcknowledgement(self.save_manager, parent=self)
                if dialog.exec_() == QDialog.Accepted:
                    self.update_integration_visibility()
            else:
                self.update_integration_visibility()

        self.resize_window(enforce_minimum=checked)

    def update_integration_visibility(self):
        enabled = self.enable_integrations_checkbox.isChecked()
        self.software_selector.setVisible(enabled)
        self.update_software_options()

    def update_software_options(self):
        """Populates the software integration dropdown with available options."""
        self.software_selector.clear()

        available_options = [
            "None",
            "Computer-Rx",
            "PharmacyOne",
            "Rx30",
            "Ask us for more!"
        ]

        # Ensure only "None" and "Computer-Rx" are currently selectable
        for option in available_options:
            index = self.software_selector.count()
            self.software_selector.addItem(option)
            if option not in ["None", "Computer-Rx"]:
                self.software_selector.model().item(index).setEnabled(False)  # Grayed-out, non-selectable

        # Set default selection
        self.software_selector.setCurrentText("None")

    def handle_software_selection(self):
        """Handles additional actions when a software selection is made."""
        selected_software = self.software_selector.currentText()

        # If the user selects "Computer-Rx", check for required Pervasive SQL files
        if selected_software == "Computer-Rx":
            pervasive_dll_path = r"C:\Program Files (x86)\Actian\PSQL\bin\wbtrv32.dll"
            pervasive10_dll_path = r"C:\Program Files (x86)\Pervasive Software\PSQL\bin\wbtrv32.dll"

            if not os.path.exists(pervasive_dll_path) and not os.path.exists(pervasive10_dll_path):
                # Warn the user and reset selection to "None"
                QMessageBox.critical(
                    self, "Integration Unavailable",
                    "Computer-Rx integration requires Pervasive to be installed.\n"
                    "This installation is missing the required files.\n"
                    "Please contact Computer-Rx for assistance."
                )
                self.software_selector.setCurrentText("None")
                return  # Stop further execution

        # Show the locate button only for Computer-Rx
        self.locate_program_button.setVisible(selected_software == "Computer-Rx")
        self.update_winrx_integration_button()

    def prompt_for_winrx_path(self):
        """Prompts the user to select the path to WinRx and validates its directory."""

        # Inform user about what we are looking for
        message = (
            "To enable integration with Computer-Rx (WinRx), we need to locate its installation folder.\n\n"
            "Look for 'WinRx.exe' in the main installation directory. Typically, this can be found in:\n"
            "- H:\\Pharmacy\n"
            "- D:\\ComputerRx\\Pharmacy\n"
            "- E:\\Computer-Rx\\Pharmacy\n"
            "- A mapped network drive (e.g., H:\\ or similar)\n"
            "- Check your desktop for a WinRx shortcut\n\n"
            "Once selected, we will verify that critical database files are present in the same folder."
        )
        QMessageBox.information(self, "Locate WinRx", message)

        # Search for WinRx.exe in common paths
        common_paths = [
            "H:\\Pharmacy",
            "C:\\Pharmacy",
            "D:\\Computer-Rx\\Pharmacy",
            "D:\\ComputerRx\\Pharmacy",
            "E:\\Computer-Rx\\Pharmacy",
        ]

        valid_paths = []

        for path in common_paths:
            winrx_exe = os.path.join(path, "WinRx.exe")
            if os.path.exists(winrx_exe):
                valid_paths.append(path)

        # Detect desktop shortcuts pointing to WinRx.exe
        desktop_path = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation)
        for file in os.listdir(desktop_path):
            if file.lower().startswith("winrx") and file.lower().endswith(".lnk"):
                shortcut_path = os.path.join(desktop_path, file)
                try:
                    target_path = shutil.readlink(shortcut_path)  # Extracts real path from shortcut
                    if os.path.exists(os.path.join(target_path, "WinRx.exe")):
                        valid_paths.insert(0, target_path)  # Prioritize the found shortcut
                except Exception as e:
                    self.log_system.log_message('error', f"Failed to read shortcut: {e}")

        # If multiple valid paths exist, prompt the user to choose one
        if len(valid_paths) > 1:
            selected_path, ok = QInputDialog.getItem(self, "Select WinRx Path",
                                                     "Multiple valid installations detected. Please select the correct one:",
                                                     valid_paths, 0, False)
            if not ok:
                return  # User canceled selection
        elif valid_paths:
            selected_path = valid_paths[0]
        else:
            selected_path = ""

        # If no valid paths were found, allow manual selection
        if not selected_path:
            file_dialog = QFileDialog()
            file_path, _ = file_dialog.getOpenFileName(self, "Select WinRx.exe", "", "WinRx Executable (WinRx.exe)")
            if not file_path or not file_path.lower().endswith("winrx.exe"):
                QMessageBox.critical(self, "Invalid Selection", "You must select WinRx.exe.")
                return  # User canceled or selected the wrong file

            # Extract directory from selected file
            selected_path = os.path.dirname(file_path)

        # Verify that FaxControl.btr exists in the same directory
        fax_control_path = os.path.join(selected_path, "FaxControl.btr")

        if os.path.exists(fax_control_path):
            # **Save the FULL path in the config**
            self.save_manager.config.set("Integrations", "winrx_path", selected_path)
            self.save_manager.save_changes()

            # **Set truncated version for display only**
            self.locate_program_button.setText(self.truncate_path(selected_path))

            QMessageBox.information(self, "Success",
                                    "WinRx directory has been set successfully, and integration is ready.")
        else:
            QMessageBox.critical(self, "Error",
                                 "Invalid directory: Critical files not found. Please try again or hit cancel to go back.")

    def update_winrx_integration_button(self):
        """Updates the Locate Program button text based on saved integration status."""
        saved_path = self.save_manager.get_config_value("Integrations", "winrx_path")

        if saved_path and saved_path != "Locate Program":
            self.locate_program_button.setText(self.truncate_path(saved_path))  # Display truncated version
        else:
            self.locate_program_button.setText("Locate Program")  # Default label

    def truncate_path(self, path, max_length=30):
        """Truncates the middle of a file path if it exceeds max_length."""
        if len(path) <= max_length:
            return path
        return f"{path[:15]}...{path[-15:]}"

    def toggle_print_options(self, checked):
        """
        Show or hide the "Select Printer" button based on the checkbox state.
        """
        try:
            self.select_printer_button.setVisible(checked)  # Show if checked, hide if unchecked

            self.resize_window(enforce_minimum=checked)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to toggle print options: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def toggle_archive_duration(self, checked):
        """Enable or disable the archive duration dropdown based on checkbox state."""
        self.archive_duration_combo.setEnabled(checked)

    def setup_logging_level_group(self, parent_layout):
        try:
            # Create a layout for logging settings
            layout = QVBoxLayout()

            # Combo Box for Logging Levels
            self.logging_level_combo = QComboBox()
            self.logging_level_combo.addItems(["Debug", "Info", "Warning", "Error", "Critical"])  # Restore all levels

            layout.addWidget(self.logging_level_combo)
            parent_layout.setLayout(layout)  # Properly set layout to the QGroupBox

        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up Logging Level Group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_account_settings_group(self, parent_layout):
        try:
            # Checkbox to enable editing sensitive settings
            self.edit_sensitive_checkbox = QCheckBox("Edit Account Settings")
            self.edit_sensitive_checkbox.toggled.connect(self.toggle_sensitive_settings)
            parent_layout.addWidget(self.edit_sensitive_checkbox)

            # API Credentials Section
            self.username_label = QLabel("API Username:")
            self.username_input = QLineEdit()
            self.username_input.setEnabled(False)
            parent_layout.addWidget(self.username_label)
            parent_layout.addWidget(self.username_input)

            self.password_label = QLabel("API Password:")
            self.password_input = QLineEdit()
            self.password_input.setEchoMode(QLineEdit.Password)
            self.password_input.setEnabled(False)
            parent_layout.addWidget(self.password_label)
            parent_layout.addWidget(self.password_input)

            self.client_id_label = QLabel("Client ID:")
            self.client_id_input = QLineEdit()
            self.client_id_input.setEnabled(False)
            parent_layout.addWidget(self.client_id_label)
            parent_layout.addWidget(self.client_id_input)

            self.client_secret_label = QLabel("Client Secret:")
            self.client_secret_input = QLineEdit()
            self.client_secret_input.setEchoMode(QLineEdit.Password)
            self.client_secret_input.setEnabled(False)
            parent_layout.addWidget(self.client_secret_label)
            parent_layout.addWidget(self.client_secret_input)

            self.fax_user_label = QLabel("Fax User:")
            self.fax_user_input = QLineEdit()
            self.fax_user_input.setEnabled(False)
            parent_layout.addWidget(self.fax_user_label)
            parent_layout.addWidget(self.fax_user_input)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up Account Options Group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def select_printer(self):
        """
        Opens a printer selection dialog and updates the button text with the selected printer.
        """
        try:
            printer_dialog = QPrintDialog()
            if printer_dialog.exec_():
                self.selected_printer_full_name = printer_dialog.printer().printerName()

                # Truncate printer name if it's too long
                truncated_name = (self.selected_printer_full_name[:20] + '..') if len(
                    self.selected_printer_full_name) > 20 else self.selected_printer_full_name

                # Update the button text
                self.update_printer_button(truncated_name)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to select printer: {e}")
            self.log_system.log_message('error', f"Failed to select printer: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def update_printer_button(self, truncated_name):
        """
        Updates the printer button text with a truncated printer name.
        """
        self.select_printer_button.setText(truncated_name)

    def populate_settings(self):
        try:
            # Populate settings from config file
            self.username_input.setText(self.save_manager.get_config_value('API', 'username'))
            self.password_input.setText(self.save_manager.get_config_value('API', 'password'))
            self.client_id_input.setText(self.save_manager.get_config_value('Client', 'client_id'))
            self.client_secret_input.setText(self.save_manager.get_config_value('Client', 'client_secret'))
            self.fax_user_input.setText(self.save_manager.get_config_value('Account', 'fax_user'))

            # Set Retrieval Enabled/Disabled
            self.disable_fax_retrieval_checkbox.setChecked(
                self.save_manager.get_config_value('Retrieval', 'auto_retrieve') == 'Disabled')

            # Set download method
            self.download_method_combo.setCurrentText(
                self.save_manager.get_config_value('Fax Options', 'download_method') or "PDF")

            # Set File Name Format
            file_name_format = self.save_manager.get_config_value('Fax Options', 'file_name_format')

            # Default to 'Fax ID' if file_name_format is None or an unexpected value
            if file_name_format not in ['Fax ID', 'cid-mmdd-hhmm']:
                file_name_format = 'Fax ID'

            # Update the radio buttons based on the file_name_format value
            self.fax_id_radio.setChecked(file_name_format == 'Fax ID')
            self.cid_mmdd_hhmm_radio.setChecked(file_name_format == 'cid-mmdd-hhmm')

            # Set print faxes option
            print_faxes = self.save_manager.get_config_value('Fax Options', 'print_faxes')
            self.print_faxes_checkbox.setChecked(print_faxes == 'Yes')  # Ensure state is properly restored
            self.toggle_print_options(print_faxes)  # Apply UI update immediately

            # Restore selected printer
            if print_faxes:
                printer_name = self.save_manager.get_config_value('Fax Options', 'printer_name')
                self.selected_printer_full_name = self.save_manager.get_config_value('Fax Options', 'printer_full_name')
                self.update_printer_button(printer_name)
            # Set delete faxes option
            delete_faxes = self.save_manager.get_config_value('Fax Options', 'delete_faxes')
            self.delete_faxes_checkbox.setChecked(delete_faxes == 'Yes')

            # Load Archive Enabled Setting
            archival_status = self.save_manager.get_config_value('Fax Options', 'archive_enabled')
            self.archive_enabled_checkbox.setChecked(archival_status == "Yes")

            # Load Archive Duration Setting
            self.archive_duration_combo.setCurrentText(
                self.save_manager.get_config_value('Fax Options', 'archive_duration') or "30")

            # Ensure the dropdown state matches the checkbox
            self.archive_duration_combo.setEnabled(self.archive_enabled_checkbox.isChecked())

            # Restore Integration Configuration and Settings
            self.enable_integrations_checkbox.setChecked(
                self.save_manager.get_config_value('Integrations', 'integration_enabled') == "Yes")

            # Restore 3rd party Config if Enabled
            self.software_selector.setCurrentText(self.save_manager.get_config_value('Integrations', 'integration_software')
                                                  or self.software_selector.itemText(0) or "None")


            # Set Debug Level
            logging_level = self.save_manager.get_config_value('UserSettings', 'logging_level')
            self.logging_level_combo.setCurrentText(logging_level)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to populate settings: {e}")
            self.log_system.log_message('error', f"Failed to populate settings: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def toggle_retrieval_settings(self, checked):
        try:
            """Show/hide fax retrieval settings while keeping the layout intact."""
            retrieval_groups = [
                self.download_options_group,
                self.fax_name_group,
                self.print_options_group,
                self.archival_group,
                self.delete_faxes_group
            ]

            for group in retrieval_groups:
                group.setHidden(checked)  # Hide without removing layout space

            self.resize_window(enforce_minimum=checked)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to toggle retrieval options: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def toggle_sensitive_settings(self, checked):
        try:
            if checked:
                if QMessageBox.warning(self, "Warning",
                                       "Changing these settings can cause the application to stop functioning properly.\n"
                                       "Continue only if you know what you are doing.",
                                       QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Ok:
                    for widget in self.account_info_group.findChildren((QLabel, QLineEdit, QComboBox)):
                        if widget == self.edit_sensitive_checkbox:
                            continue  # Keep the checkbox enabled

                        widget.setEnabled(True)
                        widget.setHidden(False)
                else:
                    # If the user cancels, uncheck the checkbox
                    self.edit_sensitive_checkbox.setChecked(False)
            else:
                # Hide and disable all sensitive settings when unchecked
                for widget in self.account_info_group.findChildren((QLabel, QLineEdit)):
                    if widget == self.edit_sensitive_checkbox:
                        continue  # Keep the checkbox enabled

                    widget.setEnabled(False)
                    widget.setHidden(True)

            self.resize_window(enforce_minimum=checked)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to toggle sensitive settings: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def save_settings(self):
        try:
            username = self.username_input.text().strip()
            password = self.password_input.text().strip()
            client_id = self.client_id_input.text().strip()
            client_secret = self.client_secret_input.text().strip()
            fax_user = self.fax_user_input.text().strip()

            # Archive settings
            archive_enabled = "Yes" if hasattr(self,
                                               'archive_enabled_checkbox') and self.archive_enabled_checkbox.isChecked() else "No"

            # Extract full numeric value from the dropdown selection
            archive_duration_match = re.search(r'\d+', self.archive_duration_combo.currentText())
            archive_duration = archive_duration_match.group() if archive_duration_match else "30"  # Default to 30 days if parsing fails

            # Flag to check if fax_user has been modified
            fax_user_modified = fax_user != self.previous_fax_user

            # Validate the new fax_user if it has been modified
            if fax_user_modified:
                valid, status = validate_fax_user(fax_user)
                if valid:
                    self._license_valid = True
                    print("Application Activated!")
                    QMessageBox.information(self, "Success", "The application has validated successfully!")
                    self.previous_fax_user = fax_user
                else:
                    self._license_valid = False
                    QMessageBox.critical(self, "Activation Error",
                                         "Account Inactive or not found. Please contact your Voice provider for assistance.")
                    return

            # Handle retrieval settings
            retrieval_disabled = self.disable_fax_retrieval_checkbox.isChecked() if hasattr(self,
                                                                                            'disable_fax_retrieval_checkbox') else False

            # Ensure Download and Delete Faxes settings are properly retrieved
            download_method = self.download_method_combo.currentText() if hasattr(self,
                                                                                  'download_method_combo') else "PDF"

            delete_faxes = "Yes" if self.delete_faxes_checkbox.isChecked() else "No"

            # 3rd Party Integration Settings
            integration_status = "Yes" if self.enable_integrations_checkbox.isChecked() else "No"
            if self.enable_integrations_checkbox.isChecked():
                integration_software = self.software_selector.currentText()
            else:
                integration_software = "None"

            # Logging level
            log_level = self.logging_level_combo.currentText() if hasattr(self, 'logging_level_combo') else "Info"

            # Handle print faxes settings
            print_faxes = 'Yes' if hasattr(self,
                                           'print_faxes_checkbox') and self.print_faxes_checkbox.isChecked() else 'No'
            printer_name = self.select_printer_button.text() if hasattr(self,
                                                                        'select_printer_button') and self.print_faxes_checkbox.isChecked() else ""
            printer_full_name = self.selected_printer_full_name if hasattr(self,
                                                                           'selected_printer_full_name') and self.print_faxes_checkbox.isChecked() else ""

            # Determine the selected file naming format
            file_name_format = "Fax ID" if self.fax_id_radio.isChecked() else "cid-mmdd-hhmm"

            settings_to_save = {
                'API': {'username': username or "None Set", 'password': password or "None Set"},
                'Client': {'client_id': client_id or "None Set", 'client_secret': client_secret or "None Set"},
                'Account': {'fax_user': fax_user or "None Set",
                            'validation_status': 'True' if self._license_valid else 'False'},
                'Fax Options': {'download_method': download_method, 'delete_faxes': delete_faxes,
                                'print_faxes': print_faxes, 'printer_name': printer_name,
                                'printer_full_name': printer_full_name, 'archive_enabled': archive_enabled,
                                'archive_duration': archive_duration, 'file_name_format': file_name_format},
                'UserSettings': {'logging_level': log_level},
                'Retrieval': {'auto_retrieve': 'Disabled' if retrieval_disabled else 'Enabled'},
                'Integrations': {'integration_enabled': integration_status,
                                 'integration_software': integration_software}
            }

            for section, options in settings_to_save.items():
                if not self.save_manager.config.has_section(section):
                    self.save_manager.config.add_section(section)
                for option, value in options.items():
                    if value:  # Ensure we only save non-empty values
                        self.save_manager.config.set(section, option, value)

            try:
                self.save_manager.save_changes()
                self.save_manager.read_encrypted_ini()  # Reload configuration after saving
                QMessageBox.information(self, "Settings Updated", "Settings have been updated successfully.")
                self.edit_sensitive_checkbox.setChecked(False)
                if self.main_window:
                    self.main_window.update_status_bar("Settings saved successfully.", 5000)
                self.retrieve_token.retrieve_token()
                if self.main_window:
                    self.main_window.update_status_bar("Logging in...", 5000)
                self.main_window.reload_ui()
                self.fax_timer_progress_bar.restart_progress()
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                if self.main_window:
                    self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
                return

            self.accept()  # Close the dialog

        except Exception as e:
            self.log_system.log_message('error', f"Failed to save settings: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
            QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))

    def resize_window(self, enforce_minimum=True):
        """Dynamically adjusts the window size while preventing unexpected collapses or excessive expansion."""
        self.adjustSize()
        self.setMinimumWidth(700)  # Ensure proper width for all elements to be visible
        # self.setMinimumHeight(500)  # Ensure sufficient height for elements like radio buttons

        if enforce_minimum:
            self.setMinimumHeight(self.layout.sizeHint().height())
            self.setMaximumHeight(self.layout.sizeHint().height())
        else:
            # self.setMinimumHeight(500)
            self.setMaximumHeight(1000)

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = OptionsDialog(None)
    dialog.show()
    sys.exit(app.exec_())