import os

from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QLineEdit, \
    QMessageBox, QWidget, QSpacerItem, QSizePolicy, \
    QScrollArea, QTextEdit, QGridLayout, QFileDialog, QTabWidget

from core.config_loader import global_config, device_config


class AddressBookDialog(QDialog):
    def __init__(self, base_dir, address_book_manager, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.setWindowIcon(QIcon(os.path.join(self.base_dir, "images", "logo.ico")))
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Address Book")
        self.resize(700, 600)
        self.address_book_manager = address_book_manager

        # Cache commonly used icons (avoid disk hits per card)
        self._icon_edit = QIcon(os.path.join(self.base_dir, "images", "edit.png"))
        self._icon_select = QIcon(os.path.join(self.base_dir, "images", "CheckMark.png"))
        self._icon_delete = QIcon(os.path.join(self.base_dir, "images", "TrashCan.png"))

        self.layout = QVBoxLayout(self)

        header = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search contacts...")
        # Debounced search
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(200)
        self._search_timer.timeout.connect(self._on_search_change)
        self.search_bar.textChanged.connect(self._on_search_text_changed)
        add_btn = QPushButton("\u2795 Add Contact")
        add_btn.clicked.connect(self.open_add_dialog)
        header.addWidget(self.search_bar)
        header.addStretch()
        header.addWidget(add_btn)
        self.search_bar.setMinimumHeight(28)
        add_btn.setMinimumHeight(28)
        self.layout.addLayout(header)

        # Tabs for Contacts and Companies
        self.tabs = QTabWidget()

        # Contacts tab
        self.contacts_tab = QWidget()
        self.contacts_scroll = QScrollArea()
        self.contacts_scroll.setWidgetResizable(True)
        self.contacts_container = QWidget()
        self.grid_layout_contacts = QGridLayout(self.contacts_container)
        self.grid_layout_contacts.setSpacing(12)
        self.contacts_scroll.setWidget(self.contacts_container)
        contacts_tab_layout = QVBoxLayout(self.contacts_tab)
        contacts_tab_layout.setContentsMargins(0, 0, 0, 0)
        contacts_tab_layout.addWidget(self.contacts_scroll)
        self.tabs.addTab(self.contacts_tab, "Contacts")

        # Companies tab
        self.companies_tab = QWidget()
        self.companies_scroll = QScrollArea()
        self.companies_scroll.setWidgetResizable(True)
        self.companies_container = QWidget()
        # Companies view uses a vertical layout of grouped grids
        self.vbox_companies = QVBoxLayout(self.companies_container)
        self.vbox_companies.setSpacing(16)
        self.vbox_companies.setContentsMargins(4, 4, 4, 4)
        self.companies_scroll.setWidget(self.companies_container)
        companies_tab_layout = QVBoxLayout(self.companies_tab)
        companies_tab_layout.setContentsMargins(0, 0, 0, 0)
        companies_tab_layout.addWidget(self.companies_scroll)
        self.tabs.addTab(self.companies_tab, "Companies")

        self.layout.addWidget(self.tabs)

        footer = QHBoxLayout()
        self.import_button = QPushButton("Import Contact File")
        self.export_button = QPushButton("Export All Contacts")
        self.import_button.clicked.connect(self.import_contacts)
        self.export_button.clicked.connect(self.export_contacts)
        footer.addWidget(self.import_button)
        footer.addStretch()
        footer.addWidget(self.export_button)
        self.layout.addLayout(footer)

        # Populate both tabs
        self.populate_cards()
        self.populate_companies()

    def _on_search_change(self):
        self.populate_cards()
        self.populate_companies()

    def _on_search_text_changed(self, _text):
        # Debounce to avoid repopulation on every keystroke
        try:
            self._search_timer.start(200)
        except Exception:
            # Fallback: update immediately if timer not available
            self._on_search_change()

    def _clear_layout(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
            else:
                child_layout = item.layout()
                if child_layout is not None:
                    self._clear_layout(child_layout)

    def _add_spacer_row(self, grid_layout, row, cols=2, height=8):
        spacer = QSpacerItem(0, height, QSizePolicy.Minimum, QSizePolicy.Fixed)
        grid_layout.addItem(spacer, row, 0, 1, cols)

    def _format_phone_display(self, raw: str) -> str:
        """Format a phone string into (###) ###-#### when 10 digits are present.
        Accepts inputs with punctuation or leading +1; falls back to digits if <10.
        """
        try:
            digits = ''.join(ch for ch in (raw or '') if ch.isdigit())
            if len(digits) == 11 and digits.startswith('1'):
                digits = digits[1:]
            if len(digits) >= 10:
                d = digits[:10]
                return f"({d[:3]}) {d[3:6]}-{d[6:]}"
            return digits
        except Exception:
            return raw or ''

    def populate_cards(self):
        # Contacts tab population with favorites pinned and spacer
        self._clear_layout(self.grid_layout_contacts)
        self.contacts_container.setUpdatesEnabled(False)

        query = self.search_bar.text().strip().lower()
        has_query = bool(query)
        query_digits = ''.join(ch for ch in query if ch.isdigit())

        contacts = self.address_book_manager.contacts or []
        # filter by name/company/email or phone digits
        filtered = [
            (i, c) for i, c in enumerate(contacts)
            if (query in (c.get("name", "") or "").lower())
               or (query in (c.get("company", "") or "").lower())
               or (query in (c.get("email", "") or "").lower())
               or (query_digits and (
                    (query_digits in (''.join(ch for ch in (c.get('phone') or '') if ch.isdigit()))) or
                    (query_digits in (''.join(ch for ch in (c.get('phone1') or '') if ch.isdigit())))
               ))
        ]

        # If searching and nothing matched, display a helpful message.
        if has_query and not filtered:
            msg = QLabel("No matches found.")
            msg.setStyleSheet("color:#666; padding: 12px;")
            self.grid_layout_contacts.addWidget(msg, 0, 0, 1, 2)
            self.contacts_container.setUpdatesEnabled(True)
            return

        # Split favorites and non-favorites (placeholders treated as non-fav)
        favs = [(i, c) for i, c in filtered if c and not c.get('is_placeholder', False) and c.get('favorite', False)]
        others_mix = [(i, c) for i, c in filtered if not (c and not c.get('is_placeholder', False) and c.get('favorite', False))]

        # Ensure at least 4 visible cards overall (placeholders appended later only if no search query)
        min_cards = 4
        total_now = len(favs) + len(others_mix)
        placeholders: list[tuple[int, dict]] = []
        if (not has_query) and total_now < min_cards:
            needed = min_cards - total_now
            tips = [
                {"name": "Add a contact", "notes": "Click + Add Contact to get started."},
                {"name": "Import JSON", "notes": "Use 'Import Contact File' below."},
                {"name": "Add Company", "notes": "Include Company to enable smart grouping."},
                {"name": "Add Fax Number", "notes": "Provide Fax for one‑click sending."},
            ]
            for n in range(needed):
                t = tips[n % len(tips)]
                placeholder = {
                    "name": t.get("name", "New Contact"),
                    "phone": "",
                    "phone1": "",
                    "company": "",
                    "email": "",
                    "notes": t.get("notes", ""),
                    "custom_cover_sheet": False,
                    "custom_cover_sheet_attn": "",
                    "custom_cover_sheet_note": "",
                    "is_placeholder": True,
                }
                placeholders.append((-1, placeholder))

        # Split others into real vs placeholders (any persisted placeholders should already be removed by manager)
        real_non_favs = [(i, c) for i, c in others_mix if not (c or {}).get('is_placeholder', False)]

        # Sort within each bucket by name (or company fallback)
        def sort_key(pair):
            c = pair[1]
            return ((c.get('name') or c.get('company') or "").lower())
        favs.sort(key=sort_key)
        real_non_favs.sort(key=sort_key)
        placeholders.sort(key=sort_key)

        # Render: favorites first, spacer, other real contacts, spacer (if placeholders), then placeholders at bottom
        row = 0
        col_count = 2
        # favorites
        for idx, (true_index, contact) in enumerate(favs):
            r, col = divmod(row, col_count)
            card = self.create_contact_card(contact, true_index)
            self.grid_layout_contacts.addWidget(card, r, col)
            row += 1
        # spacer between favorites and others if both exist
        if favs and real_non_favs:
            r, _ = divmod(row, col_count)
            self._add_spacer_row(self.grid_layout_contacts, r, cols=col_count, height=10)
            row = (r + 1) * col_count
        # other real contacts
        for idx, (true_index, contact) in enumerate(real_non_favs):
            r, col = divmod(row, col_count)
            card = self.create_contact_card(contact, true_index)
            self.grid_layout_contacts.addWidget(card, r, col)
            row += 1
        # spacer between real contacts and placeholders if placeholders exist
        if placeholders:
            r, _ = divmod(row, col_count)
            self._add_spacer_row(self.grid_layout_contacts, r, cols=col_count, height=8)
            row = (r + 1) * col_count
        # placeholders last
        for idx, (true_index, contact) in enumerate(placeholders):
            r, col = divmod(row, col_count)
            card = self.create_contact_card(contact, true_index)
            self.grid_layout_contacts.addWidget(card, r, col)
            row += 1
        # Re-enable updates after population
        try:
            self.contacts_container.setUpdatesEnabled(True)
        except Exception:
            pass

    def populate_companies(self):
        # Companies tab: group by company, with favorites pinned within each group
        self._clear_layout(self.vbox_companies)
        self.companies_container.setUpdatesEnabled(False)
        query = self.search_bar.text().strip().lower()
        has_query = bool(query)
        query_digits = ''.join(ch for ch in query if ch.isdigit())

        contacts = self.address_book_manager.contacts or []
        # apply global filter on name/company/email or phone digits
        filtered = [
            (i, c) for i, c in enumerate(contacts)
            if (query in (c.get("name", "") or "").lower())
               or (query in (c.get("company", "") or "").lower())
               or (query in (c.get("email", "") or "").lower())
               or (query_digits and (
                    (query_digits in (''.join(ch for ch in (c.get('phone') or '') if ch.isdigit()))) or
                    (query_digits in (''.join(ch for ch in (c.get('phone1') or '') if ch.isdigit())))
               ))
        ]
        # If searching and nothing matched, display a helpful message.
        if has_query and not filtered:
            msg = QLabel("No matches found.")
            msg.setStyleSheet("color:#666; padding: 12px;")
            self.vbox_companies.addWidget(msg)
            self.vbox_companies.addStretch()
            try:
                self.companies_container.setUpdatesEnabled(True)
            except Exception:
                pass
            return
        # Group by company
        groups = {}
        for idx, c in filtered:
            comp = (c.get('company') or '').strip() or 'Unspecified'
            groups.setdefault(comp, []).append((idx, c))

        # Sort group names alphabetically (Unspecified last)
        group_names = sorted([g for g in groups.keys() if g != 'Unspecified'])
        if 'Unspecified' in groups:
            group_names.append('Unspecified')

        for gname in group_names:
            items = groups[gname]
            # Split favorites
            favs = [(i, c) for i, c in items if c.get('favorite', False) and not c.get('is_placeholder', False)]
            non_favs = [(i, c) for i, c in items if not (c.get('favorite', False) and not c.get('is_placeholder', False))]

            favs.sort(key=lambda pair: (pair[1].get('name') or '').lower())
            non_favs.sort(key=lambda pair: (pair[1].get('name') or '').lower())

            # Group header
            header = QLabel(f"<b>{gname}</b>")
            header.setStyleSheet("font-size: 12pt; color: #222; padding: 2px 4px;")
            self.vbox_companies.addWidget(header)

            grid = QGridLayout()
            grid.setSpacing(12)

            row = 0
            col_count = 2
            # favorites first
            for true_index, contact in [(i, c) for i, c in favs]:
                r, col = divmod(row, col_count)
                card = self.create_contact_card(contact, true_index)
                grid.addWidget(card, r, col)
                row += 1
            # spacer if both exist
            if favs and non_favs:
                r, _ = divmod(row, col_count)
                self._add_spacer_row(grid, r, cols=col_count, height=8)
                row = (r + 1) * col_count
            # non favorites
            for true_index, contact in [(i, c) for i, c in non_favs]:
                r, col = divmod(row, col_count)
                card = self.create_contact_card(contact, true_index)
                grid.addWidget(card, r, col)
                row += 1

            container = QWidget()
            container.setLayout(grid)
            self.vbox_companies.addWidget(container)
        self.vbox_companies.addStretch()
        try:
            self.companies_container.setUpdatesEnabled(True)
        except Exception:
            pass

    def create_contact_card(self, contact, index):
        # Outer container (card)
        outer = QWidget()
        is_placeholder = contact.get("is_placeholder", False)
        outer.setStyleSheet(
            "QWidget { border: 1px solid #d9d9d9; border-radius: 8px; }"
        )
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        # Header with avatar/initials and name/company
        header = QWidget()
        header.setStyleSheet("QWidget { background: #fafafa; border-top-left-radius: 8px; border-top-right-radius: 8px; }")
        h = QHBoxLayout(header)
        h.setContentsMargins(10, 10, 10, 10)
        h.setSpacing(10)

        # Avatar/initials
        avatar = QLabel()
        initials = ''.join([w[0].upper() for w in (contact.get('company') or contact.get('name') or ' ').split()[:2]]).strip() or "?"
        avatar.setText(initials)
        avatar.setAlignment(Qt.AlignCenter)
        avatar.setFixedSize(36, 36)
        avatar.setStyleSheet("QLabel { background: #1976d2; color: white; font-weight: bold; border-radius: 18px; }")
        h.addWidget(avatar)

        title_box = QVBoxLayout()
        name_txt = contact.get('name') or contact.get('company') or ("New Contact" if is_placeholder else "")
        name_lbl = QLabel(f"<b>{name_txt}</b>")
        name_lbl.setContentsMargins(0, 0, 0, 0)
        company = contact.get('company', '')
        comp_lbl = QLabel(company)
        comp_lbl.setStyleSheet("color:#666;")
        title_box.addWidget(name_lbl)
        if company:
            title_box.addWidget(comp_lbl)
        else:
            note = (contact.get('notes') or "") if is_placeholder else ""
            if note:
                hint = QLabel(note)
                hint.setStyleSheet("color:#777; font-style: italic;")
                title_box.addWidget(hint)
        # Compact spacing: no stretch between header and body
        h.addLayout(title_box, 1)
        outer_layout.addWidget(header)

        # Body (compact margins/spacing)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(10, 4, 10, 6)
        body_layout.setSpacing(2)

        def line(lbl, val):
            # Only render when a value is present to avoid empty rows
            if not val:
                return
            text = f"<span style='color:#888'>{lbl}</span> {val}"
            body_layout.addWidget(QLabel(text))

        fax_disp = self._format_phone_display(contact.get('phone', '')) if contact.get('phone') else ''
        phone_disp = self._format_phone_display(contact.get('phone1', '')) if contact.get('phone1') else ''
        line("Fax:", fax_disp)
        line("Phone:", phone_disp)
        line("Email:", contact.get('email', ''))

        # Smart hints (non-blocking)
        smart_notes = []
        if not is_placeholder:
            if not (contact.get('phone') or '').strip():
                smart_notes.append("Missing Fax number for one‑click send")
            if contact.get('email') and '@' not in contact.get('email'):
                smart_notes.append("Email looks invalid")
        if smart_notes:
            warn = QLabel(" \u26A0\uFE0F  " + " • ".join(smart_notes))
            warn.setStyleSheet("color:#b26a00;")
            body_layout.addWidget(warn)

        # Footer buttons
        footer = QWidget()
        f = QHBoxLayout(footer)
        f.setContentsMargins(10, 6, 10, 10)
        f.setSpacing(6)
        
        # Favorite toggle button (star)
        fav_btn = QPushButton("☆")
        fav_btn.setFixedSize(32, 32)
        fav_btn.setToolTip("Mark as Favorite")
        is_fav = bool(contact.get('favorite', False))
        if is_fav:
            fav_btn.setText("★")
            fav_btn.setToolTip("Unmark Favorite")
        fav_btn.setEnabled(not is_placeholder and index >= 0)
        fav_btn.clicked.connect(lambda: self._toggle_favorite(index, not is_fav))
        f.addWidget(fav_btn)
        f.addStretch()

        edit_btn = QPushButton()
        edit_btn.setIcon(self._icon_edit)
        edit_btn.setToolTip("Edit this contact")
        edit_btn.setEnabled(not is_placeholder and index >= 0)
        edit_btn.clicked.connect(lambda: self.open_edit_dialog(contact, index))

        select_btn = QPushButton()
        select_btn.setIcon(self._icon_select)
        select_btn.setToolTip("Send a fax to this contact")
        select_btn.setEnabled(not is_placeholder and index >= 0)
        select_btn.clicked.connect(lambda: self.select_contact(index))

        delete_btn = QPushButton()
        delete_btn.setIcon(self._icon_delete)
        delete_btn.setToolTip("Delete this contact")
        delete_btn.setVisible(not is_placeholder and index >= 0)
        delete_btn.clicked.connect(lambda: self.confirm_delete(index))

        # Uniform icon button styling
        for _btn in (edit_btn, select_btn, delete_btn):
            try:
                _btn.setIconSize(QSize(18, 18))
                _btn.setMinimumSize(36, 28)
                _btn.setStyleSheet(
                    "QPushButton { padding: 6px; border: 1px solid #d9d9d9; border-radius: 6px; background-color: #ffffff; }"
                    "QPushButton:hover { background-color: #f3f3f3; }"
                )
            except Exception:
                pass

        f.addWidget(edit_btn)
        f.addWidget(select_btn)
        f.addWidget(delete_btn)

        outer_layout.addWidget(body)
        outer_layout.addWidget(footer)
        return outer

    def _toggle_favorite(self, index: int, new_value: bool):
        try:
            if index is None or index < 0:
                return
            if 0 <= index < len(self.address_book_manager.contacts):
                self.address_book_manager.contacts[index]['favorite'] = bool(new_value)
                self.address_book_manager.save_contacts()
        except Exception:
            pass
        # Refresh both tabs to reflect new ordering and star state
        self.populate_cards()
        self.populate_companies()

    def open_add_dialog(self):
        dlg = AddContactDialog(self.base_dir, self.address_book_manager, self)
        if dlg.exec_() == QDialog.Accepted:
            self.populate_cards()
            self.populate_companies()

    def open_edit_dialog(self, contact, index):
        dlg = AddContactDialog(self.base_dir, self.address_book_manager, self, contact, index)
        if dlg.exec_() == QDialog.Accepted:
            self.populate_cards()
            self.populate_companies()

    def select_contact(self, index):
        contact = self.address_book_manager.contacts[index]
        parent = self.parent()
        if hasattr(parent, 'populate_from_contact'):
            parent.populate_from_contact(contact)
        else:
            # Backward compatible behavior
            selected_fax = contact.get('phone', '')
            if hasattr(parent, 'populate_phone_fields'):
                parent.populate_phone_fields(selected_fax)
            if hasattr(parent, 'populate_cover_from_contact'):
                parent.populate_cover_from_contact(contact)
        self.accept()

    def confirm_delete(self, row):
        contact = self.address_book_manager.contacts[row]
        name = contact.get("name", "")
        reply = QMessageBox.question(self, "Confirm Delete", f"Are you sure you want to delete '{name}'?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.address_book_manager.delete_contact(row)
            self.populate_cards()
            self.populate_companies()

    def import_contacts(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import Contacts", "", "JSON Files (*.json)")
        if path:
            self.address_book_manager.import_contacts(path)
            self.populate_cards()
            self.populate_companies()

    def export_contacts(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export Contacts", "", "JSON Files (*.json)")
        if path:
            self.address_book_manager.export_contacts(path)


class AddContactDialog(QDialog):
    def __init__(self, base_dir, manager, parent=None, contact=None, edit_index=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setWindowTitle("Add Contact" if contact is None else "Edit Contact")
        self.setWindowIcon(QIcon(os.path.join(base_dir, "images", "logo.ico")))
        self.setMinimumWidth(450)
        self.manager = manager
        self.edit_index = edit_index

        self.fields = {}

        main_layout = QVBoxLayout(self)
        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)

        def add_field(row, col, label, key, is_text=False, span=1):
            lbl = QLabel(label)
            widget = QTextEdit() if is_text else QLineEdit()
            if not is_text:
                widget.setFixedHeight(28)
            grid.addWidget(lbl, row, col)
            grid.addWidget(widget, row, col + 1, 1, span)
            self.fields[key] = widget
            # Apply E.164-like input mask for phone fields and prefill +1
            if not is_text and key in ("phone", "phone1"):
                try:
                    widget.setInputMask("+99999999999;_")  # up to 11 digits
                    if not widget.text().strip():
                        widget.setText("+1")
                except Exception:
                    pass

        # Left column
        add_field(0, 0, "Contact Name:", "name")
        add_field(1, 0, "Fax Number:", "phone")
        add_field(2, 0, "Phone Number:", "phone1")
        add_field(3, 0, "Company:", "company")

        # Right column
        add_field(0, 2, "Email:", "email")
        add_field(1, 2, "Notes:", "notes", is_text=True, span=1)

        # Cover Sheet Section
        self.cover_checkbox = QCheckBox("Use Custom Cover Sheet")
        self.cover_checkbox.stateChanged.connect(self.toggle_cover_fields)
        main_layout.addLayout(grid)
        main_layout.addWidget(self.cover_checkbox)

        cover_grid = QGridLayout()
        attn_label = QLabel("ATTENTION:")
        attn_input = QLineEdit()
        note_label = QLabel("NOTE:")
        note_input = QTextEdit()

        attn_input.setFixedHeight(28)

        cover_grid.addWidget(attn_label, 0, 0)
        cover_grid.addWidget(attn_input, 0, 1)
        cover_grid.addWidget(note_label, 0, 2)
        cover_grid.addWidget(note_input, 0, 3)

        self.fields["custom_cover_sheet_attn"] = attn_input
        self.fields["custom_cover_sheet_note"] = note_input

        main_layout.addLayout(cover_grid)

        # Disable cover fields by default
        self.fields["custom_cover_sheet_attn"].setEnabled(False)
        self.fields["custom_cover_sheet_note"].setEnabled(False)

        # Populate if editing
        if contact:
            for key, widget in self.fields.items():
                value = contact.get(key, "")
                if isinstance(widget, QTextEdit):
                    widget.setPlainText(value)
                else:
                    widget.setText(value)
            self.cover_checkbox.setChecked(contact.get("custom_cover_sheet", False))
            self.toggle_cover_fields()

        # Save button aligned right
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton("Save Contact" if contact is None else "Update Contact")
        self.save_btn.clicked.connect(self.save)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(cancel_btn)
        main_layout.addLayout(btn_layout)

        # Track initial state and enable/disable save appropriately
        self._initial_values = {}
        for key, widget in self.fields.items():
            if isinstance(widget, QTextEdit):
                self._initial_values[key] = widget.toPlainText().strip()
            else:
                self._initial_values[key] = widget.text().strip()
        self._initial_cover = self.cover_checkbox.isChecked()

        # Connect change signals
        for key, widget in self.fields.items():
            if isinstance(widget, QTextEdit):
                widget.textChanged.connect(self._on_any_change)
            else:
                widget.textChanged.connect(self._on_any_change)
        self.cover_checkbox.stateChanged.connect(self._on_any_change)

        # For edit mode, disable until something changes; for add mode, require minimal fields
        if contact:
            self.save_btn.setEnabled(False)
        else:
            self._update_save_enabled_for_new()

    def toggle_cover_fields(self):
        enabled = self.cover_checkbox.isChecked()
        self.fields["custom_cover_sheet_attn"].setEnabled(enabled)
        self.fields["custom_cover_sheet_note"].setEnabled(enabled)

    def _on_any_change(self):
        # Decide enabling of save based on mode (new vs edit)
        if self.edit_index is not None:
            # Enable only if something changed
            changed = self.cover_checkbox.isChecked() != self._initial_cover
            if not changed:
                for key, widget in self.fields.items():
                    current = widget.toPlainText().strip() if isinstance(widget, QTextEdit) else widget.text().strip()
                    if current != self._initial_values.get(key, ""):
                        changed = True
                        break
            self.save_btn.setEnabled(changed)
        else:
            # New contact: minimal validation
            self._update_save_enabled_for_new()

    def _update_save_enabled_for_new(self):
        name_ok = bool(self.fields.get("name").text().strip())
        phone = (self.fields.get("phone").text() or "").strip()
        digits = ''.join([c for c in phone if c.isdigit()])
        phone_ok = len(digits) >= 7  # allow non-10 digit but require something reasonable
        self.save_btn.setEnabled(name_ok and phone_ok)

    def save(self):
        # Gather form values
        values = {}
        for key, widget in self.fields.items():
            values[key] = widget.toPlainText().strip() if isinstance(widget, QTextEdit) else widget.text().strip()
        values["custom_cover_sheet"] = self.cover_checkbox.isChecked()

        if self.edit_index is not None and 0 <= self.edit_index < len(self.manager.contacts):
            # Delegate to manager to normalize and persist
            self.manager.update_contact(self.edit_index, values)
        else:
            # Delegate to manager add_contact to normalize and persist
            self.manager.add_contact(
                name=values.get("name", ""),
                phone=values.get("phone", ""),
                phone1=values.get("phone1", ""),
                company=values.get("company", ""),
                email=values.get("email", ""),
                notes=values.get("notes", ""),
                custom_cover_sheet=values.get("custom_cover_sheet", False),
                custom_cover_sheet_attn=values.get("custom_cover_sheet_attn", ""),
                custom_cover_sheet_note=values.get("custom_cover_sheet_note", ""),
            )

        self.accept()
