import json

from PyQt5.QtCore import QEvent, Qt
from PyQt5.QtGui import QColor
from PyQt5.QtWidgets import (QApplication, QCheckBox, QComboBox, QHBoxLayout,
                             QHeaderView, QLabel, QPushButton, QSizePolicy,
                             QSplitter, QTableWidget, QTableWidgetItem,
                             QTextEdit, QVBoxLayout, QWidget)

from core.api_client import ApiClient


class LogViewerTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout()
        self.setObjectName("panel")
        self.setLayout(self.layout)

        self.advanced_mode = False

        # --- Filter Controls ---
        self.filter_row = QHBoxLayout()

        self.collection_dropdown = QComboBox()
        self.collection_dropdown.addItems(["access_logs", "audit_logs"])
        self.collection_dropdown.currentIndexChanged.connect(
            self.handle_collection_change
        )

        self.event_type_dropdown = QComboBox()
        self.event_type_dropdown.addItems(["<All>"])
        self.event_type_dropdown.currentIndexChanged.connect(
            self.handle_event_type_change
        )

        self.refresh_btn = QPushButton("Refresh Events")
        self.refresh_btn.setObjectName("refreshButton")
        self.refresh_btn.clicked.connect(self.load_logs)

        self.mode_toggle = QCheckBox("Advanced View")
        self.mode_toggle.stateChanged.connect(self.toggle_mode)

        self.filter_row.addWidget(QLabel("Log Collection:"))
        self.filter_row.addWidget(self.collection_dropdown)
        self.filter_row.addWidget(QLabel("Event Type:"))
        self.filter_row.addWidget(self.event_type_dropdown)
        self.filter_row.addWidget(self.refresh_btn)
        self.filter_row.addWidget(self.mode_toggle)

        self.layout.addLayout(self.filter_row)

        self.splitter = QSplitter(Qt.Vertical)

        self.table = QTableWidget()
        self.table.setObjectName("logTable")
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        # Provide object names for headers to allow stylesheet targeting
        self.table.horizontalHeader().setObjectName("logTableHeader")
        self.table.verticalHeader().setObjectName("logTableVHeader")
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.cellClicked.connect(self.display_payload)
        self.splitter.addWidget(self.table)

        self.payload_view = QTextEdit()
        self.payload_view.setObjectName("payloadView")
        self.payload_view.setReadOnly(True)
        self.payload_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.splitter.addWidget(self.payload_view)

        self.copy_btn = QPushButton("Copy Payload")
        self.copy_btn.setObjectName("primary")
        self.copy_btn.clicked.connect(self.copy_payload)
        self.layout.addWidget(self.copy_btn)

        self.splitter.setSizes([600, 200])
        self.layout.addWidget(self.splitter)

        # Recolor rows when the application's theme property changes
        QApplication.instance().installEventFilter(self)

        self.configure_table()
        # Defer data loading until MainWindow confirms FRAAPI connectivity.
        self.api = ApiClient()

    def configure_table(self):
        self.table.clear()
        # Ensure core table naming and behaviors after clear
        self.table.setAlternatingRowColors(True)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setObjectName("logTableHeader")
        self.table.verticalHeader().setObjectName("logTableVHeader")
        if self.advanced_mode:
            self.table.setColumnCount(8)
            self.table.setHorizontalHeaderLabels(
                [
                    "Timestamp",
                    "Event Type",
                    "Domain UUID",
                    "Device",
                    "IP",
                    "Actor",
                    "Object",
                    "Note",
                ]
            )
        else:
            self.table.setColumnCount(4)
            self.table.setHorizontalHeaderLabels(
                ["Timestamp", "Event Type", "Actor", "Note"]
            )
        self.table.setRowCount(0)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def toggle_mode(self):
        self.advanced_mode = self.mode_toggle.isChecked()
        self.configure_table()
        self.load_logs()

    def get_event_types(self, collection_name):
        try:
            types = self.api.get_log_event_types(collection_name)
            return sorted(types)
        except Exception:
            return []

    def load_logs(self):
        self.table.setRowCount(0)
        self.payload_view.clear()

        collection_name = self.collection_dropdown.currentText()
        event_filter = self.event_type_dropdown.currentText()

        try:
            self.entries = self.api.update_all_logs(
                collection_name,
                None if event_filter == "<All>" else event_filter,
                limit=200,
            )
        except Exception:
            self.entries = []

        for row, entry in enumerate(self.entries):
            self.table.insertRow(row)

            payload = entry.get("object", {}).get("payload", {})
            is_empty_payload = not payload
            event_type = entry.get("event_type", "").lower()

            if self.advanced_mode:
                self.table.setItem(row, 0, QTableWidgetItem(entry.get("timestamp", "")))
                self.table.setItem(
                    row, 1, QTableWidgetItem(entry.get("event_type", ""))
                )
                self.table.setItem(
                    row, 2, QTableWidgetItem(entry.get("domain_uuid", ""))
                )
                self.table.setItem(row, 3, QTableWidgetItem(entry.get("device_id", "")))
                self.table.setItem(row, 4, QTableWidgetItem(entry.get("source_ip", "")))
                self.table.setItem(
                    row, 5, QTableWidgetItem(self.fmt_actor(entry.get("actor")))
                )
                self.table.setItem(
                    row, 6, QTableWidgetItem(self.fmt_object(entry.get("object")))
                )
                self.table.setItem(row, 7, QTableWidgetItem(entry.get("note", "")))
            else:
                self.table.setItem(row, 0, QTableWidgetItem(entry.get("timestamp", "")))
                self.table.setItem(
                    row, 1, QTableWidgetItem(entry.get("event_type", ""))
                )
                self.table.setItem(
                    row, 2, QTableWidgetItem(self.fmt_actor(entry.get("actor")))
                )
                self.table.setItem(row, 3, QTableWidgetItem(entry.get("note", "")))

            theme = QApplication.instance().property("fra_theme") or "light"
            dark = theme == "dark"

            # Coloring logic
            if dark:
                bg_color = QColor("#2a2f3a")  # default dark row
                if not is_empty_payload:
                    bg_color = QColor("#244024")  # green-ish dark
                if "delete" in event_type:
                    bg_color = QColor("#402424")  # red-ish dark
                elif "fail" in event_type or "error" in event_type:
                    bg_color = QColor("#403824")  # amber-ish dark
            else:
                bg_color = QColor("#fdfdfd")  # default light row
                if not is_empty_payload:
                    bg_color = QColor("#e9f6e9")
                if "delete" in event_type:
                    bg_color = QColor("#ffecec")
                elif "fail" in event_type or "error" in event_type:
                    bg_color = QColor("#fff4e5")

            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(bg_color)

    def recolor_rows(self):
        if not hasattr(self, "entries"):
            return
        theme = QApplication.instance().property("fra_theme") or "light"
        dark = theme == "dark"
        for row in range(self.table.rowCount()):
            if row >= len(self.entries):
                continue
            entry = self.entries[row]
            payload = entry.get("object", {}).get("payload", {})
            is_empty_payload = not payload
            event_type = (entry.get("event_type", "") or "").lower()

            if dark:
                bg_color = QColor("#2a2f3a")
                if not is_empty_payload:
                    bg_color = QColor("#244024")
                if "delete" in event_type:
                    bg_color = QColor("#402424")
                elif "fail" in event_type or "error" in event_type:
                    bg_color = QColor("#403824")
            else:
                bg_color = QColor("#fdfdfd")
                if not is_empty_payload:
                    bg_color = QColor("#e9f6e9")
                if "delete" in event_type:
                    bg_color = QColor("#ffecec")
                elif "fail" in event_type or "error" in event_type:
                    bg_color = QColor("#fff4e5")

            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setBackground(bg_color)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (
            QEvent.StyleChange,
            QEvent.PaletteChange,
            QEvent.ApplicationPaletteChange,
        ):
            self.recolor_rows()

    def eventFilter(self, obj, event):
        # Listen for dynamic property changes on the application, e.g., fra_theme toggle
        if (
            obj is QApplication.instance()
            and event.type() == QEvent.DynamicPropertyChange
        ):
            try:
                name = event.propertyName()
            except Exception:
                name = b""
            if name == b"fra_theme":
                self.recolor_rows()
        return False

    def handle_collection_change(self):
        collection_name = self.collection_dropdown.currentText()
        self.event_type_dropdown.clear()
        self.event_type_dropdown.addItems(
            ["<All>"] + self.get_event_types(collection_name)
        )
        self.load_logs()

    def handle_event_type_change(self):
        self.load_logs()

    def fmt_actor(self, actor_dict):
        if not actor_dict:
            return ""
        return f"{actor_dict.get('component', '')}.{actor_dict.get('function', '')}\n{actor_dict.get('request_id', '')}"

    def fmt_object(self, obj_dict):
        if not obj_dict:
            return ""
        return f"{obj_dict.get('type', '')}:{obj_dict.get('operation', '')}"

    def display_payload(self, row, column):
        if row < len(self.entries):
            payload = self.entries[row].get("object", {}).get("payload", {})
            try:
                text = json.dumps(payload, indent=2)
            except Exception:
                text = str(payload)
            self.payload_view.setText(text)

    def copy_payload(self):
        text = self.payload_view.toPlainText().strip()
        if text:
            from PyQt5.QtWidgets import QApplication

            QApplication.clipboard().setText(text)
