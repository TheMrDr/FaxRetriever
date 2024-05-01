import configparser
import os
import winreg as reg
from datetime import datetime

from cryptography.fernet import Fernet

from SystemLog import SystemLog


class SaveManager:
    _instance = None  # Singleton pattern implementation

    def __new__(cls, application_name="CN-FaxRetriever"):
        if cls._instance is None:
            cls._instance = super(SaveManager, cls).__new__(cls)
            cls._instance.init(application_name)
        return cls._instance

    def init(self, application_name):
        self.log_system = SystemLog()
        self.application_name = application_name
        self.config = configparser.ConfigParser()
        self.registry_path = fr"Software\Clinic Networking, LLC"
        self.key_name = "FaxRetriever"
        self.ini_dir = os.path.join(os.getenv('LOCALAPPDATA'), self.application_name)
        os.makedirs(self.ini_dir, exist_ok=True)
        self.ini_path = os.path.join(self.ini_dir, "config.ini")
        self.read_encrypted_ini()

    @staticmethod
    def generate_encryption_key():
        return Fernet.generate_key().decode()

    def get_encryption_key(self):
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, self.registry_path, 0, reg.KEY_READ) as registry_key:
                encryption_key, _ = reg.QueryValueEx(registry_key, self.key_name)
                return encryption_key
        except FileNotFoundError:
            with reg.CreateKey(reg.HKEY_CURRENT_USER, self.registry_path) as registry_key:
                encryption_key = self.generate_encryption_key()
                reg.SetValueEx(registry_key, self.key_name, 0, reg.REG_SZ, encryption_key)
                self.log_system.log_message('info', "Encryption key generated and stored.")
                return encryption_key

    def read_encrypted_ini(self):
        encryption_key = self.get_encryption_key()
        fernet = Fernet(encryption_key.encode())
        if not os.path.exists(self.ini_path):
            self.log_system.log_message('warning', "Configuration file not found, creating empty config.")
            return self.config  # Return an empty config if the file doesn't exist

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
                    self.log_system.log_message('error', f"Error decrypting {option} in section {section}: {e}")
                    self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
                    decrypted_config.set(section, option, encrypted_value)

        self.config = decrypted_config
        self.log_system.log_message('info', f"Configuration loaded from: {self.ini_path}")
        self.log_system.log_message('info', f"Encryption Key: [Protected]")
        self.log_system.log_message('debug', f"Encryption Key: {encryption_key}")

    def save_changes(self):
        """Encrypt and write the in-memory configuration to file."""
        encryption_key = self.get_encryption_key()
        fernet = Fernet(encryption_key.encode())
        encrypted_config = configparser.ConfigParser()

        # Ensure all current sections and options are processed
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
                    self.main_window.update_status_bar(f"Error: {str(e)}", 10000)
                    continue  # Skip this item or handle appropriately

        # Attempt to write the encrypted config to file
        try:
            with open(self.ini_path, 'w') as file:
                encrypted_config.write(file)
            self.log_system.log_message('info', "All configurations have been encrypted and saved.")
        except Exception as e:
            self.log_system.log_message('error', f"Failed to write configuration to file: {e}")
            self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def get_config_value(self, section, option):
        encryption_key = self.get_encryption_key()
        fernet = Fernet(encryption_key.encode())
        if not self.config.has_section(section):
            self.config.add_section(section)
            self.log_system.log_message('warning', f"New section '{section}' added to configuration.")
        if not self.config.has_option(section, option):
            self.log_system.log_message('warning',
                                        f"Option '{option}' not found in section '{section}', setting default value.")
            default_value = self.get_default_value_for_option(section, option)
            self.config.set(section, option, default_value)
            self.save_changes()  # Write changes back to the .ini file
            return default_value
        settings_value = self.config.get(section, option)
        return settings_value

    def get_default_value_for_option(self, section, option):
        # Define default values for options
        defaults = {
            ("Token", "token_expiration"): datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            ("Token", "access_token"): "None Set",
            ("Path", "save_path"): os.path.join(os.getenv('PUBLIC'), 'Desktop', 'FaxRetriever'),
            ("Retrieval", "auto_retrieve"): "Disabled",
            ("Logging", "logging_level"): "Info",
            ("UserSettings", "selected_inboxes"): "",
        }
        return defaults.get((section, option), "None Set")
