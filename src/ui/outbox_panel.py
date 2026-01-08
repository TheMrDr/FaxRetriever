import os
from datetime import datetime
from typing import Dict, Any

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableWidget,
    QTableWidgetItem,
    QPushButton,
    QMessageBox,
    QFileDialog,
    QLabel,
)

from core.outbox_ledger import all_jobs, delete_job
from fax_io.sender import FaxSender
from utils.logging_utils import get_logger


class OutboxPanel(QWidget):
    """
    Dedicated Outbox view showing in-flight and terminal outbound fax jobs with recovery actions.

    Buckets (by status):
      - accepted (In-flight)
      - delivered (Success)
      - failed_delivery (Failed)
      - invalid_number (Needs correction)
      - quarantined (Failed after retries)
      - delivery_unknown (Timed out)

    Actions per row:
      - View PDF (open default viewer)
      - Open Folder
      - Retry (enabled only if a PDF file exists); allows editing destination via correction dialog upstream
      - Remove (terminal states only)
    """

    request_correction = pyqtSignal(dict)  # emitted to show number-correction dialog in UI layer

    def __init__(self, base_dir: str, app_state, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.app_state = app_state
        self.log = get_logger("ui.outbox")
        self._build_ui()
        self._timer = QTimer(self)
        self._timer.setInterval(45000)  # 45s refresh
        self._timer.timeout.connect(self.refresh)
        self._timer.start()

    def _build_ui(self):
        v = QVBoxLayout(self)
        head = QHBoxLayout()
        head.addWidget(QLabel("Outbox: in-flight and recent outbound jobs"))
        head.addStretch(1)
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh)
        head.addWidget(self.refresh_btn)
        v.addLayout(head)

        self.table = QTableWidget(0, 8, self)
        self.table.setHorizontalHeaderLabels([
            "Status",
            "Destination",
            "Caller",
            "Attempts",
            "Last Error",
            "File",
            "Accepted At",
            "Actions",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(self.table.SelectRows)
        self.table.setEditTriggers(self.table.NoEditTriggers)
        v.addWidget(self.table, 1)

    def refresh(self):
        try:
            jobs: Dict[str, Any] = all_jobs(self.base_dir) or {}
        except Exception:
            jobs = {}
        # Flatten and sort by accepted_at/created_at desc
        rows = []
        for key, job in jobs.items():
            st = str(job.get("status") or "queued")
            # Map to buckets: put accepted first
            rows.append((key, job))
        def sort_key(item):
            key, job = item
            ts = job.get("accepted_at") or job.get("created_at") or ""
            return ts
        rows.sort(key=sort_key, reverse=True)

        self.table.setRowCount(0)
        for key, job in rows:
            self._add_row(key, job)

    def _add_row(self, key: str, job: Dict[str, Any]):
        row = self.table.rowCount()
        self.table.insertRow(row)
        status = str(job.get("status") or "queued")
        dest = str(job.get("dest") or "")
        caller = str(job.get("caller") or "")
        attempts = str(job.get("attempts") or "0")
        last_error = str(job.get("last_error") or "")
        file_path = str(job.get("file") or "")
        acc = str(job.get("accepted_at") or "")

        self.table.setItem(row, 0, QTableWidgetItem(status))
        self.table.setItem(row, 1, QTableWidgetItem(self._pretty(dest)))
        self.table.setItem(row, 2, QTableWidgetItem(self._pretty(caller)))
        self.table.setItem(row, 3, QTableWidgetItem(attempts))
        self.table.setItem(row, 4, QTableWidgetItem(last_error))
        self.table.setItem(row, 5, QTableWidgetItem(file_path))
        self.table.setItem(row, 6, QTableWidgetItem(acc))

        # Actions widget
        actions = QWidget()
        h = QHBoxLayout(actions)
        h.setContentsMargins(0, 0, 0, 0)
        btn_view = QPushButton("View PDF")
        btn_open = QPushButton("Open Folder")
        btn_retry = QPushButton("Retry/Send")
        btn_remove = QPushButton("Remove")
        h.addWidget(btn_view)
        h.addWidget(btn_open)
        h.addWidget(btn_retry)
        h.addWidget(btn_remove)
        h.addStretch(1)
        self.table.setCellWidget(row, 7, actions)

        # Enable/disable by state
        terminal = status in {"delivered", "failed_delivery", "invalid_number", "delivery_unknown", "quarantined"}
        pdf_exists = bool(file_path and os.path.exists(file_path))
        # Retry is allowed for invalid_number, failed_delivery, quarantined; must have a PDF
        can_retry = status in {"invalid_number", "failed_delivery", "quarantined"} and pdf_exists
        btn_retry.setEnabled(can_retry)
        # Remove only for terminal states
        btn_remove.setEnabled(terminal)

        btn_view.clicked.connect(lambda _: self._on_view(file_path))
        btn_open.clicked.connect(lambda _: self._on_open_folder(file_path))
        btn_retry.clicked.connect(lambda _: self._on_retry(job, key))
        btn_remove.clicked.connect(lambda _: self._on_remove(key))

    def _on_view(self, file_path: str):
        try:
            if file_path and os.path.exists(file_path):
                os.startfile(file_path)  # Windows-only
            else:
                QMessageBox.information(self, "View PDF", "File not found.")
        except Exception:
            QMessageBox.information(self, "View PDF", "Unable to open the file.")

    def _on_open_folder(self, file_path: str):
        try:
            if file_path and os.path.exists(file_path):
                folder = os.path.dirname(file_path)
                os.startfile(folder)
            else:
                QMessageBox.information(self, "Open Folder", "File not found.")
        except Exception:
            QMessageBox.information(self, "Open Folder", "Unable to open the folder.")

    def _on_retry(self, job: Dict[str, Any], key: str):
        # Enforce: must have a PDF available for resend
        file_path = str(job.get("file") or "")
        if not (file_path and os.path.exists(file_path)):
            QMessageBox.information(self, "Retry", "PDF is not available for resend. Retry is blocked.")
            return
        # Ask UI layer to open correction dialog (modeless), prefilled with dest
        payload = {
            "source": job.get("type") or "manual",
            "record_id": job.get("record_id"),
            "original_number": job.get("dest") or "",
            "file_path": file_path,
            "suggested": job.get("dest") or "",
        }
        self.request_correction.emit(payload)

    def _on_remove(self, key: str):
        try:
            delete_job(self.base_dir, key)
            self.refresh()
        except Exception:
            pass

    @staticmethod
    def _pretty(n: str) -> str:
        d = "".join(ch for ch in (n or "") if ch.isdigit())
        if len(d) == 7:
            return f"{d[:3]}-{d[3:]}"
        if len(d) == 10:
            return f"({d[:3]}) {d[3:6]}-{d[6:]}"
        if len(d) == 11 and d.startswith('1'):
            return f"+1 ({d[1:4]}) {d[4:7]}-{d[7:]}"
        return n or ""