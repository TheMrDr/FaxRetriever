import os
import sys

import markdown
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QLabel

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


class AboutDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("About CN-FaxRetriever")
        self.setFixedSize(800, 800)  # Adjusted size for better readability

        # 🔹 Disable "X" (Close) button
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)  # Adds padding

        # Set the application logo
        logo_path = os.path.join(bundle_dir, "images", "logo.ico")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))  # Set window icon

        # Header Label
        header_label = QLabel("📄 CN-FaxRetriever - Developed by Clinic Networking, LLC")
        header_label.setFont(QFont("Arial", 13, QFont.Bold))
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Application Logo (if available)
        if os.path.exists(logo_path):
            logo_label = QLabel(self)
            pixmap = QPixmap(logo_path).scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)

        # About Viewer (formatted markdown)
        self.about_viewer = QTextBrowser()
        # self.about_viewer.setFont(QFont("Arial", 11))
        self.about_viewer.setOpenExternalLinks(True)  # Enable clickable links
        self.load_readme()  # Load markdown as formatted HTML
        layout.addWidget(self.about_viewer)

        # Acknowledge Button
        acknowledge_button = QPushButton("Close")
        acknowledge_button.setFont(QFont("Arial", 10, QFont.Bold))
        acknowledge_button.clicked.connect(self.accept)
        layout.addWidget(acknowledge_button)

        self.setLayout(layout)

    def load_readme(self):
        """Load the markdown ReadMe file and convert it to formatted HTML."""
        readme_path = os.path.join(bundle_dir, "readme.md")
        if os.path.exists(readme_path):
            with open(readme_path, "r", encoding="utf-8") as file:
                markdown_content = file.read()
                html_content = markdown.markdown(markdown_content)  # Convert markdown to HTML
                styled_html = f"<style>body {{ font-family: Arial; font-size: 12pt; }}</style>{html_content}"
                self.about_viewer.setHtml(styled_html)  # Display formatted text
        else:
            self.about_viewer.setText("<b>Error:</b> ReadMe file not found.")
