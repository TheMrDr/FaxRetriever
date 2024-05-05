import os
import sys
from PyQt5 import QtGui
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory

class AboutDialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("About")
        self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
        self.setFixedSize(600, 400)

        # Read contents of the 'ReadMe' file
        with open(os.path.join(bundle_dir, "ReadMe"), 'r') as file:
            readme_content = file.read()

        # Create a QTextEdit to display the readme content
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(readme_content)
        self.text_edit.setReadOnly(True)
        self.text_edit.setWordWrapMode(QtGui.QTextOption.WordWrap)

        # Create a QPushButton to close the dialog
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.close)

        # Layout setup
        layout = QVBoxLayout()
        layout.addWidget(self.text_edit)
        layout.addWidget(self.close_button)

        self.setLayout(layout)
