import markdown
import os
import sys
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton, QLabel
from PyQt5.QtGui import QFont, QPixmap, QIcon
from PyQt5.QtCore import Qt
from Version import __version__


# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


class WhatsNewDialog(QDialog):
    def __init__(self, version, changes_file):
        super().__init__()
        self.version = version
        self.changes_file = changes_file
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("FaxRetriever has been updated!")
        self.setFixedSize(800, 800)  # Slightly increased height for better readability

        # 🔹 Disable "X" (Close) and "?" (Help) buttons
        self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)

        layout = QVBoxLayout()
        layout.setContentsMargins(15, 15, 15, 15)  # Adds padding

        # Set the application logo
        logo_path = os.path.join(os.path.dirname(__file__), "images", "logo.ico")
        if os.path.exists(logo_path):
            self.setWindowIcon(QIcon(logo_path))  # Set window icon

        # Header Label
        header_label = QLabel(f"🎉 FaxRetriever has been updated to version {self.version}! 🎉")
        header_label.setFont(QFont("Arial", 14, QFont.Bold))
        header_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(header_label)

        # Application Logo (if available)
        if os.path.exists(logo_path):
            logo_label = QLabel(self)
            pixmap = QPixmap(logo_path).scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo_label)

        # Changes Viewer (now properly formatted)
        self.changes_viewer = QTextBrowser()
        self.load_changes()  # Load markdown as formatted HTML
        layout.addWidget(self.changes_viewer)

        # Acknowledge Button
        acknowledge_button = QPushButton("Got It!")
        acknowledge_button.setFont(QFont("Arial", 12, QFont.Bold))
        acknowledge_button.clicked.connect(self.mark_update_acknowledged)
        layout.addWidget(acknowledge_button)

        self.setLayout(layout)

    def load_changes(self):
        """Load the markdown file and convert it to formatted HTML."""
        if os.path.exists(self.changes_file):
            with open(self.changes_file, "r", encoding="utf-8") as file:
                markdown_content = file.read()
                html_content = markdown.markdown(markdown_content)  # Convert markdown to HTML
                styled_html = f"<style>body {{ font-family: Arial; font-size: 12pt; }}</style>{html_content}"
                self.changes_viewer.setHtml(styled_html)  # Display formatted text
        else:
            self.changes_viewer.setText("No update details found.")

    def mark_update_acknowledged(self):
        """Mark the update as acknowledged by writing the current version to a file."""
        version_file = os.path.join("log", "version_flag.txt")
        with open(version_file, "w") as file:
            file.write(self.version)
        self.accept()


def check_and_display_whats_new(current_version):
    version_file = os.path.join("log", "version_flag.txt")

    # Determine the base directory for bundled data
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    # Use the bundled path for changes.md
    changes_file = os.path.join(base_path, "changes.md")

    # Check if version flag exists
    if os.path.exists(version_file):
        with open(version_file, "r") as file:
            last_acknowledged_version = file.read().strip()
    else:
        last_acknowledged_version = ""

    # If new version is detected, show the dialog
    if last_acknowledged_version != current_version:
        dialog = WhatsNewDialog(current_version, changes_file)
        dialog.exec_()

def display_whats_new():
    """Directly display the 'What's New' dialog without version checks."""
    # Determine the base directory for bundled data
    if hasattr(sys, '_MEIPASS'):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    # Use the bundled path for changes.md
    changes_file = os.path.join(base_path, "changes.md")

    # Open the dialog immediately
    dialog = WhatsNewDialog(__version__, changes_file)
    dialog.exec_()


if __name__ == "__main__":
    from PyQt5.QtWidgets import QApplication

    app = QApplication(sys.argv)
    check_and_display_whats_new("1.2.0")  # Example version number
    sys.exit(app.exec_())
