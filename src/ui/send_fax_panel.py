import io
import os

from PyQt5.QtCore import Qt, QRectF, QSize, QThread
from PyQt5.QtGui import QIcon, QPixmap, QImage, QMovie
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit, \
    QGroupBox, QMessageBox, QListWidget, QGridLayout, QFileDialog, \
    QGraphicsView, QGraphicsScene, QMenu, QComboBox, QDialog, QListWidgetItem, QSizePolicy

from core.config_loader import global_config, device_config
from fax_io.sender import FaxSender
from utils.document_utils import normalize_document
from tempfile import mkstemp
import random
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import inch
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False
from utils.logging_utils import get_logger
from workers.scan_worker import ScanWorker
from ui.busy import BusyDialog


class SendFaxPanel(QWidget):
    """
    Embedded send-fax panel for attaching files, selecting a recipient, and sending.
    Extracted from SendFaxDialog but implemented as a QWidget to live inside MainWindow.
    """
    def __init__(self, base_dir, exe_dir, app_state, address_book_manager, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.exe_dir = exe_dir
        self.app_state = app_state
        self.address_book_manager = address_book_manager
        self.setObjectName("SendFaxPanel")
        self.log = get_logger("send_fax_panel")

        self.zoomed = False
        self.attachments = []
        self.page_images = []
        self.current_page = 0
        self.scan_session_count = 0
        self._cover_temp_path = None

        main_layout = QVBoxLayout(self)
        # Header
        header = QLabel("Send a Fax")
        header.setStyleSheet("font-weight: bold; font-size: 12pt;")
        main_layout.addWidget(header)

        # Recipient Row
        recipient_group = QGroupBox("Recipient")
        recipient_group.setStyleSheet("font-size: 11pt;")
        recipient_layout = QGridLayout()
        recipient_layout.setContentsMargins(10, 8, 10, 8)
        recipient_layout.setHorizontalSpacing(8)
        recipient_layout.setVerticalSpacing(6)
        # Define grid: 6 columns where 0=labels, 1-4=content, 5=trailing buttons
        recipient_layout.setColumnStretch(0, 0)
        recipient_layout.setColumnStretch(1, 2)
        recipient_layout.setColumnStretch(2, 1)
        recipient_layout.setColumnStretch(3, 1)
        recipient_layout.setColumnStretch(4, 1)
        recipient_layout.setColumnStretch(5, 0)

        # Caller ID (source number)
        from core.app_state import app_state as _app_state
        self.caller_id_combo = QComboBox()
        self.caller_id_combo.setEditable(False)
        nums = _app_state.global_cfg.all_numbers or []
        # Populate dropdown
        for n in nums:
            self.caller_id_combo.addItem(str(n))
        # Initialize selection from device settings if present
        preselect = _app_state.device_cfg.selected_fax_number or (nums[0] if nums else "")
        if preselect and preselect in nums:
            self.caller_id_combo.setCurrentText(preselect)
        # Persist selection to device settings when changed
        def _on_caller_changed(text):
            device_config.set("Account", "selected_fax_number", text)
            device_config.save()
            _app_state.device_cfg.selected_fax_number = text
        self.caller_id_combo.currentTextChanged.connect(_on_caller_changed)

        self.fax_area = QLineEdit()
        self.fax_area.setMaxLength(3)
        self.fax_area.setFixedWidth(48)
        self.fax_area.setToolTip("Area code")
        self.fax_area.setPlaceholderText("Area")
        try:
            from PyQt5.QtGui import QIntValidator
            self.fax_area.setValidator(QIntValidator(0, 999))
        except Exception:
            pass

        self.fax_prefix = QLineEdit()
        self.fax_prefix.setMaxLength(3)
        self.fax_prefix.setFixedWidth(48)
        self.fax_prefix.setToolTip("First 3 digits")
        self.fax_prefix.setPlaceholderText("Prefix")
        try:
            from PyQt5.QtGui import QIntValidator
            self.fax_prefix.setValidator(QIntValidator(0, 999))
        except Exception:
            pass

        self.fax_suffix = QLineEdit()
        self.fax_suffix.setMaxLength(4)
        self.fax_suffix.setFixedWidth(64)
        self.fax_suffix.setToolTip("Last 4 digits")
        self.fax_suffix.setPlaceholderText("Suffix")
        try:
            from PyQt5.QtGui import QIntValidator
            self.fax_suffix.setValidator(QIntValidator(0, 9999))
        except Exception:
            pass

        self.fax_area.textChanged.connect(lambda: self._auto_advance(self.fax_area, self.fax_prefix))
        self.fax_prefix.textChanged.connect(lambda: self._auto_advance(self.fax_prefix, self.fax_suffix))

        # Address Book button
        self.address_book_btn = QPushButton("Address Book")
        self.address_book_btn.setToolTip("Select a contact to populate fax number")
        self.address_book_btn.clicked.connect(self._open_address_book)

        row = 0
        recipient_layout.addWidget(QLabel("Caller ID:"), row, 0)
        recipient_layout.addWidget(self.caller_id_combo, row, 1, 1, 5)
        row += 1
        recipient_layout.addWidget(QLabel("Fax:"), row, 0)
        # Build compact phone input row: +1 country code, then area-prefix-suffix with visual separators
        self.fax_row_widget = QWidget()
        fax_row_h = QHBoxLayout(self.fax_row_widget)
        fax_row_h.setContentsMargins(0, 0, 0, 0)
        fax_row_h.setSpacing(6)
        cc_lbl = QLabel("+1")
        cc_lbl.setStyleSheet("color: #555;")
        dash1 = QLabel("-")
        dash2 = QLabel("-")
        dash1.setStyleSheet("color: #555;")
        dash2.setStyleSheet("color: #555;")
        fax_row_h.addWidget(cc_lbl)
        fax_row_h.addWidget(self.fax_area)
        fax_row_h.addWidget(dash1)
        fax_row_h.addWidget(self.fax_prefix)
        fax_row_h.addWidget(dash2)
        fax_row_h.addWidget(self.fax_suffix)
        fax_row_h.addStretch()
        recipient_layout.addWidget(self.fax_row_widget, row, 1, 1, 3)
        recipient_layout.addWidget(self.address_book_btn, row, 4, 1, 2)
        row += 1

        self.cover_checkbox = QCheckBox("Include Cover Sheet")
        self.cover_checkbox.setToolTip("Attach a cover sheet before the document(s)")
        # Add Configure Cover Sheet button next to the checkbox
        self.configure_cover_btn = QPushButton("Configure Cover Sheet")
        self.configure_cover_btn.setToolTip("Set header details and footer options for the cover sheet")
        self.configure_cover_btn.clicked.connect(self._open_cover_config)
        recipient_layout.addWidget(self.cover_checkbox, row, 0, 1, 3)
        recipient_layout.addWidget(self.configure_cover_btn, row, 3, 1, 3)
        row += 1

        # Cover Sheet Fields: To/Attention and Memo
        self.cover_to_input = QLineEdit()
        self.cover_to_input.setPlaceholderText("To / Attention")
        self.cover_to_input.setToolTip("Displayed on the cover sheet To / Attention line")
        try:
            self.cover_to_input.setClearButtonEnabled(True)
        except Exception:
            pass
        self.cover_memo_input = QLineEdit()
        self.cover_memo_input.setPlaceholderText("Memo")
        self.cover_memo_input.setToolTip("Displayed on the cover sheet Memo line")
        try:
            self.cover_memo_input.setClearButtonEnabled(True)
        except Exception:
            pass
        # Start disabled until include checkbox is checked
        self.cover_to_input.setEnabled(False)
        self.cover_memo_input.setEnabled(False)
        def _toggle_cover_fields(state):
            enabled = state == Qt.Checked
            self.cover_to_input.setEnabled(enabled)
            self.cover_memo_input.setEnabled(enabled)
            if enabled:
                self._ensure_cover_present(regenerate=True)
            else:
                self._remove_cover_if_present()
        self.cover_checkbox.stateChanged.connect(_toggle_cover_fields)
        # Regenerate cover only when inputs are completed (editing finished), not on each change
        try:
            self.cover_to_input.editingFinished.connect(lambda: self._ensure_cover_present(regenerate=True))
            self.cover_memo_input.editingFinished.connect(lambda: self._ensure_cover_present(regenerate=True))
        except Exception:
            # Fallback if editingFinished is unavailable in some contexts
            pass
        recipient_layout.addWidget(QLabel("To:"), row, 0)
        recipient_layout.addWidget(self.cover_to_input, row, 1, 1, 2)
        recipient_layout.addWidget(QLabel("Memo:"), row, 3)
        recipient_layout.addWidget(self.cover_memo_input, row, 4, 1, 2)
        row += 1

        recipient_group.setLayout(recipient_layout)
        main_layout.addWidget(recipient_group)

        # Document Pane
        document_split = QHBoxLayout()
        self.file_list = QListWidget()
        self.file_list.setToolTip("List of attached documents")
        self.file_list.currentRowChanged.connect(self._preview_document)
        self.file_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.file_list.customContextMenuRequested.connect(self._show_file_context_menu)

        right_preview_layout = QVBoxLayout()

        self.preview_view = QGraphicsView()
        self.preview_view.setStyleSheet("border: 1px solid #ccc; background: white;")
        self.preview_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.preview_view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.preview_view.setDragMode(QGraphicsView.ScrollHandDrag)
        # Allow the preview to expand with available space; avoid rigid minimums that cause overlap
        self.preview_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.preview_scene = QGraphicsScene()
        self.preview_view.setScene(self.preview_scene)
        self.preview_view.setMouseTracking(True)
        self.preview_view.viewport().installEventFilter(self)

        right_preview_layout.addWidget(self.preview_view)

        # Scanning progress indicator (GIF)
        self.scan_gif_label = QLabel()
        self.scan_gif_label.setAlignment(Qt.AlignCenter)
        self.scan_gif_label.setVisible(False)
        try:
            self.scan_movie = QMovie(os.path.join(self.base_dir, "images", "scanner.gif"))
            # Modest display size so it fits within the preview area
            self.scan_movie.setScaledSize(QSize(128, 128))
            self.scan_gif_label.setMovie(self.scan_movie)
        except Exception:
            self.scan_movie = None
        right_preview_layout.addWidget(self.scan_gif_label)

        # Build the documents/preview side-by-side
        document_split.addWidget(self.file_list, 1)
        document_split.addLayout(right_preview_layout, 3)
        # Make the list expand to fill available space as well
        self.file_list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # Let the document area take the flexible vertical space; controls will sit below
        main_layout.addLayout(document_split, 1)

        # Unified controls row: Attach/Scan | Preview Controls | Send/Clear
        controls_row = QHBoxLayout()
        # Attach/Scan
        self.attach_button = QPushButton("Attach Document")
        self.scan_button = QPushButton("Scan Document")
        self.attach_button.clicked.connect(self._on_attach)
        self.scan_button.clicked.connect(self._on_scan)
        controls_row.addWidget(self.attach_button)
        controls_row.addWidget(self.scan_button)

        controls_row.addStretch()

        # Preview controls
        icon_size = QSize(24, 24)
        self.zoom_in_btn = QPushButton()
        self.zoom_in_btn.setIcon(QIcon(os.path.join(self.base_dir, "images", "zoom.png")))
        self.zoom_in_btn.setIconSize(icon_size)
        self.zoom_in_btn.setToolTip("Zoom In")
        self.zoom_in_btn.clicked.connect(self._on_zoom)

        self.zoom_out_btn = QPushButton()
        self.zoom_out_btn.setIcon(QIcon(os.path.join(self.base_dir, "images", "unzoom.png")))
        self.zoom_out_btn.setIconSize(icon_size)
        self.zoom_out_btn.setToolTip("Zoom Out")
        self.zoom_out_btn.clicked.connect(self._on_unzoom)

        self.page_prev_btn = QPushButton()
        self.page_prev_btn.setIcon(QIcon(os.path.join(self.base_dir, "images", "page_minus.png")))
        self.page_prev_btn.setIconSize(icon_size)
        self.page_prev_btn.setToolTip("Previous Page")
        self.page_prev_btn.clicked.connect(self._on_prev_page)
        self.page_prev_btn.setEnabled(False)

        self.page_next_btn = QPushButton()
        self.page_next_btn.setIcon(QIcon(os.path.join(self.base_dir, "images", "page_plus.png")))
        self.page_next_btn.setIconSize(icon_size)
        self.page_next_btn.setToolTip("Next Page")
        self.page_next_btn.clicked.connect(self._on_next_page)
        self.page_next_btn.setEnabled(False)

        for btn in [self.zoom_in_btn, self.zoom_out_btn, self.page_prev_btn, self.page_next_btn]:
            btn.setFixedSize(32, 32)
            controls_row.addWidget(btn)

        controls_row.addStretch()

        # Send/Clear
        self.send_button = QPushButton("Send Fax")
        self.clear_button = QPushButton("Clear")
        self.send_button.clicked.connect(self._on_send)
        self.clear_button.clicked.connect(self._on_clear)
        controls_row.addWidget(self.send_button)
        controls_row.addWidget(self.clear_button)

        # Keep controls row at natural height (non-stretch) to avoid overlap
        main_layout.addLayout(controls_row, 0)

    def refresh_caller_id_numbers(self):
        """Refresh the Caller ID dropdown from current app_state.global_cfg.all_numbers.
        Preserves selection when possible and falls back to device selection or first available.
        """
        try:
            from core.app_state import app_state as _app_state
        except Exception:
            _app_state = None
        try:
            current_text = self.caller_id_combo.currentText()
        except Exception:
            current_text = ""
        # Obtain latest numbers
        nums = []
        if _app_state and getattr(_app_state, 'global_cfg', None):
            try:
                nums = _app_state.global_cfg.all_numbers or []
            except Exception:
                nums = []
        # Rebuild combo items only if changed to avoid flicker
        try:
            existing = [self.caller_id_combo.itemText(i) for i in range(self.caller_id_combo.count())]
        except Exception:
            existing = []
        try:
            if nums != existing:
                self.caller_id_combo.blockSignals(True)
                self.caller_id_combo.clear()
                for n in nums:
                    self.caller_id_combo.addItem(str(n))
                # Determine selection priority: keep current if still valid -> device setting -> first number
                target = None
                if current_text and current_text in nums:
                    target = current_text
                else:
                    try:
                        sel = device_config.get("Account", "selected_fax_number", "")
                    except Exception:
                        sel = ""
                    if sel and sel in nums:
                        target = sel
                    elif nums:
                        target = nums[0]
                    else:
                        target = ""
                if target:
                    self.caller_id_combo.setCurrentText(target)
                self.caller_id_combo.blockSignals(False)
        except Exception:
            try:
                self.caller_id_combo.blockSignals(False)
            except Exception:
                pass
            # Silently ignore UI refresh errors
            return

    def _open_cover_config(self):
        from PyQt5.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QDialogButtonBox, QLabel, QHBoxLayout
        dlg = QDialog(self)
        dlg.setWindowTitle("Configure Cover Sheet")
        v = QVBoxLayout(dlg)
        form = QFormLayout()
        company = QLineEdit(device_config.get("Cover Sheet", "company", ""))
        address = QLineEdit(device_config.get("Cover Sheet", "address", ""))
        phone = QLineEdit(device_config.get("Cover Sheet", "phone", ""))
        email = QLineEdit(device_config.get("Cover Sheet", "email", ""))
        phone.setCursorPosition(2)
        phone.setMaxLength(12)

        # E.164 mask for phone if empty
        try:
            if not phone.text().strip():
                phone.setInputMask("+99999999999;_")
                phone.setText("+1")
        except Exception:
            pass

        # Footer enable + category + info (spoiler)
        footer_chk = QCheckBox("Add a little… to your cover page")
        footer_chk.setChecked((device_config.get("Cover Sheet", "footer_enabled", "No") or "No").lower() == "yes")

        # Load categories dynamically from shared/cover_messages.json (normalized to lowercase)
        try:
            from utils.cover_messages import load_message_pool
            pool = load_message_pool(self.base_dir)
        except Exception:
            pool = {"classic": ["The remainder of this page is intentionally left blank."]}
        categories = sorted(list(pool.keys())) if isinstance(pool, dict) else ["classic"]

        footer_combo = QComboBox()
        for key in categories:
            display = key.title()
            footer_combo.addItem(display, key)
        cur_cat = (device_config.get("Cover Sheet", "footer_category", "classic") or "classic").strip().lower()
        idx = max(0, footer_combo.findData(cur_cat))
        footer_combo.setCurrentIndex(idx)

        # Info icon (ℹ) to preview messages of selected category when enabled
        info_lbl = QLabel("\u2139")  # ℹ
        info_lbl.setToolTip("")
        info_lbl.setFixedWidth(18)
        info_lbl.setAlignment(Qt.AlignCenter)
        info_lbl.setStyleSheet("QLabel { border: 1px solid #999; border-radius: 9px; color: #555; font-weight: bold; }")

        def _update_info_tooltip():
            key = footer_combo.currentData() or "classic"
            msgs = pool.get(key) if isinstance(pool, dict) else []
            if not msgs:
                tip = "No sample messages available."
            else:
                # Build a compact tooltip with up to ~10 messages
                sample = msgs[:10]
                tip = "\n".join(f"• {m}" for m in sample)
            info_lbl.setToolTip(tip)
            info_lbl.setVisible(footer_chk.isChecked())

        footer_combo.currentIndexChanged.connect(_update_info_tooltip)
        footer_chk.toggled.connect(_update_info_tooltip)

        # Row widget for footer controls
        footer_row = QHBoxLayout()
        footer_row.addWidget(footer_chk)
        footer_row.addWidget(footer_combo)
        footer_row.addWidget(info_lbl)
        footer_row.addStretch()

        form.addRow("Company Name", company)
        form.addRow("Address", address)
        form.addRow("Phone", phone)
        form.addRow("Email", email)
        # Add composed footer row
        row_container = QWidget()
        row_container.setLayout(footer_row)
        form.addRow(row_container)
        v.addLayout(form)

        # Initialize the info tooltip visibility/content
        _update_info_tooltip()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        v.addWidget(buttons)

        def on_save():
            try:
                device_config.set("Cover Sheet", "company", company.text().strip())
                device_config.set("Cover Sheet", "address", address.text().strip())
                device_config.set("Cover Sheet", "phone", phone.text().strip())
                device_config.set("Cover Sheet", "email", email.text().strip())
                device_config.set("Cover Sheet", "footer_enabled", "Yes" if footer_chk.isChecked() else "No")
                selected_key = footer_combo.currentData() or (footer_combo.currentText() or "classic").strip().lower()
                device_config.set("Cover Sheet", "footer_category", selected_key)
                device_config.save()
            except Exception:
                pass
            # If cover is active, regenerate it
            if self.cover_checkbox.isChecked():
                self._ensure_cover_present(regenerate=True)
            dlg.accept()

        buttons.accepted.connect(on_save)
        buttons.rejected.connect(dlg.reject)
        dlg.exec_()

    def _auto_advance(self, current_field, next_field):
        if len(current_field.text()) == current_field.maxLength():
            next_field.setFocus()

    def _on_attach(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Attach Document",
            "",
            "Documents (*.html *.pdf *.doc *.docx *.jpg *.jpeg *.png *.tiff *.txt)"
        )
        if filepath:
            try:
                result = normalize_document(filepath)
                if result:
                    if filepath.lower().endswith((".doc", ".docx")):
                        QMessageBox.information(
                            self,
                            "Word Document Notice",
                            "FaxRetriever cannot alter Word documents.\n\n"
                            "Please ensure your document is formatted using portrait orientation before attaching."
                        )
                    self.attachments.append(result)
                    self.file_list.addItem(os.path.basename(filepath))
                    if self.cover_checkbox.isChecked():
                        self._pin_cover_to_front()
                    self._preview_document(self.file_list.count() - 1)
                else:
                    QMessageBox.warning(self, "Failed", "Could not normalize document orientation.")

            except Exception as e:
                self.log.exception("Document normalization failed")
                QMessageBox.critical(self, "Error", f"Failed to process document:\n{e}")

    def _show_file_context_menu(self, position):
        menu = QMenu()
        delete_action = menu.addAction("Remove Document")
        action = menu.exec_(self.file_list.mapToGlobal(position))
        if action == delete_action:
            index = self.file_list.currentRow()
            # Prevent removing the generated cover via context menu; require unchecking the box
            if self._is_cover_index(index):
                QMessageBox.information(self, "Cover Sheet", "Uncheck 'Include Cover Sheet' to remove the cover sheet.")
                return
            if 0 <= index < len(self.attachments):
                del self.attachments[index]
                self.file_list.takeItem(index)
                self._preview_document(self.file_list.currentRow())

    def _on_scan(self):
        self.scan_button.setEnabled(False)
        # Show scanning GIF
        try:
            if hasattr(self, 'scan_movie') and self.scan_movie:
                self.scan_gif_label.setVisible(True)
                self.scan_movie.start()
        except Exception:
            pass
        self.thread = QThread()
        self.worker = ScanWorker(session_number=self.scan_session_count)
        self.worker.moveToThread(self.thread)

        self.worker.success.connect(self._on_scan_success)
        self.worker.error.connect(self._on_scan_error)
        self.worker.finished.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        self.thread.started.connect(self.worker.run)
        self.thread.start()

    def _on_scan_success(self, paths):
        # Hide scanning GIF
        try:
            if hasattr(self, 'scan_movie') and self.scan_movie:
                self.scan_movie.stop()
                self.scan_gif_label.setVisible(False)
        except Exception:
            pass
        self.scan_session_count += 1
        # Normalize scanned outputs before attaching
        added_any = False
        for p in paths or []:
            try:
                norm = normalize_document(p)
            except Exception as e:
                norm = None
            if norm:
                self.attachments.append(norm)
                self.file_list.addItem(os.path.basename(norm))
                added_any = True
        if not added_any:
            QMessageBox.warning(self, "Scanner", "No usable document produced by scan.")
        # If cover is selected, keep it pinned to index 0
        if self.cover_checkbox.isChecked():
            self._pin_cover_to_front()
        # Update preview to the last item
        if self.file_list.count() > 0:
            self._preview_document(self.file_list.count() - 1)
        self.scan_button.setEnabled(True)

    def _on_scan_error(self, message):
        # Hide scanning GIF on error
        try:
            if hasattr(self, 'scan_movie') and self.scan_movie:
                self.scan_movie.stop()
                self.scan_gif_label.setVisible(False)
        except Exception:
            pass
        QMessageBox.warning(self, "Scanner Error", message)
        self.scan_button.setEnabled(True)

    def _on_zoom(self):
        self.zoomed = True
        self.preview_view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._update_preview_zoom(1.0)

    def _on_unzoom(self):
        self.zoomed = False
        self.preview_view.setDragMode(QGraphicsView.NoDrag)
        self._update_preview_zoom(1.0)

    def _update_preview_zoom(self, factor, center=None):
        self.preview_scene.clear()
        if hasattr(self, 'original_pixmap'):
            if center:
                w, h = self.original_pixmap.width(), self.original_pixmap.height()
                x = int(center.x() * (w / self.preview_view.viewport().width()))
                y = int(center.y() * (h / self.preview_view.viewport().height()))
                crop = self.original_pixmap.copy(x - 100, y - 100, 200, 200)
                self.preview_scene.addPixmap(crop)
            else:
                if self.zoomed:
                    self.preview_scene.addPixmap(self.original_pixmap)
                    self.preview_view.setSceneRect(QRectF(self.original_pixmap.rect()))
                else:
                    viewport_size = self.preview_view.viewport().size()
                    scaled = self.original_pixmap.scaled(viewport_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.preview_scene.addPixmap(scaled)
                    self.preview_view.setSceneRect(QRectF(scaled.rect()))

    def _preview_document(self, index):
        self.preview_scene.clear()
        self.page_images.clear()
        self.current_page = 0

        if index < 0 or index >= len(self.attachments):
            self.preview_scene.addText("No preview")
            self.page_prev_btn.setEnabled(False)
            self.page_next_btn.setEnabled(False)
            return

        path = self.attachments[index]
        if path.lower().endswith(".pdf"):
            try:
                imgs = []
                # Try PyMuPDF (fitz) first to avoid spawning Poppler subprocesses (no console windows)
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(path)
                    if doc.page_count <= 0:
                        raise RuntimeError("Empty PDF")
                    for i in range(doc.page_count):
                        page = doc.load_page(i)
                        pix = page.get_pixmap(dpi=200, alpha=False)
                        img_bytes = pix.tobytes("png")
                        qimg = QImage.fromData(img_bytes)
                        imgs.append(QPixmap.fromImage(qimg))
                except Exception:
                    # Fallback to pdf2image + Poppler if PyMuPDF is unavailable
                    from pdf2image import convert_from_path
                    # Prefer MEIPASS/base_dir (onefile extraction) for Poppler, then fallback to exe_dir
                    candidates = [
                        os.path.join(self.base_dir, "poppler", "bin"),
                        os.path.join(self.exe_dir or self.base_dir, "poppler", "bin"),
                    ]
                    poppler_bin = next((p for p in candidates if os.path.isdir(p)), None)
                    kwargs = {"dpi": 200}
                    if poppler_bin:
                        kwargs["poppler_path"] = poppler_bin
                    pages = convert_from_path(path, **kwargs)
                    for pil_image in pages:
                        buf = io.BytesIO()
                        pil_image.save(buf, format='PNG')
                        qt_image = QImage.fromData(buf.getvalue())
                        imgs.append(QPixmap.fromImage(qt_image))

                if imgs:
                    self.page_images = imgs
                    self.original_pixmap = self.page_images[0]
                    self._update_preview_zoom(1.0)
                    multi = len(self.page_images) > 1
                    self.page_prev_btn.setEnabled(multi)
                    self.page_next_btn.setEnabled(multi)
                else:
                    self.preview_scene.addText("Failed to render PDF.")
                    self.page_prev_btn.setEnabled(False)
                    self.page_next_btn.setEnabled(False)
            except Exception as e:
                self.preview_scene.addText(f"Preview error: {e}")
                self.page_prev_btn.setEnabled(False)
                self.page_next_btn.setEnabled(False)
        else:
            self.preview_scene.addText("Preview not supported for this file type.")
            self.page_prev_btn.setEnabled(False)
            self.page_next_btn.setEnabled(False)

    def _on_prev_page(self):
        if self.current_page > 0:
            self.current_page -= 1
            self.original_pixmap = self.page_images[self.current_page]
            self._update_preview_zoom(1.0)

    def _on_next_page(self):
        if self.current_page < len(self.page_images) - 1:
            self.current_page += 1
            self.original_pixmap = self.page_images[self.current_page]
            self._update_preview_zoom(1.0)

    def _on_send(self):
        fax = f"1{self.fax_area.text()}{self.fax_prefix.text()}{self.fax_suffix.text()}"
        if len(fax) != 11 or not fax.isdigit():
            QMessageBox.warning(self, "Invalid", "Enter a valid 10-digit fax number")
            return

        # Ensure cover sheet is (re)generated as the first document if requested
        if self.cover_checkbox.isChecked():
            self._ensure_cover_present(regenerate=True)

        # Require at least one non-cover document? Spec says include cover in picker; still require any doc
        if not self.attachments or (len(self.attachments) == 1 and self._is_cover_index(0)):
            QMessageBox.warning(self, "Missing", "You must attach at least one non-cover document.")
            return

        # Caller ID selection persisted above; include cover choice and (optionally) To/Memo metadata
        include_cover = self.cover_checkbox.isChecked()
        # Optional: Persist To/Memo to device settings for convenience (non-breaking)
        try:
            device_config.set("Fax Options", "cover_attn", self.cover_to_input.text())
            device_config.set("Fax Options", "cover_memo", self.cover_memo_input.text())
            device_config.save()
        except Exception:
            pass
        with BusyDialog(self, "Sending fax..."):
            success = FaxSender.send_fax(self.base_dir, fax, self.attachments, include_cover)
        if success:
            QMessageBox.information(self, "Success", "Fax sent successfully.")
            # Clear the panel first per UX requirement
            self._on_clear()
            try:
                # Refresh History and trigger polling via MainWindow if available
                mw = self.window()
                if mw:
                    if hasattr(mw, 'fax_history_panel'):
                        # Use consolidated refresh entry-point
                        if hasattr(mw.fax_history_panel, 'request_refresh'):
                            mw.fax_history_panel.request_refresh()
                        else:
                            mw.fax_history_panel.refresh()
                    # Trigger an immediate inbound poll so received faxes are up-to-date
                    try:
                        if hasattr(mw, '_manual_poll'):
                            mw._manual_poll()
                        elif hasattr(mw, 'poll_bar') and getattr(mw, 'poll_bar'):
                            mw.poll_bar.retrieveFaxes()
                    except Exception:
                        pass
                    # Restart the poll progress bar countdown if present
                    try:
                        if hasattr(mw, 'poll_bar') and getattr(mw, 'poll_bar'):
                            mw.poll_bar.restart_progress()
                    except Exception:
                        pass
            except Exception:
                pass
        else:
            QMessageBox.critical(self, "Failed", "Fax failed to send.")

    def _on_clear(self):
        # Clean up any temp cover sheet and Recipient Info
        self.fax_area.clear()
        self.fax_prefix.clear()
        self.fax_suffix.clear()
        self.cover_to_input.clear()
        self.cover_memo_input.clear()
        self.cover_checkbox.setChecked(False)
        try:
            if hasattr(self, '_cover_temp_path') and self._cover_temp_path and os.path.exists(self._cover_temp_path):
                os.remove(self._cover_temp_path)
        except Exception:
            pass
        self._cover_temp_path = None
        self.page_images = []
        self.original_pixmap = None
        self.current_page = 0
        self.attachments.clear()
        self.file_list.clear()
        self.scan_session_count = 0
        self.preview_scene.clear()

    def _open_address_book(self):
        try:
            # Prefer MainWindow handler (modeless, single-instance reuse)
            mw = self.window()
            if mw and hasattr(mw, 'open_address_book_dialog'):
                mw.open_address_book_dialog()
                return
            from ui.address_book_dialog import AddressBookDialog
            # Fallback: open modelessly with reuse within this panel
            existing = getattr(self, '_address_book_dialog', None)
            if existing is not None:
                try:
                    existing.show()
                    existing.raise_()
                    existing.activateWindow()
                    return
                except Exception:
                    try:
                        existing.close()
                    except Exception:
                        pass
            dlg = AddressBookDialog(self.base_dir, self.address_book_manager, self)
            dlg.setModal(False)
            dlg.setAttribute(Qt.WA_DeleteOnClose, True)
            def _on_destroyed(_obj=None):
                try:
                    self._address_book_dialog = None
                except Exception:
                    pass
            try:
                dlg.destroyed.connect(_on_destroyed)
            except Exception:
                pass
            self._address_book_dialog = dlg
            dlg.show()
        except Exception as e:
            try:
                QMessageBox.warning(self, "Address Book", f"Failed to open Address Book: {e}")
            except Exception:
                pass

    def populate_phone_fields(self, phone: str):
        # Accepts 10-digit string, optionally with punctuation
        digits = ''.join([c for c in (phone or '') if c.isdigit()])
        if len(digits) == 11 and digits.startswith('1'):
            digits = digits[1:]
        if len(digits) >= 10:
            digits = digits[:10]
            self.fax_area.setText(digits[:3])
            self.fax_prefix.setText(digits[3:6])
            self.fax_suffix.setText(digits[6:])

    def populate_cover_from_contact(self, contact: dict):
        try:
            if contact.get("custom_cover_sheet", False):
                self.cover_checkbox.setChecked(True)
                attn = contact.get("custom_cover_sheet_attn", "")
                note = contact.get("custom_cover_sheet_note", "")
                self.cover_to_input.setText(attn)
                self.cover_memo_input.setText(note)
        except Exception:
            pass

    def populate_from_contact(self, contact: dict):
        try:
            # name = contact.get('name', '')
            phone = contact.get('phone', '')
            # self.recipient_name.setText(name)
            self.populate_phone_fields(phone)
            self.populate_cover_from_contact(contact)
        except Exception:
            pass

    # ----- Cover Sheet Generation and Management -----
    def _generate_cover_pdf(self) -> str | None:
        """Generate a one-page cover PDF using configured header/footer + To/Memo. Returns temp file path or None."""
        if not REPORTLAB_AVAILABLE:
            return None
        try:
            from utils.cover_messages import random_footer
        except Exception:
            random_footer = None
        try:
            # Load saved cover config
            company = device_config.get("Cover Sheet", "company", "")
            address = device_config.get("Cover Sheet", "address", "")
            phone = device_config.get("Cover Sheet", "phone", "")
            email = device_config.get("Cover Sheet", "email", "")
            footer_enabled = (device_config.get("Cover Sheet", "footer_enabled", "No") or "No").lower() == "yes"
            footer_category = device_config.get("Cover Sheet", "footer_category", "classic")
        except Exception:
            company = address = phone = email = ""
            footer_enabled = False
            footer_category = "classic"
        try:
            fd, path = mkstemp(suffix='.pdf')
            os.close(fd)
            c = canvas.Canvas(path, pagesize=letter)
            width, height = letter

            # Header block: company info (centered for a professional presentation)
            top = height - 0.9*inch
            c.setFont("Helvetica-Bold", 16)
            if company:
                c.drawCentredString(width/2.0, top, company)
                top -= 0.22*inch
            c.setFont("Helvetica", 10)
            if address:
                c.drawCentredString(width/2.0, top, address)
                top -= 0.18*inch
            if phone or email:
                contact_line = " ".join([x for x in [phone, (f"| {email}" if email else "")] if x])
                c.drawCentredString(width/2.0, top, contact_line)
                top -= 0.18*inch

            # Title centered both horizontally and vertically
            c.setFont("Helvetica-Bold", 28)
            center_y = height / 2.0
            c.drawCentredString(width / 2.0, center_y + 0.35*inch, "COVER SHEET")

            # Body: To / Memo centered beneath the title
            c.setFont("Helvetica", 12)
            attn = (self.cover_to_input.text() or "").strip()
            memo = (self.cover_memo_input.text() or "").strip()
            c.drawCentredString(width / 2.0, center_y - 0.05*inch, f"To / Attn: {attn}")
            c.drawCentredString(width / 2.0, center_y - 0.35*inch, f"Memo: {memo}")

            # Footer: either random from pool or classic default
            footer_text = "The remainder of this page is intentionally left blank."
            try:
                if footer_enabled and random_footer is not None:
                    footer_text = random_footer(self.base_dir, footer_category)
            except Exception:
                pass
            c.setFont("Helvetica-Oblique", 10)
            c.drawCentredString(width/2.0, 0.75*inch, footer_text)

            c.showPage()
            c.save()
            return path
        except Exception:
            return None

    def _is_cover_index(self, index: int) -> bool:
        if index < 0 or index >= len(self.attachments):
            return False
        try:
            item = self.file_list.item(index)
            return bool(item and item.text().lower().startswith("Cover Sheet".lower()))
        except Exception:
            return False

    def _pin_cover_to_front(self):
        """Ensure the cover (if exists) is the first item in attachments and list."""
        try:
            # Find cover in list
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item and item.text().lower().startswith("Cover Sheet".lower()):
                    if i == 0:
                        return
                    # Move in list widget
                    itm = self.file_list.takeItem(i)
                    self.file_list.insertItem(0, itm)
                    # Move in attachments array accordingly
                    cover_path = self.attachments.pop(i)
                    self.attachments.insert(0, cover_path)
                    self.file_list.setCurrentRow(0)
                    return
        except Exception:
            pass

    def _ensure_cover_present(self, regenerate: bool = False):
        if not self.cover_checkbox.isChecked():
            return
        # On regenerate, delete the original cover (file and list item), then replace with a new one
        if regenerate:
            try:
                self._remove_cover_if_present()
            except Exception:
                pass
        # Create if missing
        if not self._cover_temp_path or not os.path.exists(self._cover_temp_path):
            path = self._generate_cover_pdf()
            if path:
                self._cover_temp_path = path
                # Insert at front
                self.attachments.insert(0, path)
                self.file_list.insertItem(0, QListWidgetItem("Cover Sheet.pdf"))
                self.file_list.setCurrentRow(0)
        # Keep at the front
        self._pin_cover_to_front()
        # Update preview to reflect cover changes
        try:
            self._preview_document(self.file_list.currentRow())
        except Exception:
            pass

    def _remove_cover_if_present(self):
        # Remove list item labeled as cover and delete temp file
        try:
            for i in range(self.file_list.count()):
                item = self.file_list.item(i)
                if item and item.text().lower().startswith("Cover Sheet".lower()):
                    self.file_list.takeItem(i)
                    if 0 <= i < len(self.attachments):
                        self.attachments.pop(i)
                    break
            if self._cover_temp_path and os.path.exists(self._cover_temp_path):
                os.remove(self._cover_temp_path)
        except Exception:
            pass
        self._cover_temp_path = None
