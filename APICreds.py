from PyQt5 import QtGui
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton

from SaveManager import EncryptionKeyManager
from SystemLog import SystemLog


# noinspection PyUnresolvedReferences
class SetApiCredentialsDialog(QDialog):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.log_system = SystemLog()
        self.setWindowIcon(QtGui.QIcon(".\\images\\logo.ico"))
        self.setWindowTitle("Set API Credentials")
        self.layout = QVBoxLayout()
        self.setup_ui()

    def setup_ui(self):
        self.username_label = QLabel("API Username:")
        self.username_input = QLineEdit()

        self.password_label = QLabel("API Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)

        self.client_id_label = QLabel("Client ID:")
        self.client_id_input = QLineEdit()

        self.client_secret_label = QLabel("Client Secret:")
        self.client_secret_input = QLineEdit()
        self.client_secret_input.setEchoMode(QLineEdit.Password)

        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save_credentials)

        self.layout.addWidget(self.username_label)
        self.layout.addWidget(self.username_input)
        self.layout.addWidget(self.password_label)
        self.layout.addWidget(self.password_input)
        self.layout.addWidget(self.client_id_label)
        self.layout.addWidget(self.client_id_input)
        self.layout.addWidget(self.client_secret_label)
        self.layout.addWidget(self.client_secret_input)
        self.layout.addWidget(self.save_button)

        self.setLayout(self.layout)

    def save_credentials(self):
        try:
            # Retrieve credentials from input fields, stripping any whitespace
            username = self.username_input.text().strip()
            password = self.password_input.text().strip()
            client_id = self.client_id_input.text().strip()
            client_secret = self.client_secret_input.text().strip()

            # Instance of EncryptionKeyManager
            encryption_manager = EncryptionKeyManager()

            # Store credentials in the encrypted .ini file
            encryption_manager.write_encrypted_ini('API', 'username', username)
            encryption_manager.write_encrypted_ini('API', 'password', password)
            encryption_manager.write_encrypted_ini('Client', 'client_id', client_id)
            encryption_manager.write_encrypted_ini('Client', 'client_secret', client_secret)

            # Log details (masking password and client secret)
            self.log_system.log_message('info', f'API Credentials Modified: Username: {username}, Password: [Protected], Client ID: {client_id}, Client Secret: [Protected]')
            self.log_system.log_message('info', 'Credentials saved successfully.')

            # Indicate that data needs refreshing and close the dialog
            self.main_window.populate_data()
            self.accept()  # Close the dialog or indicate completion
        except Exception as e:
            self.log_system.log_message('error', f'Failed to save credentials: {str(e)}')
            raise e  # Optionally re-raise the exception if you want it to be caught elsewhere.
