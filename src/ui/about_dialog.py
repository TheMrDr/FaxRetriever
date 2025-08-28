import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QTextBrowser

from core.config_loader import global_config, device_config


class AboutDialog(QDialog):
    """
    About screen with content loaded from ./docs/readme.md.
    Includes application heading and logo.
    """
    def __init__(self, base_dir, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)  # Remove '?' button
        self.setWindowTitle("About FaxRetriever")
        self.setMinimumSize(600, 500)

        header = QHBoxLayout()
        logo = QLabel()
        logo_path = os.path.join(self.base_dir, "assets", "logo.png")
        if os.path.exists(logo_path):
            logo.setPixmap(QPixmap(logo_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        title = QLabel("FaxRetriever – Developed by Clinic Networking, LLC")
        title.setStyleSheet("font-weight: bold; font-size: 14pt")
        header.addWidget(logo)
        header.addWidget(title)
        header.addStretch()

        layout = QVBoxLayout()
        self.text_browser = QTextBrowser()
        layout.addWidget(self.text_browser)
        self.setLayout(layout)

        try:
            readme_path = os.path.join(self.base_dir, "docs", "readme.md")
            if os.path.exists(readme_path):
                with open(readme_path, "r", encoding="utf-8") as f:
                    contents = f.read()
                    self.text_browser.setMarkdown(contents)
            else:
                self.text_browser.setText("README file not found.")
        except Exception as e:
            self.text_browser.setText(f"Failed to load README: {e}")