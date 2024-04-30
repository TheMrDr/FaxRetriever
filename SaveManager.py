import configparser
import os
import winreg as reg
from datetime import datetime

from cryptography.fernet import Fernet

from SystemLog import SystemLog


class EncryptionKeyManager:
    def __init__(self, application_name="CN-FaxRetriever"):
        self.log_system = SystemLog()
        self.application_name = application_name
        self.config = configparser.ConfigParser()
        self.registry_path = fr"Software\Clinic Networking, LLC"
        self.key_name = "FaxRetriever"
        self.ini_dir = os.path.join(os.getenv('LOCALAPPDATA'), self.application_name)
        if not os.path.exists(self.ini_dir):
            os.makedirs(self.ini_dir)
        self.ini_path = os.path.join(self.ini_dir, "config.ini")
        self.read_encrypted_ini()

    def check_encryption_key(self):
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, self.registry_path, 0, reg.KEY_READ) as registry_key:
                value, _ = reg.QueryValueEx(registry_key, self.key_name)
                return value
        except FileNotFoundError:
            with reg.CreateKey(reg.HKEY_CURRENT_USER, self.registry_path) as registry_key:
                encryption_key = self.generate_encryption_key()
                reg.SetValueEx(registry_key, self.key_name, 0, reg.REG_SZ, encryption_key)
                self.log_system.log_message('info', "Encryption key generated and stored.")
                return encryption_key

    @staticmethod
    def generate_encryption_key():
        return Fernet.generate_key().decode()

    def read_encrypted_ini(self):
        encryption_key = self.check_encryption_key()
        fernet = Fernet(encryption_key.encode())
        if not os.path.exists(self.ini_path):
            self.log_system.log_message('warning', "Configuration file not found, returning empty config.")
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
                    decrypted_config.set(section, option, encrypted_value)

        self.config = decrypted_config
        self.log_system.log_message('info', f"Configuration loaded from: {self.ini_path}")
        self.log_system.log_message('info', f"Encryption Key: [Protected]")
        self.log_system.log_message('debug', f"Encryption Key: {encryption_key}")
        return self.config

    def write_encrypted_ini(self, section=None, option=None, value=None):
        encryption_key = self.check_encryption_key()
        fernet = Fernet(encryption_key.encode())
        if not os.path.exists(self.ini_path):
            with open(self.ini_path, 'w') as file:
                file.write("")
        self.config.read(self.ini_path)

        if section and option and value is not None:
            encrypted_value = fernet.encrypt(value.encode()).decode()
            if not self.config.has_section(section):
                self.config.add_section(section)
            self.config.set(section, option, encrypted_value)
            self.log_system.log_message('debug', f"Encrypted value set for {section}/{option}.")

        with open(self.ini_path, 'w') as file:
            self.config.write(file)
            self.log_system.log_message('info', "Configuration written to file.")

    def get_config_value(self, section, option):
        encryption_key = self.check_encryption_key()
        fernet = Fernet(encryption_key.encode())
        if not self.config.has_section(section):
            self.config.add_section(section)
            self.log_system.log_message('warning', f"New section '{section}' added to configuration.")
        if not self.config.has_option(section, option):
            self.log_system.log_message('warning', f"Option '{option}' not found in section '{section}', setting default value.")
            default_value = self.get_default_value_for_option(section, option)
            encrypted_value = fernet.encrypt(default_value.encode()).decode()
            self.config.set(section, option, encrypted_value)
            self.write_encrypted_ini(section, option)  # Write changes back to the .ini file
            return default_value

        return self.config.get(section, option)

    def get_default_value_for_option(self, section, option):
        if section == "Token" and option == "token_expiration":
            return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        elif section == "Path" and option == "save_path":
            return os.path.join(os.environ.get('PUBLIC'), 'Desktop', 'FaxRetriever')
        elif section == "Retrieval" and option == "autoretrieve":
            return "Enabled"
        elif section == "Debug" and option == "debug_level":
            return "Info"
        return "None Set"
