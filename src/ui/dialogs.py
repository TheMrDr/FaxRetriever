"""
ui/dialogs.py

Centralized dialog module for FaxRetriever 2.0.
Includes reusable QDialog subclasses:
- OptionsDialog: app configuration
- AboutDialog: application metadata
- SendFaxDialog: manual outbound fax
- FaxStatusDialog: view/send status summary
"""

import os

from PyQt5.Qt import QDesktopServices
from PyQt5.QtCore import Qt, QTimer, QUrl
from PyQt5.QtGui import QFont, QIcon, QPixmap, QTextCursor
from PyQt5.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                             QPushButton, QTextBrowser, QTextEdit, QVBoxLayout)

from core.app_state import app_state
from core.config_loader import device_config, global_config


class LogViewer(QDialog):
    """
    Displays the contents of the application log in real time.
    """

    def __init__(self, base_dir, exe_dir=None, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.exe_dir = exe_dir or base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )  # Remove '?' button

        self.setWindowTitle("System Log Viewer")
        self.setMinimumSize(700, 500)
        # Prefer the log adjacent to the executable; fall back to base_dir
        preferred = os.path.join(self.exe_dir, "log", "ClinicFax.log")
        fallback = os.path.join(self.base_dir, "log", "ClinicFax.log")
        self.log_file = preferred if os.path.exists(preferred) else fallback

        self.layout = QVBoxLayout()
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.layout.addWidget(self.log_view)
        # Buttons row: Close
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        self.layout.addLayout(btn_row)
        self.setLayout(self.layout)

        self.last_size = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_log)
        self.timer.start(1000)
        self._update_log()

    def closeEvent(self, event):
        try:
            if hasattr(self, "timer") and self.timer:
                self.timer.stop()
        except Exception:
            pass
        return super().closeEvent(event)

    def _update_log(self):
        if os.path.exists(self.log_file):
            with open(self.log_file, "r") as f:
                f.seek(self.last_size)
                new = f.read()
                self.last_size = f.tell()
                if new:
                    self.log_view.moveCursor(QTextCursor.End)
                    self.log_view.insertPlainText(new)
                    self.log_view.verticalScrollBar().setValue(
                        self.log_view.verticalScrollBar().maximum()
                    )


class IntegrationAcknowledgement(QDialog):
    """
    One-time warning dialog for third-party integration limitations.
    """

    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )  # Remove '?' button
        self.setWindowTitle("Third-Party Integration Notice")
        self.setFixedSize(450, 250)

        layout = QVBoxLayout()

        logo = QLabel()
        logo.setPixmap(
            QPixmap(os.path.join(self.base_dir, "images", "logo.png")).scaled(
                48, 48, Qt.KeepAspectRatio
            )
        )
        logo.setAlignment(Qt.AlignCenter)
        layout.addWidget(logo)

        message = QLabel(
            "Third-party integrations are still in development and may not be fully stable."
        )
        message.setWordWrap(True)
        message.setAlignment(Qt.AlignCenter)
        layout.addWidget(message)

        self.checkbox = QCheckBox("Don't remind me again")
        layout.addWidget(self.checkbox, alignment=Qt.AlignCenter)

        btn_ack = QPushButton("Acknowledge")
        btn_ack.clicked.connect(self._on_ack)
        layout.addWidget(btn_ack)

        btn_disable = QPushButton("Disable 3rd Party Integrations")
        btn_disable.clicked.connect(self._on_disable)
        layout.addWidget(btn_disable)

        self.setLayout(layout)

    from core.config_loader import global_config

    def _on_ack(self):
        if self.checkbox.isChecked():
            global_config.set("Integrations", "acknowledgement", "True")
            global_config.save()
            app_state.sync_from_config()
        self.accept()

    def _on_disable(self):
        global_config.set("Integrations", "enable_third_party", "No")
        global_config.set("Integrations", "acknowledgement", "False")
        global_config.save()
        app_state.sync_from_config()
        self.reject()


class WhatsNewDialog(QDialog):
    """
    Simple viewer for changelog content in Markdown format.
    """

    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )  # Remove '?' button
        self.setWindowTitle("What's New")
        self.setMinimumSize(650, 500)

        layout = QVBoxLayout()
        self.text_view = QTextBrowser()
        self.text_view.setOpenExternalLinks(True)
        # Slightly polished default font
        body_font = QFont()
        body_font.setPointSize(10)
        self.text_view.document().setDefaultFont(body_font)
        layout.addWidget(self.text_view)
        # Buttons row: Print and Close
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_print = QPushButton("Print")
        btn_close = QPushButton("Close")

        def _do_print():
            try:
                from PyQt5.QtPrintSupport import QPrintDialog, QPrinter

                printer = QPrinter(QPrinter.HighResolution)
                dlg = QPrintDialog(printer, self)
                dlg.setWindowTitle("Print What's New")
                if dlg.exec_() == QDialog.Accepted:
                    # QTextDocument.print_ sends the formatted content to the printer
                    self.text_view.document().print_(printer)
            except Exception:
                # Silently ignore print errors to avoid blocking the user
                pass

        btn_print.clicked.connect(_do_print)
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_print)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self.setLayout(layout)

        # Prefer src\docs\changes.md; fallback to top-level docs\changes.md
        candidates = [
            os.path.join(self.base_dir, "src", "docs", "changes.md"),
            os.path.join(self.base_dir, "docs", "changes.md"),
        ]
        changelog_path = next((p for p in candidates if os.path.exists(p)), None)
        if changelog_path:
            try:
                from PyQt5.QtCore import QUrl

                self.text_view.document().setBaseUrl(
                    QUrl.fromLocalFile(os.path.dirname(changelog_path) + os.sep)
                )
            except Exception:
                pass
            with open(changelog_path, "r", encoding="utf-8") as f:
                self.text_view.setMarkdown(f.read())
        else:
            self.text_view.setText("Changelog not found.")


class MarkdownViewer(QDialog):
    """Reusable, polished Markdown viewer dialog (modeless-capable)."""

    def __init__(
        self, base_dir: str, title: str, md_path: str | None = None, parent=None
    ):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle(title)
        self.setMinimumSize(720, 560)

        layout = QVBoxLayout()
        # Optional top heading/logo area could be added; keep minimal and clean
        self.viewer = QTextBrowser()
        self.viewer.setOpenExternalLinks(True)
        body_font = QFont()
        body_font.setPointSize(10)
        self.viewer.document().setDefaultFont(body_font)
        # Light styling for readability
        self.viewer.setStyleSheet("QTextBrowser { padding: 12px; }")
        layout.addWidget(self.viewer)
        self.setLayout(layout)

        if md_path:
            self.load_markdown(md_path)

    def load_markdown(self, md_path: str):
        try:
            # Resolve relative paths for images/links
            self.viewer.document().setBaseUrl(
                QUrl.fromLocalFile(os.path.dirname(md_path) + os.sep)
            )
            if os.path.exists(md_path):
                with open(md_path, "r", encoding="utf-8") as f:
                    self.viewer.setMarkdown(f.read())
            else:
                self.viewer.setHtml(f"<h2>Document not found</h2><p>{md_path}</p>")
        except Exception as e:
            self.viewer.setHtml(f"<h2>Unable to load document</h2><pre>{e}</pre>")
