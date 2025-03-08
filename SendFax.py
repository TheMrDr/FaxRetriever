import os
import shutil
import sys
import tempfile
import threading

import pyinsane2
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import requests
from PIL import Image, ImageDraw
from pypdf import PdfReader, PdfWriter
from PyQt5 import QtGui, QtCore
from PyQt5.QtCore import pyqtSignal, Qt, QObject
from PyQt5.QtGui import QPixmap, QImage, QPainter, QTransform, QMovie
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QInputDialog,
                             QComboBox, QListWidget, QGridLayout, QMessageBox, QMenu, QAction, QHBoxLayout, QGraphicsView,
                             QGraphicsScene, QGraphicsPixmapItem, QProgressBar)
from docx import Document

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
            self.setup_ui()
            self.current_page_index = 0

            self.caller_id_label.setFont(QtGui.QFont("Arial", 12, QtGui.QFont.Bold))
            self.caller_id_combo.setFont(QtGui.QFont("Arial", 12))
            self.caller_id_combo.setMinimumHeight(35)

            font = QtGui.QFont("Arial", 14, QtGui.QFont.Bold)
            self.destination_label.setFont(font)
            self.phone_label.setFont(font)
            self.area_code_input.setFont(font)
            self.first_three_input.setFont(font)
            self.last_four_input.setFont(font)
            self.document_label.setFont(font)
            self.document_button.setFont(font)
            self.preview_label.setFont(font)
            self.document_preview.setFont(font)
            self.scan_button.setFont(font)
            self.prev_page_button.setFont(font)
            self.next_page_button.setFont(font)

            self.area_code_input.setMinimumHeight(40)
            self.first_three_input.setMinimumHeight(40)
            self.last_four_input.setMinimumHeight(40)

            self.document_button.setFont(QtGui.QFont("Arial", 12))
            self.scan_button.setFont(QtGui.QFont("Arial", 12))
            self.prev_page_button.setFont(QtGui.QFont("Arial", 12))
            self.next_page_button.setFont(QtGui.QFont("Arial", 12))
            self.document_button.setMinimumHeight(40)
            self.scan_button.setMinimumHeight(40)
            self.prev_page_button.setMinimumHeight(40)
            self.next_page_button.setMinimumHeight(40)

            self.document_preview.setFixedSize(400, 400)  # Increase preview size

            self.send_button.setFont(QtGui.QFont("Arial", 14, QtGui.QFont.Bold))
            self.send_button.setMinimumHeight(50)
            self.send_button.setStyleSheet("background-color: #2a81dc; color: white; border-radius: 10px;")

            self.cancel_button.setFont(QtGui.QFont("Arial", 14))
            self.cancel_button.setMinimumHeight(50)
            self.cancel_button.setStyleSheet("background-color: #dc2a2a; color: white; border-radius: 10px;")

            self.send_button.setToolTip("Click to send the fax.")
            self.cancel_button.setToolTip("Cancel and return to the main menu.")

            self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
            self.setWindowFlags(Qt.Window | Qt.WindowTitleHint | Qt.CustomizeWindowHint | Qt.MSWindowsFixedSizeDialogHint)

        except Exception as e:
            print(f"Initialization error: {e}")

    def setup_ui(self):
        try:
            layout = QVBoxLayout(self)
            self.setup_caller_id_section(layout)
            self.setup_destination_number_section(layout)
            self.setup_document_section(layout)
            self.setup_action_buttons(layout)
        except Exception as e:
            print(f"Setup UI error: {e}")


    def setup_caller_id_section(self, layout):
        try:
            self.caller_id_label = QLabel("Faxing From:")
            self.caller_id_combo = QComboBox()
            layout.addWidget(self.caller_id_label)
            layout.addWidget(self.caller_id_combo)
        except Exception as e:
            print(f"Setup caller ID section error: {e}")

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
            self.add_contact_button.setIcon(QtGui.QIcon(os.path.join("images", "AddContact.png")))
            self.add_contact_button.setIconSize(QtCore.QSize(30, 30))  # Scale icon inside the button
            self.add_contact_button.setFixedSize(40, 40)  # Ensures button is square
            self.add_contact_button.setToolTip("Add Contact")
            self.add_contact_button.clicked.connect(self.open_add_contact_dialog)

            self.address_book_button = QPushButton()
            self.address_book_button.setIcon(QtGui.QIcon(os.path.join("images", "AddressBook.png")))
            self.address_book_button.setIconSize(QtCore.QSize(30, 30))
            self.address_book_button.setFixedSize(40, 40)
            self.address_book_button.setToolTip("Address Book")
            self.address_book_button.clicked.connect(self.open_address_book_dialog)

            grid_layout.addWidget(self.phone_label, 0, 0)
            grid_layout.addWidget(self.area_code_input, 0, 1)
            grid_layout.addWidget(QLabel(")"), 0, 2)
            grid_layout.addWidget(self.first_three_input, 0, 3)
            grid_layout.addWidget(QLabel("-"), 0, 4)
            grid_layout.addWidget(self.last_four_input, 0, 5)
            grid_layout.addWidget(self.add_contact_button, 0, 6)
            grid_layout.addWidget(self.address_book_button, 0, 7)

            # Connect field transitions
            self.area_code_input.textChanged.connect(
                lambda: self.focus_next(self.area_code_input, self.first_three_input))
            self.first_three_input.textChanged.connect(
                lambda: self.focus_next(self.first_three_input, self.last_four_input))
        except Exception as e:
            print(f"Setup destination number section error: {e}")

    def focus_next(self, current_widget, next_widget):
        try:
            if len(current_widget.text()) == current_widget.maxLength():
                next_widget.setFocus()
        except Exception as e:
            print(f"Focus next error: {e}")

    def open_add_contact_dialog(self):
        dialog = AddContactDialog(self.address_book_manager, self)
        dialog.exec_()

    def open_address_book_dialog(self):
        dialog = AddressBookDialog(self.address_book_manager, self)
        dialog.exec_()

    def populate_phone_fields(self, phone):
        phone = phone.replace(" ", "").replace("(", "").replace(")", "").replace("-", "")
        if len(phone) == 10:
            self.area_code_input.setText(phone[:3])
            self.first_three_input.setText(phone[3:6])
            self.last_four_input.setText(phone[6:])


    def setup_document_section(self, layout):
        try:
            h_layout = QHBoxLayout()

            # Left side: list and attach/scan buttons.
            v_layout = QVBoxLayout()
            self.document_label = QLabel("Attached Documents:")
            self.document_list = QListWidget()
            self.document_list.setContextMenuPolicy(Qt.CustomContextMenu)
            document_buttons_layout = QHBoxLayout()
            self.document_button = QPushButton("Attach Document")
            self.scan_button = QPushButton("Scan Document")
            document_buttons_layout.addWidget(self.document_button)
            document_buttons_layout.addWidget(self.scan_button)
            v_layout.addWidget(self.document_label)
            v_layout.addWidget(self.document_list)
            v_layout.addLayout(document_buttons_layout)
            h_layout.addLayout(v_layout)

            # Right side: preview with navigation.
            preview_layout = QVBoxLayout()
            # Add a heading for Image Preview
            self.preview_label = QLabel("Image Preview")
            self.preview_label.setAlignment(Qt.AlignLeft)  # Align with "Attached Documents"
            preview_layout.addWidget(self.preview_label)

            nav_buttons_layout = QHBoxLayout()
            self.prev_page_button = QPushButton("<")
            self.next_page_button = QPushButton(">")
            nav_buttons_layout.addWidget(self.prev_page_button)
            nav_buttons_layout.addWidget(self.next_page_button)

            # Replace the QLabel preview with our zoomable preview widget.
            self.document_preview = DocumentPreviewWidget()
            self.document_preview.setFixedSize(400, 400)  # Adjust preview size as needed

            preview_layout.addWidget(self.document_preview)
            preview_layout.addLayout(nav_buttons_layout)
            h_layout.addLayout(preview_layout)
            layout.addLayout(h_layout)

            # Connect navigation buttons.
            self.prev_page_button.clicked.connect(self.show_previous_page)
            self.next_page_button.clicked.connect(self.show_next_page)

            # When the user selects a document from the list, reset the page index.
            self.document_list.itemSelectionChanged.connect(self.document_selection_changed)
        except Exception as e:
            print(f"Setup document section error: {e}")

    def document_selection_changed(self):
        # When a new document is selected, reset the preview to page 0.
        self.current_page_index = 0
        selected_items = self.document_list.selectedItems()
        if selected_items:
            # Retrieve the full file path (assumed to be stored in DocumentManager.documents_paths)
            index = self.document_list.row(selected_items[0])
            doc_path = self.document_manager.documents_paths[index]
            self.document_manager.update_image_label(doc_path, self.document_preview, page=self.current_page_index)

    def show_previous_page(self):
        # Decrement page index and update preview if possible.
        if self.current_page_index > 0:
            self.current_page_index -= 1
            selected_items = self.document_list.selectedItems()
            if selected_items:
                index = self.document_list.row(selected_items[0])
                doc_path = self.document_manager.documents_paths[index]
                self.document_manager.update_image_label(doc_path, self.document_preview, page=self.current_page_index)

    def show_next_page(self):
        # Increment page index if the document has additional pages.
        selected_items = self.document_list.selectedItems()
        if selected_items:
            index = self.document_list.row(selected_items[0])
            doc_path = self.document_manager.documents_paths[index]
            num_pages = self.document_manager.get_page_count(doc_path)
            if self.current_page_index < num_pages - 1:
                self.current_page_index += 1
                self.document_manager.update_image_label(doc_path, self.document_preview, page=self.current_page_index)

    def setup_action_buttons(self, layout):
        try:
            self.send_button = QPushButton("Send Fax")
            self.cancel_button = QPushButton("Cancel")
            layout.addWidget(self.send_button)
            layout.addWidget(self.cancel_button)
        except Exception as e:
            print(f"Setup action buttons error: {e}")

    def closeEvent(self, event):
        """Override the close event to clear the document list, destination number fields, and prevent crashes."""
        self.clear_document_list()

        # Clear destination number fields
        self.area_code_input.clear()
        self.first_three_input.clear()
        self.last_four_input.clear()

        # Explicitly reset the preview image before closing
        self.pixmap_item = None

        # Reset the Area Code on the Fax window
        self.populate_area_code()

        super().closeEvent(event)

    def clear_document_list(self):
        """Clear the document list and reset the document preview widget"""
        self.document_list.clear()
        self.document_preview.scene.clear()


class DocumentManager:
    def __init__(self, ui_manager):
        try:
            self.ui_manager = ui_manager
            self.cover_sheet_path = None
            # We'll store paths to our normalized (or original, for DOCX) documents.
            self.documents_paths = []
        except Exception as e:
            print(f"Initialization error: {e}")

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
            if files:
                for file in files:
                    converted = self.convert_to_pdf(file)
                    if converted:
                        self.documents_paths.append(converted)
                        self.ui_manager.document_list.addItem(self.format_display_name(file))
                        self.update_document_image(converted)
        except Exception as e:
            print(f"Attach document error: {e}")

    def remove_document(self):
        try:
            selected_items = self.ui_manager.document_list.selectedItems()
            if not selected_items:
                return
            for item in selected_items:
                index = self.ui_manager.document_list.row(item)
                # Remove the temporary file only if it's a converted PDF.
                temp_file = self.documents_paths[index]
                if os.path.exists(temp_file) and temp_file.endswith('.pdf'):
                    os.remove(temp_file)
                del self.documents_paths[index]
                self.ui_manager.document_list.takeItem(index)
                if self.documents_paths:
                    self.update_document_image(self.documents_paths[0])
                else:
                    self.ui_manager.document_image_label.clear()
        except Exception as e:
            print(f"Remove document error: {e}")

    def format_display_name(self, filepath):
        try:
            base_name = os.path.basename(filepath)
            if len(base_name) > 30:
                return f"{base_name[:15]}...{base_name[-10:]}"
            return base_name
        except Exception as e:
            print(f"Format display name error: {e}")
            return filepath

    def update_document_image(self, filepath):
        try:
            if filepath:
                # Reload the (possibly converted) PDF for preview.
                self.update_image_label(filepath, self.ui_manager.document_image_label)
            else:
                self.ui_manager.document_image_label.clear()
        except Exception as e:
            print(f"Update document image error: {e}")

    def update_image_label(self, filepath, preview_widget, page=0):
        try:
            # For PDFs, load the specified page.
            if filepath.lower().endswith('.pdf'):
                import fitz
                doc = fitz.open(filepath)
                if page < 0 or page >= doc.page_count:
                    page = 0
                page_obj = doc.load_page(page)
                pix = page_obj.get_pixmap()
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                pixmap = QPixmap.fromImage(image)
            # For DOC/DOCX files, load the DOCX icon.
            elif filepath.lower().endswith(('.doc', '.docx')):
                # Adjust the path as necessary (relative to your application's root or resource folder)
                docx_icon_path = os.path.join("images", "docx.png")
                pixmap = QPixmap(docx_icon_path)
            else:
                # For other file types, load the image directly.
                pixmap = QPixmap(filepath)

            # Use the preview widget's method if available.
            if hasattr(preview_widget, "set_pixmap"):
                preview_widget.set_pixmap(pixmap)
            else:
                preview_widget.setPixmap(pixmap.scaled(preview_widget.size(), Qt.KeepAspectRatio))
        except Exception as e:
            print(f"Failed to load image: {str(e)}")
            if hasattr(preview_widget, "scene"):
                preview_widget.scene.clear()
            else:
                preview_widget.clear()

    def get_page_count(self, filepath):
        # For PDFs, use fitz to get the number of pages.
        if filepath.lower().endswith('.pdf'):
            import fitz
            doc = fitz.open(filepath)
            return doc.page_count
        # For other types, assume a single page.
        return 1

    def convert_to_pdf(self, filepath):
        """
        Converts the input file to a high-quality, portrait-oriented PDF when possible.
        For DOC and DOCX files, we handle them as delivered and display a warning.
        Returns the path to the temporary PDF file or the original filepath if not converted.
        """
        try:
            ext = os.path.splitext(filepath)[1].lower()
            if ext == '.pdf':
                # Normalize the existing PDF.
                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)
                self.normalize_pdf_to_portrait(filepath, temp_path)
                return temp_path
            elif ext in ['.doc', '.docx']:
                # Instead of converting, warn the user and return the original file.
                QMessageBox.warning(
                    self.ui_manager,
                    "Document Warning",
                    "DOC/DOCX files will be sent as-is. Please verify that the orientation is correct before sending."
                )
                return filepath
            elif ext in ['.jpg', '.jpeg', '.png', '.tif', '.tiff']:
                # Convert image to PDF using PIL.
                with Image.open(filepath) as img:
                    img = img.convert('RGB')
                    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                    os.close(temp_fd)
                    img.save(temp_path, 'PDF', resolution=100.0)
                    return temp_path
            elif ext == '.txt':
                # Use ReportLab to generate a PDF from text.
                temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                os.close(temp_fd)
                c = canvas.Canvas(temp_path, pagesize=letter)
                with open(filepath, 'r', encoding='utf-8') as f:
                    text = f.read()
                # Write the text; for a real-world scenario, implement proper pagination.
                c.drawString(10, 750, text)
                c.save()
                return temp_path
            else:
                print(f"Unsupported file type: {ext}")
                return None
        except Exception as e:
            print(f"Error converting file {filepath} to PDF: {e}")
            return None

    def normalize_pdf_to_portrait(self, input_pdf_path, output_pdf_path):
        """
        Reads the PDF at input_pdf_path, rotates any landscape pages
        so that they are in portrait orientation, and writes the result
        to output_pdf_path.
        """
        try:
            reader = PdfReader(input_pdf_path)
            writer = PdfWriter()
            for page in reader.pages:
                width = float(page.mediabox.width)
                height = float(page.mediabox.height)
                if width > height:
                    page.rotate_clockwise(90)
                writer.add_page(page)
            with open(output_pdf_path, 'wb') as f:
                writer.write(f)
        except Exception as e:
            print(f"Error normalizing PDF: {e}")


class DocumentPreviewWidget(QGraphicsView):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)
        self.pixmap_item = None
        self._hover_zoom = 2.0  # Zoom factor when the mouse is over the widget
        self.setMouseTracking(True)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)

    def set_pixmap(self, pixmap):
        """Set the pixmap to display and fit it into the view."""
        self.scene.clear()
        self.pixmap_item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(self.pixmap_item)
        self.setSceneRect(self.pixmap_item.boundingRect())
        self.fit_image()

    def fit_image(self):
        """Scale the view so that the entire pixmap_item fits into the viewport."""
        if hasattr(self, "pixmap_item") and self.pixmap_item and not self.pixmap_item.scene() is None:
            # This call automatically scales the view to keep the pixmap in view.
            self.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def enterEvent(self, event):
        # When the mouse enters, zoom in by applying a hover zoom factor.
        if self.pixmap_item:
            # Save the fitted transformation before zooming
            current_transform = self.transform()
            # Apply an extra zoom on top of the fitted view.
            self.setTransform(QTransform().scale(self._hover_zoom, self._hover_zoom))
        super().enterEvent(event)

    def leaveEvent(self, event):
        # When the mouse leaves, revert to the full-fit view only if the item still exists.
        if hasattr(self, "pixmap_item") and self.pixmap_item and not self.pixmap_item.scene() is None:
            self.fit_image()

        super().leaveEvent(event)

    def mouseMoveEvent(self, event):
        # Pan the view so that the area under the cursor stays centered.
        scene_pos = self.mapToScene(event.pos())
        self.centerOn(scene_pos)
        super().mouseMoveEvent(event)



class FaxSender:
    def __init__(self, ui_manager, document_manager, encryption_manager):
        try:
            self.ui_manager = ui_manager
            self.document_manager = document_manager
            self.encryption_manager = encryption_manager
        except Exception as e:
            print(f"Initialization error: {e}")

    def send_fax(self):
        try:
            fax_user = self.encryption_manager.get_config_value('Account', 'fax_user')
            token = self.encryption_manager.get_config_value('Token', 'access_token')
            caller_id = self.ui_manager.caller_id_combo.currentText().strip()
            destination = ('1' + self.ui_manager.area_code_input.text() +
                           self.ui_manager.first_three_input.text() +
                           self.ui_manager.last_four_input.text())
            url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
            headers = {"Authorization": f"Bearer {token}"}
            files = {}
            data = {"caller_id": caller_id, "destination": destination}

            temp_files = []  # to keep track of temporary files

            for idx, doc_path in enumerate(self.document_manager.documents_paths):
                file_extension = os.path.splitext(doc_path)[1].lower()
                # Process PDFs to ensure portrait orientation
                if file_extension == '.pdf':
                    # Create a temporary file for the normalized PDF
                    temp_fd, temp_path = tempfile.mkstemp(suffix='.pdf')
                    os.close(temp_fd)  # we will write to this path
                    self.normalize_pdf_to_portrait(doc_path, temp_path)
                    doc_to_send = temp_path
                    temp_files.append(temp_path)
                    mime_type = 'application/pdf'
                else:
                    doc_to_send = doc_path
                    mime_type = 'image/' + file_extension.strip('.')

                file_key = f'filename[{idx + 1}]' if self.document_manager.cover_sheet_path else f'filename[{idx}]'
                files[file_key] = (os.path.basename(doc_to_send), open(doc_to_send, 'rb'), mime_type)

            try:
                response = requests.post(url, files=files, data=data, headers=headers)
                if response.status_code == 200:
                    QMessageBox.information(self.ui_manager, "Fax Sent", "Your fax has been queued successfully.")
                    self.ui_manager.accept()
                else:
                    QMessageBox.critical(self.ui_manager, "Sending Failed", f"Failed to send fax: {response.text}")
            except Exception as e:
                QMessageBox.critical(self.ui_manager, "Error", f"An error occurred: {str(e)}")
            finally:
                for _, file_tuple in files.items():
                    file_tuple[1].close()
                # Clean up temporary files
                for temp_file in temp_files:
                    os.remove(temp_file)
        except Exception as e:
            print(f"Send fax error: {e}")
            QMessageBox.critical(self.ui_manager, "Error",
                                 f"An error occurred while preparing to send the fax: {str(e)}")

    def normalize_pdf_to_portrait(self, input_pdf_path, output_pdf_path):
        reader = PdfReader(input_pdf_path)
        writer = PdfWriter()
        for page in reader.pages:
            width = float(page.mediabox.width)
            height = float(page.mediabox.height)
            if width > height:
                page.rotate_clockwise(90)
            writer.add_page(page)
        with open(output_pdf_path, 'wb') as f:
            writer.write(f)


class ScanningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scanning Document")
        self.setFixedSize(300, 150)
        self.setWindowFlags(Qt.Dialog | Qt.WindowTitleHint | Qt.CustomizeWindowHint)
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

        # Add an animated GIF
        self.icon_label = QLabel(self)
        self.scanner_animation = QMovie(os.path.join(bundle_dir, "images", "scanner.gif"))  # Use your GIF file
        self.icon_label.setMovie(self.scanner_animation)
        self.icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.icon_label)

        # Start the animation
        self.scanner_animation.start()

        # Status Label
        self.label = QLabel("Scanning, please wait...", self)
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        # Progress Bar
        self.progress_bar = QProgressBar(self)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
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

        self.scan_started.connect(self._init_scanner)
        self.scan_finished.connect(self.update_ui_with_scanned_documents)
        self.show_message.connect(self._show_message)
        self.scanning_dialog_closed.connect(self._close_scanning_dialog)

    def scan_document(self):
        self.scanning_dialog = ScanningDialog(self.ui_manager)
        self.scanning_dialog.show()
        self.scan_started.emit()
        threading.Thread(target=self._scan_document_thread).start()

    def _init_scanner(self):
        try:
            pyinsane2.init()  # Try initializing WIA first

            devices = pyinsane2.get_devices()
            if devices:
                print(f"Found {len(devices)} WIA scanner(s).")
                return  # Exit if WIA is working

            # If no WIA scanners are found, reinitialize for TWAIN
            print("No WIA devices found, switching to TWAIN mode...")
            pyinsane2.exit()  # Shut down WIA
            pyinsane2.init(driver="twain")  # Reinitialize for TWAIN

            devices = pyinsane2.get_devices()
            if devices:
                print(f"Found {len(devices)} TWAIN scanner(s).")
                return  # Exit if TWAIN is working

            # If no devices are found in either mode, notify user
            self.show_message.emit(
                "No Scanner Found",
                "No scanners were detected. Ensure your scanner is connected and powered on.",
                QMessageBox.Warning,
            )

        except Exception as e:
            print(f"Scanner Initialization Error: {e}")
            self.show_message.emit(
                "Scanner Error",
                f"An error occurred while initializing the scanner: {str(e)}",
                QMessageBox.Critical,
            )

    def _scan_document_thread(self):
        with self.lock:
            scanned_files = []
            try:
                devices = pyinsane2.get_devices()
                if not devices:
                    self.show_message.emit("No Scanner Found", "No scanners were found on your system.", QMessageBox.Warning)
                    self.scanning_dialog_closed.emit()
                    return

                if len(devices) > 1:
                    device_names = [device.model for device in devices]  # Use model name for display
                    scanner_model, ok = QInputDialog.getItem(self.ui_manager, "Select Scanner", "Available Scanners:", device_names, 0, False)
                    if not ok:
                        self.scanning_dialog_closed.emit()
                        return
                    scanner = next(device for device in devices if device.model == scanner_model)
                else:
                    scanner = devices[0]

                print(f"Selected scanner: {scanner.model}")

                self._set_scanner_options(scanner)

                scan_session = scanner.scan(multiple=True)

                directory = os.path.join(os.getcwd(), "Scanned Docs")
                if not os.path.exists(directory):
                    os.makedirs(directory)
                else:
                    shutil.rmtree(directory)
                    os.makedirs(directory)
                print(f"Directory created at: {directory}")

                while True:
                    try:
                        scan_session.scan.read()
                    except EOFError:
                        print(f"Got page {len(scan_session.images)}")
                        if scan_session.images:
                            image = scan_session.images[-1]
                            scanned_image_path = os.path.join(directory, f"scanned_document_page_{len(scan_session.images)}.jpg")
                            image.save(scanned_image_path, 'JPEG')
                            print(f"Image saved at: {scanned_image_path}")
                            self._compress_image(scanned_image_path)
                            scanned_files.append(scanned_image_path)
                    except StopIteration:
                        print(f"Got {len(scan_session.images)} pages")
                        break
                    except Exception as e:
                        print(f"Error reading scan: {str(e)}")
                        break

                print(f"Finished scanning. Total pages: {len(scanned_files)}")

                if not scanned_files:
                    self.show_message.emit("Scan Error", "No images were scanned.", QMessageBox.Warning)
                    return

            except (pyinsane2.WIAException, pyinsane2.SaneException, Exception) as e:
                print(f"Scan Error: {str(e)}")
                self.show_message.emit("Scan Error", f"An error occurred during scanning: {str(e)}", QMessageBox.Critical)
            finally:
                self.scan_finished.emit(scanned_files)
                self.scanning_dialog_closed.emit()

    def _set_scanner_options(self, scanner):
        def set_option(option_name, value):
            if option_name in scanner.options:
                try:
                    scanner.options[option_name].value = value
                    print(f"Set {option_name} to {value}")
                except Exception as e:
                    print(f"Failed to set {option_name}: {str(e)}")

        try:
            if 'resolution' in scanner.options:
                set_option('resolution', 200)
            if 'mode' in scanner.options:
                set_option('mode', 'Color')
            if 'tl-x' in scanner.options and 'tl-y' in scanner.options and 'br-x' in scanner.options and 'br-y' in scanner.options:
                set_option('tl-x', 0)
                set_option('tl-y', 0)
                set_option('br-x', 1701)  # Approximate Letter size in pixels at 200 DPI
                set_option('br-y', 2197)  # Approximate Letter size in pixels at 200 DPI
            elif 'page_size' in scanner.options:
                set_option('page_size', 'a4')
            if 'source' in scanner.options:
                source_options = scanner.options['source'].constraint
                if 'ADF Duplex' in source_options:
                    set_option('source', 'ADF Duplex')
                elif 'ADF' in source_options:
                    set_option('source', 'ADF')
                elif len(source_options) > 1:
                    source_name, ok = QInputDialog.getItem(self.ui_manager, "Select Source", "Available Sources:", source_options, 0, False)
                    if not ok:
                        return
                    set_option('source', source_name)
                else:
                    set_option('source', source_options[0])
            if 'blank_page' in scanner.options:
                set_option('blank_page', True)
        except Exception as e:
            print(f"Set scanner options error: {e}")

    def _compress_image(self, image_path):
        try:
            img = Image.open(image_path)
            img = img.convert('L')  # Convert to grayscale
            compressed_image_path = os.path.splitext(image_path)[0] + "_compressed.jpg"
            img.save(compressed_image_path, "JPEG", quality=50, optimize=True, progressive=True)  # Lower quality and add progressive option
            os.replace(compressed_image_path, image_path)  # Replace original image with compressed one
            print(f"Original image saved at: {image_path}")
            print(f"Compressed image saved at: {image_path}")
        except Exception as e:
            print(f"Failed to compress image: {str(e)}")

    def update_ui_with_scanned_documents(self, scanned_files):
        try:
            print("Updating UI with scanned documents.")
            for scanned_image_path in scanned_files:
                print(f"Adding {scanned_image_path} to document list.")
                self.document_manager.documents_paths.append(scanned_image_path)
                self.ui_manager.document_list.addItem(self.document_manager.format_display_name(scanned_image_path))
                self.document_manager.update_document_image(scanned_image_path)
            print("Completed UI update with scanned documents.")
        except Exception as e:
            print(f"Error updating UI with scanned documents: {e}")

    def _show_message(self, title, message, icon):
        QMessageBox(icon, title, message, QMessageBox.Ok, self.ui_manager).exec_()

    def _close_scanning_dialog(self):
        self.scanning_dialog.accept()


# noinspection PyUnresolvedReferences
class SendFax(UIManager):
    def __init__(self, main_window=None, parent=None):
        try:
            super().__init__(main_window, parent)
            self.encryption_manager = SaveManager(self.main_window)
            self.log_system = SystemLog()
            self.document_manager = DocumentManager(self)
            self.fax_sender = FaxSender(self, self.document_manager, self.encryption_manager)
            self.scanner_manager = ScannerManager(self, self.document_manager)
            self.setup_connections()
            self.populate_caller_id_combo_box()
            self.clear_document_list()
        except Exception as e:
            print(f"Initialization error: {e}")

    def setup_connections(self):
        try:
            self.caller_id_combo.currentIndexChanged.connect(self.populate_area_code)
            self.document_button.clicked.connect(self.document_manager.attach_document)
            self.scan_button.clicked.connect(self.scanner_manager.scan_document)
            self.send_button.clicked.connect(self.fax_sender.send_fax)
            self.cancel_button.clicked.connect(self.close)
            self.document_list.customContextMenuRequested.connect(self.show_document_context_menu)
            self.document_list.itemClicked.connect(self.display_document_image)
        except Exception as e:
            print(f"Setup connections error: {e}")

    def show_document_context_menu(self, pos):
        try:
            document_item = self.document_list.itemAt(pos)
            if document_item:
                menu = QMenu()
                remove_action = QAction("Remove Document", self)
                remove_action.triggered.connect(self.document_manager.remove_document)
                menu.addAction(remove_action)
                menu.exec_(self.document_list.mapToGlobal(pos))
        except Exception as e:
            print(f"Show document context menu error: {e}")

    def display_document_image(self):
        try:
            item = self.document_list.currentItem()
            if item:
                index = self.document_list.row(item)
                self.document_manager.update_document_image(self.document_manager.documents_paths[index])
        except Exception as e:
            print(f"Display document image error: {e}")

    def populate_caller_id_combo_box(self):
        try:
            # Retrieve all fax numbers stored in the configuration
            all_fax_numbers = self.encryption_manager.get_config_value('Account', 'all_numbers')

            if all_fax_numbers:
                # Split the stored string by commas to get individual numbers
                numbers = all_fax_numbers.split(',')

                # Format each number before adding it to the combo box
                formatted_numbers = [self.main_window.format_phone_number(num) for num in numbers]

                # Add each formatted number to the combo box
                for number in formatted_numbers:
                    self.caller_id_combo.addItem(number.strip())  # Ensure to strip any whitespace

                # Automatically select the first number if there's only one
                if len(numbers) == 1:
                    self.caller_id_combo.setCurrentIndex(0)
        except Exception as e:
            print(f"Populate caller ID combo box error: {e}")

    def populate_area_code(self):
        try:
            if self.caller_id_combo.currentIndex() != -1:
                selected_number = self.caller_id_combo.currentText()
                area_code = selected_number[selected_number.find('(') + 1:selected_number.find(')')]
                self.area_code_input.setText(area_code)
        except Exception as e:
            print(f"Populate area code error: {e}")
