"""
ui/main_window.py

Primary UI controller for FaxRetriever 2.0.
Handles application window, menus, dialogs, and basic signal routing.
Heavy logic is offloaded to core modules and app state accessors.
"""

import os
from datetime import datetime, timedelta, timezone

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (QAction, QApplication, QFileDialog, QGridLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget,
                             QListWidgetItem, QMainWindow, QMenu, QMenuBar,
                             QMessageBox, QPushButton, QSizePolicy, QSplitter,
                             QStatusBar, QScrollArea, QSystemTrayIcon, QVBoxLayout, QWidget)

from core.address_book import AddressBookManager
from core.app_state import app_state
from core.auto_update import UpdateChecker, UpdateInstaller, is_time_to_check
from core.config_loader import device_config, global_config
from core.license_client import retrieve_skyswitch_token
from fax_io.receiver import FaxReceiver
from integrations.computer_rx import CRxIntegration2
from ui.threads.crx_delivery_poller import CrxDeliveryPoller
from ui.safe_notifier import get_notifier
from ui.about_dialog import AboutDialog
from ui.address_book_dialog import AddressBookDialog
from ui.dialogs import LogViewer, MarkdownViewer, WhatsNewDialog
from ui.fax_history_panel import FaxHistoryPanel
from ui.options_dialog import OptionsDialog
from ui.send_fax_panel import SendFaxPanel
from ui.status_panel import FaxPollTimerProgressBar
from utils.logging_utils import get_logger
from utils.document_utils import convert_pdf_to_jpgs
from version import __version__


class MainWindow(QMainWindow):
    """
    Main application window for FaxRetriever.
    Orchestrates menu, central layout, tray, and modal dialogs.
    """

    # Auto-update signals are handled via worker instances

    settingsLoaded = pyqtSignal()  # Triggered after first GUI show

    def __init__(self, base_dir, exe_dir):
        super().__init__()
        self.base_dir = base_dir
        self.exe_dir = exe_dir
        self.app_state = app_state
        self._force_exit = False
        self.crx_thread = None
        # Keep references to modeless help/document windows to prevent GC
        self._doc_windows = {}

        self.log = get_logger("ui")
        self.setWindowTitle(f"FaxRetriever {__version__}")
        # Allow resizable window for single-pane layout
        # Lowered minimum height to support smaller displays while keeping width
        self.setMinimumSize(1100, 700)
        # self.setWindowFlags(self.windowFlags() & ~Qt.WindowMaximizeButtonHint)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.setWindowFlags(self.windowFlags() | Qt.WindowCloseButtonHint)

        # UI components
        self.status_bar = QStatusBar()
        self.central_widget = QWidget()
        self.main_layout = QGridLayout(self.central_widget)

        # Limited-mode full-screen logo placeholder
        self.limited_logo_label = QLabel()
        self.limited_logo_label.setAlignment(Qt.AlignCenter)
        self.limited_logo_label.setVisible(False)

        self.banner = QLabel()
        self.save_location_input = QLineEdit()
        self.save_location_input.setReadOnly(True)
        self.select_folder_button = QPushButton("Select Save Location")
        self.send_fax_button = QPushButton("Send Fax")
        self.poll_button = QPushButton("Check for New Faxes")
        self.poll_bar = FaxPollTimerProgressBar()

        # Cache banner pixmap once to avoid repeated disk reads and rescaling
        try:
            self._banner_pixmap_orig = QPixmap(
                os.path.join(self.base_dir, "images", "corner_logo.png")
            )
        except Exception:
            self._banner_pixmap_orig = QPixmap()
        # Preload splash image for inactive state
        try:
            self._splash_pixmap_orig = QPixmap(
                os.path.join(self.base_dir, "images", "splash.png")
            )
        except Exception:
            self._splash_pixmap_orig = QPixmap()

        # Proactive bearer refresh handled by poll bar when within 60 minutes of expiry
        self.poll_bar.refresh_bearer_cb = self._retrieve_token
        self.poll_bar.retrieveFaxes = self._on_poll_timer

        # Dialogs
        self.options_dialog = OptionsDialog(self.base_dir, self.app_state)
        self.about_dialog = AboutDialog(self.base_dir)
        self.whats_new_dialog = WhatsNewDialog(self.base_dir)
        self.log_dialog = LogViewer(self.base_dir, self.exe_dir)
        self.address_book_model = AddressBookManager(self.exe_dir)

        self._setup_ui()

        # Auto-update workers
        self._update_checker = None
        self._update_installer = None

        # Busy indicator for receiver processing (non-modal)
        self._receiver_busy = None

        # Validate and Start the System
        self.settingsLoaded.connect(self._validate_and_start)

    def _setup_ui(self):
        """Initialize all UI components and layout."""
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setStatusBar(self.status_bar)
        self.setCentralWidget(self.central_widget)

        self._build_menu()
        self._build_banner()
        self._build_main_controls()
        self._init_tray_icon()

        QTimer.singleShot(0, self._trigger_startup)
        # Run What's New check early (before update checker may overwrite stored version)
        QTimer.singleShot(500, self._maybe_show_whats_new)
        # Defer update check slightly to ensure UI is responsive
        QTimer.singleShot(1500, lambda: self._maybe_check_for_updates(force=True))

    def _show_overlay(self, dialog: QWidget):
        """Show a child dialog as an in-app modal overlay with dimmed scrim and solid content background."""
        scrim = None
        try:
            # Create dim scrim over the main window
            scrim = QWidget(self)
            scrim.setObjectName("overlayScrim")
            scrim.setStyleSheet("#overlayScrim { background: rgba(0,0,0,160); }")
            scrim.setGeometry(self.rect())
            scrim.setAttribute(Qt.WA_TransparentForMouseEvents, False)
            scrim.show()

            # Prepare dialog to appear as overlay content
            dialog.setParent(self)
            dialog.setWindowModality(Qt.ApplicationModal)
            dialog.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
            dialog.setAttribute(Qt.WA_TranslucentBackground, True)
            # Ensure the dialog and its children have an opaque background and visible border
            dialog.setAutoFillBackground(True)
            dialog.setStyleSheet(
                "QDialog { background: #ffffff; border: 1px solid rgba(0,0,0,90); border-radius: 10px; } * { background-color: #ffffff; }"
            )
        except Exception:
            # Fallback to normal modal if anything fails
            pass

        # Center dialog roughly in the main window
        try:
            w = max(500, dialog.minimumWidth())
            h = max(400, dialog.minimumHeight())
            cx = self.geometry().center()
            dialog.setGeometry(cx.x() - w // 2, cx.y() - h // 2, w, h)
        except Exception:
            pass

        dialog.exec_()
        try:
            if scrim is not None:
                scrim.deleteLater()
        except Exception:
            pass

    def _build_menu(self):
        """Initialize system/tool/help menus."""
        menu_bar = QMenuBar(self)
        self.setMenuBar(menu_bar)

        self.system_menu = QMenu("&System", self)
        self.tools_menu = QMenu("&Tools", self)
        self.help_menu = QMenu("&Help", self)

        # System Menu
        opt_action = QAction("Options", self)
        opt_action.triggered.connect(self._show_options_dialog)
        self.system_menu.addAction(opt_action)

        close_action = QAction("Close", self)
        close_action.triggered.connect(self.close)
        self.system_menu.addAction(close_action)

        # Tools Menu
        manage_ab_action = QAction("Manage Address Book", self)
        manage_ab_action.triggered.connect(self.open_address_book_dialog)
        self.tools_menu.addAction(manage_ab_action)

        convert_pdf_jpg_action = QAction("Convert PDF to JPG...", self)
        convert_pdf_jpg_action.setToolTip("Convert one or more PDFs into JPG pages")
        convert_pdf_jpg_action.triggered.connect(self._convert_pdf_to_jpg)
        self.tools_menu.addAction(convert_pdf_jpg_action)
        # Per requirements, remove Fax Status and Send Fax from the menu bar.

        # Help Menu
        # User Guide (Read Me)
        user_guide_action = QAction("Read Me (User Guide)", self)
        user_guide_action.triggered.connect(
            lambda: self._open_markdown_viewer(
                "FaxRetriever 2.0 — User Guide",
                os.path.join(self.base_dir, "src", "docs", "readme.md"),
            )
        )
        self.help_menu.addAction(user_guide_action)

        # What's New
        whats_new_action = QAction("What's New (2.0)", self)
        whats_new_action.triggered.connect(
            lambda: self._open_markdown_viewer(
                "What's New in FaxRetriever 2.0",
                os.path.join(self.base_dir, "src", "docs", "changes.md"),
            )
        )
        self.help_menu.addAction(whats_new_action)

        # About
        view_log_action = QAction("View Log", self)
        view_log_action.triggered.connect(lambda: self._show_overlay(self.log_dialog))
        self.help_menu.addAction(view_log_action)

        # Attach Menus
        menu_bar.addMenu(self.system_menu)
        menu_bar.addMenu(self.tools_menu)
        menu_bar.addMenu(self.help_menu)

    def _open_markdown_viewer(self, title: str, preferred_path: str):
        """Open a Markdown document in a modeless viewer; prefer src\docs then fallback to top-level docs."""
        try:
            candidates = [
                preferred_path,
                os.path.join(self.base_dir, "docs", os.path.basename(preferred_path)),
            ]
            md_path = next((p for p in candidates if os.path.exists(p)), preferred_path)
            key = f"{title}:{md_path}"
            if key in self._doc_windows:
                w = self._doc_windows[key]
                try:
                    w.show()
                    w.raise_()
                    w.activateWindow()
                except Exception:
                    pass
                return
            dlg = MarkdownViewer(self.base_dir, title, md_path, parent=self)
            dlg.setModal(False)
            dlg.show()
            self._doc_windows[key] = dlg
        except Exception as e:
            try:
                QMessageBox.information(
                    self, "Document", f"Unable to open document:\n{e}"
                )
            except Exception:
                pass

    def _convert_pdf_to_jpg(self):
        """Tool: Convert one or more PDFs to JPG pages.
        - Prompts for PDF files.
        - Prompts for an output folder (defaults to Save Location if set).
        - Creates a subfolder per PDF and writes page images there.
        """
        try:
            # Determine a reasonable starting directory
            start_dir = self.app_state.device_cfg.save_path or device_config.get(
                "Fax Options", "save_path", os.path.expanduser("~"))
            if not start_dir or not os.path.isdir(start_dir):
                start_dir = os.path.expanduser("~")

            files, _ = QFileDialog.getOpenFileNames(
                self,
                "Select PDF(s) to convert",
                start_dir,
                "PDF Files (*.pdf)"
            )
            if not files:
                return

            # Choose output directory (defaults to Save Location)
            default_out = self.app_state.device_cfg.save_path or start_dir
            out_dir = QFileDialog.getExistingDirectory(
                self,
                "Select output folder for JPG pages",
                default_out,
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks,
            )
            if not out_dir:
                return

            # Resolve Poppler path similar to thumbnail renderer
            try:
                candidates = [
                    os.path.join(self.base_dir, "poppler", "bin"),
                    os.path.join(self.exe_dir or self.base_dir, "poppler", "bin"),
                ]
                poppler_bin = next((p for p in candidates if os.path.isdir(p)), None)
            except Exception:
                poppler_bin = None

            # Convert each selected PDF
            total_written = 0
            failures: list[str] = []

            # Show busy cursor during conversion
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
            except Exception:
                pass

            from utils.document_utils import convert_pdf_to_jpgs  # local import safety

            for pdf in files:
                try:
                    if not pdf or not os.path.isfile(pdf):
                        failures.append(f"Missing file: {pdf}")
                        continue
                    base = os.path.splitext(os.path.basename(pdf))[0]
                    pdf_out_dir = os.path.join(out_dir, base)
                    os.makedirs(pdf_out_dir, exist_ok=True)
                    result = convert_pdf_to_jpgs(pdf, pdf_out_dir, dpi=200, quality=90, poppler_path=poppler_bin)
                    if isinstance(result, dict) and result.get("error"):
                        failures.append(f"{os.path.basename(pdf)}: {result['error']}")
                        continue
                    total_written += len(result or [])
                except Exception as e:
                    failures.append(f"{os.path.basename(pdf)}: {e}")
                    try:
                        self.log.exception(f"Convert to JPG failed for {pdf}: {e}")
                    except Exception:
                        pass
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

            # Build summary message
            if failures:
                msg = (
                    f"Conversion completed with issues.\n\n"
                    f"Files converted: {len(files) - len(failures)} of {len(files)}\n"
                    f"Total pages written: {total_written}\n\n"
                    f"Problems:\n- " + "\n- ".join(failures)
                )
            else:
                msg = (
                    f"Conversion completed successfully.\n\n"
                    f"Files converted: {len(files)}\n"
                    f"Total pages written: {total_written}\n\n"
                    f"Output folder:\n{out_dir}"
                )
            try:
                QMessageBox.information(self, "Convert PDF to JPG", msg)
            except Exception:
                pass
        except Exception as e:
            try:
                self.log.exception(f"Unexpected error in Convert PDF to JPG tool: {e}")
                QMessageBox.warning(self, "Convert PDF to JPG", f"Unexpected error: {e}")
            except Exception:
                pass

    def _show_options_dialog(self):
        dialog = OptionsDialog(
            base_dir=self.base_dir, app_state=self.app_state, main_window=self
        )
        dialog.load_state_into_form()
        self._show_overlay(dialog)

    def _build_banner(self):
        """Prepare the logo; it will scale to the header's height dynamically."""
        try:
            # Ensure we have an original pixmap cached
            if not hasattr(self, "_banner_pixmap_orig") or self._banner_pixmap_orig.isNull():
                self._banner_pixmap_orig = QPixmap(
                    os.path.join(self.base_dir, "images", "corner_logo.png")
                )
            # Set a temporary pixmap; actual scaling happens in _scale_banner_to_header()
            if not self._banner_pixmap_orig.isNull():
                self.banner.setPixmap(self._banner_pixmap_orig)
        except Exception:
            pass
        self.banner.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        # Let layout control width; keep height constrained by header's max height
        self.banner.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        try:
            self._scale_banner_to_header()
        except Exception:
            pass

    def _scale_banner_to_header(self):
        """Scale the logo pixmap to fit within the header height while preserving aspect ratio."""
        try:
            if not hasattr(self, "header_widget") or self.header_widget is None:
                return
            pix = getattr(self, "_banner_pixmap_orig", QPixmap())
            if pix.isNull():
                return
            # Determine target height: header's height minus vertical margins
            header_h = max(self.header_widget.height(), 1)
            # Account for layout top/bottom margins (~16 total from 8,8,8,8 earlier)
            target_h = max(min(header_h - 10, 200), 24)
            scaled = pix.scaledToHeight(target_h, Qt.SmoothTransformation)
            self.banner.setPixmap(scaled)
        except Exception:
            pass

    def _build_main_controls(self):
        """Main content: left control pane + embedded Send Fax + right history panel in a splitter."""
        self.save_location_input.setPlaceholderText("No folder selected...")
        self.select_folder_button.clicked.connect(self.select_folder)

        # Repurpose Send Fax button as Setup Fax Retrieval per requirements
        self.send_fax_button.setText("Setup Fax Retrieval")
        self.send_fax_button.clicked.connect(self._setup_fax_retrieval)

        # Build left pane
        left_container = QWidget()
        left_v = QVBoxLayout(left_container)
        left_v.setSpacing(8)

        # Header row removed; logo now lives in the full-width top header

        # Left side remains focused on Send Fax; retrieval controls moved to right panel
        # (Save location moved to right Retrieval section)

        # Embedded send fax panel (wrapped in scroll area for small screens)
        self.send_fax_panel = SendFaxPanel(
            self.base_dir, self.exe_dir, self.app_state, self.address_book_model, self
        )
        # Allow panel to shrink vertically; scroll area will preserve access to controls
        try:
            self.send_fax_panel.setMinimumHeight(0)
        except Exception:
            pass
        send_scroll = QScrollArea()
        send_scroll.setWidgetResizable(True)
        try:
            send_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        send_scroll.setWidget(self.send_fax_panel)
        left_v.addWidget(send_scroll, 1)

        # Right side: Fax History (bottom area). Retrieval controls move to a full-width top header.
        self.fax_history_panel = FaxHistoryPanel(
            self.base_dir, self.app_state, self.exe_dir
        )
        self.fax_history_panel.setMinimumWidth(300)

        # Build a full-width top header with logo (left) and retrieval controls (right)
        header = QWidget()
        header.setObjectName("retrievalSection")  # reuse styling/gray-out logic
        header_h = QHBoxLayout(header)
        header_h.setContentsMargins(8, 8, 8, 8)
        header_h.setSpacing(10)

        # Left: small logo
        header_h.addWidget(self.banner)

        # Right: retrieval controls stack
        retrieval_box = QWidget()
        rb_v = QVBoxLayout(retrieval_box)
        rb_v.setContentsMargins(0, 0, 0, 0)
        rb_v.setSpacing(6)

        # Row 1: Save location, Select button, Configure, Manual Poll, Stop
        top_row = QHBoxLayout()
        self.save_location_input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_row.addWidget(self.save_location_input)
        top_row.addWidget(self.select_folder_button)
        self.setup_retrieval_button = QPushButton("Configure Fax Retrieval")
        self.setup_retrieval_button.setToolTip(
            "Select fax number(s) for retrieval on this device"
        )
        self.setup_retrieval_button.clicked.connect(self._setup_fax_retrieval)
        top_row.addWidget(self.setup_retrieval_button)
        top_row.addWidget(self.poll_button)
        self.stop_retrieval_button = QPushButton("Stop Retrieving Faxes")
        self.stop_retrieval_button.setToolTip("Rescind this device's retriever status")
        self.stop_retrieval_button.clicked.connect(self._stop_retrieving_faxes)
        top_row.addWidget(self.stop_retrieval_button)
        rb_v.addLayout(top_row)

        # Row 2: Poll progress bar (fills the available width)
        try:
            self.poll_bar.setFixedHeight(18)
        except Exception:
            pass
        bars_v = QVBoxLayout()
        bars_v.setContentsMargins(0, 0, 0, 0)
        bars_v.setSpacing(4)
        self.poll_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        bars_v.addWidget(self.poll_bar)
        rb_v.addLayout(bars_v)

        header_h.addWidget(retrieval_box, 1)

        # Splitter: left (SendFax) and right (History)
        right_container = QWidget()
        right_v = QVBoxLayout(right_container)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(6)
        right_v.addWidget(self.fax_history_panel, 1)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_container)
        splitter.addWidget(right_container)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        total_w = max(self.width(), 1000)
        splitter.setSizes([int(total_w * 0.65), int(total_w * 0.35)])

        # Place header on top (row 0), splitter below (row 1)
        self.main_layout.addWidget(header, 0, 0, 1, 3)
        self.main_layout.addWidget(splitter, 1, 0, 1, 3)
        # Full-screen limited logo spans all rows
        self.main_layout.addWidget(self.limited_logo_label, 0, 0, 2, 3)
        try:
            self.main_layout.setRowStretch(0, 0)
            self.main_layout.setRowStretch(1, 1)
        except Exception:
            pass

        # Keep a handle for gray-out logic and top widgets
        self.retrieval_section = header
        self.header_widget = header
        self.splitter = splitter

        self.poll_button.clicked.connect(self._manual_poll)

        # Initial interactivity state based on configuration
        self._update_retrieval_interactables()
        self._apply_retrieval_section_state()

    def _init_tray_icon(self):
        """Create system tray icon and right-click menu."""
        icon = QIcon(os.path.join(self.base_dir, "images", "logo.ico"))
        self.tray_icon = QSystemTrayIcon(icon, self)
        menu = QMenu()
        menu.addAction("Open FaxRetriever", self._restore_from_tray)
        exit_action = menu.addAction("Exit FaxRetriever", self._quit_via_tray)
        self.tray_icon.setContextMenu(menu)
        try:
            self.tray_icon.activated.connect(self._on_tray_activated)
        except Exception:
            pass
        self.tray_icon.show()

    def _restore_from_tray(self):
        try:
            self.show()
            self.showNormal()
            try:
                self.raise_()
            except Exception:
                pass
            try:
                self.activateWindow()
            except Exception:
                pass
        except Exception:
            pass

    def _on_tray_activated(self, reason):
        try:
            if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
                self._restore_from_tray()
        except Exception:
            pass

    def _quit_via_tray(self):
        try:
            try:
                self.log.info("User requested Quit via system tray menu.")
            except Exception:
                pass
            self._force_exit = True
            try:
                if hasattr(self, "tray_icon") and self.tray_icon:
                    self.tray_icon.hide()
            except Exception:
                pass
            self.close()
        except Exception:
            try:
                self.log.exception("Error during tray quit flow")
            except Exception:
                pass
            self.close()

    def _manual_poll(self):
        """Trigger manual fax check (delegated)."""
        # Enforce authorization before allowing any retrieval
        mode_ok = ((self.app_state.device_cfg.retriever_mode or "").lower() == "sender_receiver")
        status_ok = ((self.app_state.device_cfg.retriever_status or "").lower() == "allowed")
        if not (mode_ok and status_ok):
            try:
                self.log.warning("Manual poll blocked: device is not authorized as retriever.")
            except Exception:
                pass
            self.status_bar.showMessage("This device is not authorized to retrieve faxes.", 4000)
            try:
                self.poll_bar.timer.stop()
            except Exception:
                pass
            return
        self.status_bar.showMessage("Manual fax poll requested")
        self.poll_bar.retrieveFaxes()

    def _stop_retrieving_faxes(self):
        """Rescind retriever status for this device (unregister assignments)."""
        # Confirm with user before proceeding
        resp = QMessageBox.question(
            self,
            "Stop Retrieving Faxes",
            "Are you sure you want to stop retrieving faxes from this device?\n\nYou may re-enroll at any time so long as there isn't already another retriever device.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        try:
            from core.admin_client import get_device_id, unregister_assignments
        except Exception:
            unregister_assignments = None
            get_device_id = lambda: "UNKNOWN"
        jwt = self.app_state.global_cfg.jwt_token or ""
        numbers = list(self.app_state.device_cfg.selected_fax_numbers or [])
        if unregister_assignments and jwt:
            try:
                # Unregister selected numbers; if none recorded, unregister all for device
                payload_numbers = numbers if numbers else None
                res = unregister_assignments(jwt, payload_numbers, get_device_id())
                if res.get("error"):
                    QMessageBox.warning(
                        self, "Unregister", f"Failed to unregister: {res['error']}"
                    )
                else:
                    self.status_bar.showMessage(
                        "Retriever assignments rescinded.", 4000
                    )
            except Exception as e:
                QMessageBox.warning(
                    self, "Unregister", f"Unregister request failed: {e}"
                )
        # Update local config regardless to reflect stop state
        try:
            device_config.set("Account", "selected_fax_numbers", [])
            device_config.set("Account", "selected_fax_number", "")
            device_config.set("Account", "retriever_mode", "sender_only")
            device_config.set("Account", "requested_retriever_mode", "sender_only")
            device_config.set("Token", "retriever_status", "revoked")
            device_config.save()
        except Exception:
            pass
        self.app_state.sync_from_config()
        # Stop timers/polling
        try:
            self.poll_bar.timer.stop()
        except Exception:
            pass
        # Apply new UI state
        self._apply_operational_mode()

    def _setup_fax_retrieval(self):
        """Open in-app modal to select fax numbers; consult assignments routes and apply on confirm."""
        from PyQt5.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

        from core.admin_client import (get_device_id, list_assignments,
                                       request_assignments)

        dlg = QDialog(self)
        dlg.setWindowTitle("Setup Fax Retrieval")
        v = QVBoxLayout(dlg)

        instructions = QLabel(
            "Select fax number(s) to retrieve on this device. Only one retriever per number is allowed."
        )
        instructions.setWordWrap(True)
        v.addWidget(instructions)

        lst = QListWidget()
        lst.setSelectionMode(QListWidget.MultiSelection)
        v.addWidget(lst)

        # Populate list with ownership coloring
        numbers = self.app_state.global_cfg.all_numbers or []
        owners = {}
        jwt = self.app_state.global_cfg.jwt_token or ""
        if jwt:
            from ui.busy import BusyDialog

            with BusyDialog(self, "Loading assignments…"):
                data = list_assignments(jwt)
            owners = (data.get("results") or {}) if isinstance(data, dict) else {}
        dev_id = get_device_id()
        for n in numbers:
            owner = (owners.get(n) or {}).get("owner") if owners else None
            label = f"{n}"
            if owner:
                label += f"  — owner: {owner}"
            item = QListWidgetItem(label)
            if owner and owner == dev_id:
                item.setForeground(Qt.darkGreen)
            elif owner and owner != dev_id:
                item.setForeground(Qt.darkRed)
            if n in (self.app_state.device_cfg.selected_fax_numbers or []):
                item.setSelected(True)
            lst.addItem(item)

        # Buttons row
        row = QHBoxLayout()
        row.addStretch()
        ok = QPushButton("Apply Selection")
        cancel = QPushButton("Cancel")
        row.addWidget(ok)
        row.addWidget(cancel)
        v.addLayout(row)

        def on_ok():
            selected = [i.text().split()[0] for i in lst.selectedItems()]
            if not selected:
                QMessageBox.warning(
                    dlg, "Select Numbers", "Please select at least one fax number."
                )
                return
            jwt_token = self.app_state.global_cfg.jwt_token or ""
            if not jwt_token:
                QMessageBox.warning(
                    dlg,
                    "Missing JWT",
                    "Initialize in Options before requesting assignments.",
                )
                return
            from ui.busy import BusyDialog

            with BusyDialog(self, "Applying selection…"):
                res = request_assignments(jwt_token, selected)
            if res.get("error"):
                QMessageBox.critical(dlg, "Assignment Error", f"{res['error']}")
                return
            # Persist upgraded JWT if backend provided additional scopes (e.g., assignments.unregister)
            new_jwt = res.get("jwt_token")
            if new_jwt:
                try:
                    global_config.set("Token", "jwt_token", new_jwt)
                    global_config.save()
                    self.app_state.global_cfg.jwt_token = new_jwt
                except Exception:
                    pass
            results = res.get("results", {})
            allowed = [
                n for n, r in results.items() if (r or {}).get("status") == "allowed"
            ]
            denied = [
                n for n, r in results.items() if (r or {}).get("status") != "allowed"
            ]
            if allowed:
                device_config.set("Account", "selected_fax_numbers", allowed)
                device_config.set("Account", "selected_fax_number", allowed[0])
                device_config.set("Account", "retriever_mode", "sender_receiver")
                device_config.set(
                    "Account", "requested_retriever_mode", "sender_receiver"
                )
                device_config.set("Token", "retriever_status", "allowed")
                device_config.save()
                self.app_state.sync_from_config()
                self._apply_operational_mode()
            msg = []
            if allowed:
                msg.append(f"Allowed: {', '.join(allowed)}")
            if denied:
                msg.append(f"Denied: {', '.join(denied)}")
            self.status_bar.showMessage("; ".join(msg) or "No changes.", 5000)
            dlg.accept()

        ok.clicked.connect(on_ok)
        cancel.clicked.connect(dlg.reject)
        self._show_overlay(dlg)

    def _on_receiver_finished(self):
        # Close any active busy indicator for receiver processing
        try:
            if getattr(self, "_receiver_busy", None):
                self._receiver_busy.close()
                self._receiver_busy = None
        except Exception:
            pass
        # After any receiver pass completes, refresh the history panel
        try:
            if hasattr(self, "fax_history_panel"):
                if hasattr(self.fax_history_panel, "request_refresh"):
                    self.fax_history_panel.request_refresh()
                else:
                    self.fax_history_panel.refresh()
        except Exception:
            pass
        # Kick integrations if configured
        try:
            self._maybe_run_integrations()
        except Exception:
            pass
        self.status_bar.showMessage("Poll pass complete.", 2000)

    def _on_poll_timer(self):
        """
        Bound to FaxPollTimerProgressBar.retrieveFaxes.
        Policy:
          - If not authorized as retriever, do nothing.
          - If bearer missing or <60 min remaining, attempt refresh.
          - Always run the receiver pass afterward.
        """
        # Authorization check
        mode_ok = ((self.app_state.device_cfg.retriever_mode or "").lower() == "sender_receiver")
        status_ok = ((self.app_state.device_cfg.retriever_status or "").lower() == "allowed")
        if not (mode_ok and status_ok):
            try:
                self.log.info("Poll timer tick ignored: device is not authorized as retriever.")
            except Exception:
                pass
            try:
                self.poll_bar.timer.stop()
            except Exception:
                pass
            return

        try:
            if not self._has_valid_bearer_token(min_minutes=60):
                self.log.info(
                    "Bearer missing/stale (<60m). Attempting refresh before poll."
                )
                self._retrieve_token()
        except Exception as e:
            self.log.warning(f"Bearer check failed: {e}")

        # Run one poll pass
        try:
            # Show a non-blocking busy indicator while the receiver processes faxes
            try:
                from ui.busy import BusyDialog

                # Close any prior busy indicator just in case
                try:
                    if getattr(self, "_receiver_busy", None):
                        self._receiver_busy.close()
                except Exception:
                    pass
                self._receiver_busy = BusyDialog(self, "Processing faxes…", modal=False)
                self._receiver_busy.show()
            except Exception:
                self._receiver_busy = None

            self.receiver_thread = FaxReceiver(self.base_dir)
            self.receiver_thread.finished.connect(self._on_receiver_finished)
            self.receiver_thread.start()
        except Exception as e:
            # Ensure busy indicator is closed on failure
            try:
                if getattr(self, "_receiver_busy", None):
                    self._receiver_busy.close()
                    self._receiver_busy = None
            except Exception:
                pass
            self.log.exception(f"Receiver start failed: {e}")
            QMessageBox.warning(self, "Receiver", f"Poll failed to start:\n{e}")

    def select_folder(self):
        """Prompt user to choose a new save folder."""
        path = QFileDialog.getExistingDirectory(self, "Select Folder")
        if path:
            self.app_state.device_cfg.save_path = path
            device_config.set("Fax Options", "save_path", path)
            device_config.save()

            self.status_bar.showMessage("Save location updated.", 3000)
            self.save_location_input.setText(path)
            self._update_retrieval_interactables()
        else:
            self.status_bar.showMessage("Save location unchanged.", 3000)

    def _post_load_state(self):
        """Apply config-based UI states after load."""
        current_path = device_config.get("Fax Options", "save_path", "")
        if current_path:
            self.save_location_input.setText(current_path)
        else:
            self.status_bar.showMessage("No save folder configured.", 5000)

    def _validate_and_start(self):
        global_config._load()
        self.app_state.sync_from_config()

        if not self.app_state.global_cfg.fax_user:
            QMessageBox.warning(
                self,
                "Missing User",
                "Please configure your Fax User in System > Options.",
            )
            self._apply_operational_mode()
            return

        if not self.app_state.global_cfg.validation_status:
            QMessageBox.critical(
                self,
                "Not Licensed",
                "This account is not licensed or authenticated. Open Options to configure.",
            )
            self._apply_operational_mode()
            return

        if not self._has_valid_bearer_token():
            self._retrieve_token()
        else:
            self._apply_operational_mode()

    def _retrieve_token(self):
        from ui.busy import BusyDialog

        with BusyDialog(self, "Refreshing token..."):
            result = retrieve_skyswitch_token(self.app_state)

        if result.get("error"):
            QMessageBox.critical(
                self,
                "Token Error",
                f"Failed to retrieve SkySwitch bearer token:\n\n{result['error']}",
            )
            self._apply_operational_mode()
            return

        self.app_state.global_cfg.bearer_token = result["bearer_token"]
        self.app_state.global_cfg.bearer_token_expiration = result["expires_at"]
        self.app_state.global_cfg.bearer_token_retrieved = datetime.now(
            timezone.utc
        ).isoformat()

        self.poll_bar.restart_progress()
        self.status_bar.showMessage("Bearer refreshed.", 2000)

        numbers = result.get(
            "all_fax_numbers", self.app_state.global_cfg.all_numbers or []
        )
        self.app_state.update_token_state(
            bearer_token=result["bearer_token"],
            expires_at=result["expires_at"],
            fax_numbers=numbers,
        )

        # After refreshing bearer, update retriever assignments cache (global)
        try:
            from core.admin_client import list_assignments

            jwt = self.app_state.global_cfg.jwt_token or ""
            if jwt:
                data = list_assignments(jwt)
                results = data.get("results") if isinstance(data, dict) else None
                if isinstance(results, dict):
                    global_config.set("Account", "retriever_assignments", results)
                    global_config.save()
        except Exception:
            pass

        self._apply_operational_mode()

    def _has_valid_bearer_token(self, min_minutes: int = 5) -> bool:
        """
        True if bearer exists and expires later than now + min_minutes.
        """
        try:
            exp = self.app_state.global_cfg.bearer_token_expiration
            token = self.app_state.global_cfg.bearer_token
            if not token or not exp:
                return False
            buffer = timedelta(minutes=min_minutes)
            # Use UTC if input is naive
            exp_dt = datetime.fromisoformat(exp)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return exp_dt > now + buffer
        except Exception as e:
            self.log.debug(f"Token validity check failed: {e}")
            return False

    def _start_token_refresh(self):

        self.token_thread = RetrieveToken()
        self.token_thread.token_retrieved.connect(self._start_services)
        self.token_thread.finished.connect(self._token_result)
        self.token_thread.start()

    def _token_result(self, status, msg):
        if status != "Success":
            QMessageBox.critical(self, "Token Error", msg)

    def _start_services(self):
        # Authorization check: never start receiver unless explicitly authorized
        mode_ok = ((self.app_state.device_cfg.retriever_mode or "").lower() == "sender_receiver")
        status_ok = ((self.app_state.device_cfg.retriever_status or "").lower() == "allowed")
        if not (mode_ok and status_ok):
            try:
                self.log.info("Start services skipped: device not authorized as retriever.")
            except Exception:
                pass
            try:
                self.poll_bar.timer.stop()
            except Exception:
                pass
            return

        self.status_bar.showMessage("Initializing fax engine...")
        # Kick a one-time preflight token attempt if we’re already inside the 60m window
        try:
            if not self._has_valid_bearer_token(min_minutes=60):
                self.log.info("Initial start: bearer near-expiry; attempting refresh.")
                self._retrieve_token()
        except Exception as e:
            self.log.warning(f"Initial bearer preflight failed: {e}")

        # Show a non-blocking busy indicator during initial receiver run
        try:
            from ui.busy import BusyDialog

            try:
                if getattr(self, "_receiver_busy", None):
                    self._receiver_busy.close()
            except Exception:
                pass
            self._receiver_busy = BusyDialog(self, "Processing faxes…", modal=False)
            self._receiver_busy.show()
        except Exception:
            self._receiver_busy = None

        self.receiver_thread = FaxReceiver(self.base_dir)
        self.receiver_thread.finished.connect(self._on_receiver_finished)
        self.receiver_thread.start()
        # Also start third-party integrations if configured
        try:
            self._maybe_run_integrations()
        except Exception:
            pass
        self.poll_bar.restart_progress()
        self.status_bar.showMessage("Fax engine ready.", 3000)

    def open_address_book_dialog(self):
        # Open Address Book dialog modelessly; keep single instance and reuse
        try:
            # Prefer SendFaxPanel as parent so selections populate fax fields
            parent_widget = getattr(self, "send_fax_panel", self)
            # Reuse existing dialog if open
            existing = getattr(self, "_address_book_dialog", None)
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
            dlg = AddressBookDialog(
                self.base_dir, self.address_book_model, parent_widget
            )
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
        except Exception:
            # Fallback to modal open to preserve functionality if modeless fails
            try:
                dlg = AddressBookDialog(
                    self.base_dir,
                    self.address_book_model,
                    getattr(self, "send_fax_panel", self),
                )
                dlg.exec_()
            except Exception:
                pass

    def _trigger_startup(self):
        # Attempt one-time migration of v1 settings before loading state
        try:
            from core.v1_migration import migrate_v1_if_present

            if migrate_v1_if_present():
                try:
                    self.status_bar.showMessage(
                        "Imported settings from FaxRetriever v1.", 5000
                    )
                except Exception:
                    pass
        except Exception:
            # Migration is best-effort; continue silently on failure
            pass
        self._post_load_state()
        self._validate_and_start()
        # Also mark that startup completed for potential UI prompts

    def _focus_fax_history(self):
        try:
            if hasattr(self, "fax_history_panel"):
                self.fax_history_panel.setVisible(True)
                if hasattr(self.fax_history_panel, "request_refresh"):
                    self.fax_history_panel.request_refresh()
                else:
                    self.fax_history_panel.refresh()
                # Optional: provide feedback
                self.status_bar.showMessage("Fax history refreshed.", 2000)
        except Exception as e:
            self.log.debug(f"Fax history focus failed: {e}")

    def _apply_operational_mode(self):
        """
        Applies UI visibility and behavior based on current validation and auto-retrieve mode.
        States:
        - Limited Mode: only a full-screen logo is displayed.
        - Send-Only Mode (no numbers approved): show only the Configure button.
        - Post-Approval (numbers approved but not fully configured): hide Configure; show Save/QLineEdit and Poll, with Poll disabled until save path stored.
        - Full Mode (all requirements met): hide Configure; show everything enabled and start services.
        """
        global_config.save()
        device_config.save()
        validation = self.app_state.global_cfg.validation_status
        auto_retrieve = (
            self.app_state.device_cfg.retriever_mode or ""
        ).lower() == "sender_receiver"
        status_allowed = (self.app_state.device_cfg.retriever_status or "").lower() == "allowed"
        allowed_to_retrieve = auto_retrieve and status_allowed
        numbers_approved = bool(self.app_state.device_cfg.selected_fax_numbers)
        save_path = self.app_state.device_cfg.save_path or device_config.get(
            "Fax Options", "save_path", ""
        )
        self.save_location_input.setText(save_path)
        # If save_path exists in persisted config but not hydrated into runtime yet, hydrate now
        if not self.app_state.device_cfg.save_path and save_path:
            try:
                self.app_state.update_save_path(save_path)
            except Exception:
                pass

        # Prepare full-screen splash pixmap (use cached pixmap)
        try:
            pix = getattr(self, "_splash_pixmap_orig", QPixmap())
            if pix.isNull():
                pix = QPixmap(os.path.join(self.base_dir, "images", "splash.png"))
            if not pix.isNull():
                self.limited_logo_label.setPixmap(
                    pix.scaled(self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )
        except Exception:
            pass

        if not validation:
            # ── Limited Mode ────────────────────────────────────────
            self.log.warning("Entering limited mode (validation_status=False).")
            # Hide menus and status, show only a full-screen logo
            try:
                self.menuBar().setVisible(True)
                self.status_bar.setVisible(True)
            except Exception:
                pass
            # Hide all panels/controls
            if hasattr(self, "header_widget"):
                self.header_widget.setVisible(False)
            if hasattr(self, "splitter"):
                self.splitter.setVisible(False)
            if hasattr(self, "fax_history_panel"):
                self.fax_history_panel.setVisible(False)
            if hasattr(self, "send_fax_panel"):
                self.send_fax_panel.setVisible(False)
            try:
                self.poll_bar.timer.stop()
            except Exception:
                pass
            self.limited_logo_label.setVisible(True)
            return

        # ── Validated Mode ─────────────────────────────────────────
        # Restore menu/status and base sections
        try:
            self.menuBar().setVisible(True)
        except Exception:
            pass
        self.status_bar.setVisible(True)
        if hasattr(self, "header_widget"):
            self.header_widget.setVisible(True)
        if hasattr(self, "splitter"):
            self.splitter.setVisible(True)
        self.limited_logo_label.setVisible(False)

        self.tools_menu.menuAction().setVisible(True)
        if hasattr(self, "fax_history_panel"):
            self.fax_history_panel.setVisible(True)
        if hasattr(self, "send_fax_panel"):
            self.send_fax_panel.setVisible(True)

        # Default visibility for retrieval header controls
        show_configure = True
        show_save = False
        show_poll = False
        show_bars = True
        show_stop = False

        # Startup confirmation: log whether we are authorized as a retriever
        try:
            if allowed_to_retrieve:
                self.log.info(
                    f"Startup: device authorized as retriever (mode=sender_receiver, status=allowed)."
                )
            else:
                self.log.info(
                    f"Startup: device is NOT authorized as retriever (mode={'sender_receiver' if auto_retrieve else (self.app_state.device_cfg.retriever_mode or '').lower()}, status={'allowed' if status_allowed else (self.app_state.device_cfg.retriever_status or '').lower()}). Running as sender-only."
                )
        except Exception:
            pass

        if allowed_to_retrieve and self._requirements_met_for_retrieval():
            # ── Full Mode (Send + Polling) ─────────────────────────
            self.log.info("System in full service mode (Send + Polling).")
            show_configure = False
            show_save = True
            show_poll = True
            show_stop = True
            self._start_services()
            self.status_bar.showMessage("Ready (All Services Mode)")
        elif allowed_to_retrieve and numbers_approved:
            # ── Post-Approval / Partial Config ─────────────────────
            self.log.info("Numbers approved; awaiting full configuration.")
            show_configure = False
            show_save = True
            show_poll = True
            show_stop = True
            # Enablement handled below: poll disabled until save_path exists
            if not save_path:
                self.status_bar.showMessage(
                    "Select a Save Location to enable retrieving faxes."
                )
            else:
                self.status_bar.showMessage("Ready to retrieve faxes.")
        else:
            # ── Send-Only ──────────────────────────────────────────
            self.log.info("System in send-only mode; show Configure button only.")
            show_configure = True
            show_save = False
            show_poll = False
            show_stop = False
            # Ensure polling timer is stopped when not authorized
            try:
                self.poll_bar.timer.stop()
            except Exception:
                pass
            self.status_bar.showMessage(
                "Ready (Send Only) — Configure Fax Retrieval to begin."
            )

        # Apply visibility
        if hasattr(self, "setup_retrieval_button"):
            self.setup_retrieval_button.setVisible(show_configure)
        self.save_location_input.setVisible(show_save)
        self.select_folder_button.setVisible(show_save)
        self.poll_button.setVisible(show_poll)
        self.poll_bar.setVisible(show_bars)
        if hasattr(self, "stop_retrieval_button"):
            self.stop_retrieval_button.setVisible(show_stop)

        # Enablement: disable poll until minimum requirements met for this stage
        # For post-approval stage, require at least save_path. For full mode, existing logic applies.
        if numbers_approved and not save_path:
            self.poll_button.setEnabled(False)
            self.poll_bar.setEnabled(False)
        else:
            self._update_retrieval_interactables()
        # Apply gray-out styling/enabling based on retriever status
        self._apply_retrieval_section_state()

    def _requirements_met_for_retrieval(self) -> bool:
        cfg = self.app_state.device_cfg
        # Prefer in-memory value but fall back to persisted config to avoid startup race
        path = cfg.save_path or device_config.get("Fax Options", "save_path", "")
        have_numbers = bool(cfg.selected_fax_numbers)
        have_path = bool(path)
        # Authorization: must be explicitly configured as sender_receiver and allowed
        mode_ok = ((cfg.retriever_mode or "").lower() == "sender_receiver")
        status_ok = ((cfg.retriever_status or "").lower() == "allowed")
        allowed = mode_ok and status_ok
        # Use sensible defaults if fields are unset (legacy configs)
        try:
            pf = (
                cfg.polling_frequency
                if cfg.polling_frequency is not None
                else device_config.get("Fax Options", "polling_frequency", 15)
            )
            have_poll = bool(int(pf or 15))
        except Exception:
            have_poll = True
        have_method = bool(
            (
                cfg.download_method
                or device_config.get("Fax Options", "download_method", "PDF")
            )
        )
        # file_name_format defaults to 'faxid' if missing; do not block readiness on it
        have_format = True
        # If we discovered a persisted save path but app_state lacks it, hydrate runtime state
        if not cfg.save_path and path:
            try:
                self.app_state.update_save_path(path)
            except Exception:
                pass
        return all([allowed, have_numbers, have_path, have_poll, have_method, have_format])

    def _update_retrieval_interactables(self):
        cfg = self.app_state.device_cfg
        # Authorization: must be explicitly configured as sender_receiver and allowed
        mode_ok = ((cfg.retriever_mode or "").lower() == "sender_receiver")
        status_ok = ((cfg.retriever_status or "").lower() == "allowed")
        allowed = mode_ok and status_ok
        # If numbers are approved and a save path is set, allow manual polling,
        # otherwise fall back to the stricter full-requirements check.
        path = cfg.save_path or device_config.get("Fax Options", "save_path", "")
        enabled_min = bool(cfg.selected_fax_numbers) and bool(path)
        # If we found a persisted path but app_state lacks it, hydrate
        if not cfg.save_path and path:
            try:
                self.app_state.update_save_path(path)
            except Exception:
                pass
        enabled = allowed and (enabled_min or self._requirements_met_for_retrieval())
        self.poll_button.setEnabled(enabled)
        self.poll_bar.setEnabled(enabled)
        if enabled:
            try:
                self.poll_bar.restart_progress()
            except Exception:
                pass
        else:
            try:
                self.poll_bar.timer.stop()
                self.poll_bar.setValue(0)
            except Exception:
                pass
        self._apply_retrieval_section_state()

    def _apply_retrieval_section_state(self):
        """Gray-out Retrieval section when client retrieval is disabled; leave Configure button enabled if permitted."""
        try:
            status = (self.app_state.device_cfg.retriever_status or "").lower()
            mode = (self.app_state.device_cfg.retriever_mode or "").lower()
            is_allowed = (status == "allowed" and mode == "sender_receiver")
            # Configure is allowed when validated (JWT present)
            can_configure = bool(self.app_state.global_cfg.jwt_token)
            if hasattr(self, "setup_retrieval_button"):
                self.setup_retrieval_button.setEnabled(can_configure)
            # Disable other controls if not allowed
            for w in [
                self.save_location_input,
                self.select_folder_button,
                self.poll_button,
                self.poll_bar,
            ]:
                try:
                    w.setEnabled(
                        is_allowed
                        and (
                            w not in [self.poll_button, self.poll_bar]
                            or self._requirements_met_for_retrieval()
                        )
                    )
                except Exception:
                    pass
            # Visual gray-out
            if hasattr(self, "retrieval_section") and self.retrieval_section:
                if not is_allowed:
                    self.retrieval_section.setStyleSheet(
                        "#retrievalSection{background-color:#f5f5f5;} QWidget{color:#888;}"
                    )
                else:
                    self.retrieval_section.setStyleSheet("")
        except Exception:
            pass

    def _maybe_run_integrations(self):
        """Start Computer-Rx integration once if enabled/selected and not already running."""
        try:
            # Prefer device-level settings
            settings = device_config.get(
                "Integrations", "integration_settings", {}
            ) or (self.app_state.device_cfg.integration_settings or {})
            enabled = (
                settings.get("enable_third_party") or ""
            ).strip().lower() == "yes"
            software = (settings.get("integration_software") or "None").strip()
            if not (enabled and software == "Computer-Rx"):
                return
            winrx_path = device_config.get("Integrations", "winrx_path", "") or (
                self.app_state.device_cfg.winrx_path or ""
            )
            if not (winrx_path and os.path.isdir(winrx_path)):
                return
            if (
                self.crx_thread is not None
                and hasattr(self.crx_thread, "isRunning")
                and self.crx_thread.isRunning()
            ):
                return
            self.crx_thread = CRxIntegration2(self.base_dir)

            # Start delivery poller if enabled
            try:
                poll_enabled = True
                try:
                    cfg = device_config.get("Integrations", "integration_settings", {}) or {}
                    v = str(cfg.get("enable_crx_delivery_tracking", "Yes") or "Yes").strip().lower()
                    poll_enabled = (v == "yes")
                except Exception:
                    poll_enabled = True
                if poll_enabled:
                    interval = 60
                    max_attempts = 3
                    try:
                        interval = int(cfg.get("crx_poll_interval_sec", 60))
                    except Exception:
                        pass
                    try:
                        max_attempts = int(cfg.get("crx_max_attempts", 3))
                    except Exception:
                        pass
                    # Avoid duplicate poller
                    if getattr(self, "crx_poller", None) is None or not self.crx_poller.isRunning():
                        self.crx_poller = CrxDeliveryPoller(self, interval_sec=interval, max_attempts=max_attempts)
                        self.crx_poller.start()
            except Exception:
                pass

            def _on_done():
                try:
                    self.crx_thread = None
                except Exception:
                    pass

            try:
                self.crx_thread.finished.connect(_on_done)
            except Exception:
                pass
            self.crx_thread.start()
        except Exception as e:
            try:
                self.log.debug(f"Integrations start skipped: {e}")
            except Exception:
                pass

    def closeEvent(self, event):
        try:
            if getattr(self, "_force_exit", False):
                try:
                    self.log.info("Application closing (forced exit requested).")
                except Exception:
                    pass
                # Stop CRx delivery poller if running
                try:
                    if getattr(self, "crx_poller", None):
                        self.crx_poller.stop()
                        try:
                            self.crx_poller.wait(2000)
                        except Exception:
                            pass
                        self.crx_poller = None
                except Exception:
                    pass
                event.accept()
                return
            close_to_tray = (
                str(getattr(self.app_state.device_cfg, "close_to_tray", "No") or "No")
                .strip()
                .lower()
                == "yes"
            )
            is_receiver = (
                str(getattr(self.app_state.device_cfg, "retriever_mode", "") or "")
                .strip()
                .lower()
                == "sender_receiver"
            )
            if close_to_tray:
                try:
                    self.log.info("Close requested; honoring 'Close to Tray' setting and minimizing to tray.")
                except Exception:
                    pass
                try:
                    if hasattr(self, "tray_icon") and self.tray_icon:
                        self.tray_icon.showMessage(
                            "FaxRetriever",
                            "Running in background."
                            + (" Receiver mode active." if is_receiver else ""),
                            QSystemTrayIcon.Information,
                            3000,
                        )
                except Exception:
                    pass
                self.hide()
                event.ignore()
                return
            if is_receiver:
                try:
                    self.log.info("Close requested while in Receiver mode; prompting user for action.")
                except Exception:
                    pass
                box = QMessageBox(self)
                box.setWindowTitle("Close FaxRetriever")
                box.setIcon(QMessageBox.Warning)
                box.setText(
                    "FaxRetriever is in Receiver mode. Closing the application will prevent faxes from being downloaded.\nWhat would you like to do?"
                )
                minimize_btn = box.addButton("Minimize to Tray", QMessageBox.AcceptRole)
                close_btn = box.addButton("Close Anyway", QMessageBox.DestructiveRole)
                cancel_btn = box.addButton("Cancel", QMessageBox.RejectRole)
                box.exec_()
                clicked = box.clickedButton()
                if clicked == minimize_btn:
                    try:
                        self.log.info("User chose: Minimize to Tray.")
                    except Exception:
                        pass
                    self.hide()
                    event.ignore()
                    return
                elif clicked == close_btn:
                    try:
                        self.log.info("User chose: Close Anyway. Application window will close.")
                    except Exception:
                        pass
                    event.accept()
                    return
                else:
                    try:
                        self.log.info("User canceled close.")
                    except Exception:
                        pass
                    event.ignore()
                    return
            try:
                self.log.info("Application window closed by user.")
            except Exception:
                pass
            event.accept()
        except Exception:
            event.accept()

    def showEvent(self, event):
        try:
            get_notifier().set_ready(self)
        except Exception:
            pass
        return super().showEvent(event)

    def resizeEvent(self, event):
        try:
            if hasattr(self, "retrieval_section") and self.retrieval_section:
                # Cap header to a reasonable height; allow up to ~25% but not overly large
                cap = int(min(max(120, self.height() * 0.25), 240))
                self.retrieval_section.setMaximumHeight(cap)
            # After capping header height, scale the banner to fit the header area
            try:
                self._scale_banner_to_header()
            except Exception:
                pass
            # Rescale limited-mode splash to fill window while preserving aspect
            if (
                hasattr(self, "limited_logo_label")
                and self.limited_logo_label.isVisible()
            ):
                pix = getattr(self, "_splash_pixmap_orig", QPixmap())
                if pix.isNull():
                    pix = QPixmap(os.path.join(self.base_dir, "images", "splash.png"))
                if not pix.isNull():
                    self.limited_logo_label.setPixmap(
                        pix.scaled(
                            self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
        except Exception:
            pass
        return super().resizeEvent(event)

    def _maybe_show_whats_new(self):
        """
        Show the What's New dialog automatically when the app version changes,
        and on the first deployment of FaxRetriever v2+.
        Uses device_config[AutoUpdate][current_version] as the last-seen marker.
        """
        try:
            prev = str(
                device_config.get("AutoUpdate", "current_version", "") or ""
            ).strip()
            current = str(__version__ or "").strip()

            def major(v: str) -> int:
                try:
                    v = v.strip()
                    if v.startswith("v"):
                        v = v[1:]
                    core = v.split("-")[0]
                    return int((core.split(".")[0] or "0"))
                except Exception:
                    return 0

            show = False
            if not prev:
                # First run on this device; only auto-pop for v2+
                show = major(current) >= 2
            else:
                show = prev != current
            if show:
                try:
                    # Prefer the pre-created dialog instance for consistency
                    self._show_overlay(self.whats_new_dialog)
                except Exception:
                    # Fallback to a standalone modal if overlay fails
                    try:
                        dlg = WhatsNewDialog(self.base_dir, self)
                        dlg.exec_()
                    except Exception:
                        pass
                # Persist that the current version has been acknowledged
                try:
                    device_config.set("AutoUpdate", "current_version", current)
                    device_config.save()
                except Exception:
                    pass
        except Exception as e:
            try:
                self.log.debug(f"WhatsNew check failed: {e}")
            except Exception:
                pass

    # ─────────────────────────── Auto-Update Support ───────────────────────────
    def _maybe_check_for_updates(self, force: bool = False):
        try:
            if not is_time_to_check(force):
                return
            # Provide subtle status to user
            try:
                self.status_bar.showMessage("Checking for updates...", 5000)
            except Exception:
                pass
            self._update_checker = UpdateChecker(force=force)
            try:
                self._update_checker.update_available.connect(self._on_update_available)
                self._update_checker.no_update.connect(self._on_no_update)
                self._update_checker.error.connect(self._on_update_error)
            except Exception:
                pass
            self._update_checker.start()
        except Exception as e:
            self.log.debug(f"Auto-update check skipped: {e}")

    def _on_update_available(self, version: str, url: str):
        try:
            # Ask the user for confirmation
            box = QMessageBox(self)
            box.setWindowTitle("Update Available")
            box.setIcon(QMessageBox.Information)
            box.setText(
                f"A new version of FaxRetriever is available: {version}.\n\nInstall now? The current version will be backed up and the app will restart."
            )
            yes_btn = box.addButton("Install Now", QMessageBox.AcceptRole)
            later_btn = box.addButton("Later", QMessageBox.RejectRole)
            box.exec_()
            if box.clickedButton() != yes_btn:
                try:
                    self.status_bar.showMessage("Update postponed.", 4000)
                except Exception:
                    pass
                return
            # Start installer
            self.status_bar.showMessage("Downloading update...", 3000)
            self._update_installer = UpdateInstaller(version, url, self.exe_dir)
            try:
                self._update_installer.progress.connect(
                    lambda msg: self.status_bar.showMessage(msg, 5000)
                )
                self._update_installer.completed.connect(
                    self._on_update_install_started
                )
                self._update_installer.failed.connect(self._on_update_failed)
            except Exception:
                pass
            self._update_installer.start()
        except Exception as e:
            self.log.exception(f"Failed to present update: {e}")

    def _on_no_update(self, message: str):
        try:
            # Only show in status bar, non-intrusive
            self.status_bar.showMessage(message or "No updates available.", 4000)
        except Exception:
            pass

    def _on_update_error(self, message: str):
        try:
            self.status_bar.showMessage(message or "Update check failed.", 5000)
        except Exception:
            pass

    def _on_update_install_started(self):
        try:
            # The installer batch will close/restart the app; request a graceful quit
            self._force_exit = True
            QApplication.instance().quit()
        except Exception:
            pass

    def _on_update_failed(self, message: str):
        try:
            box = QMessageBox(self)
            box.setWindowTitle("Update Failed")
            box.setIcon(QMessageBox.Warning)
            box.setText(f"The update could not be installed.\n\n{message}")
            box.exec_()
            self.status_bar.showMessage("Update failed.", 5000)
        except Exception:
            pass
