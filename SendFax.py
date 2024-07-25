import io
import os
import pyinsane2
import shutil
import sys
import requests
import threading

from docx import Document

from PIL import Image, ImageDraw

from PyQt5 import QtGui
from PyQt5.QtCore import pyqtSignal, Qt, QObject
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
        try:
            self.main_window = main_window
            self.setWindowIcon(QtGui.QIcon(os.path.join(bundle_dir, "images", "logo.ico")))
            self.setWindowTitle("Send Fax")
            self.setup_ui()
        except Exception as e:
            print(f"Initialization error: {e}")

    def setup_ui(self):
        try:
            layout = QVBoxLayout(self)
            self.setup_caller_id_section(layout)
            self.setup_destination_number_section(layout)
            # self.setup_cover_sheet_section(layout)
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
        except Exception as e:
            print(f"Setup destination number section error: {e}")

    def focus_next(self, current_widget, next_widget):
        try:
            if len(current_widget.text()) == current_widget.maxLength():
                next_widget.setFocus()
        except Exception as e:
            print(f"Focus next error: {e}")

    def setup_document_section(self, layout):
        try:
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
        except Exception as e:
            print(f"Setup document section error: {e}")

    def setup_action_buttons(self, layout):
        try:
            self.send_button = QPushButton("Send Fax")
            self.cancel_button = QPushButton("Cancel")
            layout.addWidget(self.send_button)
            layout.addWidget(self.cancel_button)
        except Exception as e:
            print(f"Setup action buttons error: {e}")

    def closeEvent(self, event):
        """Override the close event to clear the document list"""
        self.clear_document_list()
        super().closeEvent(event)

    def clear_document_list(self):
        """Clear the document list and reset the document image label"""
        self.document_list.clear()
        self.document_image_label.clear()


class DocumentManager:
    def __init__(self, ui_manager):
        try:
            self.ui_manager = ui_manager
            self.cover_sheet_path = None
            self.documents_paths = []
        except Exception as e:
            print(f"Initialization error: {e}")

    def attach_document(self):
        try:
            options = QFileDialog.Options()
            files, _ = QFileDialog.getOpenFileNames(self.ui_manager, "Select one or more files to fax", "",
                                                    "Documents (*.pdf *.doc *.docx *.jpg *.png *.tif *.tiff *.txt)",
                                                    options=options)
            if files:
                for file in files:
                    self.documents_paths.append(file)
                    self.ui_manager.document_list.addItem(self.format_display_name(file))
                    self.update_document_image(file)
        except Exception as e:
            print(f"Attach document error: {e}")

    def remove_document(self):
        try:
            selected_items = self.ui_manager.document_list.selectedItems()
            if not selected_items:
                return
            for item in selected_items:
                index = self.ui_manager.document_list.row(item)
                del self.documents_paths[index]
                self.ui_manager.document_list.takeItem(index)
                self.update_document_image(None if not self.documents_paths else self.documents_paths[0])
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
                self.update_image_label(filepath, self.ui_manager.document_image_label)
            else:
                self.ui_manager.document_image_label.clear()
        except Exception as e:
            print(f"Update document image error: {e}")

    def update_image_label(self, filepath, label):
        try:
            if filepath.lower().endswith(('.pdf', '.doc', '.docx', '.txt')):
                if filepath.lower().endswith('.pdf'):
                    import fitz
                    doc = fitz.open(filepath)
                    page = doc.load_page(0)
                    pix = page.get_pixmap()
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(image)
                elif filepath.lower().endswith('.docx'):
                    doc = Document(filepath)
                    text = "\n".join([p.text for p in doc.paragraphs[:10]])  # Adjust number of paragraphs as needed
                    image = Image.new('RGB', (800, 1000), color='white')
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
                    image = QImage(800, 1000, QImage.Format_RGB32)
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
            destination = '1' + self.ui_manager.area_code_input.text() + self.ui_manager.first_three_input.text() + self.ui_manager.last_four_input.text()
            url = f"https://telco-api.skyswitch.com/users/{fax_user}/faxes/send"
            headers = {"Authorization": f"Bearer {token}"}
            files = {}
            data = {"caller_id": caller_id, "destination": destination}

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
        except Exception as e:
            print(f"Send fax error: {e}")
            QMessageBox.critical(self.ui_manager, "Error", f"An error occurred while preparing to send the fax: {str(e)}")


class ScanningDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scanning...")
        self.setFixedSize(200, 100)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)  # Remove window decorations
        self.setWindowModality(Qt.ApplicationModal)  # Make it modal
        layout = QVBoxLayout()
        layout.setContentsMargins(10, 10, 10, 10)  # Set minimal padding around the text
        self.label = QLabel("Scanning, please wait...", self)
        layout.addWidget(self.label, alignment=Qt.AlignCenter)  # Center align the text
        self.setLayout(layout)

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
        pyinsane2.init()

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
        except Exception as e:
            print(f"Initialization error: {e}")

    def setup_connections(self):
        try:
            self.caller_id_combo.currentIndexChanged.connect(self.populate_area_code)
            # self.cover_sheet_button.clicked.connect(self.document_manager.attach_or_change_cover_sheet)
            # self.scan_cover_sheet_button.clicked.connect(lambda: self.scanner_manager.scan_document(is_cover_sheet=True))
            self.document_button.clicked.connect(self.document_manager.attach_document)
            self.scan_button.clicked.connect(self.scanner_manager.scan_document)
            self.send_button.clicked.connect(self.fax_sender.send_fax)
            self.cancel_button.clicked.connect(self.close)
            # self.cover_sheet_list.customContextMenuRequested.connect(self.show_cover_sheet_context_menu)
            self.document_list.customContextMenuRequested.connect(self.show_document_context_menu)
            # self.cover_sheet_list.itemClicked.connect(self.display_cover_sheet_image)
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
