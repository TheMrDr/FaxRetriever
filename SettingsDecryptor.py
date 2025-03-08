import configparser
import os
import winreg

from cryptography.fernet import Fernet


# Function to read encryption key from registry
def get_encryption_key():
    try:
        reg_key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Clinic Networking, LLC")
        encryption_key, reg_type = winreg.QueryValueEx(reg_key, "FaxRetriever")
        winreg.CloseKey(reg_key)
        return encryption_key.encode()  # Ensure key is in bytes for Fernet
    except FileNotFoundError:
        print("Registry key not found.")
        return None

# Function to decrypt encrypted values in the config file
def decrypt_value(encrypted_value, encryption_key):
    try:
        fernet = Fernet(encryption_key)
        decrypted_value = fernet.decrypt(encrypted_value.encode()).decode()
        return decrypted_value
    except Exception as e:
        print(f"Error decrypting value: {e}")
        return None

# Function to read and decrypt config.ini
def read_config_file(file_path, encryption_key):
    config = configparser.ConfigParser()
    config.read(file_path)

    decrypted_values = {}
    for section in config.sections():
        decrypted_values[section] = {}
        for key in config[section]:
            encrypted_value = config[section][key]
            decrypted_value = decrypt_value(encrypted_value, encryption_key)
            decrypted_values[section][key] = decrypted_value

    return decrypted_values

# Main program
if __name__ == "__main__":
    # Registry key path for the encryption key
    encryption_key = get_encryption_key()

    if encryption_key:
        # Resolve the path to the settings file
        config_file_path = os.path.expandvars(r"%localappdata%\CN-FaxRetriever\config.ini")

        # Decrypt and read config file
        decrypted_config = read_config_file(config_file_path, encryption_key)

        # Display decrypted values
        if decrypted_config:
            for section, values in decrypted_config.items():
                print(f"[{section}]")
                for key, value in values.items():
                    print(f"{key} = {value}")
        else:
            print("No decrypted values found.")
    else:
        print("Encryption key not found.")
