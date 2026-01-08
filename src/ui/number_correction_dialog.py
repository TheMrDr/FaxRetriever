import os
import re
import threading
from typing import Optional

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QMessageBox,
)

from core.app_state import app_state
from fax_io.sender import FaxSender
from utils.logging_utils import get_logger


class NumberCorrectionDialog(QDialog):
    """
    Modeless dialog prompting the user to correct an invalid/ambiguous destination number.
    Does not block the UI thread. Sends in a background thread when user clicks Send Now.

    Expected payload dict keys:
      - source: "crx" | "manual"
      - record_id: Optional[int]
      - original_number: str (raw as read from BTR or previous attempt)
      - suggested: Optional[str] (pre-filled digits if we have one)
      - file_path: str (absolute path to PDF to send)
    """

    send_completed = pyqtSignal(bool)

    def __init__(self, base_dir: str, payload: dict, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.payload = payload or {}
        self.log = get_logger("ui.number_correction")
        self.setWindowTitle("Correct Fax Number")
        self.setWindowModality(Qt.NonModal)
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self._build_ui()

    def _build_ui(self):
        v = QVBoxLayout(self)
        orig = str(self.payload.get("original_number") or "")
        suggested = str(self.payload.get("suggested") or "")
        file_path = str(self.payload.get("file_path") or "")

        v.addWidget(QLabel("The phone number from WinRx appears invalid or ambiguous."))
        v.addWidget(QLabel("Please verify the doctor's fax number in WinRx and correct it below if needed."))

        self.lbl_original = QLabel(f"Original: {self._pretty(orig)}")
        v.addWidget(self.lbl_original)

        h = QHBoxLayout()
        h.addWidget(QLabel("Destination:"))
        self.input_dest = QLineEdit()
        self.input_dest.setPlaceholderText("Enter corrected fax number")
        self.input_dest.setText(suggested or orig)
        h.addWidget(self.input_dest)
        v.addLayout(h)

        self.lbl_file = QLabel(f"PDF: {file_path if file_path else '(missing)'}")
        v.addWidget(self.lbl_file)

        # Buttons
        hb = QHBoxLayout()
        self.btn_view = QPushButton("View PDF")
        self.btn_send = QPushButton("Send Now")
        self.btn_cancel = QPushButton("Close")
        hb.addWidget(self.btn_view)
        hb.addStretch(1)
        hb.addWidget(self.btn_send)
        hb.addWidget(self.btn_cancel)
        v.addLayout(hb)

        self.btn_view.clicked.connect(self._on_view)
        self.btn_send.clicked.connect(self._on_send)
        self.btn_cancel.clicked.connect(self.close)

        # Disable send if file missing
        self.btn_send.setEnabled(bool(file_path and os.path.exists(file_path)))

    def _on_view(self):
        file_path = str(self.payload.get("file_path") or "")
        try:
            if file_path and os.path.exists(file_path):
                os.startfile(file_path)
            else:
                QMessageBox.information(self, "View PDF", "File not found.")
        except Exception:
            QMessageBox.information(self, "View PDF", "Unable to open the file.")

    def _normalize(self, phone_number: str, caller_id: str) -> str:
        digits = re.sub(r"\D", "", phone_number or "")
        cid = re.sub(r"\D", "", caller_id or "")
        area = None
        if len(cid) == 11 and cid.startswith("1"):
            area = cid[1:4]
        elif len(cid) == 10:
            area = cid[0:3]
        if len(digits) == 7 and area:
            digits = area + digits
        if len(digits) == 12 and digits.startswith("11"):
            digits = digits[1:]
        if len(digits) == 10:
            digits = "1" + digits
        return digits if (len(digits) == 11 and digits.startswith("1")) else ""

    def _on_send(self):
        # Avoid blocking UI: run in background thread
        file_path = str(self.payload.get("file_path") or "")
        if not (file_path and os.path.exists(file_path)):
            QMessageBox.information(self, "Send", "PDF file is missing; cannot send.")
            return
        raw = self.input_dest.text().strip()
        # Derive caller ID from app state
        caller_raw = app_state.device_cfg.selected_fax_number or (
            app_state.device_cfg.selected_fax_numbers[0] if app_state.device_cfg.selected_fax_numbers else (
                app_state.global_cfg.all_numbers[0] if app_state.global_cfg.all_numbers else ""
            )
        )
        normalized = self._normalize(raw, caller_raw)
        if not normalized:
            QMessageBox.information(self, "Send", "Please enter a valid fax number (NANP).")
            return

        def _run_send():
            ok = False
            try:
                ok = FaxSender.send_fax(self.base_dir, normalized, [file_path], include_cover=False)
            except Exception:
                ok = False
            def _finish():
                if ok:
                    QMessageBox.information(self, "Send", "Fax accepted by carrier.")
                    try:
                        self.send_completed.emit(True)
                    except Exception:
                        pass
                    self.close()
                else:
                    QMessageBox.information(self, "Send", "Send failed. Please try again later.")
                    try:
                        self.send_completed.emit(False)
                    except Exception:
                        pass
            # Re-enter GUI thread
            try:
                self.btn_send.setEnabled(True)
            except Exception:
                pass
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, _finish)

        # Disable send while running
        self.btn_send.setEnabled(False)
        t = threading.Thread(target=_run_send, daemon=True)
        t.start()

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