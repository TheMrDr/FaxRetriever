import os
import pyinsane2
import shutil
import sys
import requests

from PIL import Image

from PyQt5 import QtGui
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QPixmap, QImage, QPainter
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog, QInputDialog,
                             QComboBox, QListWidget, QGridLayout, QMessageBox, QMenu, QAction, QHBoxLayout)

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
        self.main_window = main_window
        self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
        self.setWindowTitle("Send Fax")
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        self.setup_caller_id_section(layout)
        self.setup_destination_number_section(layout)
        self.setup_cover_sheet_section(layout)
        self.setup_document_section(layout)
        self.setup_action_buttons(layout)

    def setup_caller_id_section(self, layout):
        self.caller_id_label = QLabel("Faxing From:")
        self.caller_id_combo = QComboBox()
        layout.addWidget(self.caller_id_label)
        layout.addWidget(self.caller_id_combo)

    def setup_destination_number_section(self, layout):
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
        grid_layout.addWidget(self.phone_label, 0, 0)
        grid_layout.addWidget(self.area_code_input, 0, 1)
        grid_layout.addWidget(QLabel(")"), 0, 2)
        grid_layout.addWidget(self.first_three_input, 0, 3)
        grid_layout.addWidget(QLabel("-"), 0, 4)
        grid_layout.addWidget(self.last_four_input, 0, 5)

        # Connect field transitions
        self.area_code_input.textChanged.connect(
            lambda: self.focus_next(self.area_code_input, self.first_three_input))
        self.first_three_input.textChanged.connect(
            lambda: self.focus_next(self.first_three_input, self.last_four_input))

    def focus_next(self, current_widget, next_widget):
        if len(current_widget.text()) == current_widget.maxLength():
            next_widget.setFocus()

    def setup_cover_sheet_section(self, layout):
        h_layout = QHBoxLayout()

        # Left side for list and buttons
        v_layout = QVBoxLayout()
        self.cover_sheet_label = QLabel("Select or Upload a Cover Sheet:")
        self.cover_sheet_list = QListWidget()
        self.cover_sheet_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cover_sheet_button = QPushButton("Add Cover Sheet")
        self.scan_cover_sheet_button = QPushButton("Scan Cover Sheet")
        cover_sheet_buttons_layout = QHBoxLayout()
        cover_sheet_buttons_layout.addWidget(self.cover_sheet_button)
        cover_sheet_buttons_layout.addWidget(self.scan_cover_sheet_button)
        v_layout.addWidget(self.cover_sheet_label)
        v_layout.addWidget(self.cover_sheet_list)
        v_layout.addLayout(cover_sheet_buttons_layout)
        h_layout.addLayout(v_layout)

        # Right side for image
        self.cover_sheet_image_label = QLabel()
        self.cover_sheet_image_label.setFixedSize(200, 200)  # Adjust size as needed
        self.cover_sheet_image_label.setStyleSheet("border: 1px solid black;")
        h_layout.addWidget(self.cover_sheet_image_label)

        layout.addLayout(h_layout)

    def setup_document_section(self, layout):
        h_layout = QHBoxLayout()

        # Left side for list and buttons
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

        # Right side for image
        self.document_image_label = QLabel()
        self.document_image_label.setFixedSize(200, 200)  # Adjust size as needed
        self.document_image_label.setStyleSheet("border: 1px solid black;")
        h_layout.addWidget(self.document_image_label)

        layout.addLayout(h_layout)

    def setup_action_buttons(self, layout):
        self.send_button = QPushButton("Send Fax")
        self.cancel_button = QPushButton("Cancel")
        layout.addWidget(self.send_button)
        layout.addWidget(self.cancel_button)


class DocumentManager:
    def __init__(self, ui_manager):
        self.ui_manager = ui_manager
        self.cover_sheet_path = None
        self.documents_paths = []

    def attach_or_change_cover_sheet(self):
        options = QFileDialog.Options()
        filename, _ = QFileDialog.getOpenFileName(self.ui_manager, "Select a cover sheet", "", "Documents (*.pdf *.doc *.docx *.jpg *.png *.tif *.tiff *.txt)", options=options)
        if filename:
            self.cover_sheet_path = filename
            self.ui_manager.cover_sheet_list.clear()
            self.ui_manager.cover_sheet_list.addItem(self.format_display_name(filename))
            self.update_cover_sheet_image(filename)

    def remove_cover_sheet(self):
        self.cover_sheet_path = None
        self.ui_manager.cover_sheet_list.clear()
        self.update_cover_sheet_image(None)

    def attach_document(self):
        options = QFileDialog.Options()
        files, _ = QFileDialog.getOpenFileNames(self.ui_manager, "Select one or more files to fax", "", "Documents (*.pdf *.doc *.docx *.jpg *.png *.tif *.tiff *.txt)", options=options)
        if files:
            for file in files:
                self.documents_paths.append(file)
                self.ui_manager.document_list.addItem(self.format_display_name(file))
                self.update_document_image(file)

    def remove_document(self):
        selected_items = self.ui_manager.document_list.selectedItems()
        if not selected_items:
            return
        for item in selected_items:
            index = self.ui_manager.document_list.row(item)
            del self.documents_paths[index]
            self.ui_manager.document_list.takeItem(index)
            self.update_document_image(None if not self.documents_paths else self.documents_paths[0])

    def format_display_name(self, filepath):
        base_name = os.path.basename(filepath)
        if len(base_name) > 30:
            return f"{base_name[:15]}...{base_name[-10:]}"
        return base_name

    def update_cover_sheet_image(self, filepath):
        if filepath:
            self.update_image_label(filepath, self.ui_manager.cover_sheet_image_label)
        else:
            self.ui_manager.cover_sheet_image_label.clear()

    def update_document_image(self, filepath):
        if filepath:
            self.update_image_label(filepath, self.ui_manager.document_image_label)
        else:
            self.ui_manager.document_image_label.clear()

    def update_image_label(self, filepath, label):
        try:
            if filepath.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):
                # For simplicity, we will convert the first page to an image using a third-party library like PyMuPDF (for PDFs) or python-docx (for DOCX)
                if filepath.lower().endswith('.pdf'):
                    import fitz
                    doc = fitz.open(filepath)
                    page = doc.load_page(0)  # number of page
                    pix = page.get_pixmap()
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(image)
                elif filepath.lower().endswith('.docx'):
                    from docx import Document
                    import io
                    from PIL import Image as PILImage, ImageDraw

                    doc = Document(filepath)
                    # Extract text from the first page (first section)
                    text = doc.paragraphs[0].text
                    image = PILImage.new('RGB', (200, 200), color='white')
                    d = ImageDraw.Draw(image)
                    d.text((10, 10), text, fill='black')
                    byte_arr = io.BytesIO()
                    image.save(byte_arr, format='PNG')
                    byte_arr.seek(0)
                    image = QImage.fromData(byte_arr.read())
                    pixmap = QPixmap.fromImage(image)
                else:  # .txt
                    with open(filepath, 'r') as file:
                        text = file.read()
                    image = QImage(200, 200, QImage.Format_RGB32)
                    image.fill(Qt.white)
                    painter = QPainter(image)
                    painter.setPen(Qt.black)
                    painter.drawText(image.rect(), Qt.AlignLeft | Qt.AlignTop, text)
                    painter.end()
                    pixmap = QPixmap.fromImage(image)
            else:
                pixmap = QPixmap(filepath)
            label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio))
        except Exception as e:
            print(f"Failed to load image: {str(e)}")
            label.clear()


class FaxSender:
    def __init__(self, ui_manager, document_manager, encryption_manager):
        self.ui_manager = ui_manager
        self.document_manager = document_manager
        self.encryption_manager = encryption_manager

    def send_fax(self):
        fax_user = self.encryption_manager.get_config_value('Account', 'fax_user')
        token = self.encryption_manager.get_config_value('Token', 'access_token')
        caller_id = self.ui_manager.caller_id_combo.currentText().strip()
        destination = '1' + self.ui_manager.area_code_input.text() + self.ui_manager.first_three_input.text() + self.ui_manager.last_four_input.text()
        url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
        headers = {"Authorization": f"Bearer {token}"}
        files = {}
        data = {"caller_id": caller_id, "destination": destination}

        if self.document_manager.cover_sheet_path:
            files['filename[0]'] = (os.path.basename(self.document_manager.cover_sheet_path), open(self.document_manager.cover_sheet_path, 'rb'), 'application/pdf')

        for idx, doc_path in enumerate(self.document_manager.documents_paths):
            file_extension = os.path.splitext(doc_path)[1]
            mime_type = 'application/pdf' if file_extension == '.pdf' else 'image/' + file_extension.strip('.')
            file_key = f'filename[{idx + 1}]' if self.document_manager.cover_sheet_path else f'filename[{idx}]'
            files[file_key] = (os.path.basename(doc_path), open(doc_path, 'rb'), mime_type)

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


class ScannerManager:
    def __init__(self, ui_manager, document_manager):
        self.ui_manager = ui_manager
        self.document_manager = document_manager

    def scan_document(self, is_cover_sheet=False):
        pyinsane2.init()
        scanned_files = []
        try:
            devices = pyinsane2.get_devices()
            if not devices:
                QMessageBox.warning(self.ui_manager, "No Scanner Found", "No scanners were found on your system.")
                return

            if len(devices) > 1:
                device_names = [device.model for device in devices]  # Use model name for display
                scanner_model, ok = QInputDialog.getItem(self.ui_manager, "Select Scanner", "Available Scanners:",
                                                         device_names, 0, False)
                if not ok:
                    return
                scanner = next(device for device in devices if device.model == scanner_model)
            else:
                scanner = devices[0]

            # Debug: Print selected scanner
            print(f"Selected scanner: {scanner.model}")

            available_options = scanner.options.keys()
            self.set_scanner_options(scanner, available_options)

            scan_session = scanner.scan(multiple=True)

            # Create and clear appropriate directory
            if is_cover_sheet:
                directory = os.path.join(os.getcwd(), "Cover Sheets")
            else:
                directory = os.path.join(os.getcwd(), "Scanned Docs")

            if os.path.exists(directory):
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
                        print(f"Image saved at: {scanned_image_path}")  # Debug statement
                        self.compress_image(scanned_image_path)

                        # Collect scanned file paths
                        scanned_files.append(scanned_image_path)
                except StopIteration:
                    print(f"Got {len(scan_session.images)} pages")
                    break
                except Exception as e:
                    print(f"Error reading scan: {str(e)}")
                    break

            print(f"Finished scanning. Total pages: {len(scanned_files)}")

            if not scanned_files:
                QMessageBox.warning(self.ui_manager, "Scan Error", "No images were scanned.")
                return

        except (pyinsane2.WIAException, pyinsane2.SaneException, Exception) as e:
            print(f"Scan Error: {str(e)}")
            QMessageBox.critical(self.ui_manager, "Scan Error", f"An error occurred during scanning: {str(e)}")
        finally:
            # After scanning, update document manager and UI
            print("Updating UI with scanned documents.")
            if is_cover_sheet:
                # Handle cover sheet separately
                cover_sheet_path = scanned_files[0] if scanned_files else None
                if cover_sheet_path:
                    self.document_manager.cover_sheet_path = cover_sheet_path
                    self.ui_manager.cover_sheet_list.clear()
                    self.ui_manager.cover_sheet_list.addItem(self.document_manager.format_display_name(cover_sheet_path))
                    self.document_manager.update_cover_sheet_image(cover_sheet_path)
            else:
                for scanned_image_path in scanned_files:
                    print(f"Adding {scanned_image_path} to document list.")
                    self.document_manager.documents_paths.append(scanned_image_path)
                    self.ui_manager.document_list.addItem(self.document_manager.format_display_name(scanned_image_path))
                    self.document_manager.update_document_image(scanned_image_path)

            print("Completed UI update with scanned documents.")
            print(f"Closing scanner.")
            pyinsane2.exit()


    def set_scanner_options(self, scanner, available_options):
        def set_option(option_name, value):
            if option_name in available_options:
                try:
                    scanner.options[option_name].value = value
                    print(f"Set {option_name} to {value}")
                except Exception as e:
                    print(f"Failed to set {option_name}: {str(e)}")

        if 'resolution' in available_options:
            set_option('resolution', 200)
        if 'mode' in available_options:
            set_option('mode', 'Color')
        if 'tl-x' in available_options and 'tl-y' in available_options and 'br-x' in available_options and 'br-y' in available_options:
            set_option('tl-x', 0)
            set_option('tl-y', 0)
            set_option('br-x', 1701)  # Approximate Letter size in pixels at 300 DPI
            set_option('br-y', 2197)  # Approximate Letter size in pixels at 300 DPI
        elif 'page_size' in available_options:
            set_option('page_size', 'a4')
        if 'source' in available_options:
            source_options = scanner.options['source'].constraint
            if 'ADF Duplex' in source_options:
                set_option('source', 'ADF Duplex')
            elif 'ADF' in source_options:
                set_option('source', 'ADF')
            elif len(source_options) > 1:
                source_name, ok = QInputDialog.getItem(self.ui_manager, "Select Source", "Available Sources:",
                                                       source_options, 0, False)
                if not ok:
                    return
                set_option('source', source_name)
            else:
                set_option('source', source_options[0])
        if 'blank_page' in available_options:
            set_option('blank_page', True)

    def compress_image(self, image_path):
        try:
            img = Image.open(image_path)
            img = img.convert('L')  # Convert to grayscale
            compressed_image_path = os.path.splitext(image_path)[0] + "_compressed.jpg"
            img.save(compressed_image_path, "JPEG", quality=50, optimize=True,
                     progressive=True)  # Lower quality and add progressive option
            os.replace(compressed_image_path, image_path)  # Replace original image with compressed one
            print(f"Original image saved at: {image_path}")
            print(f"Compressed image saved at: {image_path}")
        except Exception as e:
            print(f"Failed to compress image: {str(e)}")


# noinspection PyUnresolvedReferences
class SendFax(UIManager):
    def __init__(self, main_window=None, parent=None):
        super().__init__(main_window, parent)
        self.encryption_manager = SaveManager(self.main_window)
        self.log_system = SystemLog()
        self.document_manager = DocumentManager(self)
        self.fax_sender = FaxSender(self, self.document_manager, self.encryption_manager)
        self.scanner_manager = ScannerManager(self, self.document_manager)
        self.setup_connections()
        self.populate_caller_id_combo_box()

    def setup_connections(self):
        self.caller_id_combo.currentIndexChanged.connect(self.populate_area_code)
        self.cover_sheet_button.clicked.connect(self.document_manager.attach_or_change_cover_sheet)
        self.scan_cover_sheet_button.clicked.connect(lambda: self.scanner_manager.scan_document(is_cover_sheet=True))
        self.document_button.clicked.connect(self.document_manager.attach_document)
        self.scan_button.clicked.connect(lambda: self.scanner_manager.scan_document(is_cover_sheet=False))
        self.send_button.clicked.connect(self.fax_sender.send_fax)
        self.cancel_button.clicked.connect(self.close)
        self.cover_sheet_list.customContextMenuRequested.connect(self.show_cover_sheet_context_menu)
        self.document_list.customContextMenuRequested.connect(self.show_document_context_menu)
        self.cover_sheet_list.itemClicked.connect(self.display_cover_sheet_image)
        self.document_list.itemClicked.connect(self.display_document_image)

    def show_document_context_menu(self, pos):
        document_item = self.document_list.itemAt(pos)
        if document_item:
            menu = QMenu()
            remove_action = QAction("Remove Document", self)
            remove_action.triggered.connect(self.document_manager.remove_document)
            menu.addAction(remove_action)
            menu.exec_(self.document_list.mapToGlobal(pos))

    def show_cover_sheet_context_menu(self, pos):
        cover_sheet_item = self.cover_sheet_list.itemAt(pos)
        if cover_sheet_item:
            menu = QMenu()
            remove_action = QAction("Remove Cover Sheet", self)
            remove_action.triggered.connect(self.document_manager.remove_cover_sheet)
            menu.addAction(remove_action)
            menu.exec_(self.cover_sheet_list.mapToGlobal(pos))

    def display_cover_sheet_image(self):
        item = self.cover_sheet_list.currentItem()
        if item:
            self.document_manager.update_cover_sheet_image(self.document_manager.cover_sheet_path)

    def display_document_image(self):
        item = self.document_list.currentItem()
        if item:
            index = self.document_list.row(item)
            self.document_manager.update_document_image(self.document_manager.documents_paths[index])

    def scan_cover_sheet(self):
        # Call the scanner manager to scan as a cover sheet
        self.scanner_manager.scan_document(is_cover_sheet=True)

    def populate_caller_id_combo_box(self):
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

    def populate_area_code(self):
        if self.caller_id_combo.currentIndex() != -1:
            selected_number = self.caller_id_combo.currentText()
            area_code = selected_number[selected_number.find('(') + 1:selected_number.find(')')]
            self.area_code_input.setText(area_code)
