import os
import re
import sys

from PyQt5 import QtGui
from PyQt5.QtPrintSupport import QPrintDialog
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout, QCheckBox, QMessageBox,
                             QRadioButton, QGroupBox, QHBoxLayout, QButtonGroup, QComboBox)

from ProgressBars import FaxPollTimerProgressBar
from RetrieveToken import RetrieveToken
from SaveManager import SaveManager
from SystemLog import SystemLog
from Validation import validate_fax_user

# from ImportConfig import ImportConfig


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

        try:
            self.save_manager = SaveManager(self.main_window)
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))

            self.setWindowTitle("Options")
            self.setFixedWidth(400)

            self.layout = QVBoxLayout()
            self.setup_ui()
            self.populate_settings()
            self.fax_timer_progress_bar = FaxPollTimerProgressBar(self.main_window, token_progress_bar)

            self.selected_printer_full_name = None

            # Initialize to store the previous fax_user value
            self.previous_fax_user = self.save_manager.get_config_value('Account', 'fax_user')
            self._license_valid = self.save_manager.get_config_value('Account', 'validation_status') == 'True'

        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize OptionsDialog: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_ui(self):
        try:
            form_layout = QFormLayout()

            self.fax_retrieval_group = QGroupBox("Fax Retrieval Settings")
            fax_retrieval_group_layout = QVBoxLayout()
            self.setup_disable_fax(fax_retrieval_group_layout)
            self.setup_download_options_group(fax_retrieval_group_layout)
            # self.setup_print_options_group(fax_retrieval_group_layout)
            self.setup_delete_faxes_group(fax_retrieval_group_layout)
            self.fax_retrieval_group.setLayout(fax_retrieval_group_layout)

            # # Import Config Button
            # self.import_config_button = QPushButton("Import Config String")
            # self.import_config_button.clicked.connect(self.import_config_string)
            # self.import_config_button.setEnabled(False)

            self.account_info_group = QGroupBox("Account Settings")
            account_settings_layout = QVBoxLayout()
            self.setup_account_settings_group(account_settings_layout)
            self.account_info_group.setLayout(account_settings_layout)

            # Save button
            self.save_button = QPushButton("Save")
            self.save_button.clicked.connect(self.save_settings)

            # Cancel button
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.clicked.connect(self.close)

            # Add widgets to the form
            form_layout.addRow(self.fax_retrieval_group)

            form_layout.addRow(self.account_info_group)

            form_layout.addRow(self.save_button)
            form_layout.addRow(self.cancel_button)

            self.layout.addLayout(form_layout)
            self.setLayout(self.layout)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up UI: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_disable_fax(self, parent_layout):
        try:
            # Create Fax Retrieval Group
            self.fax_retrieval_group = QGroupBox("Fax Retrieval Settings")
            fax_retrieval_layout = QVBoxLayout()

            # Disable Fax Retrieval Checkbox (This should remain interactive)
            self.disable_fax_retrieval_checkbox = QCheckBox("Disable Fax Retrieval")
            self.disable_fax_retrieval_checkbox.toggled.connect(self.toggle_retrieval_settings)
            fax_retrieval_layout.addWidget(self.disable_fax_retrieval_checkbox)

            # Download Method Group
            self.download_options_group = QGroupBox("Download Method")
            download_options_layout = QVBoxLayout()
            self.download_method_combo = QComboBox()
            self.download_method_combo.addItems(["PDF", "JPG", "Both"])
            download_options_layout.addWidget(self.download_method_combo)
            self.download_options_group.setLayout(download_options_layout)
            fax_retrieval_layout.addWidget(self.download_options_group)

            # Print Faxes Group
            self.print_options_group = QGroupBox("Print Faxes")
            print_options_layout = QVBoxLayout()

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
            self.setup_archival_group(fax_retrieval_layout)

            # Delete Faxes Group
            self.delete_faxes_group = QGroupBox("Delete Faxes After Download")
            delete_faxes_layout = QVBoxLayout()
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

    def setup_print_options_group(self, parent_layout):
        try:
            # Print Faxes Checkbox
            self.print_faxes_checkbox = QCheckBox("Print Faxes")
            self.print_faxes_checkbox.toggled.connect(self.toggle_print_options)

            # Select Printer Button (Initially Hidden)
            self.select_printer_button = QPushButton("Select Printer")
            self.select_printer_button.clicked.connect(self.select_printer)
            self.select_printer_button.setVisible(False)  # Start hidden

            # Add to layout
            parent_layout.addWidget(self.print_faxes_checkbox)
            parent_layout.addWidget(self.select_printer_button)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up print options group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def toggle_print_options(self, checked):
        """
        Show or hide the "Select Printer" button based on the checkbox state.
        """
        try:
            self.select_printer_button.setVisible(checked)  # Show if checked, hide if unchecked

        except Exception as e:
            self.log_system.log_message('error', f"Failed to toggle print options: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_download_options_group(self, parent_layout):
        try:
            self.download_method_group = QGroupBox("Download Method")
            self.download_method_button_group = QButtonGroup(self)
            download_layout = QHBoxLayout()
            self.pdf_radio = QRadioButton("PDF")
            self.jpg_radio = QRadioButton("JPG")
            self.both_radio = QRadioButton("Both")
            self.download_method_button_group.addButton(self.pdf_radio)
            self.download_method_button_group.addButton(self.jpg_radio)
            self.download_method_button_group.addButton(self.both_radio)
            download_layout.addWidget(self.pdf_radio)
            download_layout.addWidget(self.jpg_radio)
            download_layout.addWidget(self.both_radio)
            self.download_method_group.setLayout(download_layout)
            parent_layout.addWidget(self.download_method_group)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up download method group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_delete_faxes_group(self, parent_layout):
        try:
            self.delete_faxes_group = QGroupBox("Delete Faxes After Download")
            self.delete_faxes_button_group = QButtonGroup(self)
            delete_layout = QHBoxLayout()
            self.delete_yes_radio = QRadioButton("Yes")
            self.delete_no_radio = QRadioButton("No")
            self.delete_faxes_button_group.addButton(self.delete_yes_radio)
            self.delete_faxes_button_group.addButton(self.delete_no_radio)
            delete_layout.addWidget(self.delete_yes_radio)
            delete_layout.addWidget(self.delete_no_radio)
            self.delete_faxes_group.setLayout(delete_layout)
            parent_layout.addWidget(self.delete_faxes_group)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up delete faxes group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_archival_group(self, parent_layout):
        """Set up the Fax Archival settings inside the Fax Retrieval group."""
        self.archival_group = QGroupBox("Fax Archival Settings")
        archival_layout = QVBoxLayout()

        # Archive Faxes Checkbox
        self.archive_enabled_checkbox = QCheckBox("Archive Incoming Faxes")
        self.archive_enabled_checkbox.toggled.connect(self.toggle_archive_duration)

        # Archive Duration Dropdown
        self.archive_duration_label = QLabel("Archive Incoming Faxes For:")
        self.archive_duration_combo = QComboBox()
        self.archive_duration_combo.addItems(["30 Days", "60 Days", "90 Days", "120 Days", "365 Days"])
        self.archive_duration_combo.setEnabled(False)  # Initially disabled

        # Add widgets to the layout
        archival_layout.addWidget(self.archive_enabled_checkbox)
        archival_layout.addWidget(self.archive_duration_label)
        archival_layout.addWidget(self.archive_duration_combo)
        self.archival_group.setLayout(archival_layout)

        parent_layout.addWidget(self.archival_group)

    def toggle_archive_duration(self, checked):
        """Enable or disable the archive duration dropdown based on checkbox state."""
        self.archive_duration_combo.setEnabled(checked)

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

            self.logging_level_label = QLabel("Logging Level:")
            self.logging_level_combo = QComboBox()
            # self.logging_level_combo.addItems(["Debug", "Info", "Warning", "Error", "Critical"])
            self.logging_level_combo.addItems(["Info"])
            parent_layout.addWidget(self.logging_level_label)
            parent_layout.addWidget(self.logging_level_combo)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up Account Options Group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def toggle_retrieval_settings(self, checked):
        try:
            # Ensure all child widgets inside "Fax Retrieval Settings" except the checkbox are disabled
            for widget in self.fax_retrieval_group.findChildren((QComboBox, QCheckBox, QPushButton)):

                # Keep the "Disable Fax Retrieval" checkbox enabled
                if widget == self.disable_fax_retrieval_checkbox:
                    continue

                widget.setDisabled(checked)

        except Exception as e:
            self.log_system.log_message('error', f"Failed to toggle retrieval options: {e}")
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
            retrieve_faxes = self.save_manager.get_config_value('Retrieval', 'auto_retrieve')
            self.disable_fax_retrieval_checkbox.setChecked(retrieve_faxes == 'Disabled')

            # Set download method
            download_method = self.save_manager.get_config_value('Fax Options', 'download_method')
            self.download_method_combo.setCurrentText(download_method)  # Use combo box instead of radio buttons

            # Set delete faxes option
            delete_faxes = self.save_manager.get_config_value('Fax Options', 'delete_faxes')
            self.delete_faxes_checkbox.setChecked(delete_faxes == 'Yes')

            # Set print faxes option
            print_faxes = self.save_manager.get_config_value('Fax Options', 'print_faxes') == 'Yes'
            self.print_faxes_checkbox.setChecked(print_faxes)  # Ensure state is properly restored
            self.toggle_print_options(print_faxes)  # Apply UI update immediately

            # Restore selected printer
            if print_faxes:
                printer_name = self.save_manager.get_config_value('Fax Options', 'printer_name')
                self.selected_printer_full_name = self.save_manager.get_config_value('Fax Options', 'printer_full_name')
                self.update_printer_button(printer_name)

            # Load Archive Enabled Setting
            archive_enabled = self.save_manager.get_config_value('Fax Options', 'archive_enabled')
            self.archive_enabled_checkbox.setChecked(archive_enabled == "Yes")

            # Load Archive Duration Setting
            archive_duration = self.save_manager.get_config_value('Fax Options', 'archive_duration')
            if archive_duration in ["30", "60", "90"]:
                self.archive_duration_combo.setCurrentText(f"{archive_duration} Days")
            else:
                self.archive_duration_combo.setCurrentText("30 Days")  # Default if unset

            # Ensure the dropdown state matches the checkbox
            self.archive_duration_combo.setEnabled(self.archive_enabled_checkbox.isChecked())

            # Set Debug Level
            logging_level = self.save_manager.get_config_value('UserSettings', 'logging_level')
            self.logging_level_combo.setCurrentText(logging_level)

        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to populate settings: {e}")
            self.log_system.log_message('error', f"Failed to populate settings: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def toggle_sensitive_settings(self, checked):
        try:
            if checked:
                if QMessageBox.warning(self, "Warning", "Changing these settings can cause the application to stop "
                                                        "functioning properly.\n Continue only if you know what you are "
                                                        "doing.",
                                       QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Ok:
                    self.username_input.setEnabled(True)
                    self.password_input.setEnabled(True)
                    self.client_id_input.setEnabled(True)
                    self.client_secret_input.setEnabled(True)
                    self.fax_user_input.setEnabled(True)
                else:
                    self.edit_sensitive_checkbox.setChecked(False)
            else:
                self.username_input.setEnabled(False)
                self.password_input.setEnabled(False)
                self.client_id_input.setEnabled(False)
                self.client_secret_input.setEnabled(False)
                self.fax_user_input.setEnabled(False)
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

            # Logging level
            log_level = self.logging_level_combo.currentText() if hasattr(self, 'logging_level_combo') else "Info"

            # Handle print faxes settings
            print_faxes = 'Yes' if hasattr(self,
                                           'print_faxes_checkbox') and self.print_faxes_checkbox.isChecked() else 'No'
            printer_name = self.select_printer_button.text() if hasattr(self,
                                                                        'select_printer_button') and self.print_faxes_checkbox.isChecked() else ""
            printer_full_name = self.selected_printer_full_name if hasattr(self,
                                                                           'selected_printer_full_name') and self.print_faxes_checkbox.isChecked() else ""

            settings_to_save = {
                'API': {'username': username or "None Set", 'password': password or "None Set"},
                'Client': {'client_id': client_id or "None Set", 'client_secret': client_secret or "None Set"},
                'Account': {'fax_user': fax_user or "None Set",
                            'validation_status': 'True' if self._license_valid else 'False'},
                'Fax Options': {'download_method': download_method, 'delete_faxes': delete_faxes,
                                'print_faxes': print_faxes, 'printer_name': printer_name,
                                'printer_full_name': printer_full_name, 'archive_enabled': archive_enabled,
                                'archive_duration': archive_duration},
                'UserSettings': {'logging_level': log_level},
                'Retrieval': {'auto_retrieve': 'Disabled' if retrieval_disabled else 'Enabled'}
            }

            for section, options in settings_to_save.items():
                if not self.save_manager.config.has_section(section):
                    self.save_manager.config.add_section(section)
                for option, value in options.items():
                    if value:  # Ensure we only save non-empty values
                        self.save_manager.config.set(section, option, value)

            try:
                self.retrieve_token.retrieve_token()
                self.save_manager.save_changes()
                self.save_manager.read_encrypted_ini()  # Reload configuration after saving
                QMessageBox.information(self, "Settings Updated", "Settings have been updated successfully.")
                self.edit_sensitive_checkbox.setChecked(False)
                if self.main_window:
                    self.main_window.update_status_bar("Settings saved successfully.", 5000)
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


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = OptionsDialog(None)
    dialog.show()
    sys.exit(app.exec_())