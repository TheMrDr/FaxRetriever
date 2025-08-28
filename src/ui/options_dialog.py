# /ui/options_dialog.py

import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta
import jwt

import requests
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtPrintSupport import QPrinterInfo, QPrinter, QPrintDialog
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QSpinBox, QComboBox, QCheckBox, QPushButton,
    QGroupBox, QRadioButton, QButtonGroup, QInputDialog, QMessageBox,
    QWidget, QListWidget, QListWidgetItem, QDialogButtonBox, QFileDialog
)

from core.config_loader import global_config, device_config
from core.license_client import initialize_session, retrieve_skyswitch_token
from utils.logging_utils import get_logger
from integrations.computer_rx import CRxIntegration2
from ui.busy import BusyDialog

SAFETY_BUFFER_MINUTES = 5

def format_auth_token(raw: str) -> str:
    digits = ''.join(filter(str.isdigit, raw))
    if len(digits) != 10:
        return raw
    return f"{digits[:5]}-{digits[5:]}"

def _ts_is_future_iso(ts: str, buffer_minutes: int = SAFETY_BUFFER_MINUTES) -> bool:
    if not ts:
        return False
    try:
        dt = datetime.fromisoformat(ts)
        return dt > (datetime.now(timezone.utc) + timedelta(minutes=buffer_minutes))
    except Exception:
        return False

def _jwt_is_valid(token: str) -> bool:
    if not token:
        return False
    try:
        decoded = jwt.decode(token, options={"verify_signature": False})
        exp = decoded.get("exp")
        if not exp:
            return False
        return datetime.now(timezone.utc).timestamp() + (SAFETY_BUFFER_MINUTES * 60) < float(exp)
    except Exception:
        return False


class OptionsDialog(QDialog):
    def __init__(self, base_dir, app_state, main_window=None):
        super().__init__(main_window)
        self.setWindowTitle("Options")
        self.base_dir = base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setFixedSize(900, 450)
        self.setModal(True)

        self.log = get_logger("options_dialog")
        self.app_state = app_state
        self.main_window = main_window
        # Attention flash state for Account section
        self._account_flash_done = False
        self._account_flash_timer = None

        layout = QVBoxLayout(self)
        layout.addLayout(self._build_header())

        content = QHBoxLayout()
        content.addWidget(self._build_left_column(), 1)
        content.addWidget(self._build_right_column(), 1)
        layout.addLayout(content)

        layout.addLayout(self._build_buttons())

        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    def _build_header(self):
        header = QVBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        title = QLabel("<b style='font-size: 16pt'>FaxRetriever</b>")
        subtitle = QLabel("<b style='font-size: 10pt'>developed by Clinic Networking, LLC</b>")
        title.setAlignment(Qt.AlignCenter)
        subtitle.setAlignment(Qt.AlignCenter)
        header.addWidget(title)
        header.addWidget(subtitle)
        return header

    def _build_left_column(self):
        left = QVBoxLayout()
        left.addWidget(self._retrieval_group())
        return self._wrap_group(left)

    def _build_right_column(self):
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addWidget(self._logging_section())
        right.addWidget(self._integrations_section())
        right.addWidget(self._account_section())
        return self._wrap_group(right)

    def _wrap_group(self, layout):
        wrapper = QWidget()
        wrapper.setLayout(layout)
        return wrapper

    def _build_buttons(self):
        row = QHBoxLayout()
        row.addStretch()
        save = QPushButton("Save")
        cancel = QPushButton("Cancel")
        save.clicked.connect(self._save_settings)
        cancel.clicked.connect(self.reject)
        row.addWidget(save)
        row.addWidget(cancel)
        return row

    def _retrieval_group(self):
        group = QGroupBox("Fax Retrieval Settings")
        layout = QVBoxLayout()
        layout.setSpacing(8)


        polling_row = QHBoxLayout()
        polling_row.addWidget(QLabel("Polling Frequency (minutes):"))
        self.polling_frequency_spinbox = QSpinBox()
        self.polling_frequency_spinbox.setRange(5, 60)
        self.polling_frequency_spinbox.setValue(device_config.get("Fax Options", "polling_frequency", 15) or 15)
        polling_row.addWidget(self.polling_frequency_spinbox)
        layout.addLayout(polling_row)

        layout.addWidget(QLabel("Download Format:"))
        download_format_row = QHBoxLayout()
        self.download_pdf_radio = QRadioButton("PDF")
        self.download_jpg_radio = QRadioButton("JPG")
        self.download_both_radio = QRadioButton("Both")
        download_format_row.addWidget(self.download_pdf_radio)
        download_format_row.addWidget(self.download_jpg_radio)
        download_format_row.addWidget(self.download_both_radio)
        layout.addLayout(download_format_row)

        method = (device_config.get("Fax Options", "download_method", "PDF") or "PDF").lower()
        getattr(self, f"download_{method}_radio").setChecked(True)

        format_group = QButtonGroup()
        for rb in [self.download_pdf_radio, self.download_jpg_radio, self.download_both_radio]:
            format_group.addButton(rb)

        layout.addWidget(QLabel("File Naming:"))
        naming_format_row = QHBoxLayout()
        self.naming_cid_radio = QRadioButton("Use CID-DDMM-HHMM")
        self.naming_faxid_radio = QRadioButton("Use Fax ID")
        naming_format_row.addWidget(self.naming_cid_radio)
        naming_format_row.addWidget(self.naming_faxid_radio)
        layout.addLayout(naming_format_row)

        self.naming_group = QButtonGroup()
        self.naming_group.addButton(self.naming_cid_radio)
        self.naming_group.addButton(self.naming_faxid_radio)
        self.naming_cid_radio.setChecked(
            (device_config.get("Fax Options", "file_name_format", "cid") or "").lower() == "cid")

        # Before the print_row widgets
        self.selected_printer_label = QLabel(device_config.get("Fax Options", "printer_name", ""))
        self.selected_printer_label.setStyleSheet("padding-left: 10px; color: #444;")

        self.print_checkbox = QCheckBox("Print Faxes")
        self.print_checkbox.setChecked((self.app_state.device_cfg.print_faxes or "").lower() == "yes")
        self.print_checkbox.stateChanged.connect(self._handle_print_checkbox_toggle)

        print_row = QHBoxLayout()
        print_row.addWidget(self.print_checkbox)
        print_row.addWidget(self.selected_printer_label)
        print_row.addStretch()

        layout.addLayout(print_row)

        # Notifications + Close to Tray row
        notif_row = QHBoxLayout()
        self.notifications_checkbox = QCheckBox("Enable Notifications")
        self.notifications_checkbox.setChecked(((self.app_state.device_cfg.notifications_enabled or "Yes").lower() == "yes"))
        notif_row.addWidget(self.notifications_checkbox)
        self.close_to_tray_checkbox = QCheckBox("Close to Tray")
        self.close_to_tray_checkbox.setChecked(((self.app_state.device_cfg.close_to_tray or "No").lower() == "yes"))
        notif_row.addWidget(self.close_to_tray_checkbox)
        notif_row.addStretch()
        layout.addLayout(notif_row)

        # Start with System row
        start_row = QHBoxLayout()
        self.start_with_system_checkbox = QCheckBox("Start with System")
        self.start_with_system_checkbox.setChecked(((self.app_state.device_cfg.start_with_system or "No").lower() == "yes"))
        start_row.addWidget(self.start_with_system_checkbox)
        start_row.addStretch()
        layout.addLayout(start_row)
        
        
        # Archival is always enabled; provide only server retention selector
        archive_row = QHBoxLayout()
        archive_row.addWidget(QLabel("Server Retention:"))
        
        self.retention_input = QComboBox()
        self.retention_input.addItems(["15", "30", "60", "90", "180", "365"])
        # Coerce any previous invalid/legacy values to a safe bound
        try:
            cur_val = int(self.app_state.device_cfg.archive_duration or 365)
            if cur_val > 365:
                cur_val = 365
            if str(cur_val) not in ["15","30","60","90","180","365"]:
                cur_val = 365
            self.retention_input.setCurrentText(str(cur_val))
        except Exception:
            self.retention_input.setCurrentText("365")
        
        archive_row.addWidget(self.retention_input)
        archive_row.addWidget(QLabel("days"))
        archive_row.addStretch()
        layout.addLayout(archive_row)
        
        group.setLayout(layout)
        return group


    def _logging_section(self):
        group = QGroupBox("Logging")
        layout = QVBoxLayout()
        self.logging_combo = QComboBox()
        self.logging_combo.addItems(["Debug", "Info", "Warning", "Error", "Critical"])
        self.logging_combo.setCurrentText(self.app_state.global_cfg.logging_level or "Info")
        layout.addWidget(self.logging_combo)
        group.setLayout(layout)
        return group

    def _integrations_section(self):
        group = QGroupBox("Integrations")
        layout = QVBoxLayout()
        # Prefer device-level settings; fallback to global
        dev_settings = self.app_state.device_cfg.integration_settings or {}
        glob_settings = self.app_state.global_cfg.integration_settings or {}
        settings = {**glob_settings, **dev_settings}

        self.integration_checkbox = QCheckBox("Enable 3rd Party Integrations")
        self.integration_checkbox.setChecked((settings.get("enable_third_party", "") or "").lower() == "yes")
        layout.addWidget(self.integration_checkbox)

        # Software selector
        self.integration_combo = QComboBox()
        self.integration_combo.addItems(["None", "Computer-Rx"])
        self.integration_combo.setCurrentText(settings.get("integration_software", "") or "None")
        layout.addWidget(self.integration_combo)

        # WinRx path row (visible only for Computer-Rx)
        path_row = QHBoxLayout()
        self.winrx_path_input = QLineEdit(self.app_state.device_cfg.winrx_path or device_config.get("Integrations", "winrx_path", "") or "")
        self.winrx_path_input.setPlaceholderText("Select WinRx folder (contains FaxControl.btr)")
        browse_btn = QPushButton("Browse")
        def on_browse():
            path = QFileDialog.getExistingDirectory(self, "Select WinRx Folder")
            if path:
                self.winrx_path_input.setText(path)
        browse_btn.clicked.connect(on_browse)
        path_row.addWidget(QLabel("WinRx Path:"))
        path_row.addWidget(self.winrx_path_input, 1)
        path_row.addWidget(browse_btn)
        layout.addLayout(path_row)

        def toggle_visibility():
            enabled = self.integration_checkbox.isChecked()
            software = self.integration_combo.currentText()
            show = enabled and software == "Computer-Rx"
            for i in range(path_row.count()):
                w = path_row.itemAt(i).widget()
                if w:
                    w.setVisible(show)
        self.integration_checkbox.toggled.connect(lambda _: toggle_visibility())
        self.integration_combo.currentTextChanged.connect(lambda _: toggle_visibility())
        QTimer.singleShot(0, toggle_visibility)

        group.setLayout(layout)
        return group

    def _account_section(self):
        group = QGroupBox("Account")
        group.setObjectName("accountGroup")
        layout = QFormLayout()
        self.client_domain_input = QLineEdit(self.app_state.global_cfg.fax_user or "")
        self.client_domain_input.setPlaceholderText("100@sample.12345.service")
        self.auth_token_input = QLineEdit()
        self.auth_token_input.setEchoMode(QLineEdit.Password)
        self.auth_token_input.setText(self.app_state.global_cfg.authentication_token or "")
        self.auth_token_input.textChanged.connect(self._format_token_live)
        self.change_account_button = QPushButton("Change Account")
        self.change_account_button.clicked.connect(self.toggle_account_settings)
        self.change_account_button.setEnabled(False)
        layout.addRow("Fax User", self.client_domain_input)
        layout.addRow("Authentication Token", self.auth_token_input)
        layout.addRow(self.change_account_button)
        group.setLayout(layout)
        # Keep a reference for subtle attention cues
        self.account_group = group
        return group


    def _apply_saved_printer_settings(self, qprinter: QPrinter):
        try:
            settings = device_config.get("Fax Options", "printer_settings", {}) or {}
            # Basic settings mapping
            orient = settings.get("orientation")
            if orient == "Portrait":
                qprinter.setOrientation(QPrinter.Portrait)
            elif orient == "Landscape":
                qprinter.setOrientation(QPrinter.Landscape)
            duplex = settings.get("duplex")
            if duplex == "None":
                qprinter.setDuplex(QPrinter.DuplexNone)
            elif duplex == "LongSide":
                qprinter.setDuplex(QPrinter.DuplexLongSide)
            elif duplex == "ShortSide":
                qprinter.setDuplex(QPrinter.DuplexShortSide)
            color = settings.get("color_mode")
            if color == "Color":
                qprinter.setColorMode(QPrinter.Color)
            elif color == "GrayScale":
                qprinter.setColorMode(QPrinter.GrayScale)
            # Paper size may vary by driver; try common names
            paper = settings.get("paper_name")
            if paper:
                try:
                    from PyQt5.QtPrintSupport import QPrinterInfo as _QPI
                    # If the printer supports a default paper size mapping, we can attempt
                    pass
                except Exception:
                    pass
        except Exception:
            pass

    def _collect_printer_settings(self, qprinter: QPrinter) -> dict:
        try:
            settings = {
                "orientation": "Landscape" if qprinter.orientation() == QPrinter.Landscape else "Portrait",
            }
            # Duplex
            try:
                dp = qprinter.duplex()
                settings["duplex"] = (
                    "LongSide" if dp == QPrinter.DuplexLongSide else (
                        "ShortSide" if dp == QPrinter.DuplexShortSide else "None"
                    )
                )
            except Exception:
                settings["duplex"] = "None"
            # Color
            try:
                cm = qprinter.colorMode()
                settings["color_mode"] = "Color" if cm == QPrinter.Color else "GrayScale"
            except Exception:
                settings["color_mode"] = "Color"
            # Paper name (best-effort)
            try:
                settings["paper_name"] = str(qprinter.paperName()) if hasattr(qprinter, "paperName") else ""
            except Exception:
                settings["paper_name"] = ""
            return settings
        except Exception:
            return {}

    def _handle_print_checkbox_toggle(self, state):
        if state == Qt.Checked:
            # Initialize printer with previously selected device and settings if available
            qprinter = QPrinter(QPrinter.HighResolution)
            saved_printer = device_config.get("Fax Options", "printer_name", "") or ""
            if saved_printer:
                try:
                    qprinter.setPrinterName(saved_printer)
                except Exception:
                    pass
            self._apply_saved_printer_settings(qprinter)

            dlg = QPrintDialog(qprinter, self)
            dlg.setWindowTitle("Select Printer and Preferences")
            # Show the native Windows dialog
            if dlg.exec_() == QDialog.Accepted:
                try:
                    chosen = qprinter.printerName()
                except Exception:
                    chosen = ""
                if chosen:
                    self.selected_printer_label.setText(chosen)
                    device_config.set("Fax Options", "printer_name", chosen)
                    device_config.set("Fax Options", "printer_settings", self._collect_printer_settings(qprinter))
                else:
                    # If no printer picked, uncheck and clear
                    self.print_checkbox.setChecked(False)
                    self.selected_printer_label.setText("")
                    device_config.set("Fax Options", "printer_name", "")
                    device_config.set("Fax Options", "printer_settings", {})
            else:
                # User canceled selection; uncheck and clear
                self.print_checkbox.setChecked(False)
                self.selected_printer_label.setText("")
                device_config.set("Fax Options", "printer_name", "")
                device_config.set("Fax Options", "printer_settings", {})
        else:
            self.selected_printer_label.setText("")
            device_config.set("Fax Options", "printer_name", "")
            device_config.set("Fax Options", "printer_settings", {})

    def _format_token_live(self):
        raw = self.auth_token_input.text()
        formatted = format_auth_token(raw)
        if formatted != raw:
            self.auth_token_input.setText(formatted)

    def _ensure_startup_shortcut(self, enable: bool):
        try:
            startup = os.path.join(os.environ.get('APPDATA', ''), 'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup')
            if not startup or not os.path.isdir(startup):
                return
            link_path = os.path.join(startup, 'FaxRetriever.lnk')
            if not enable:
                try:
                    if os.path.exists(link_path):
                        os.remove(link_path)
                except Exception:
                    pass
                return

            # Determine target and arguments
            icon_path = os.path.join(self.base_dir, 'images', 'logo.ico')
            workdir = self.base_dir
            if getattr(sys, 'frozen', False):
                target = sys.executable
                args = ''
            else:
                # Prefer pythonw.exe if present to avoid console window
                pyw = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
                target = pyw if os.path.exists(pyw) else sys.executable
                script = os.path.join(self.base_dir, 'main.py')
                args = f'"{script}"'

            # Escape for PowerShell single-quoted strings
            def esc(s: str) -> str:
                return (s or '').replace("'", "''")

            ps = (
                f"$ws = New-Object -ComObject WScript.Shell; "
                f"$lnk = $ws.CreateShortcut('{esc(link_path)}'); "
                f"$lnk.TargetPath = '{esc(target)}'; "
                f"$lnk.Arguments = '{esc(args)}'; "
                f"$lnk.WorkingDirectory = '{esc(workdir)}'; "
                f"$lnk.IconLocation = '{esc(icon_path)}'; "
                f"$lnk.Save()"
            )
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps], stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception:
            # Silently ignore failures
            pass

    def toggle_account_settings(self):
        response = QMessageBox.warning(
            self,
            "Warning",
            "Changing account settings may prevent the application from activating.\n"
            "Are you sure you want to proceed?",
            QMessageBox.Yes | QMessageBox.No
        )

        if response == QMessageBox.Yes:
            self.client_domain_input.setEnabled(True)
            self.auth_token_input.setEnabled(True)
            self.change_account_button.setEnabled(False)

    def _flash_account_attention(self):
        try:
            # Only flash once per dialog instance to avoid annoyance
            if getattr(self, "_account_flash_done", False):
                return
            if not hasattr(self, "account_group") or self.account_group is None:
                return

            self._account_flash_done = True

            # Prepare a short, subtle flash using border and title color
            highlight_a = (
                "QGroupBox#accountGroup { border: 2px solid #f1c40f; border-radius: 4px; margin-top: 6px; } "
                "QGroupBox#accountGroup::title { subcontrol-origin: margin; left: 8px; color: #d35400; }"
            )
            highlight_b = (
                "QGroupBox#accountGroup { border: 2px solid #e67e22; border-radius: 4px; margin-top: 6px; } "
                "QGroupBox#accountGroup::title { subcontrol-origin: margin; left: 8px; color: #e67e22; }"
            )
            base_style = self.account_group.styleSheet() or ""

            self._account_flash_timer = QTimer(self)
            self._account_flash_timer.setInterval(220)
            self._account_flash_count = 0

            def tick():
                try:
                    self._account_flash_count += 1
                    # Alternate between two highlight tones
                    if self._account_flash_count % 2 == 1:
                        self.account_group.setStyleSheet(highlight_a)
                    else:
                        self.account_group.setStyleSheet(highlight_b)
                    # Run for ~6 ticks (~1.3s), then restore
                    if self._account_flash_count >= 6:
                        self._account_flash_timer.stop()
                        self.account_group.setStyleSheet(base_style)
                except Exception:
                    # On any styling error, stop and restore
                    try:
                        self._account_flash_timer.stop()
                        self.account_group.setStyleSheet(base_style)
                    except Exception:
                        pass

            self._account_flash_timer.timeout.connect(tick)
            # Start shortly after dialog shows to ensure layout is ready
            QTimer.singleShot(50, self._account_flash_timer.start)
        except Exception:
            # Never block UI on cosmetic issues
            pass

    def _save_settings(self):
        try:
            # 0) Inputs
            client_domain = (self.client_domain_input.text() or "").strip()
            raw_token = (self.auth_token_input.text() or "").strip()
            formatted_token = format_auth_token(raw_token)
            # Full fax_user must be stored as-is (e.g., "100@sample.12345.service")
            # FRA will derive the domain portion by stripping the extension internally during /init
            # Retrieval enablement is configured via Setup Fax Retrieval in the main UI
            requested_mode = "sender"
            minutes = int(self.polling_frequency_spinbox.value())

            if not client_domain or not formatted_token:
                QMessageBox.warning(self, "Missing Input", "Fax User and Authentication Token are required.")
                return

            # 1) Persist UI choices immediately (write-through, no network)
            global_config.set("Account", "fax_user", client_domain)
            global_config.set("Account", "authentication_token", formatted_token)
            global_config.set("UserSettings", "logging_level", self.logging_combo.currentText())
            integration_settings = {
                "enable_third_party": "Yes" if self.integration_checkbox.isChecked() else "No",
                "integration_software": self.integration_combo.currentText()
            }
            global_config.set("Integrations", "integration_settings", integration_settings)
            # Mirror to device-level for runtime gating
            device_config.set("Integrations", "integration_settings", integration_settings)
            # Persist Computer-Rx WinRx path (device-level)
            try:
                winrx_path = self.winrx_path_input.text().strip() if hasattr(self, 'winrx_path_input') else ""
            except Exception:
                winrx_path = ""
            device_config.set("Integrations", "winrx_path", winrx_path)
            device_config.set("Account", "requested_retriever_mode", requested_mode)
            # Force effective runtime to sender at this stage
            device_config.set("Account", "retriever_mode", "sender")

            if self.download_pdf_radio.isChecked():
                device_config.set("Fax Options", "download_method", "PDF")
            elif self.download_jpg_radio.isChecked():
                device_config.set("Fax Options", "download_method", "JPG")
            else:
                device_config.set("Fax Options", "download_method", "Both")

            device_config.set("Fax Options", "file_name_format",
                              "faxid" if self.naming_faxid_radio.isChecked() else "cid")
            device_config.set("Fax Options", "polling_frequency", minutes)
            device_config.set("Fax Options", "print_faxes", "Yes" if self.print_checkbox.isChecked() else "No")
            device_config.set("Fax Options", "notifications_enabled", "Yes" if self.notifications_checkbox.isChecked() else "No")
            device_config.set("Fax Options", "close_to_tray", "Yes" if self.close_to_tray_checkbox.isChecked() else "No")
            device_config.set("Fax Options", "start_with_system", "Yes" if self.start_with_system_checkbox.isChecked() else "No")
            # Archival is always enabled; persist as Yes
            device_config.set("Fax Options", "archive_enabled", "Yes")
            device_config.set("Fax Options", "archive_duration", self.retention_input.currentText())

            global_config.save()
            device_config.save()

            # Apply Start with System shortcut
            try:
                self._ensure_startup_shortcut(self.start_with_system_checkbox.isChecked())
            except Exception:
                pass

            # 2) Decide network work using cached credentials
            jwt_cur = global_config.get("Token", "jwt_token", "")
            bearer_exp = global_config.get("Token", "bearer_token_expires_at", "")
            have_valid_jwt = _jwt_is_valid(jwt_cur)
            have_valid_bearer = _ts_is_future_iso(bearer_exp)

            # 3) Ensure JWT via license_client only if needed
            if not have_valid_jwt:
                with BusyDialog(self, "Initializing…"):
                    init_result = initialize_session(self.app_state, client_domain, formatted_token, mode="sender")
                if init_result.get("error"):
                    self.log.error(f"initialize_session failed: {init_result['error']}")
                    QMessageBox.critical(self, "Init Failed",
                                         f"Initialization error: {init_result['error']}")
                    return
                # license_client writes jwt_token, retriever_status, and validation_status to config/app_state

            # 4) Ensure bearer via license_client only if needed
            if not have_valid_bearer:
                with BusyDialog(self, "Retrieving token…"):
                    bearer_result = retrieve_skyswitch_token(self.app_state)
                if bearer_result.get("error"):
                    self.log.error(f"retrieve_skyswitch_token failed: {bearer_result['error']}")
                    QMessageBox.critical(self, "Token Error",
                                         f"Failed to retrieve bearer token: {bearer_result['error']}")
                    return

            # 5) Finalize persisted state
            global_config.set("Account", "validation_status", True)
            global_config.save()
            device_config.save()

            # 6) Refresh runtime + UI
            self.app_state.sync_from_config()
            self.change_account_button.setEnabled(True)
            self.app_state.device_cfg.polling_frequency = minutes

            if self.main_window:
                self.main_window._apply_operational_mode()
                if self.main_window.poll_bar:
                    self.main_window.poll_bar.interval_secs = minutes * 60
                    self.main_window.poll_bar.restart_progress()
                if self.main_window.status_bar:
                    self.main_window.status_bar.showMessage("Settings saved. Sender mode enabled.", 5000)
                # Update Send panel Caller ID numbers immediately if available
                try:
                    if hasattr(self.main_window, 'send_fax_panel') and getattr(self.main_window, 'send_fax_panel'):
                        panel = self.main_window.send_fax_panel
                        if hasattr(panel, 'refresh_caller_id_numbers'):
                            panel.refresh_caller_id_numbers()
                except Exception:
                    pass
                # One-time Computer-Rx first-run cleanup (if applicable)
                try:
                    CRxIntegration2.run_initial_cleanup_if_needed(self)
                except Exception:
                    pass
                # Trigger integrations if applicable
                try:
                    if hasattr(self.main_window, '_maybe_run_integrations'):
                        self.main_window._maybe_run_integrations()
                except Exception:
                    pass

            self.accept()

        except Exception as e:
            self.log.exception("Failed to save settings")
            QMessageBox.critical(self, "Error", f"Failed to save settings: {e}")

    @staticmethod
    def compute_effective_mode(requested_mode: str, retriever_status: str | None, jwt_valid: bool) -> str:
        # FRA rules override local wishes when known
        if retriever_status == "denied":
            return "sender"
        if retriever_status == "allowed":
            return "sender_receiver" if requested_mode == "sender_receiver" else "sender"
        # If we don't know yet (no init or no claims), be conservative
        return "sender" if not jwt_valid else ("sender_receiver" if requested_mode == "sender_receiver" else "sender")

    def load_state_into_form(self):
        naming = (self.app_state.device_cfg.file_name_format or "").lower()
        self.naming_faxid_radio.setChecked(naming == "faxid")
        self.naming_cid_radio.setChecked(naming == "cid")
        self.polling_frequency_spinbox.setValue(device_config.get("Fax Options", "polling_frequency", 15) or 15)
        self.selected_printer_label.setText(self.app_state.device_cfg.printer_name or "")
        self.print_checkbox.setChecked((self.app_state.device_cfg.print_faxes or "").lower() == "yes")
        self.notifications_checkbox.setChecked(((self.app_state.device_cfg.notifications_enabled or "Yes").lower() == "yes"))
        # New toggles
        try:
            self.close_to_tray_checkbox.setChecked(((self.app_state.device_cfg.close_to_tray or "No").lower() == "yes"))
        except Exception:
            pass
        try:
            self.start_with_system_checkbox.setChecked(((self.app_state.device_cfg.start_with_system or "No").lower() == "yes"))
        except Exception:
            pass
        self.retention_input.setCurrentText(self.app_state.device_cfg.archive_duration or "365")
        self.logging_combo.setCurrentText(self.app_state.global_cfg.logging_level or "Info")
        # Use device-level settings when available
        dev_settings = self.app_state.device_cfg.integration_settings or {}
        glob_settings = self.app_state.global_cfg.integration_settings or {}
        cur_enable = (dev_settings.get("enable_third_party") or glob_settings.get("enable_third_party") or "")
        self.integration_checkbox.setChecked((cur_enable or "").lower() == "yes")
        # Prefer device-level integration software
        dev_settings = self.app_state.device_cfg.integration_settings or {}
        glob_settings = self.app_state.global_cfg.integration_settings or {}
        cur_sw = (dev_settings.get("integration_software") or glob_settings.get("integration_software") or "None")
        self.integration_combo.setCurrentText(cur_sw)
        # WinRx path
        try:
            if hasattr(self, 'winrx_path_input'):
                self.winrx_path_input.setText(self.app_state.device_cfg.winrx_path or device_config.get("Integrations", "winrx_path", "") or "")
        except Exception:
            pass
        self.client_domain_input.setText(self.app_state.global_cfg.fax_user or "")
        self.auth_token_input.setText(self.app_state.global_cfg.authentication_token or "")

        fax_user = self.app_state.global_cfg.fax_user
        auth_token = self.app_state.global_cfg.authentication_token
        have_both = bool(fax_user and auth_token)
        # During initial provisioning (either missing), allow editing both fields.
        self.change_account_button.setEnabled(have_both)
        self.client_domain_input.setEnabled(not have_both)
        self.auth_token_input.setEnabled(not have_both)
        # Subtly draw attention to the Account section when unconfigured
        if not have_both:
            self._flash_account_attention()