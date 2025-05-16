import datetime
import os
import re
import shutil
import sys
import tempfile
import threading
import traceback
import pyinsane2
import requests

from PIL import Image
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import pyqtSignal, Qt, QObject
from PyQt5.QtGui import QPixmap, QImage, QTransform, QMovie
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QInputDialog,
                             QComboBox, QListWidget, QGridLayout, QMessageBox, QMenu, QAction, QHBoxLayout,
                             QGraphicsView, QCheckBox, QGraphicsScene, QGraphicsPixmapItem, QProgressBar)
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas

from AddressBook import AddressBookManager, AddressBookDialog, AddContactDialog
from SaveManager import SaveManager
from SystemLog import SystemLog

Image.MAX_IMAGE_PIXELS = None

# Determine if running as a bundled executable
if hasattr(sys, '_MEIPASS'):
    bundle_dir = sys._MEIPASS
else:
    bundle_dir = os.path.dirname(os.path.abspath(__file__))  # Default to script directory


# noinspection PyUnresolvedReferences
class UIManager(QDialog):
    finished = pyqtSignal(str, str)  # Signal to indicate the fax send result

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        try:
            self.main_window = main_window
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
            self.setWindowTitle("Send Fax")
            self.setMaximumWidth(700)
            self.address_book_manager = AddressBookManager()
            self.save_manager = SaveManager()
            self.setup_ui()
            self.current_page_index = 0

            # Apply fonts and sizes uniformly
            self._apply_font_styles()

            # Visual adjustments
            self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.MSWindowsFixedSizeDialogHint)
        except Exception as e:
            print(f"Initialization error: {e}\n{traceback.format_exc()}")

    def setup_ui(self):
        try:
            layout = QVBoxLayout(self)
            self.setup_caller_id_section(layout)
            self.setup_destination_number_section(layout)
            self.setup_cover_sheet_section(layout)
            self.setup_document_section(layout)
            self.setup_action_buttons(layout)
        except Exception as e:
            print(f"Setup UI error: {e}\n{traceback.format_exc()}")

    def setup_caller_id_section(self, layout):
        self.caller_id_label = QLabel("Faxing From:")
        self.caller_id_combo = QComboBox()
        layout.addWidget(self.caller_id_label)
        layout.addWidget(self.caller_id_combo)

    def setup_destination_number_section(self, layout):
        try:
            self.destination_label = QLabel("Destination Number:")
            layout.addWidget(self.destination_label)
            grid_layout = QGridLayout()
            layout.addLayout(grid_layout)

            self.phone_label = QLabel("+1 (")
            self.area_code_input = QLineEdit()
            self.area_code_input.setMaxLength(3)
            self.first_three_input = QLineEdit()
            self.first_three_input.setMaxLength(3)
            self.last_four_input = QLineEdit()
            self.last_four_input.setMaxLength(4)

            self.add_contact_button = QPushButton()
            self._configure_icon_button(self.add_contact_button, "AddContact.png", "Add Contact", self.open_add_contact_dialog)

            self.address_book_button = QPushButton()
            self._configure_icon_button(self.address_book_button, "AddressBook.png", "Address Book", self.open_address_book_dialog)

            grid_layout.addWidget(self.phone_label, 0, 0)
            grid_layout.addWidget(self.area_code_input, 0, 1)
            grid_layout.addWidget(QLabel(")"), 0, 2)
            grid_layout.addWidget(self.first_three_input, 0, 3)
            grid_layout.addWidget(QLabel("-"), 0, 4)
            grid_layout.addWidget(self.last_four_input, 0, 5)
            grid_layout.addWidget(self.add_contact_button, 0, 6)
            grid_layout.addWidget(self.address_book_button, 0, 7)

            self.area_code_input.textChanged.connect(lambda: self.focus_next(self.area_code_input, self.first_three_input))
            self.first_three_input.textChanged.connect(lambda: self.focus_next(self.first_three_input, self.last_four_input))
        except Exception as e:
            print(f"Setup destination number section error: {e}\n{traceback.format_exc()}")

    def setup_cover_sheet_section(self, layout):
        try:
            cover_sheet_layout = QVBoxLayout()

            cover_sheet_layout.setSpacing(8)
            cover_sheet_layout.setContentsMargins(10, 5, 10, 5)

            self.include_cover_checkbox = QCheckBox("Include Cover Sheet")
            self.include_cover_checkbox.setFont(QtGui.QFont("Arial", 12))
            self.include_cover_checkbox.toggled.connect(self.toggle_include_cover_sheet)

            buttons_layout = QHBoxLayout()
            self.create_cover_button = QPushButton("Create Cover Sheet")
            self.create_cover_button.clicked.connect(self.open_cover_sheet_dialog)

            self.upload_cover_button = QPushButton("Upload Cover Sheet")
            self.upload_cover_button.clicked.connect(self.upload_cover_sheet)

            self.view_cover_button = QPushButton("View Cover Sheet")
            self.view_cover_button.clicked.connect(self.view_cover_sheet)

            attn_layout = QHBoxLayout()
            self.attn_label = QLabel("Attention:")
            self.attn_label.setFont(QtGui.QFont("Arial", 12))
            self.attn_line_edit = QLineEdit()
            self.attn_line_edit.setPlaceholderText("Enter recipient's name")
            self.attn_line_edit.setFont(QtGui.QFont("Arial", 12))
            self.attn_line_edit.editingFinished.connect(self.on_cover_field_edited)
            attn_layout.addWidget(self.attn_label)
            attn_layout.addWidget(self.attn_line_edit)

            memo_layout = QHBoxLayout()
            self.memo_label = QLabel("Memo:")
            self.memo_label.setFont(QtGui.QFont("Arial", 12))
            self.memo_line_edit = QLineEdit()
            self.memo_line_edit.setPlaceholderText("Enter memo")
            self.memo_line_edit.setFont(QtGui.QFont("Arial", 12))
            self.memo_line_edit.editingFinished.connect(self.on_cover_field_edited)
            memo_layout.addWidget(self.memo_label)
            memo_layout.addWidget(self.memo_line_edit)

            for btn in [self.create_cover_button, self.upload_cover_button, self.view_cover_button]:
                btn.setMinimumHeight(35)
                btn.setFont(QtGui.QFont("Arial", 11))

            buttons_layout.addWidget(self.create_cover_button)
            buttons_layout.addWidget(self.upload_cover_button)
            buttons_layout.addWidget(self.view_cover_button)

            cover_sheet_layout.addWidget(self.include_cover_checkbox)
            cover_sheet_layout.addLayout(buttons_layout)
            cover_sheet_layout.addLayout(attn_layout)
            cover_sheet_layout.addLayout(memo_layout)

            layout.addLayout(cover_sheet_layout)

            # At the end of setup_cover_sheet_section()
            saved_value = self.save_manager.get_config_value("Fax Options", "include_cover_sheet")
            is_enabled = saved_value == "Yes"
            self.include_cover_checkbox.setChecked(is_enabled)
            self.create_cover_button.setEnabled(is_enabled)
            self.upload_cover_button.setEnabled(is_enabled)
            self.attn_line_edit.setEnabled(is_enabled)
            self.memo_line_edit.setEnabled(is_enabled)
            self.view_cover_button.setEnabled(
                is_enabled and os.path.exists(os.path.join(os.getcwd(), "cover_sheet.pdf")))
            self.update_cover_sheet_button_states()

        except Exception as e:
            print(f"Setup cover sheet section error: {e}\n{traceback.format_exc()}")

    def setup_document_section(self, layout):
        try:
            h_layout = QHBoxLayout()
            v_layout = QVBoxLayout()

            self.document_label = QLabel("Attached Documents:")
            self.document_list = QListWidget()
            self.document_list.setContextMenuPolicy(Qt.CustomContextMenu)

            self.document_button = QPushButton("Attach Document")
            self.scan_button = QPushButton("Scan Document")

            document_buttons_layout = QHBoxLayout()
            document_buttons_layout.addWidget(self.document_button)
            document_buttons_layout.addWidget(self.scan_button)

            v_layout.addWidget(self.document_label)
            v_layout.addWidget(self.document_list)
            v_layout.addLayout(document_buttons_layout)
            h_layout.addLayout(v_layout)

            preview_layout = QVBoxLayout()
            self.preview_label = QLabel("Image Preview")
            self.preview_label.setAlignment(Qt.AlignLeft)

            nav_buttons_layout = QHBoxLayout()
            self.prev_page_button = QPushButton("<")
            self.next_page_button = QPushButton(">")
            nav_buttons_layout.addWidget(self.prev_page_button)
            nav_buttons_layout.addWidget(self.next_page_button)

            self.document_preview = DocumentPreviewWidget()
            self.document_preview.setFixedSize(400, 400)

            preview_layout.addWidget(self.preview_label)
            preview_layout.addWidget(self.document_preview)
            preview_layout.addLayout(nav_buttons_layout)
            h_layout.addLayout(preview_layout)

            layout.addLayout(h_layout)

            self.prev_page_button.clicked.connect(self.show_previous_page)
            self.next_page_button.clicked.connect(self.show_next_page)
            self.document_list.itemSelectionChanged.connect(self.document_selection_changed)
        except Exception as e:
            print(f"Setup document section error: {e}\n{traceback.format_exc()}")

    def setup_action_buttons(self, layout):
        self.send_button = QPushButton("Send Fax")
        self.cancel_button = QPushButton("Cancel")
        layout.addWidget(self.send_button)
        layout.addWidget(self.cancel_button)

    def document_selection_changed(self):
        self.current_page_index = 0
        selected_items = self.document_list.selectedItems()
        if selected_items:
            index = self.document_list.row(selected_items[0])
            doc_path = self.document_manager.documents_paths[index]
            self.document_manager.update_image_label(doc_path, self.document_preview, page=self.current_page_index)

    def show_previous_page(self):
        if self.current_page_index > 0:
            self.current_page_index -= 1
            selected_items = self.document_list.selectedItems()
            if selected_items:
                index = self.document_list.row(selected_items[0])
                doc_path = self.document_manager.documents_paths[index]
                self.document_manager.update_image_label(doc_path, self.document_preview, page=self.current_page_index)

    def show_next_page(self):
        selected_items = self.document_list.selectedItems()
        if selected_items:
            index = self.document_list.row(selected_items[0])
            doc_path = self.document_manager.documents_paths[index]
            num_pages = self.document_manager.get_page_count(doc_path)
            if self.current_page_index < num_pages - 1:
                self.current_page_index += 1
                self.document_manager.update_image_label(doc_path, self.document_preview, page=self.current_page_index)

    def focus_next(self, current_widget, next_widget):
        if len(current_widget.text()) == current_widget.maxLength():
            next_widget.setFocus()

    def open_add_contact_dialog(self):
        dialog = AddContactDialog(self.address_book_manager, self)
        dialog.exec_()

    def open_address_book_dialog(self):
        dialog = AddressBookDialog(self.address_book_manager, self)
        dialog.exec_()

    def populate_phone_fields(self, phone):
        phone = phone.translate({ord(c): None for c in " ()-"})
        if len(phone) == 10:
            self.area_code_input.setText(phone[:3])
            self.first_three_input.setText(phone[3:6])
            self.last_four_input.setText(phone[6:])

    def clear_document_list(self):
        self.document_list.clear()
        self.document_preview.clear_preview()
        self.document_manager.clear_documents()

    def closeEvent(self, event):
        self.clear_document_list()
        # self.area_code_input.clear()
        self.first_three_input.clear()
        self.last_four_input.clear()
        self.attn_line_edit.clear()
        self.memo_line_edit.clear()

        self.generate_cover_sheet_pdf()

        self.pixmap_item = None
        self.populate_area_code()
        super().closeEvent(event)

    # ---------- Utility Methods ----------

    def _configure_icon_button(self, button, icon_filename, tooltip, callback):
        icon_path = os.path.join(bundle_dir, "images", icon_filename)
        button.setIcon(QtGui.QIcon(icon_path))
        button.setIconSize(QtCore.QSize(30, 30))
        button.setFixedSize(40, 40)
        button.setToolTip(tooltip)
        button.clicked.connect(callback)

    def _apply_font_styles(self):
        """Apply consistent font and sizing to widgets"""
        bold_font = QtGui.QFont("Arial", 14, QtGui.QFont.Bold)
        regular_font = QtGui.QFont("Arial", 12)

        self.caller_id_label.setFont(regular_font)
        self.caller_id_combo.setFont(regular_font)
        self.caller_id_combo.setMinimumHeight(35)

        widgets = [
            self.destination_label, self.phone_label,
            self.area_code_input, self.first_three_input, self.last_four_input,
            self.document_label, self.document_button, self.scan_button,
            self.preview_label, self.prev_page_button, self.next_page_button
        ]
        for widget in widgets:
            widget.setFont(bold_font)

        inputs = [self.area_code_input, self.first_three_input, self.last_four_input]
        for input_field in inputs:
            input_field.setMinimumHeight(40)

        # Buttons with lighter font
        for button in [self.document_button, self.scan_button, self.prev_page_button, self.next_page_button]:
            button.setFont(regular_font)
            button.setMinimumHeight(40)

        self.send_button.setFont(bold_font)
        self.send_button.setMinimumHeight(50)
        self.send_button.setStyleSheet("background-color: #2a81dc; color: white; border-radius: 10px;")
        self.send_button.setToolTip("Click to send the fax.")

        self.cancel_button.setFont(regular_font)
        self.cancel_button.setMinimumHeight(50)
        self.cancel_button.setStyleSheet("background-color: #dc2a2a; color: white; border-radius: 10px;")
        self.cancel_button.setToolTip("Cancel and return to the main menu.")

    def toggle_include_cover_sheet(self, checked):
        """Update config setting, save, and enable/disable cover sheet buttons."""
        try:
            value = "Yes" if checked else "No"
            if not self.save_manager.config.has_section("Fax Options"):
                self.save_manager.config.add_section("Fax Options")

            self.save_manager.config.set("Fax Options", "include_cover_sheet", value)
            self.save_manager.save_changes()

            # Enable/disable buttons based on checkbox state
            self.create_cover_button.setEnabled(checked)
            self.upload_cover_button.setEnabled(checked)
            self.view_cover_button.setEnabled(checked and os.path.exists(os.path.join(os.getcwd(), "cover_sheet.pdf")))
            self.attn_line_edit.setEnabled(checked)
            self.memo_line_edit.setEnabled(checked)

            if self.main_window:
                self.main_window.update_status_bar(f"Cover sheet setting saved: {value}", 5000)

            self.update_cover_sheet_button_states()

        except Exception as e:
            print(f"Error saving cover sheet toggle: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def open_cover_sheet_dialog(self):
        try:
            dialog = QDialog(self)
            dialog.setWindowTitle("Create Cover Sheet")
            dialog.setFixedWidth(400)
            dialog.setWindowFlags(dialog.windowFlags() & ~Qt.WindowContextHelpButtonHint)

            layout = QVBoxLayout(dialog)

            fields = {
                "Business Name": QLineEdit(),
                "Business Address": QLineEdit(),
                "Business Phone": QLineEdit(),
                "Business Email": QLineEdit()
            }

            # Populate fields if values already exist
            saved_keys = {
                "Business Name": "cover_sheet_business_name",
                "Business Address": "cover_sheet_business_address",
                "Business Phone": "cover_sheet_business_phone",
                "Business Email": "cover_sheet_business_email"
            }

            for label, line_edit in fields.items():
                value = self.save_manager.get_config_value("Fax Options", saved_keys[label]) or ""
                line_edit.setText(value)
                form_layout = QVBoxLayout()
                form_layout.addWidget(QLabel(label + ":"))
                form_layout.addWidget(line_edit)
                layout.addLayout(form_layout)

            # Buttons
            button_layout = QHBoxLayout()
            save_btn = QPushButton("Save")
            cancel_btn = QPushButton("Cancel")
            button_layout.addWidget(save_btn)
            button_layout.addWidget(cancel_btn)
            layout.addLayout(button_layout)

            save_btn.clicked.connect(lambda: self._save_cover_sheet_data(dialog, fields, saved_keys))
            cancel_btn.clicked.connect(dialog.reject)

            dialog.exec_()
        except Exception as e:
            print(f"Error opening cover sheet dialog: {e}")

    def _save_cover_sheet_data(self, dialog, fields, keys):
        try:
            if not self.save_manager.config.has_section("Fax Options"):
                self.save_manager.config.add_section("Fax Options")

            for label, line_edit in fields.items():
                key = keys[label]
                value = line_edit.text().strip() or "None"
                self.save_manager.config.set("Fax Options", key, value)

            self.save_manager.save_changes()
            if self.main_window:
                self.main_window.update_status_bar("Cover sheet information saved.", 5000)
            self.generate_cover_sheet_pdf()
            dialog.accept()
        except Exception as e:
            print(f"Error saving cover sheet data: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def generate_cover_sheet_pdf(self):
        try:
            business_name = self.save_manager.get_config_value("Fax Options", "cover_sheet_business_name") or ""
            business_address = self.save_manager.get_config_value("Fax Options", "cover_sheet_business_address") or ""
            business_phone = self.save_manager.get_config_value("Fax Options", "cover_sheet_business_phone") or ""
            business_email = self.save_manager.get_config_value("Fax Options", "cover_sheet_business_email") or ""
            attn_text = self.attn_line_edit.text().strip()
            memo_text = self.memo_line_edit.text().strip()

            output_path = os.path.join(os.getcwd(), "cover_sheet.pdf")
            c = canvas.Canvas(output_path, pagesize=letter)
            width, height = letter

            # Header
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(width / 2.0, height - 1.25 * inch, business_name)
            c.setFont("Helvetica", 12)
            c.drawCentredString(width / 2.0, height - 1.5 * inch, business_address)
            c.drawCentredString(width / 2.0, height - 1.7 * inch, f"Phone: {business_phone} | Email: {business_email}")

            # Main Title
            c.setFont("Helvetica-Bold", 36)
            c.drawCentredString(width / 2.0, height / 2.0, "COVER SHEET")

            # ATTN and Memo Section
            c.setFont("Helvetica-Bold", 14)
            c.drawString(1 * inch, height / 2.0 - 0.75 * inch, f"Attention: {attn_text}")
            c.drawString(1 * inch, height / 2.0 - 1.1 * inch, f"Memo: {memo_text}")

            # Footer (optional)
            c.setFont("Helvetica-Oblique", 10)
            c.drawCentredString(width / 2.0, 0.75 * inch, "This page intentionally left blank")

            c.showPage()
            c.save()

            if self.main_window:
                self.main_window.update_status_bar("Cover sheet PDF generated.", 5000)

            self.view_cover_button.setEnabled(self.include_cover_checkbox.isChecked() and os.path.exists(
                os.path.join(os.getcwd(), "cover_sheet.pdf")))

            self.save_manager.config.set("Fax Options", "cover_sheet_type", "Generated")
            self.save_manager.save_changes()

            self.update_cover_sheet_button_states()

        except Exception as e:
            print(f"Error generating cover sheet PDF: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def upload_cover_sheet(self):
        try:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Cover Sheet", "", "PDF Files (*.pdf);;Image Files (*.jpg *.jpeg *.png)"
            )
            if not file_path:
                return  # User cancelled

            dest_path = os.path.join(os.getcwd(), "custom_cover_sheet.pdf")

            # Handle image conversion
            if file_path.lower().endswith((".jpg", ".jpeg", ".png")):
                image = Image.open(file_path).convert("RGB")
                image.save(dest_path, "PDF", resolution=100.0)
            else:
                shutil.copyfile(file_path, dest_path)

            if self.main_window:
                self.main_window.update_status_bar("Cover sheet uploaded successfully.", 5000)

            self.view_cover_button.setEnabled(self.include_cover_checkbox.isChecked() and os.path.exists(
                os.path.join(os.getcwd(), "custom_cover_sheet.pdf")))

            self.save_manager.config.set("Fax Options", "cover_sheet_type", "Uploaded")
            self.save_manager.save_changes()

            self.update_cover_sheet_button_states()

        except Exception as e:
            print(f"Error uploading cover sheet: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def view_cover_sheet(self):
        try:
            pdf_path = os.path.join(os.getcwd(), "cover_sheet.pdf")
            if not os.path.exists(pdf_path):
                return  # Silently do nothing (for now)

            if sys.platform.startswith('darwin'):
                os.system(f'open "{pdf_path}"')
            elif os.name == 'nt':
                os.startfile(pdf_path)
            elif os.name == 'posix':
                os.system(f'xdg-open "{pdf_path}"')
        except Exception as e:
            print(f"Error opening cover sheet PDF: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def update_cover_sheet_button_states(self):
        """Adjusts button behavior based on whether cover_sheet.pdf exists."""
        has_cover = os.path.exists(os.path.join(os.getcwd(), "cover_sheet.pdf"))
        cover_enabled = self.include_cover_checkbox.isChecked()

        self.create_cover_button.setEnabled(cover_enabled and not has_cover)
        self.view_cover_button.setEnabled(cover_enabled and has_cover)

        if has_cover:
            self.upload_cover_button.setText("Remove Cover Sheet")
            self.upload_cover_button.clicked.disconnect()
            self.upload_cover_button.clicked.connect(self.remove_cover_sheet)
            self.upload_cover_button.setEnabled(cover_enabled)
        else:
            self.upload_cover_button.setText("Upload Cover Sheet")
            self.upload_cover_button.clicked.disconnect()
            self.upload_cover_button.clicked.connect(self.upload_cover_sheet)
            self.upload_cover_button.setEnabled(cover_enabled)

    def remove_cover_sheet(self):
        try:
            pdf_path = os.path.join(os.getcwd(), "cover_sheet.pdf")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            if self.main_window:
                self.main_window.update_status_bar("Cover sheet removed.", 5000)

            self.update_cover_sheet_button_states()
        except Exception as e:
            print(f"Error removing cover sheet: {e}")
            if self.main_window:
                self.main_window.update_status_bar(f"Error: {str(e)}", 10000)

    def on_cover_field_edited(self):
        cover_type = self.save_manager.get_config_value("Fax Options", "cover_sheet_type")

        if cover_type == "Uploaded":
            reply = QMessageBox.question(
                self,
                "Overwrite Uploaded Cover Sheet?",
                "You're currently using a custom uploaded cover sheet.\n"
                "Editing these fields will generate a new one and overwrite the selection.\n\n"
                "Do you want to continue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        self.generate_cover_sheet_pdf()


class DocumentManager:
    def __init__(self, ui_manager):
        try:
            self.ui_manager = ui_manager
            self.cover_sheet_path = None
            self.documents_paths = []  # Stores converted/normalized paths
        except Exception as e:
            print(f"Initialization error: {e}\n{traceback.format_exc()}")

    def attach_document(self):
        try:
            options = QFileDialog.Options()
            files, _ = QFileDialog.getOpenFileNames(
                self.ui_manager,
                "Select one or more files to fax",
                "",
                "Documents (*.pdf *.doc *.docx *.jpg *.png *.tif *.tiff *.txt)",
                options=options
            )
            for file in files:
                converted = self.convert_to_pdf(file)
                if converted:
                    self.documents_paths.append(converted)
                    self.ui_manager.document_list.addItem(self.format_display_name(file))
                    self.update_document_image(converted)
        except Exception as e:
            print(f"Attach document error: {e}\n{traceback.format_exc()}")

    def remove_document(self):
        try:
            selected_items = self.ui_manager.document_list.selectedItems()
            if not selected_items:
                return
            for item in selected_items:
                index = self.ui_manager.document_list.row(item)
                path = self.documents_paths[index]
                if os.path.exists(path) and path.endswith('.pdf'):
                    os.remove(path)
                del self.documents_paths[index]
                self.ui_manager.document_list.takeItem(index)
            if self.documents_paths:
                self.update_document_image(self.documents_paths[0])
            else:
                self.ui_manager.document_preview.scene.clear()
        except Exception as e:
            print(f"Remove document error: {e}\n{traceback.format_exc()}")

    def format_display_name(self, filepath):
        try:
            name = os.path.basename(filepath)
            return f"{name[:15]}...{name[-10:]}" if len(name) > 30 else name
        except Exception as e:
            print(f"Format display name error: {e}\n{traceback.format_exc()}")
            return filepath

    def update_document_image(self, filepath):
        try:
            if filepath:
                self.update_image_label(filepath, self.ui_manager.document_preview)
            else:
                self._clear_preview()
        except Exception as e:
            print(f"Update document image error: {e}\n{traceback.format_exc()}")

    def update_image_label(self, filepath, preview_widget, page=0):
        try:
            pixmap = None
            ext = filepath.lower()
            if ext.endswith('.pdf'):
                import fitz
                doc = fitz.open(filepath)
                page = max(0, min(page, doc.page_count - 1))
                pix = doc.load_page(page).get_pixmap()
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(image)
            elif ext.endswith(('.doc', '.docx')):
                icon_path = os.path.join("images", "docx.png")
                pixmap = QPixmap(icon_path)
            else:
                pixmap = QPixmap(filepath)

            if hasattr(preview_widget, "set_pixmap"):
                preview_widget.set_pixmap(pixmap)
            else:
                preview_widget.setPixmap(pixmap.scaled(preview_widget.size(), Qt.KeepAspectRatio))
        except Exception as e:
            print(f"Failed to load image: {e}\n{traceback.format_exc()}")
            self._clear_preview(preview_widget)

    def get_page_count(self, filepath):
        try:
            if filepath.lower().endswith('.pdf'):
                import fitz
                return fitz.open(filepath).page_count
        except Exception as e:
            print(f"Error getting page count: {e}\n{traceback.format_exc()}")
        return 1

    def convert_to_pdf(self, filepath):
        try:
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.pdf':
                return self._normalize_existing_pdf(filepath)
            elif ext in ['.doc', '.docx']:
                self._warn_docx_orientation()
                return filepath
            elif ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff']:
                return self._convert_image_to_pdf(filepath)
            elif ext == '.txt':
                return self._convert_text_to_pdf(filepath)
            else:
                print(f"Unsupported file type: {ext}")
                return None
        except Exception as e:
            print(f"Error converting file {filepath} to PDF: {e}\n{traceback.format_exc()}")
            return None

    def normalize_pdf_to_portrait(self, input_pdf_path, output_pdf_path):
        try:
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            for page in reader.pages:
                width, height = float(page.mediabox.width), float(page.mediabox.height)
                if width > height:
                    page.rotate(90)
                writer.add_page(page)
            with open(output_pdf_path, 'wb') as f:
                writer.write(f)
        except Exception as e:
            print(f"Error normalizing PDF: {e}\n{traceback.format_exc()}")

    def clear_documents(self):
        try:
            for file in self.documents_paths:
                if os.path.exists(file) and file.endswith('.pdf'):
                    try:
                        os.remove(file)
                    except Exception as e:
                        print(f"Failed to remove temp file: {file} | {e}")
            self.documents_paths.clear()
            self.cover_sheet_path = None
        except Exception as e:
            print(f"Error during document cleanup: {e}\n{traceback.format_exc()}")

    # ---------- Private Helpers ----------

    def _clear_preview(self, widget=None):
        preview = widget or self.ui_manager.document_preview
        if hasattr(preview, "scene"):
            preview.scene.clear()
        else:
            preview.clear()

    def _warn_docx_orientation(self):
        QMessageBox.warning(
            self.ui_manager,
            "Document Warning",
            "DOC/DOCX files will be sent as-is. Please verify that the orientation is correct before sending."
        )

    def _create_temp_pdf_path(self):
        fd, path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        return path

    def _normalize_existing_pdf(self, filepath):
        temp_path = self._create_temp_pdf_path()
        self.normalize_pdf_to_portrait(filepath, temp_path)
        return temp_path

    def _convert_image_to_pdf(self, filepath):
        with Image.open(filepath) as img:
            img = img.convert('RGB')
            temp_path = self._create_temp_pdf_path()
            img.save(temp_path, 'PDF', resolution=100.0)
            return temp_path

    def _convert_text_to_pdf(self, filepath):
        temp_path = self._create_temp_pdf_path()
        with open(filepath, 'r', encoding='utf-8') as f:
            text = f.read()
        c = canvas.Canvas(temp_path, pagesize=letter)
        c.drawString(10, 750, text)
        c.save()
        return temp_path


class DocumentPreviewWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = None
        self._hover_zoom = 2.0

        # Enable mouse tracking and configure view behavior
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)

    def set_pixmap(self, pixmap):
        """Set and display a pixmap, scaled to fit the current view."""
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.fit_image()

    def fit_image(self):
        """Scale the view so that the entire pixmap_item fits into the viewport."""
        if self.pixmap_item and self.pixmap_item.scene() is not None:
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def enterEvent(self, event):
        """Zoom in slightly when the mouse enters the widget."""
        if self.pixmap_item:
            self.setTransform(QTransform().scale(self._hover_zoom, self._hover_zoom))
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Reset zoom when the mouse leaves the widget."""
        if self.pixmap_item:
            self.fit_image()
        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        """Center the view on the mouse position while zoomed."""
        self.centerOn(self.mapToScene(event.pos()))
        super().mouseMoveEvent(event)

    def clear_preview(self):
        """Safely clear the current image and reset the pixmap reference."""
        self.scene.clear()
        self.pixmap_item = None


class FaxSender:
    def __init__(self, ui_manager, document_manager, save_manager):
        try:
            self.ui_manager = ui_manager
            self.document_manager = document_manager
            self.save_manager = save_manager
        except Exception as e:
            print(f"Initialization error: {e}\n{traceback.format_exc()}")

    def send_fax(self):
        try:
            # Validate caller ID
            raw_caller_id = self.ui_manager.caller_id_combo.currentText().strip()
            if not raw_caller_id:
                QMessageBox.warning(
                    self.ui_manager,
                    "Missing Caller ID",
                    "Please select a Caller ID (source fax number) before sending."
                )
                return

            # Strip all non-digit characters
            caller_id = re.sub(r'\D', '', raw_caller_id)

            if not caller_id or len(caller_id) < 10:
                QMessageBox.critical(
                    self.ui_manager,
                    "Invalid Caller ID",
                    f"The caller ID '{raw_caller_id}' is invalid. Please enter a valid phone number with at least 10 digits."
                )
                return

            # Validate destination number
            area = self.ui_manager.area_code_input.text().strip()
            first = self.ui_manager.first_three_input.text().strip()
            last = self.ui_manager.last_four_input.text().strip()
            destination = '1' + area + first + last

            if not (area.isdigit() and first.isdigit() and last.isdigit()) or len(destination) != 11:
                QMessageBox.warning(
                    self.ui_manager,
                    "Invalid Destination Number",
                    "Please enter a complete 10-digit destination phone number."
                )
                return

            # Validate attached documents
            if not self.document_manager.documents_paths:
                QMessageBox.warning(
                    self.ui_manager,
                    "No Documents",
                    "Please attach at least one document to send with the fax."
                )
                return

            # Validate cover sheet inclusion (if enabled)
            include_cover = self.save_manager.get_config_value("Fax Options", "include_cover_sheet") == "Yes"
            cover_type = self.save_manager.get_config_value("Fax Options", "cover_sheet_type")
            cover_path = os.path.join(os.getcwd(),
                                      "custom_cover_sheet.pdf" if cover_type == "Uploaded" else "cover_sheet.pdf")

            if include_cover and not os.path.exists(cover_path):
                QMessageBox.warning(self.ui_manager, "Missing Cover Sheet",
                                    "Cover sheet selected, but file not found. Please re-upload or re-generate.")
                return

            fax_user = self.save_manager.get_config_value('Account', 'fax_user')
            token = self.save_manager.get_config_value('Token', 'access_token')
            url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
            headers = {"Authorization": f"Bearer {token}"}
            data = {"caller_id": caller_id, "destination": destination}

            files, temp_files = self._prepare_documents_for_upload()

            try:
                response = requests.post(url, files=files, data=data, headers=headers)
                if response.status_code == 200:
                    QMessageBox.information(self.ui_manager, "Fax Sent", "Your fax has been queued successfully.")
                    self.ui_manager.clear_document_list()
                    self._clear_inputs()
                    self.ui_manager.attn_line_edit.blockSignals(True)
                    self.ui_manager.attn_line_edit.clear()
                    self.ui_manager.attn_line_edit.blockSignals(False)
                    self.ui_manager.memo_line_edit.clear()
                    self.ui_manager.accept()
                else:
                    QMessageBox.critical(self.ui_manager, "Sending Failed", f"Failed to send fax: {response.text}")
            except Exception as e:
                QMessageBox.critical(self.ui_manager, "Error", f"An error occurred: {str(e)}")
            finally:
                self._cleanup_files(files, temp_files)
                self.document_manager.clear_documents()

        except Exception as e:
            print(f"Send fax error: {e}\n{traceback.format_exc()}")
            QMessageBox.critical(
                self.ui_manager,
                "Error",
                f"An error occurred while preparing to send the fax: {str(e)}"
            )

    def _prepare_documents_for_upload(self):
        """Prepare file attachments for the API and return (files, temp_files) tuple."""
        files = {}
        temp_files = []
        file_index = 0

        # Step 1: Include cover sheet if requested
        include_cover = self.save_manager.get_config_value("Fax Options", "include_cover_sheet") == "Yes"
        cover_path = os.path.join(os.getcwd(), "cover_sheet.pdf")

        if include_cover and os.path.exists(cover_path):
            try:
                temp_path = self._create_normalized_pdf(cover_path)
                temp_files.append(temp_path)
                files[f'filename[{file_index}]'] = (
                    os.path.basename(temp_path),
                    open(temp_path, 'rb'),
                    'application/pdf'
                )
                file_index += 1
            except Exception as e:
                print(f"Failed to include cover sheet: {e}")

        # Step 2: Attach user documents
        for doc_path in self.document_manager.documents_paths:
            ext = os.path.splitext(doc_path)[1].lower()
            if ext == '.pdf':
                temp_path = self._create_normalized_pdf(doc_path)
                temp_files.append(temp_path)
                doc_to_send = temp_path
                mime_type = 'application/pdf'
            else:
                doc_to_send = doc_path
                mime_type = f'image/{ext.lstrip(".")}'

            files[f'filename[{file_index}]'] = (
                os.path.basename(doc_to_send),
                open(doc_to_send, 'rb'),
                mime_type
            )
            file_index += 1

        return files, temp_files

    def _create_normalized_pdf(self, source_path):
        """Create a portrait-oriented temporary PDF from an existing PDF file."""
        fd, temp_path = tempfile.mkstemp(suffix='.pdf')
        os.close(fd)
        self.normalize_pdf_to_portrait(source_path, temp_path)
        return temp_path

    def normalize_pdf_to_portrait(self, input_pdf_path, output_pdf_path):
        """Rotate landscape pages to portrait in a new PDF."""
        try:
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            for page in reader.pages:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                if width > height:
                    page.rotate(90)
                writer.add_page(page)
            with open(output_pdf_path, 'wb') as f:
                writer.write(f)
        except Exception as e:
            print(f"Error normalizing PDF: {e}\n{traceback.format_exc()}")

    def _clear_inputs(self):
        """Clear fax number fields after sending a fax."""
        self.ui_manager.area_code_input.clear()
        self.ui_manager.first_three_input.clear()
        self.ui_manager.last_four_input.clear()

    def _cleanup_files(self, files, temp_files):
        """Close file handles and delete temporary files."""
        for _, file_tuple in files.items():
            try:
                file_tuple[1].close()
            except Exception as e:
                print(f"Failed to close file handle: {e}")
        for path in temp_files:
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception as e:
                    print(f"Failed to delete temp file: {path} | {e}")

class ScanningDialog(QDialog):
    """
    Displays a modal scanning animation with a progress bar and status message.
    """
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Scanning Document")
        self.setFixedSize(300, 150)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.WindowCloseButtonHint)
        self.setStyleSheet("""
            QDialog {
                background-color: #f0f0f0;
                border-radius: 8px;
                padding: 10px;
            }
            QLabel {
                font-size: 14px;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)

        # Animated GIF
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.scanner_animation = QMovie(os.path.join(bundle_dir, "images", "scanner.gif"))
        self.icon_label.setMovie(self.scanner_animation)
        self.scanner_animation.start()
        layout.addWidget(self.icon_label)

        # Status Text
        self.label = QLabel("Scanning, please wait...")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        # Indeterminate Progress Bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.setLayout(layout)

# noinspection PyUnresolvedReferences
class ScannerManager(QObject):
    scan_started = pyqtSignal()
    scan_finished = pyqtSignal(list)
    show_message = pyqtSignal(str, str, QMessageBox.Icon)
    scanning_dialog_closed = pyqtSignal()

    def __init__(self, ui_manager, document_manager):
        super().__init__()
        self.ui_manager = ui_manager
        self.document_manager = document_manager
        self.lock = threading.Lock()
        self.scanner = None
        self.directory = None

        self.scan_started.connect(self._init_scanner)
        self.scan_finished.connect(self.update_ui_with_scanned_documents)
        self.show_message.connect(self._show_message)
        self.scanning_dialog_closed.connect(self._close_scanning_dialog)

    def scan_document(self):
        self.scanning_dialog = ScanningDialog(self.ui_manager)
        self.scanning_dialog.show()
        self.scan_started.emit()
        threading.Thread(target=self._scan_document_thread, daemon=True).start()

    def _init_scanner(self):
        try:
            print("Initializing scanner detection...")
            pyinsane2.exit()
            pyinsane2.init()
            devices = pyinsane2.get_devices()

            if not devices:
                print("No scanners detected. Checking again after power-on...")
                self.show_message.emit(
                    "No Scanner Found",
                    "No scanners were detected. Ensure your scanner is powered on and properly connected.",
                    QMessageBox.Warning
                )
                return

            # Remove duplicates by model name
            scanner_dict = {device.model: device for device in devices}
            unique_scanners = list(scanner_dict.values())

            if len(unique_scanners) == 1:
                self.scanner = unique_scanners[0]
                print(f"Auto-selected scanner: {self.scanner.model}")
                return

            # Prompt user if multiple
            scanner_names = [scanner.model for scanner in unique_scanners]
            selected_scanner, ok = QInputDialog.getItem(
                self.ui_manager, "Select Scanner", "Available Scanners:", scanner_names, 0, False
            )
            if ok:
                self.scanner = next(d for d in unique_scanners if d.model == selected_scanner)
                print(f"User selected scanner: {self.scanner.model}")
            else:
                print("Scanner selection cancelled.")
        except Exception as e:
            print(f"Scanner Initialization Error: {e}\n{traceback.format_exc()}")
            self.show_message.emit("Scanner Error", f"An error occurred: {str(e)}", QMessageBox.Critical)

    def _scan_document_thread(self):
        with self.lock:
            scanned_files = []
            try:
                if not self.scanner:
                    self.show_message.emit("Scanner Error", "No scanner was selected.", QMessageBox.Warning)
                    self.scanning_dialog_closed.emit()
                    return

                scanner = self.scanner
                print(f"Using scanner: {scanner.model}")
                self._set_scanner_options(scanner)

                base_path = os.path.join(os.getcwd(), "Scanned Docs")

                if self.directory is None:
                    # First scan in this session, make a new folder
                    timestamp = datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
                    self.directory = os.path.join(base_path, timestamp)
                    os.makedirs(self.directory, exist_ok=True)
                    print(f"Scan directory created: {self.directory}")

                    # Clean up old folders (excluding this one)
                    self._clean_old_scan_folders(base_path, keep=self.directory)
                else:
                    print(f"Reusing existing scan folder: {self.directory}")

                scan_session = scanner.scan(multiple=True)

                saved_image_count = 0

                while True:
                    try:
                        scan_session.scan.read()
                    except EOFError:
                        # Process any *new* pages added since last read
                        for image in scan_session.images[saved_image_count:]:
                            self.ui_manager.scan_session_counter += 1
                            image_path = os.path.join(
                                self.directory,
                                f"scanned_document_page_{self.ui_manager.scan_session_counter}.jpg"
                            )
                            image.save(image_path, 'JPEG')
                            print(f"Image saved: {image_path}")
                            self._compress_image(image_path)
                            scanned_files.append(image_path)
                            saved_image_count += 1
                    except StopIteration:
                        print(f"Scan complete: {len(scan_session.images)} pages")
                        break
                    except Exception as e:
                        print(f"Scan read error: {e}\n{traceback.format_exc()}")
                        break

                if not scanned_files:
                    self.show_message.emit("Scan Error", "No images were scanned.", QMessageBox.Warning)
                    return

            except (pyinsane2.WIAException, Exception) as e:
                print(f"Scan Error: {e}\n{traceback.format_exc()}")
                self.show_message.emit("Scan Error", f"An error occurred during scanning: {str(e)}",
                                       QMessageBox.Critical)
            finally:
                self.scan_finished.emit(scanned_files)
                self.scanning_dialog_closed.emit()
                self.scanner = None  # Reset for next session

    def _set_scanner_options(self, scanner):
        def set_option(option, value):
            try:
                if option in scanner.options:
                    scanner.options[option].value = value
                    print(f"Set {option} = {value}")
            except Exception as e:
                print(f"Failed to set {option}: {e}")

        try:
            set_option('resolution', 200)
            set_option('mode', 'Color')

            if all(opt in scanner.options for opt in ['tl-x', 'tl-y', 'br-x', 'br-y']):
                set_option('tl-x', 0)
                set_option('tl-y', 0)
                set_option('br-x', 1701)
                set_option('br-y', 2197)
            elif 'page_size' in scanner.options:
                set_option('page_size', 'a4')

            if 'source' in scanner.options:
                sources = scanner.options['source'].constraint
                preferred = next((s for s in ['ADF Duplex', 'ADF'] if s in sources), None)
                if preferred:
                    set_option('source', preferred)
                elif len(sources) > 1:
                    source_name, ok = QInputDialog.getItem(self.ui_manager, "Select Source", "Available Sources:", sources, 0, False)
                    if ok:
                        set_option('source', source_name)
                else:
                    set_option('source', sources[0])

            set_option('blank_page', True)
        except Exception as e:
            print(f"Set scanner options error: {e}\n{traceback.format_exc()}")

    def _compress_image(self, image_path):
        try:
            img = Image.open(image_path).convert('L')
            temp_path = image_path.replace('.jpg', '_compressed.jpg')
            img.save(temp_path, "JPEG", quality=50, optimize=True, progressive=True)
            os.replace(temp_path, image_path)
            print(f"Compressed and replaced: {image_path}")
        except Exception as e:
            print(f"Compression failed for {image_path}: {e}\n{traceback.format_exc()}")

    def update_ui_with_scanned_documents(self, scanned_files):
        try:
            print("Updating UI with scanned documents.")
            for path in scanned_files:
                self.document_manager.documents_paths.append(path)
                self.ui_manager.document_list.addItem(self.document_manager.format_display_name(path))
                self.document_manager.update_document_image(path)
            print("UI update complete.")
        except Exception as e:
            print(f"UI update error: {e}\n{traceback.format_exc()}")

    def _show_message(self, title, message, icon):
        QMessageBox(icon, title, message, QMessageBox.Ok, self.ui_manager).exec_()

    def _close_scanning_dialog(self):
        if hasattr(self, 'scanning_dialog'):
            self.scanning_dialog.accept()

    def _clean_old_scan_folders(self, base_dir, keep=None):
        if not os.path.exists(base_dir):
            return

        for entry in os.listdir(base_dir):
            path = os.path.join(base_dir, entry)
            if path == keep or not os.path.isdir(path):
                continue
            try:
                shutil.rmtree(path)
                print(f"Cleaned old scan folder: {path}")
            except Exception as e:
                print(f"Skipped folder (in use?): {path} | {e}")


# noinspection PyUnresolvedReferences
class SendFax(UIManager):
    def __init__(self, main_window=None, parent=None):
        try:
            super().__init__(main_window, parent)
            self.save_manager = SaveManager(self.main_window)
            self.log_system = SystemLog()
            self.document_manager = DocumentManager(self)
            self.fax_sender = FaxSender(self, self.document_manager, self.save_manager)
            self.scanner_manager = ScannerManager(self, self.document_manager)

            self.setup_connections()
            self.populate_caller_id_combo_box()
            self.clear_document_list()
        except Exception as e:
            print(f"Initialization error: {e}\n{traceback.format_exc()}")

    def setup_connections(self):
        """Connect UI elements to their corresponding slots."""
        try:
            self.caller_id_combo.currentIndexChanged.connect(self.populate_area_code)
            self.document_button.clicked.connect(self.document_manager.attach_document)
            self.scan_button.clicked.connect(self.scanner_manager.scan_document)
            self.send_button.clicked.connect(self.fax_sender.send_fax)
            self.cancel_button.clicked.connect(self.close)
            self.document_list.customContextMenuRequested.connect(self.show_document_context_menu)
            self.document_list.itemClicked.connect(self.display_document_image)
        except Exception as e:
            print(f"Setup connections error: {e}\n{traceback.format_exc()}")

    def show_document_context_menu(self, pos):
        """Show context menu for document removal."""
        try:
            item = self.document_list.itemAt(pos)
            if item:
                menu = QMenu(self)
                remove_action = QAction("Remove Document", self)
                remove_action.triggered.connect(self.document_manager.remove_document)
                menu.addAction(remove_action)
                menu.exec_(self.document_list.mapToGlobal(pos))
        except Exception as e:
            print(f"Show document context menu error: {e}\n{traceback.format_exc()}")

    def display_document_image(self):
        """Update preview when a document is selected."""
        try:
            item = self.document_list.currentItem()
            if item:
                index = self.document_list.row(item)
                path = self.document_manager.documents_paths[index]
                self.document_manager.update_document_image(path)
        except Exception as e:
            print(f"Display document image error: {e}\n{traceback.format_exc()}")

    def populate_caller_id_combo_box(self):
        """Populate the caller ID combo box from saved config."""
        try:
            all_fax_numbers = self.save_manager.get_config_value('Account', 'all_numbers')
            if not all_fax_numbers:
                return

            numbers = [num.strip() for num in all_fax_numbers.split(',') if num.strip()]
            formatted_numbers = [self.main_window.format_phone_number(num) for num in numbers]

            self.caller_id_combo.clear()
            self.caller_id_combo.addItems(formatted_numbers)

            if len(formatted_numbers) == 1:
                self.caller_id_combo.setCurrentIndex(0)
        except Exception as e:
            print(f"Populate caller ID combo box error: {e}\n{traceback.format_exc()}")

    def populate_area_code(self):
        """Auto-fill the area code from selected caller ID."""
        try:
            text = self.caller_id_combo.currentText()
            if '(' in text and ')' in text:
                area_code = text[text.find('(') + 1:text.find(')')]
                self.area_code_input.setText(area_code)
        except Exception as e:
            print(f"Populate area code error: {e}\n{traceback.format_exc()}")

    def clear_document_list(self):
        super().clear_document_list()
        self.scan_session_counter = 0  # Reset per fax
        self.scanner_manager.directory = None  # Reset directory for each fax
