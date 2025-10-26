# Admin/licensing_server/ui/tabs/reseller_tab.py

import base64

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from PyQt5.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                             QLabel, QLineEdit, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)

from core.api_client import ApiClient


def _derive_key(passphrase: str, salt: bytes, iterations: int = 100_000) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32, salt=salt, iterations=iterations
    )
    return kdf.derive(passphrase.encode("utf-8"))


def _decrypt_blob_local(passphrase: str, blob: dict) -> dict:
    import json

    ct = base64.b64decode(blob["ciphertext"])  # may raise
    nonce = base64.b64decode(blob["nonce"])  # may raise
    salt = base64.b64decode(blob["salt"])  # may raise
    aesgcm = AESGCM(_derive_key(passphrase, salt))
    pt = aesgcm.decrypt(nonce, ct, None)
    return json.loads(pt.decode("utf-8"))


class ResellerTab(QWidget):
    def apply_filters(self):
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            for col, line_edit in enumerate(self.filter_inputs):
                text = line_edit.text().strip().lower()
                if text and text not in self.table.item(row, col).text().lower():
                    self.table.setRowHidden(row, True)
                    break

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        form_frame = QFrame()
        form_frame.setObjectName("panel")
        form_frame.setFrameShape(QFrame.StyledPanel)
        form_layout = QVBoxLayout()
        form_frame.setLayout(form_layout)

        self.grid = QGridLayout()
        self.grid.setSpacing(6)

        self.reseller_id = QLineEdit()
        self.reseller_id.setPlaceholderText("12345")
        self.reseller_id.setMaxLength(5)
        self.voice_user = QLineEdit()
        self.voice_user.setPlaceholderText("api@reseller")
        self.voice_pass = QLineEdit()
        self.voice_pass.setPlaceholderText("Password")
        self.voice_pass.setEchoMode(QLineEdit.Password)
        self.msg_user = QLineEdit()
        self.msg_user.setPlaceholderText("00000000-0000-0000-0000-000000000000")
        self.msg_pass = QLineEdit()
        self.msg_pass.setPlaceholderText("Fax API Password")
        self.msg_pass.setEchoMode(QLineEdit.Password)

        self.contact_name = QLineEdit()
        self.contact_name.setPlaceholderText("Contact Name")
        self.contact_email = QLineEdit()
        self.contact_email.setPlaceholderText("Contact Email")
        self.contact_phone = QLineEdit()
        self.contact_phone.setPlaceholderText("(###)###-####")
        self.contact_phone.setInputMask("(000)000-0000")
        self.note = QLineEdit()
        self.note.setPlaceholderText("Optional Note")

        self.grid.addWidget(QLabel("Contact Name:"), 0, 0)
        self.grid.addWidget(self.contact_name, 0, 1)
        self.grid.addWidget(QLabel("Reseller ID:"), 0, 2)
        self.grid.addWidget(self.reseller_id, 0, 3)

        self.grid.addWidget(QLabel("Voice API Username:"), 1, 0)
        self.grid.addWidget(self.voice_user, 1, 1)
        self.grid.addWidget(QLabel("Voice API Password:"), 1, 2)
        self.grid.addWidget(self.voice_pass, 1, 3)

        self.grid.addWidget(QLabel("Fax API Username:"), 2, 0)
        self.grid.addWidget(self.msg_user, 2, 1)
        self.grid.addWidget(QLabel("Fax API Password:"), 2, 2)
        self.grid.addWidget(self.msg_pass, 2, 3)

        self.grid.addWidget(QLabel("Contact Email:"), 3, 0)
        self.grid.addWidget(self.contact_email, 3, 1)
        self.grid.addWidget(QLabel("Contact Phone:"), 3, 2)
        self.grid.addWidget(self.contact_phone, 3, 3)

        self.grid.addWidget(QLabel("Note:"), 4, 0)
        self.grid.addWidget(self.note, 4, 1, 1, 3)

        form_layout.addLayout(self.grid)

        self.button_bar = QHBoxLayout()
        self.save_btn = QPushButton("Save Reseller")
        self.save_btn.setObjectName("primary")
        self.save_btn.setFixedHeight(30)
        self.save_btn.clicked.connect(self.save_reseller)

        self.clear_form_btn = QPushButton("Clear Form")
        self.clear_form_btn.setObjectName("warning")
        self.clear_form_btn.setFixedHeight(30)
        self.clear_form_btn.setFixedWidth(100)
        self.clear_form_btn.clicked.connect(self.clear_form)

        self.delete_btn = QPushButton("Delete Reseller")
        self.delete_btn.setObjectName("danger")
        self.delete_btn.setFixedHeight(30)
        self.delete_btn.clicked.connect(self.delete_reseller)

        self.button_bar.addStretch()
        self.button_bar.addWidget(self.clear_form_btn)
        self.button_bar.addWidget(self.delete_btn)
        self.button_bar.addWidget(self.save_btn)
        form_layout.addLayout(self.button_bar)

        self.layout.addWidget(form_frame)

        self.table = QTableWidget(0, 5)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setHorizontalHeaderLabels(
            ["Reseller ID", "Contact", "Email", "Phone", "Note"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.verticalHeader().setVisible(False)
        self.table.setAlternatingRowColors(True)
        self.table.cellDoubleClicked.connect(self.populate_form)

        header = self.table.horizontalHeader()
        header.setStretchLastSection(True)
        for i in range(5):
            header.setSectionResizeMode(i, QHeaderView.Stretch)

        filter_row = QHBoxLayout()
        self.filter_inputs = []
        for i in range(5):
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(
                f"Filter {self.table.horizontalHeaderItem(i).text()}"
            )
            line_edit.textChanged.connect(self.apply_filters)
            line_edit.setFixedHeight(28)
            self.filter_inputs.append(line_edit)
            filter_row.addWidget(line_edit)
        self.layout.addLayout(filter_row)
        self.layout.addWidget(self.table)
        self.api = ApiClient()
        # Initial loading is controlled by MainWindow after connectivity is confirmed.
        # self.load_resellers()

    def load_resellers(self):
        self.table.setSortingEnabled(False)  # <-- critical
        self.table.setRowCount(0)
        try:
            # Use bulk wrapper (currently wraps list_resellers) for consistency with update_all_{x}
            records = self.api.update_all_resellers()
        except Exception:
            # Silent failure on initial listing; main banner in the MainWindow indicates connectivity.
            self.table.setSortingEnabled(True)
            return
        for record in records:
            rid = record.get("reseller_id")
            blob = record.get("encrypted_blob")
            if not rid or not blob:
                continue
            try:
                data = _decrypt_blob_local(rid, blob)
            except Exception as e:
                QMessageBox.warning(
                    self, "Decrypt Error", f"Failed to load reseller {rid}: {e}"
                )
                continue

            contact = data.get("contact_name", "")
            email = data.get("contact_email", "")
            phone = data.get("contact_phone", "")
            note = data.get("note", "")

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(rid)))
            self.table.setItem(row, 1, QTableWidgetItem(str(contact)))
            self.table.setItem(row, 2, QTableWidgetItem(str(email)))
            self.table.setItem(row, 3, QTableWidgetItem(str(phone)))
            self.table.setItem(row, 4, QTableWidgetItem(str(note)))

        self.table.setSortingEnabled(True)

    def save_reseller(self):
        rid = self.reseller_id.text().strip()
        if not rid.isdigit():
            QMessageBox.warning(self, "Invalid Input", "Reseller ID must be numeric.")
            return

        required = [
            self.voice_user.text(),
            self.voice_pass.text(),
            self.msg_user.text(),
            self.msg_pass.text(),
            self.contact_name.text(),
            self.contact_email.text(),
            self.contact_phone.text(),
        ]
        if not all(f.strip() for f in required):
            QMessageBox.warning(
                self, "Missing Fields", "All fields except Notes must be filled."
            )
            return

        payload = {
            "voice_api_user": self.voice_user.text().strip(),
            "voice_api_password": self.voice_pass.text().strip(),
            "msg_api_user": self.msg_user.text().strip(),
            "msg_api_password": self.msg_pass.text().strip(),
            "contact_name": self.contact_name.text().strip(),
            "contact_email": self.contact_email.text().strip(),
            "contact_phone": self.contact_phone.text().strip(),
            "note": self.note.text().strip(),
        }

        if self.api.save_reseller(rid, payload):
            QMessageBox.information(
                self, "Saved", f"Encrypted record for reseller {rid} saved."
            )
            self.clear_form()
            self.load_resellers()
        else:
            QMessageBox.warning(self, "Error", "Failed to save reseller.")

    def delete_reseller(self):
        rid = self.reseller_id.text().strip()
        if not rid:
            QMessageBox.warning(self, "Missing ID", "Enter a Reseller ID to delete.")
            return

        if self.api.delete_reseller(rid):
            QMessageBox.information(self, "Deleted", f"Reseller {rid} removed.")
        else:
            QMessageBox.information(self, "Not Found", f"Reseller {rid} not found.")
        self.clear_form()
        self.load_resellers()

    def clear_form(self):
        for field in [
            self.reseller_id,
            self.voice_user,
            self.voice_pass,
            self.msg_user,
            self.msg_pass,
            self.contact_name,
            self.contact_email,
            self.contact_phone,
            self.note,
        ]:
            field.clear()

    def populate_form(self, row, column):
        rid = self.table.item(row, 0).text()
        blob = self.api.get_reseller_blob(rid)
        if not blob:
            QMessageBox.warning(
                self, "Error", "No encrypted data found for this reseller."
            )
            return

        try:
            data = _decrypt_blob_local(rid, blob)
            self.reseller_id.setText(rid)
            self.voice_user.setText(data.get("voice_api_user", ""))
            self.voice_pass.setText(data.get("voice_api_password", ""))
            self.msg_user.setText(data.get("msg_api_user", ""))
            self.msg_pass.setText(data.get("msg_api_password", ""))
            self.contact_name.setText(data.get("contact_name", ""))
            self.contact_email.setText(data.get("contact_email", ""))
            self.contact_phone.setText(data.get("contact_phone", ""))
            self.note.setText(data.get("note", ""))
        except Exception as e:
            QMessageBox.warning(self, "Decryption Error", f"Failed to decrypt: {e}")
