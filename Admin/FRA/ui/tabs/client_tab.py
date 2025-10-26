# Admin/licensing_server/ui/tabs/client_tab.py

import json
import random
import string

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFormLayout, QFrame, QHBoxLayout,
                             QHeaderView, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMenu, QMessageBox, QPushButton,
                             QSizePolicy, QSplitter, QTableWidget,
                             QTableWidgetItem, QVBoxLayout, QWidget)

from core.api_client import ApiClient


def _parse_reseller_id(fax_user: str) -> str:
    s = (fax_user or "").strip().lower()
    if not s:
        return ""
    domain_part = s.split("@", 1)[1] if "@" in s else s
    labels = [p for p in domain_part.split(".") if p]
    if len(labels) >= 3:
        return labels[-2]
    if len(labels) == 2:
        return labels[-1]
    return ""




def beautify_number(num: str) -> str:
    digits = "".join(filter(str.isdigit, num))
    if len(digits) != 11 or not digits.startswith("1"):
        return num
    return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"


class ClientTab(QWidget):
    def apply_filters(self):
        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, False)
            for col, line_edit in enumerate(self.filter_inputs):
                text = line_edit.text().strip().lower()
                item = self.table.item(row, col)
                if text and item and text not in item.text().lower():
                    self.table.setRowHidden(row, True)
                    break

    def __init__(self):
        super().__init__()
        self.setContentsMargins(10, 10, 10, 10)
        layout = QVBoxLayout()
        layout.setSpacing(0)
        self.setLayout(layout)

        self.splitter = QSplitter(Qt.Vertical)
        layout.addWidget(self.splitter)

        self.form_container = QWidget()
        self.form_container.setObjectName("panel")
        self.form_layout = QVBoxLayout()
        self.form_layout.setContentsMargins(6, 6, 6, 6)
        self.form_layout.setSpacing(6)
        self.form_container.setLayout(self.form_layout)

        self.table_container = QWidget()
        self.table_container.setObjectName("panel")
        self.table_layout = QVBoxLayout()
        self.table_layout.setContentsMargins(0, 0, 0, 0)
        self.table_container.setLayout(self.table_layout)

        self.splitter.addWidget(self.form_container)
        self.splitter.addWidget(self.table_container)
        self.splitter.setSizes([250, 600])

        self.build_input_area()
        self.build_table()
        self.api = ApiClient()
        # Initial loading is controlled by MainWindow after connectivity is confirmed.
        # self.load_clients()

    def clear_form(self):
        self.domain_input.clear()
        self.token_input.setText(self.generate_token())
        self.number_input.clear()
        self.number_list.clear()

    def build_input_area(self):
        title = QLabel("Client Registration")
        title.setObjectName("title")
        self.form_layout.addWidget(title)

        input_row = QHBoxLayout()
        self.domain_input = QLineEdit()
        self.domain_input.setPlaceholderText("client_domain.12345.service - No Extension")
        self.token_input = QLineEdit()
        self.token_input.setText(self.generate_token())
        self.token_input.setReadOnly(True)
        self.token_input.setToolTip("Auto-generated auth token")
        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(QIcon("images/refresh.png"))
        self.refresh_btn.setFixedSize(26, 26)
        self.refresh_btn.clicked.connect(
            lambda: self.token_input.setText(self.generate_token())
        )

        input_row.addWidget(QLabel("Client Domain:"))
        input_row.addWidget(self.domain_input)
        input_row.addWidget(QLabel("Auth Token:"))
        input_row.addWidget(self.token_input)
        input_row.addWidget(self.refresh_btn)
        self.form_layout.addLayout(input_row)

        self.number_input = QLineEdit()
        self.number_input.setInputMask("(000)000-0000;_")
        self.number_input.setPlaceholderText("Enter fax number")
        self.number_list = QListWidget()

        row = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.del_btn = QPushButton("Remove Selected")
        self.add_btn.clicked.connect(self.add_number)
        self.del_btn.clicked.connect(self.remove_selected)
        row.addWidget(QLabel("Fax Number:"))
        row.addWidget(self.number_input)
        row.addWidget(self.add_btn)
        row.addWidget(self.del_btn)

        self.form_layout.addLayout(row)
        self.form_layout.addWidget(self.number_list)

        btn_row = QHBoxLayout()
        self.save_btn = QPushButton("Save Client")
        self.save_btn.setObjectName("primary")
        self.save_btn.setFixedHeight(34)
        self.save_btn.clicked.connect(self.handle_add_client)

        self.clear_btn = QPushButton("Clear Form")
        self.clear_btn.setObjectName("danger")
        self.clear_btn.setFixedHeight(34)
        self.clear_btn.clicked.connect(self.clear_form)

        self.save_btn.setFixedWidth(int(self.width() * 0.75))
        self.clear_btn.setFixedWidth(int(self.width() * 0.25))

        # btn_row.addStretch()
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.clear_btn)
        self.form_layout.addLayout(btn_row)

    def add_number(self):
        raw = self.number_input.text().strip()
        if "_" in raw or len(raw) < 13:
            QMessageBox.warning(
                self, "Invalid Entry", "Please enter a complete 10-digit fax number."
            )
            return
        self.number_list.addItem(QListWidgetItem(raw))
        self.number_input.clear()

    def remove_selected(self):
        for item in self.number_list.selectedItems():
            self.number_list.takeItem(self.number_list.row(item))

    def get_numbers(self):
        return [
            "+1" + "".join(filter(str.isdigit, self.number_list.item(i).text()))
            for i in range(self.number_list.count())
        ]

    def build_table(self):
        refresh_bar = QHBoxLayout()
        refresh_button = QPushButton("Refresh Client List")
        refresh_button.setObjectName("refreshButton")
        refresh_button.setFixedHeight(28)
        refresh_button.clicked.connect(self.load_clients)
        refresh_bar.addStretch()
        refresh_bar.addWidget(refresh_button)
        self.table_layout.addLayout(refresh_bar)

        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            [
                "Client Domain",
                "Auth Token",
                "Fax Number",
                "Retriever Device",
                "Bearer Expiry",
                "Active",
                "UUID",
            ]
        )
        header = self.table.horizontalHeader()
        for i in range(6):
            header.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        header.setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.sortItems(0, Qt.AscendingOrder)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.setAlternatingRowColors(True)
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.cellDoubleClicked.connect(self.populate_form)
        filter_row = QHBoxLayout()
        self.filter_inputs = []
        for i in range(6):  # exclude UUID column
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(
                f"Filter {self.table.horizontalHeaderItem(i).text()}"
            )
            line_edit.textChanged.connect(self.apply_filters)
            line_edit.setFixedHeight(28)
            self.filter_inputs.append(line_edit)
            filter_row.addWidget(line_edit)
        self.table_layout.addLayout(filter_row)
        self.table_layout.addWidget(self.table)

    def generate_token(self) -> str:
        return f"{''.join(random.choices(string.digits, k=5))}-{''.join(random.choices(string.digits, k=5))}"

    def load_clients(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        try:
            # Prefer bulk endpoint to avoid N+1 calls; ApiClient falls back internally if unavailable
            clients = self.api.update_all_clients()
        except Exception:
            # Silent failure on initial listing; main banner in the MainWindow indicates connectivity.
            self.table.setSortingEnabled(True)
            return

        for doc in clients:
            fax_user = doc.get("fax_user", "")
            uuid = doc.get("domain_uuid", "")
            token = doc.get("authentication_token", "")
            active = doc.get("active", False)
            fax_numbers = doc.get("all_fax_numbers", [])
            retriever_map_raw = doc.get("retriever_assignments", {}) or {}
            # Use ONE dict for read/write to keep UI and commits consistent
            assignments = dict(retriever_map_raw)

            # Use aggregated fields if present; otherwise fall back to per-client calls
            if "known_devices" in doc:
                known_devices = doc.get("known_devices") or []
            else:
                try:
                    known_devices = self.api.get_known_devices(uuid)
                except Exception:
                    known_devices = []

            if "bearer_expires_at" in doc:
                expires = doc.get("bearer_expires_at") or "—"
            else:
                try:
                    cache = self.api.get_cached_bearer(fax_user)
                except Exception:
                    cache = None
                expires = cache.get("expires_at", "—") if cache else "—"

            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(fax_user))
            self.table.setItem(row, 1, QTableWidgetItem(token))

            fax_dropdown = QComboBox()
            fax_dropdown.setMinimumHeight(28)
            beautified = [beautify_number(n) for n in fax_numbers]

            retriever_dropdown = QComboBox()
            retriever_dropdown.setMinimumHeight(28)

            # Avoid spurious signals during initial population
            fax_dropdown.blockSignals(True)
            retriever_dropdown.blockSignals(True)

            fax_dropdown.addItems(beautified)
            retriever_dropdown.addItem("*Unassigned*")
            retriever_dropdown.addItems(known_devices or [])

            def normalize_e164(num_text: str) -> str:
                digits = "".join(filter(str.isdigit, num_text))
                # If already 11 digits starting with '1' → +1XXXXXXXXXX
                if len(digits) == 11 and digits.startswith("1"):
                    return "+" + digits
                # If 10 digits → assume US and prefix +1
                if len(digits) == 10:
                    return "+1" + digits
                # Fallback: if original already had '+', keep '+digits'
                return "+" + digits if digits else num_text.strip()

            def load_assignment_into_dropdown(
                fax_dropdown=fax_dropdown,
                retriever_dropdown=retriever_dropdown,
                assignments=assignments,
                normalize_e164=normalize_e164,
            ):
                current_fax = normalize_e164(fax_dropdown.currentText())
                saved_dev = assignments.get(current_fax, "")
                was = retriever_dropdown.blockSignals(True)
                if not saved_dev:
                    retriever_dropdown.setCurrentIndex(0)  # "*Unassigned*"
                else:
                    idx = retriever_dropdown.findText(saved_dev)
                    retriever_dropdown.setCurrentIndex(idx if idx >= 0 else 0)
                retriever_dropdown.blockSignals(was)

            def persist_retriever_change(
                fax_dropdown=fax_dropdown,
                retriever_dropdown=retriever_dropdown,
                assignments=assignments,
                fax_user=fax_user,
                normalize_e164=normalize_e164,
            ):
                current_fax = normalize_e164(fax_dropdown.currentText())
                selected_dev = retriever_dropdown.currentText()
                value = "" if selected_dev == "*Unassigned*" else selected_dev
                assignments[current_fax] = value
                try:
                    self.api.update_assignments(fax_user, assignments)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Connection Error",
                        f"Failed to update assignments. FRAAPI unreachable?\n\nDetails: {e}",
                    )

            # Wire events AFTER initial sync
            fax_dropdown.blockSignals(False)
            retriever_dropdown.blockSignals(False)

            fax_dropdown.currentIndexChanged.connect(
                lambda _idx, f=load_assignment_into_dropdown: f()
            )
            retriever_dropdown.currentIndexChanged.connect(
                lambda _idx, p=persist_retriever_change: p()
            )

            # Initial sync for the first fax
            load_assignment_into_dropdown()

            self.table.setCellWidget(row, 2, fax_dropdown)
            self.table.setCellWidget(row, 3, retriever_dropdown)
            self.table.setItem(row, 4, QTableWidgetItem(expires))
            self.table.setItem(row, 5, QTableWidgetItem("Yes" if active else "No"))
            self.table.setItem(row, 6, QTableWidgetItem(uuid))

        self.table.setColumnHidden(6, True)
        self.table.setSortingEnabled(True)

    def handle_add_client(self):
        domain = self.domain_input.text().strip().lower()
        # Remove any extension@ prefix if provided by the operator
        if "@" in domain:
            domain = domain.split("@", 1)[1]
        token = self.token_input.text().strip().upper()

        if not domain or not token:
            QMessageBox.warning(
                self, "Missing Input", "Please provide both domain and token."
            )
            return

        fax_numbers = [
            "+1" + "".join(filter(str.isdigit, self.number_list.item(i).text()))
            for i in range(self.number_list.count())
        ]
        if not fax_numbers:
            QMessageBox.warning(
                self, "Missing Fax Numbers", "Please add at least one fax number."
            )
            return

        try:
            domain_uuid = self.api.save_client(domain, token, fax_numbers)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Connection Error",
                f"Failed to save client. FRAAPI unreachable?\n\nDetails: {e}",
            )
            return
        QMessageBox.information(
            self, "Success", f"Client '{domain}' added.\nUUID: {domain_uuid}"
        )

        self.clear_form()
        self.load_clients()

    def show_context_menu(self, pos: QPoint):
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        domain = self.table.item(row, 0).text()
        domain_uuid = self.table.item(row, 6).text()

        menu = QMenu()
        copy_user = menu.addAction("Copy Fax User")
        copy_token = menu.addAction("Copy Token")
        activate = menu.addAction("Toggle Active")
        delete = menu.addAction("Delete Client")

        action = menu.exec_(self.table.viewport().mapToGlobal(pos))


        if action == activate:
            try:
                ok = self.api.toggle_client_active(domain_uuid)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Connection Error",
                    f"Failed to toggle active. FRAAPI unreachable?\n\nDetails: {e}",
                )
                ok = False
            if ok:
                QMessageBox.information(
                    self, "Toggled", f"Client '{domain}' active status changed."
                )
            else:
                QMessageBox.warning(
                    self, "Error", f"Could not update client '{domain}'"
                )
            self.load_clients()

        elif action == copy_user:
            QApplication.clipboard().setText(domain)
            QMessageBox.information(
                self, "Fax User Copied", f"Fax user '{domain}' copied to clipboard."
            )

        elif action == copy_token:
            token = self.table.item(row, 1).text()
            QApplication.clipboard().setText(token)
            QMessageBox.information(
                self, "Token Copied", f"Token for '{domain}' copied to clipboard."
            )

        elif action == delete:
            confirm = QMessageBox.question(
                self,
                "Confirm Delete",
                f"Delete client '{domain}'?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm == QMessageBox.Yes:
                try:
                    ok = self.api.delete_client(domain_uuid)
                except Exception as e:
                    QMessageBox.warning(
                        self,
                        "Connection Error",
                        f"Failed to delete client. FRAAPI unreachable?\n\nDetails: {e}",
                    )
                    ok = False
                if ok:
                    QMessageBox.information(
                        self, "Deleted", f"Client '{domain}' removed."
                    )
                else:
                    QMessageBox.warning(
                        self, "Error", f"Could not delete client '{domain}'"
                    )
                self.load_clients()

    def populate_form(self, row, column):
        domain_item = self.table.item(row, 0)
        token_item = self.table.item(row, 1)
        uuid_item = self.table.item(row, 6)

        if not (domain_item and token_item and uuid_item):
            QMessageBox.warning(
                self, "Error", "One or more fields are missing in the selected row."
            )
            return

        domain = domain_item.text()
        token = token_item.text()
        uuid = uuid_item.text()

        self.domain_input.setText(domain)
        self.token_input.setText(token)
        self.number_list.clear()
        try:
            nums = self.api.get_fax_numbers(uuid)
        except Exception as e:
            QMessageBox.warning(
                self,
                "Connection Error",
                f"Failed to load fax numbers. FRAAPI unreachable?\n\nDetails: {e}",
            )
            nums = []
        for n in nums:
            self.number_list.addItem(QListWidgetItem(beautify_number(n)))
