import os
import sys

# from ImportConfig import ImportConfig

from ProgressBars import FaxPollTimerProgressBar

from PyQt5 import QtGui
from PyQt5.QtPrintSupport import QPrintDialog
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout, QCheckBox, QMessageBox,
                             QRadioButton, QGroupBox, QHBoxLayout, QButtonGroup, QComboBox)

from RetrieveToken import RetrieveToken

from SaveManager import SaveManager

from SystemLog import SystemLog

from Validation import validate_fax_user


# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


class OptionsDialog(QDialog):
    def __init__(self, main_window, token_progress_bar=None):
        super().__init__(parent=main_window)
        self.log_system = SystemLog()
        self.retrieve_token = RetrieveToken(self)
        self.main_window = main_window

        try:
            self.save_manager = SaveManager(self.main_window)
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))

            self.setWindowTitle("Options")
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
            self.setFixedWidth(400)

            # Checkbox to enable editing sensitive settings
            self.edit_sensitive_checkbox = QCheckBox("Edit Account Settings")
            self.edit_sensitive_checkbox.toggled.connect(self.toggle_sensitive_settings)

            # New Checkbox to disable fax retrieval
            self.disable_fax_retrieval_checkbox = QCheckBox("Disable Fax Retrieval")
            self.disable_fax_retrieval_checkbox.toggled.connect(self.toggle_download_options)

            # # Import Config Button
            # self.import_config_button = QPushButton("Import Config String")
            # self.import_config_button.clicked.connect(self.import_config_string)
            # self.import_config_button.setEnabled(False)

            # API Credentials Section
            self.username_label = QLabel("API Username:")
            self.username_input = QLineEdit()
            self.username_input.setEnabled(False)

            self.password_label = QLabel("API Password:")
            self.password_input = QLineEdit()
            self.password_input.setEchoMode(QLineEdit.Password)
            self.password_input.setEnabled(False)

            self.client_id_label = QLabel("Client ID:")
            self.client_id_input = QLineEdit()
            self.client_id_input.setEnabled(False)

            self.client_secret_label = QLabel("Client Secret:")
            self.client_secret_input = QLineEdit()
            self.client_secret_input.setEchoMode(QLineEdit.Password)
            self.client_secret_input.setEnabled(False)

            self.fax_user_label = QLabel("Fax User:")
            self.fax_user_input = QLineEdit()
            self.fax_user_input.setEnabled(False)

            self.logging_level_label = QLabel("Logging Level:")
            self.logging_level_combo = QComboBox()
            self.logging_level_combo.addItems(["Debug", "Info", "Warning", "Error", "Critical"])

            # Group Box for all print-related settings
            self.print_faxes_group = QGroupBox("Print Options")
            print_faxes_layout = QHBoxLayout()
            self.setup_print_options_group(print_faxes_layout)
            self.print_faxes_group.setLayout(print_faxes_layout)

            # Group Box for all download-related settings
            self.download_options_group = QGroupBox("Download Options")
            download_options_layout = QVBoxLayout()
            self.setup_download_method_group(download_options_layout)
            self.setup_delete_faxes_group(download_options_layout)
            self.download_options_group.setLayout(download_options_layout)

            # Save button
            self.save_button = QPushButton("Save")
            self.save_button.clicked.connect(self.save_settings)

            # Cancel button
            self.cancel_button = QPushButton("Cancel")
            self.cancel_button.clicked.connect(self.close)

            # Add widgets to the form
            form_layout.addRow(self.disable_fax_retrieval_checkbox)
            form_layout.addRow(self.print_faxes_group)
            form_layout.addRow(self.download_options_group)
            form_layout.addRow(self.edit_sensitive_checkbox)
            form_layout.addRow(self.username_label, self.username_input)
            form_layout.addRow(self.password_label, self.password_input)
            form_layout.addRow(self.client_id_label, self.client_id_input)
            form_layout.addRow(self.client_secret_label, self.client_secret_input)
            form_layout.addRow(self.fax_user_label, self.fax_user_input)
            form_layout.addRow(self.logging_level_label, self.logging_level_combo)
            form_layout.addRow(self.save_button)
            form_layout.addRow(self.cancel_button)

            self.layout.addLayout(form_layout)
            self.setLayout(self.layout)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up UI: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_print_options_group(self, parent_layout):
        try:
            self.print_faxes_checkbox = QCheckBox("Print Faxes")
            self.select_printer_button = QPushButton("Select Printer")
            self.select_printer_button.clicked.connect(self.select_printer)

            parent_layout.addWidget(self.print_faxes_checkbox)
            parent_layout.addWidget(self.select_printer_button)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to set up print options group: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def setup_download_method_group(self, parent_layout):
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
            self.delete_faxes_group = QGroupBox("Delete Downloaded Faxes")
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

    def toggle_download_options(self, checked):
        try:
            self.download_options_group.setDisabled(checked)
        except Exception as e:
            self.log_system.log_message('error', f"Failed to toggle download options: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def select_printer(self):
        try:
            printer_dialog = QPrintDialog()
            if printer_dialog.exec_() == QPrintDialog.Accepted:
                printer_info = printer_dialog.printer().printerName()
                truncated_printer_name = (printer_info[:20] + '..') if len(printer_info) > 20 else printer_info
                self.select_printer_button.setText(truncated_printer_name)
                self.selected_printer_full_name = printer_info  # Store the full printer name
        except Exception as e:
            self.log_system.log_message('error', f"Failed to select printer: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

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
            if retrieve_faxes == 'Enabled':
                self.disable_fax_retrieval_checkbox.setChecked(False)
            elif retrieve_faxes == 'Disabled':
                self.disable_fax_retrieval_checkbox.setChecked(True)

            # Set download method
            download_method = self.save_manager.get_config_value('Fax Options', 'download_method')
            if download_method == 'PDF':
                self.pdf_radio.setChecked(True)
            elif download_method == 'JPG':
                self.jpg_radio.setChecked(True)
            elif download_method == 'Both':
                self.both_radio.setChecked(True)

            # Set delete faxes option
            delete_faxes = self.save_manager.get_config_value('Fax Options', 'delete_faxes')
            if delete_faxes == 'Yes':
                self.delete_yes_radio.setChecked(True)
            else:
                self.delete_no_radio.setChecked(True)

            # Set print faxes option
            print_faxes = self.save_manager.get_config_value('Fax Options', 'print_faxes')
            if print_faxes == 'Yes':
                self.print_faxes_checkbox.setChecked(True)
                printer_name = self.save_manager.get_config_value('Fax Options', 'printer_name')
                truncated_printer_name = (printer_name[:20] + '..') if len(printer_name) > 20 else printer_name
                self.select_printer_button.setText(truncated_printer_name)
                self.selected_printer_full_name = self.save_manager.get_config_value('Fax Options',
                                                                                     'printer_full_name')

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

            retrieval_disabled = self.disable_fax_retrieval_checkbox.isChecked()
            download_method = self.download_method_button_group.checkedButton().text() if (
                self.download_method_button_group.checkedButton()) else ""
            delete_faxes = self.delete_faxes_button_group.checkedButton().text() if (
                self.delete_faxes_button_group.checkedButton()) else ""
            log_level = self.logging_level_combo.currentText()
            print_faxes = 'Yes' if self.print_faxes_checkbox.isChecked() else 'No'

            if self.print_faxes_checkbox.isChecked() and not self.selected_printer_full_name:
                QMessageBox.critical(self, "Error", "You must select a printer if the 'Print Faxes' option is enabled.")
                return

            printer_name = self.select_printer_button.text() if self.print_faxes_checkbox.isChecked() else ""
            printer_full_name = self.selected_printer_full_name if self.print_faxes_checkbox.isChecked() else ""

            settings_to_save = {
                'API': {'username': username, 'password': password},
                'Client': {'client_id': client_id, 'client_secret': client_secret},
                'Account': {'fax_user': fax_user, 'validation_status': 'True' if self._license_valid else 'False'},
                'Fax Options': {'download_method': download_method, 'delete_faxes': delete_faxes,
                                'print_faxes': print_faxes, 'printer_name': printer_name,
                                'printer_full_name': printer_full_name},
                'UserSettings': {'logging_level': log_level},
                'Retrieval': {'auto_retrieve': 'Disabled' if retrieval_disabled else 'Enabled'}
            }

            for section, options in settings_to_save.items():
                if not self.save_manager.config.has_section(section):
                    self.save_manager.config.add_section(section)
                for option, value in options.items():
                    self.save_manager.config.set(section, option, value)

            try:
                self.retrieve_token.retrieve_token()
                self.save_manager.save_changes()
                self.save_manager.read_encrypted_ini()  # Reload configuration after saving
                QMessageBox.information(self, "Settings Updated", "Settings have been updated successfully.")
                self.edit_sensitive_checkbox.setChecked(False)
                # if self.main_window():
                #     self.main_window.update_status_bar("Settings saved successfully.", 5000)
                self.main_window.reload_ui()
                self.fax_timer_progress_bar.restart_progress()
            except Exception as e:
                QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
                # if self.main_window():
                #     self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
                return
            self.accept()  # Close the dialog
        except Exception as e:
            self.log_system.log_message('error', f"Failed to save settings: {e}")
            # if self.main_window:
            #     self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
            QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))

if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    dialog = OptionsDialog(None)
    dialog.show()
    sys.exit(app.exec_())
