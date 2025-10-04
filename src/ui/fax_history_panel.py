import os

from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit, QMessageBox, QWidget, QScrollArea, QFrame, QSizePolicy, QFileDialog

from utils.logging_utils import get_logger
from core.address_book import AddressBookManager
from ui.address_book_dialog import AddContactDialog
from ui.utils.thumb_loader import ThumbnailHelper
from ui.widgets.fax_history_card import create_fax_card
from ui.widgets.pdf_viewer_dialog import open_pdf_viewer, open_pdf_viewer_confirmation
from ui.threads.retrieve_faxes_thread import RetrieveFaxesThread


class FaxHistoryPanel(QWidget):
    """
    Right-hand embedded panel: vertical scrolling list of fax entries with metadata and preview (inbound only).
    """
    def __init__(self, base_dir, app_state, exe_dir=None, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.exe_dir = exe_dir or base_dir
        self.app_state = app_state
        self.log = get_logger("fax_history")
        # Address book
        try:
            self.addr_mgr = AddressBookManager(self.base_dir)
        except Exception:
            self.addr_mgr = None
        self.setMinimumWidth(320)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        root = QVBoxLayout(self)
        # Header row with right-side actions (injected by MainWindow)
        header_row = QHBoxLayout()
        title = QLabel("Fax History")
        title.setStyleSheet("font-weight: bold; font-size: 12pt;")
        header_row.addWidget(title)
        header_row.addStretch()
        self.header_actions = QHBoxLayout()
        self.header_actions.setSpacing(6)
        # Inbound/Outbound toggles
        self.toggle_inbound = QPushButton("Inbound")
        self.toggle_inbound.setCheckable(True)
        self.toggle_inbound.setChecked(True)
        self.toggle_outbound = QPushButton("Outbound")
        self.toggle_outbound.setCheckable(True)
        self.toggle_outbound.setChecked(True)
        self.toggle_inbound.toggled.connect(lambda _: self._apply_filter(self.search.text()))
        self.toggle_outbound.toggled.connect(lambda _: self._apply_filter(self.search.text()))
        self.header_actions.addWidget(self.toggle_inbound)
        self.header_actions.addWidget(self.toggle_outbound)
        # Manual refresh button
        try:
            self.refresh_btn = QPushButton("Refresh")
            self.refresh_btn.setToolTip("Refresh fax history")
            self.refresh_btn.clicked.connect(self.request_refresh)
            self.header_actions.addWidget(self.refresh_btn)
        except Exception:
            pass
        header_row.addLayout(self.header_actions)
        root.addLayout(header_row)

        # Search box
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search number or status...")
        self.search.textChanged.connect(self._apply_filter)
        root.addWidget(self.search)

        # Scroll area with container
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        # Prevent horizontal scrolling by ensuring content adapts to viewport width
        try:
            self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        except Exception:
            pass
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setSpacing(8)
        self.vbox.addStretch()
        self.scroll.setWidget(self.container)
        # Detect near-bottom for lazy loading
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        root.addWidget(self.scroll, 1)

        # Thumbnail/network helper
        self.thumb_helper = ThumbnailHelper(self.base_dir, self.exe_dir, self.app_state, self)

        # State for data and pagination
        self._all_data = []
        self._next_inbound_page = 1
        self._next_outbound_page = 1
        self._loading_more = False

        # Load items initially
        self._data = []
        self.request_refresh()

    def request_refresh(self):
        """Public entry-point to refresh the panel. Consolidates all refresh triggers."""
        # Simple guard to prevent stacking multiple refreshes at once
        if getattr(self, "_refresh_in_progress", False):
            setattr(self, "_refresh_requested_again", True)
            return
        self._perform_refresh()

    def _perform_refresh(self):
        """Refresh list by refetching from API (page 1 for both directions)."""
        self._refresh_in_progress = True
        self._refresh_requested_again = False
        # Abort any in-flight thumbnail fetches to prevent late callbacks
        try:
            self._abort_active_replies()
        except Exception:
            pass
        self._all_data = []
        self._clear_items()
        self._next_inbound_page = 1
        self._next_outbound_page = 1
        self._loading_more = True
        # Guard: if fax_user missing, skip API calls and leave panel empty
        fax_user = getattr(self.app_state.global_cfg, "fax_user", None)
        if not fax_user:
            try:
                self.log.error("fax_user missing from config during refresh; skipping API calls until account is configured.")
            except Exception:
                pass
            # Reset flags and keep panel empty
            self._refresh_in_progress = False
            self._loading_more = False
            return
        self.worker = RetrieveFaxesThread(
            fax_user,
            self.app_state.global_cfg.bearer_token or "",
            inbound_page=self._next_inbound_page,
            outbound_page=self._next_outbound_page,
        )
        # When finished, populate and clear in-progress flag
        def _on_finished(data):
            try:
                self._populate_list(data)
            finally:
                self._refresh_in_progress = False
                # If another refresh was requested while we were working, run again
                if getattr(self, "_refresh_requested_again", False):
                    self.request_refresh()
        self.worker.finished.connect(_on_finished)
        self.worker.start()

    def _clear_items(self):
        # remove all except stretch
        count = self.vbox.count()
        for i in reversed(range(count - 1)):
            item = self.vbox.itemAt(i)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        # Also abort any active replies to avoid late callbacks hitting removed widgets
        try:
            self._abort_active_replies()
        except Exception:
            pass

    def _abort_active_replies(self):
        try:
            if hasattr(self, 'thumb_helper') and self.thumb_helper:
                self.thumb_helper.abort_active()
        except Exception:
            pass

    def _apply_filter(self, text):
        text = (text or "").strip().lower()
        show_in = self.toggle_inbound.isChecked()
        show_out = self.toggle_outbound.isChecked()
        for i in range(self.vbox.count() - 1):
            w = self.vbox.itemAt(i).widget()
            if not w:
                continue
            match_text = (w.property("match_text") or "").lower()
            direction = (w.property("direction") or "").lower()
            dir_ok = (show_in and direction == "inbound") or (show_out and direction == "outbound")
            w.setVisible(dir_ok and (text in match_text))

    def _populate_list(self, data):
        # Merge into the full dataset and record next pages
        data = data or []
        self._all_data.extend(data)
        try:
            self._next_inbound_page = getattr(self.worker, "next_inbound_page", None)
            self._next_outbound_page = getattr(self.worker, "next_outbound_page", None)
        except Exception:
            pass
        self._loading_more = False

        # Rebuild visible list according to toggles, search, and newest-first by created_at
        self._clear_items()
        # Interweave inbound/outbound sorted by created_at (already sorted in thread, but re-sort to be safe)
        try:
            sorted_all = sorted(self._all_data, key=lambda x: x.get("created_at", ""), reverse=True)
        except Exception:
            sorted_all = list(self._all_data)

        for entry in sorted_all:
            # Toggle filtering will be applied in _apply_filter
            card = self._create_card(entry)
            self.vbox.insertWidget(self.vbox.count() - 1, card)
        # re-apply filter to new items (also respects toggles)
        self._apply_filter(self.search.text())

    def _create_card(self, entry: dict) -> QWidget:
        return create_fax_card(self, entry, self.thumb_helper)

    # Public API: allow MainWindow to add small widgets into the header actions row
    def add_header_widget(self, widget):
        try:
            self.header_actions.addWidget(widget)
        except Exception:
            pass

    def _on_view_clicked(self, entry, local_pdf_path):
        # Open the full PDF viewer, fetching remote PDF if needed
        self._open_pdf_viewer(entry, local_pdf_path)

    def _open_pdf_viewer(self, entry: dict, local_pdf_path: str | None):
        open_pdf_viewer(self, entry, local_pdf_path, self.app_state, self.base_dir, self.exe_dir)

    def _on_scroll(self, _=None):
        try:
            sb = self.scroll.verticalScrollBar()
            if not sb:
                return
            near_bottom = sb.value() >= sb.maximum() - 50
            if near_bottom and not self._loading_more:
                # Decide next pages to request
                in_p = self._next_inbound_page or None
                out_p = self._next_outbound_page or None
                if not in_p and not out_p:
                    return
                self._loading_more = True
                self.worker = RetrieveFaxesThread(
                    (getattr(self.app_state.global_cfg, "fax_user", None) or self.app_state.global_cfg.fax_user or ""),
                    self.app_state.global_cfg.bearer_token or "",
                    inbound_page=in_p or 0,
                    outbound_page=out_p or 0,
                )
                self.worker.finished.connect(self._populate_list)
                self.worker.start()
        except Exception:
            pass

    def _download_pdf(self, entry: dict):
        try:
            url = entry.get("pdf")
            if not url:
                QMessageBox.information(self, "Download", "No PDF URL available.")
                return
            from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
            if not hasattr(self, '_net_mgr_dw'):
                self._net_mgr_dw = QNetworkAccessManager(self)
            req = QNetworkRequest(QUrl(url))
            token = self.app_state.global_cfg.bearer_token or ""
            if token:
                req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
            reply = self._net_mgr_dw.get(req)
            def _save():
                try:
                    if reply.error() == 0:
                        data = reply.readAll().data()
                        # Ask user where to save the file
                        fax_id = str(entry.get('id') or 'fax')
                        default_name = f"{fax_id}.pdf"
                        path, _ = QFileDialog.getSaveFileName(self, "Save Fax PDF", default_name, "PDF Files (*.pdf);;All Files (*.*)")
                        if not path:
                            # User canceled
                            return
                        # Ensure .pdf extension
                        if not path.lower().endswith('.pdf'):
                            path = f"{path}.pdf"
                        # Write file
                        try:
                            os.makedirs(os.path.dirname(path), exist_ok=True)
                        except Exception:
                            pass
                        with open(path, 'wb') as f:
                            f.write(data)
                        # Mark as downloaded in local index
                        try:
                            from utils.history_index import mark_downloaded
                            mark_downloaded(self.base_dir, fax_id)
                        except Exception:
                            pass
                        QMessageBox.information(self, "Download", f"Saved to:\n{path}")
                        try:
                            self.request_refresh()
                        except Exception:
                            pass
                    else:
                        QMessageBox.warning(self, "Download", f"Failed with error: {reply.error()} ")
                finally:
                    reply.deleteLater()
            reply.finished.connect(_save)
        except Exception as e:
            QMessageBox.warning(self, "Download", f"Failed: {e}")

    def _resolve_local_pdf(self, entry: dict):
        try:
            # Preferred inbox path from device settings
            inbox = self.app_state.device_cfg.save_path or os.path.join(self.base_dir, "Inbox")
            if not os.path.isdir(inbox):
                return None
            # Try matching by id or known fields embedded in filename
            keys = [
                str(entry.get("id", "")),
                str(entry.get("fax_id", "")),
                str(entry.get("uuid", "")),
            ]
            keys = [k for k in keys if k]
            files = [f for f in os.listdir(inbox) if f.lower().endswith('.pdf')]
            # 1) Exact matches
            for k in keys:
                for f in files:
                    if k and k in f:
                        return os.path.join(inbox, f)
            # 2) Heuristic by timestamp or number if id not present
            rn = str(entry.get("remote_number", ""))
            ts = str(entry.get("timestamp", "")).replace(":", "-")
            for f in files:
                if (rn and rn in f) or (ts and ts in f):
                    return os.path.join(inbox, f)
            return None
        except Exception:
            return None

    def _on_view_fax(self, entry):
        QMessageBox.information(self, "Stub", f"Would display fax ID {entry.get('id')}")

    def _on_view_confirmation(self, entry):
        try:
            # Open the confirmation in the PDF viewer (fetches remote if needed)
            open_pdf_viewer_confirmation(self, entry, None, self.app_state, self.base_dir, self.exe_dir)
        except Exception as e:
            try:
                QMessageBox.warning(self, "Viewer", f"Failed to open confirmation: {e}")
            except Exception:
                pass

    def _download_confirmation(self, entry: dict):
        try:
            url = entry.get("confirmation")
            if not url:
                QMessageBox.information(self, "Download", "No confirmation URL available.")
                return
            from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
            if not hasattr(self, '_net_mgr_conf'):
                self._net_mgr_conf = QNetworkAccessManager(self)
            req = QNetworkRequest(QUrl(url))
            token = self.app_state.global_cfg.bearer_token or ""
            if token:
                req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
            reply = self._net_mgr_conf.get(req)
            def _save():
                try:
                    if reply.error() == 0:
                        data = reply.readAll().data()
                        fax_id = str(entry.get('id') or 'fax')
                        default_name = f"{fax_id}-confirmation.pdf"
                        path, _ = QFileDialog.getSaveFileName(self, "Save Confirmation PDF", default_name, "PDF Files (*.pdf);;All Files (*.*)")
                        if not path:
                            return
                        if not path.lower().endswith('.pdf'):
                            path = f"{path}.pdf"
                        try:
                            os.makedirs(os.path.dirname(path), exist_ok=True)
                        except Exception:
                            pass
                        with open(path, 'wb') as f:
                            f.write(data)
                        QMessageBox.information(self, "Download", f"Confirmation saved to:\n{path}")
                    else:
                        QMessageBox.warning(self, "Download", f"Failed with error: {reply.error()} ")
                finally:
                    reply.deleteLater()
            reply.finished.connect(_save)
        except Exception as e:
            QMessageBox.warning(self, "Download", f"Failed: {e}")

    def _on_download_confirmation(self, entry):
        # Backward-compatible alias
        self._download_confirmation(entry)

    def _on_contact_link(self, href):
        try:
            if not href:
                return
            key = href
            if isinstance(href, str) and href.startswith("contact:"):
                key = href.split("contact:", 1)[1]
            digits = AddressBookManager._sanitize_phone(key)
            if not digits or not getattr(self, 'addr_mgr', None):
                return
            # Refresh contacts to ensure we have latest
            try:
                self.addr_mgr.refresh_contacts()
            except Exception:
                pass
            idx, contact = self.addr_mgr.find_contact_by_phone(digits)
            if not contact:
                try:
                    QMessageBox.information(self, "Address Book", "Contact not found.")
                except Exception:
                    pass
                return
            try:
                dlg = AddContactDialog(self.base_dir, self.addr_mgr, self, contact, idx)
                dlg.exec_()
            except Exception as e:
                try:
                    QMessageBox.warning(self, "Address Book", f"Unable to open contact: {e}")
                except Exception:
                    pass
        except Exception:
            pass
