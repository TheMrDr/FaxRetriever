from PyQt5 import QtGui
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout, QCheckBox, QMessageBox,
                             QRadioButton, QGroupBox, QHBoxLayout, QButtonGroup, QComboBox)

from ProgressBars import FaxPollTimerProgressBar
from SaveManager import SaveManager


# noinspection PyUnresolvedReferences
class OptionsDialog(QDialog):
    def __init__(self, main_window, token_progress_bar):
        super().__init__(parent=main_window)
        self.main_window = main_window
        self.save_manager = SaveManager(self.main_window)
        self.setWindowIcon(QtGui.QIcon("U:\\jfreeman\\Software Development\\FaxRetriever\\images\\logo.ico"))
        self.setWindowTitle("Options")
        self.layout = QVBoxLayout()
        self.setup_ui()
        self.populate_settings()
        self.fax_timer_progress_bar = FaxPollTimerProgressBar(self.main_window, token_progress_bar)

    def setup_ui(self):
        form_layout = QFormLayout()

        # Checkbox to enable editing sensitive settings
        self.edit_sensitive_checkbox = QCheckBox("Edit Account Settings")
        self.edit_sensitive_checkbox.toggled.connect(self.toggle_sensitive_settings)

        # New Checkbox to disable fax retrieval
        self.disable_fax_retrieval_checkbox = QCheckBox("Disable Fax Retrieval")
        self.disable_fax_retrieval_checkbox.toggled.connect(self.toggle_download_options)

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

        self.logging_level_level = QLabel("Logging Level:")
        self.logging_level_combo = QComboBox()
        self.logging_level_combo.addItems(["Debug", "Info", "Warning", "Error", "Critical"])

        # Group Box for all download-related settings
        self.download_options_group = QGroupBox("Download Options")
        download_options_layout = QVBoxLayout()

        # Individual settings within the group
        self.setup_download_method_group(download_options_layout)
        self.setup_delete_faxes_group(download_options_layout)
        # self.setup_mark_read_group(download_options_layout)

        self.download_options_group.setLayout(download_options_layout)

        # Save button
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_settings)

        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.close)

        # Add widgets to the form
        form_layout.addRow(self.disable_fax_retrieval_checkbox)
        form_layout.addRow(self.download_options_group)
        form_layout.addRow(self.edit_sensitive_checkbox)
        form_layout.addRow(self.username_label, self.username_input)
        form_layout.addRow(self.password_label, self.password_input)
        form_layout.addRow(self.client_id_label, self.client_id_input)
        form_layout.addRow(self.client_secret_label, self.client_secret_input)
        form_layout.addRow(self.fax_user_label, self.fax_user_input)
        form_layout.addRow(self.logging_level_level, self.logging_level_combo)
        form_layout.addRow(self.save_button)
        form_layout.addRow(self.cancel_button)

        self.layout.addLayout(form_layout)
        self.setLayout(self.layout)

    def setup_download_method_group(self, parent_layout):
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

    def setup_delete_faxes_group(self, parent_layout):
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
        # self.delete_no_radio.toggled.connect(self.toggle_mark_as_read)

    # def setup_mark_read_group(self, parent_layout):
    #     self.mark_read_group = QGroupBox("Mark Fax as Read")
    #     self.mark_read_button_group = QButtonGroup(self)
    #     mark_read_layout = QHBoxLayout()
    #     self.mark_read_yes_radio = QRadioButton("Yes")
    #     self.mark_read_no_radio = QRadioButton("No")
    #     self.mark_read_button_group.addButton(self.mark_read_yes_radio)
    #     self.mark_read_button_group.addButton(self.mark_read_no_radio)
    #     mark_read_layout.addWidget(self.mark_read_yes_radio)
    #     mark_read_layout.addWidget(self.mark_read_no_radio)
    #     self.mark_read_group.setLayout(mark_read_layout)
    #     parent_layout.addWidget(self.mark_read_group)

    def toggle_download_options(self, checked):
        self.download_options_group.setDisabled(checked)

    # def toggle_mark_as_read(self, checked):
    #     # Enable mark as read options only if delete is set to No
    #     self.mark_read_group.setEnabled(checked)

    def populate_settings(self):
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

        # Set Debug Level
        debug_level = self.save_manager.get_config_value('Debug', 'debug_level')
        self.logging_level_combo.setCurrentText(debug_level)

    def toggle_sensitive_settings(self, checked):
        if checked:
            if QMessageBox.warning(self, "Warning", "Changing these settings can cause the application to stop "
                                                    "functioning properly.\n Continue only if you know what you are "
                                                    "doing.", QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Ok:
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

    def save_settings(self):
        # Save all settings to config file
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()
        client_id = self.client_id_input.text().strip()
        client_secret = self.client_secret_input.text().strip()
        fax_user = self.fax_user_input.text().strip()
        retrieval_disabled = self.disable_fax_retrieval_checkbox.isChecked()
        download_method = self.download_method_button_group.checkedButton().text() if (
            self.download_method_button_group.checkedButton()) else ""
        delete_faxes = self.delete_faxes_button_group.checkedButton().text() if (
            self.delete_faxes_button_group.checkedButton()) else ""
        # mark_read = self.mark_read_button_group.checkedButton().text() if (
        #     self.mark_read_button_group.checkedButton()) else ""
        log_level = self.logging_level_combo.currentText()

        for section in ['API', 'Client', 'Account', 'Fax Options', 'Debug']:
            if not self.save_manager.config.has_section(section):
                self.save_manager.config.add_section(section)

        self.save_manager.config.set('API', 'username', username)
        self.save_manager.config.set('API', 'password', password)
        self.save_manager.config.set('Client', 'client_id', client_id)
        self.save_manager.config.set('Client', 'client_secret', client_secret)
        self.save_manager.config.set('Account', 'fax_user', fax_user)
        self.save_manager.config.set('Fax Options', 'download_method', download_method)
        self.save_manager.config.set('Fax Options', 'delete_faxes', delete_faxes)
        # self.encryption_manager.config.set('Fax Options', 'mark_read', mark_read)
        self.save_manager.config.set('UserSettings', 'logging_level', log_level)

        retrieval_status = 'Disabled' if retrieval_disabled else 'Enabled'
        self.save_manager.config.set('Retrieval', 'auto_retrieve', retrieval_status)

        try:
            self.save_manager.save_changes()
            self.save_manager.read_encrypted_ini()  # Reload configuration after saving
            QMessageBox.information(self, "Settings Updated", "Settings have been updated successfully.")
            self.main_window.update_status_bar("Settings saved successfully.", 5000)
            self.main_window.populate_data()
            self.fax_timer_progress_bar.restart_progress()
        except Exception as e:
            QMessageBox.critical(self, "Error", "Failed to save settings: " + str(e))
            self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
            return

        self.accept()  # Close the dialog

        # # Show message box asking the user to restart the application
        # msg_box = QMessageBox()
        # msg_box.setIcon(QMessageBox.Information)
        # msg_box.setText("Settings changed. Please restart the application for changes to take effect.")
        # msg_box.setWindowTitle("Restart Required")
        # msg_box.setStandardButtons(QMessageBox.Ok)
        # msg_box.buttonClicked.connect(lambda: self.main_window.restart_application())
        # msg_box.exec()
