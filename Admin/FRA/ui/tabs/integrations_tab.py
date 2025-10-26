# Admin/FRA/ui/tabs/integrations_tab.py
from __future__ import annotations

import base64
from typing import Any, Dict, Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core.api_client import ApiClient


def _truncate_b64(s: str, head: int = 10, tail: int = 6) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    if len(s) <= head + tail + 3:
        return s
    return f"{s[:head]}...{s[-tail:]}"


class IntegrationsTab(QWidget):
    """
    FRA Admin Integrations Tab

    - Per-reseller configuration panel, starting with LibertyRx.
    - Allows operator to input Liberty vendor username/password to compute
      a Basic auth header value (base64 of "username:password"), and save it
      server-side for device retrieval. Raw credentials are NOT persisted client-side.
    - Displays a read-only preview (truncated) of the saved Basic b64 for the selected reseller.
    """

    def __init__(self):
        super().__init__()
        self.api: ApiClient = ApiClient()
        self._resellers: list[Dict[str, Any]] = []
        self._reseller_index_by_id: dict[str, int] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        # Panel container
        panel = QFrame(self)
        panel.setObjectName("panel")
        panel.setFrameShape(QFrame.StyledPanel)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(10, 10, 10, 10)
        panel_layout.setSpacing(10)

        # Reseller selector row
        sel_row = QHBoxLayout()
        sel_row.setSpacing(8)
        self.reseller_combo = QComboBox()
        self.reseller_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.reseller_combo.currentIndexChanged.connect(self._on_reseller_changed)
        sel_row.addWidget(QLabel("Reseller:"))
        sel_row.addWidget(self.reseller_combo, 1)
        panel_layout.addLayout(sel_row)

        # LibertyRx group
        self.liberty_group = QGroupBox("LibertyRx")
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        self.vendor_user = QLineEdit()
        self.vendor_user.setPlaceholderText("Vendor Username")
        self.vendor_user.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.vendor_pass = QLineEdit()
        self.vendor_pass.setPlaceholderText("Vendor Password")
        self.vendor_pass.setEchoMode(QLineEdit.Password)
        self.vendor_pass.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.basic_preview = QLineEdit()
        self.basic_preview.setReadOnly(True)
        self.basic_preview.setPlaceholderText("Computed Basic (read-only)")
        self.basic_preview.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.rotated_label = QLabel("")
        self.rotated_label.setObjectName("hint")

        form.addRow("Vendor Username:", self.vendor_user)
        form.addRow("Vendor Password:", self.vendor_pass)
        form.addRow("Computed Basic:", self.basic_preview)
        form.addRow("", self.rotated_label)

        btn_row = QHBoxLayout()
        self.btn_compute_save = QPushButton("Compute & Save")
        self.btn_compute_save.setObjectName("primary")
        self.btn_compute_save.clicked.connect(self._compute_and_save)
        self.btn_clear = QPushButton("Clear")
        self.btn_clear.setObjectName("warning")
        self.btn_clear.clicked.connect(self._clear_inputs)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_clear)
        btn_row.addWidget(self.btn_compute_save)

        form.addRow(btn_row)
        self.liberty_group.setLayout(form)
        panel_layout.addWidget(self.liberty_group)

        root.addWidget(panel)
        root.addStretch()

        # Initial load is driven by MainWindow when connectivity is established
        # but we can attempt optimistic load as well (silently ignore errors)
        try:
            self.load_resellers()
        except Exception:
            pass

    # ---- Life-cycle hooks wired by MainWindow ----
    def set_api(self, api: ApiClient):
        if isinstance(api, ApiClient):
            self.api = api

    def on_show(self):
        # Refresh resellers and current selection's saved state
        self.load_resellers()

    # ---- Data loading ----
    def load_resellers(self):
        try:
            records = self.api.update_all_resellers()
        except Exception:
            # Connectivity issues are handled at MainWindow level; don’t spam popups here
            return
        self._resellers = records or []
        self._reseller_index_by_id.clear()
        self._populate_reseller_combo()
        # Trigger state load for the current selection
        self._on_reseller_changed(self.reseller_combo.currentIndex())

    def _populate_reseller_combo(self):
        cur_id = self.current_reseller_id()
        self.reseller_combo.blockSignals(True)
        self.reseller_combo.clear()
        for idx, rec in enumerate(self._resellers):
            rid = str(rec.get("reseller_id") or "").strip()
            contact = str((rec.get("encrypted_blob") or {}).get("contact_name", ""))
            display = f"{rid} — {contact}" if contact else rid
            if rid:
                self._reseller_index_by_id[rid] = idx
                self.reseller_combo.addItem(display, rid)
        # Restore previous selection if possible
        if cur_id:
            new_idx = self.reseller_combo.findData(cur_id)
            if new_idx >= 0:
                self.reseller_combo.setCurrentIndex(new_idx)
        self.reseller_combo.blockSignals(False)

    def current_reseller_id(self) -> str:
        return str(self.reseller_combo.currentData() or "").strip()

    # ---- Actions ----
    def _on_reseller_changed(self, index: int):
        rid = self.current_reseller_id()
        self.basic_preview.clear()
        self.rotated_label.setText("")
        if not rid:
            return
        try:
            data = self.api.get_liberty_vendor_basic(rid)
        except Exception as e:
            # Non-fatal; show hint label
            self.rotated_label.setText("Could not load saved Liberty credentials.")
            return
        basic_b64 = (data or {}).get("basic_b64", "")
        rotated_at = (data or {}).get("rotated_at")
        self.basic_preview.setText(_truncate_b64(basic_b64))
        if rotated_at:
            self.rotated_label.setText(f"Saved/rotated at: {rotated_at}")
        else:
            self.rotated_label.setText("")

    def _compute_basic(self) -> Optional[str]:
        user = (self.vendor_user.text() or "").strip()
        pwd = (self.vendor_pass.text() or "").strip()
        if not user or not pwd:
            QMessageBox.warning(self, "Missing Fields", "Enter vendor username and password.")
            return None
        token = f"{user}:{pwd}".encode("utf-8")
        return base64.b64encode(token).decode("ascii")

    def _compute_and_save(self):
        rid = self.current_reseller_id()
        if not rid:
            QMessageBox.warning(self, "Select Reseller", "Please select a reseller.")
            return
        basic_b64 = self._compute_basic()
        if not basic_b64:
            return
        # Update preview immediately
        self.basic_preview.setText(_truncate_b64(basic_b64))
        try:
            ok = self.api.set_liberty_vendor_basic(rid, basic_b64)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Failed to save credentials: {e}")
            return
        if ok:
            QMessageBox.information(self, "Saved", f"Liberty vendor credentials saved for reseller {rid}.")
            # Clear password field for safety; leave username as convenience
            self.vendor_pass.clear()
            # Refresh rotated timestamp
            self._on_reseller_changed(self.reseller_combo.currentIndex())
        else:
            QMessageBox.warning(self, "Error", "Server rejected the credentials save request.")

    def _clear_inputs(self):
        self.vendor_user.clear()
        self.vendor_pass.clear()
        self.basic_preview.clear()
        self.rotated_label.setText("")
        # Optional: attempt to clear on server if endpoint exists
        rid = self.current_reseller_id()
        if not rid:
            return
        try:
            cleared = self.api.clear_liberty_vendor_basic(rid)
            if cleared:
                QMessageBox.information(self, "Cleared", f"Cleared saved Liberty credentials for reseller {rid}.")
        except Exception:
            # Silently ignore if endpoint not available in this sprint
            pass
