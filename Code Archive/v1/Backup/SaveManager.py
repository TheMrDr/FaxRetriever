import configparser
import os
import winreg as reg
from datetime import datetime

from cryptography.fernet import Fernet

from SystemLog import SystemLog


class SaveManager:
    _instance = None  # Singleton pattern implementation

    def __new__(cls, main_window=None, application_name="CN-FaxRetriever"):
        if cls._instance is None:
            cls._instance = super(SaveManager, cls).__new__(cls)
            cls._instance.init(main_window, application_name)
        return cls._instance

    def init(self, main_window, application_name):
        try:
            self.log_system = SystemLog()
            self.main_window = main_window
            self.application_name = application_name
            self.config = configparser.ConfigParser()
            self.registry_path = fr"Software\Clinic Networking, LLC"
            self.key_name = "FaxRetriever"
            self.ini_dir = os.path.join(os.getenv('LOCALAPPDATA'), self.application_name)
            os.makedirs(self.ini_dir, exist_ok=True)
            self.ini_path = os.path.join(self.ini_dir, "config.ini")
            self.read_encrypted_ini()
        except Exception as e:
            self.log_system.log_message('error', f"Failed to initialize SaveManager: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    @staticmethod
    def generate_encryption_key():
        return Fernet.generate_key().decode()

    def get_encryption_key(self):
        """Retrieves the encryption key from the registry or generates one if missing. Exits on failure."""
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, self.registry_path, 0, reg.KEY_READ) as registry_key:
                encryption_key, _ = reg.QueryValueEx(registry_key, self.key_name)
                return encryption_key
        except FileNotFoundError:
            try:
                with reg.CreateKey(reg.HKEY_CURRENT_USER, self.registry_path) as registry_key:
                    encryption_key = self.generate_encryption_key()
                    reg.SetValueEx(registry_key, self.key_name, 0, reg.REG_SZ, encryption_key)
                    self.log_system.log_message('info', "Encryption key generated and stored.")
                    return encryption_key
            except Exception as e:
                self.log_system.log_message('critical', f"Failed to generate or store encryption key: {e}")
                self.critical_failure("Failed to generate encryption key.\n\n"
                                      "The application cannot continue and must be reinstalled.")
        except Exception as e:
            self.log_system.log_message('critical', f"Failed to retrieve encryption key: {e}")
            self.critical_failure("Failed to retrieve encryption key.\n\n"
                                  "The application cannot continue and must be reinstalled.")

        return None  # Should never reach this point

    def read_encrypted_ini(self):
        """Attempts to read and decrypt the settings file. Exits on failure."""
        encryption_key = self.get_encryption_key()
        if not encryption_key:
            self.critical_failure("Encryption key is missing or invalid.\n\n"
                                  "The application cannot read settings and must be reinstalled.")

        fernet = Fernet(encryption_key.encode())

        if not os.path.exists(self.ini_path):
            self.log_system.log_message('warning', "Configuration file not found, creating empty config.")
            return  # We allow an empty config file to be created

        self.config.read(self.ini_path)
        decrypted_config = configparser.ConfigParser()

        for section in self.config.sections():
            decrypted_config.add_section(section)
            self.log_system.log_message('debug', f"Section: {section}")
            for option in self.config.options(section):
                encrypted_value = self.config.get(section, option)
                try:
                    decrypted_value = fernet.decrypt(encrypted_value.encode()).decode()
                    decrypted_config.set(section, option, decrypted_value)
                    self.log_system.log_message('debug', f"  {option}: {decrypted_value}")
                except Exception as e:
                    self.log_system.log_message('critical', f"Failed to decrypt setting '{option}' in '{section}': {e}")
                    self.critical_failure("Failed to decrypt settings.\n\n"
                                          "The application cannot continue and must be reinstalled.")

        self.config = decrypted_config
        self.log_system.log_message('info', f"Configuration loaded from: {self.ini_path}")

    def save_changes(self):
        """Encrypt and write the in-memory configuration to file."""
        encryption_key = self.get_encryption_key()
        if not encryption_key:
            self.log_system.log_message('error', "Encryption key is not available.")
            return

        fernet = Fernet(encryption_key.encode())
        encrypted_config = configparser.ConfigParser()

        # Ensure all required sections and options are processed, even if they are missing
        for section in self.config.sections():
            if not encrypted_config.has_section(section):
                encrypted_config.add_section(section)  # Create the section if it does not exist

            for option in self.config.options(section):
                decrypted_value = self.config.get(section, option)
                try:
                    # Encrypt the value
                    encrypted_value = fernet.encrypt(decrypted_value.encode()).decode()
                    # Set the encrypted value
                    encrypted_config.set(section, option, encrypted_value)
                except Exception as e:
                    self.log_system.log_message('error', f"Failed to encrypt {option} in {section}: {e}")
                    if self.main_window:
                        self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
                    continue  # Skip this item or handle appropriately

        # Attempt to write the encrypted config to file
        try:
            with open(self.ini_path, 'w') as file:
                encrypted_config.write(file)
            self.log_system.log_message('info', "All configurations have been encrypted and saved.")
        except Exception as e:
            self.log_system.log_message('error', f"Failed to write configuration to file: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def get_config_value(self, section, option):
        """Retrieve a configuration value, ensuring a default exists and writing missing values immediately."""
        try:
            encryption_key = self.get_encryption_key()
            if not encryption_key:
                self.log_system.log_message('error', "Encryption key is not available.")
                return self.get_default_value_for_option(section, option)

            fernet = Fernet(encryption_key.encode())

            # Ensure the section exists
            if not self.config.has_section(section):
                self.config.add_section(section)
                self.log_system.log_message('warning', f"New section '{section}' added to configuration.")

            # Ensure the option exists
            if not self.config.has_option(section, option):
                default_value = self.get_default_value_for_option(section, option)
                self.config.set(section, option, default_value)
                self.log_system.log_message('warning',
                                            f"Missing option '{option}' in section '{section}', defaulting to '{default_value}'")
                self.save_changes()  # Persist the missing default immediately
                return default_value

            # Retrieve and decrypt the value
            settings_value = self.config.get(section, option)
            return settings_value

        except Exception as e:
            self.log_system.log_message('error', f"Error retrieving '{option}' from section '{section}': {e}")
            return self.get_default_value_for_option(section, option)  # Fallback to default

    def get_default_value_for_option(self, section, option):
        """Provide default values for all known settings to ensure stability."""
        defaults = {
            # Token settings
            ("Token", "token_expiration"): datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ("Token", "access_token"): "",

            # Fax Retrieval
            ("Retrieval", "auto_retrieve"): "Disabled",

            # Fax Options
            ("Fax Options", "download_method"): "PDF",
            ("Fax Options", "delete_faxes"): "No",
            ("Fax Options", "print_faxes"): "No",
            ("Fax Options", "printer_name"): "",
            ("Fax Options", "printer_full_name"): "",
            ("Fax Options", "archive_enabled"): "No",
            ("Fax Options", "archive_duration"): "30",  # Always store raw number, UI can append 'Days'
            ("Fax Options", "file_name_format"): "Fax ID",
            ("Fax Options", "include_cover_sheet"): "No",
            ("Fax Options", "cover_sheet_business_name"): "None",
            ("Fax Options", "cover_sheet_business_address"): "None",
            ("Fax Options", "cover_sheet_business_phone"): "None",
            ("Fax Options", "cover_sheet_business_email"): "None",

            # User Settings
            ("UserSettings", "logging_level"): "Info",
            ("UserSettings", "save_path"): os.path.join(os.getenv('PUBLIC'), 'Desktop', 'FaxRetriever'),
            ("UserSettings", "selected_inboxes"): "",

            # Integrations
            ("Integrations", "integration_enabled"): "No",
            ("Integrations", "software_integration"): "None",
            ("Integrations", "winrx_path"): "",
            ("Integrations", 'acknowledgement'): "False",

            # Account
            ("Account", "fax_user"): "",
            ("Account", "validation_status"): "False",
            ("Account", "api_username"): "",
            ("Account", "api_password"): "",
            ("Account", "client_id"): "",
            ("Account", "client_secret"): "",
        }
        return defaults.get((section, option), "")

    def critical_failure(self, message):
        """Logs a critical failure and forces the application to close."""
        self.log_system.log_message('critical', message)

        # Display a message box if running in a GUI context
        if self.main_window:
            from PyQt5.QtWidgets import QMessageBox
            QMessageBox.critical(self.main_window, "Critical Error", message)

        # Force application exit
        import sys
        sys.exit(1)
