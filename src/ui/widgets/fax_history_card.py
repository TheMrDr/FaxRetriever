import os
from typing import Optional
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame

from core.address_book import AddressBookManager
from .pdf_viewer_dialog import open_pdf_viewer


def create_fax_card(panel, entry: dict, thumb_helper) -> QWidget:
    """
    Build a single fax entry UI card.
    Delegates thumbnailing to thumb_helper and viewing/downloading to panel methods and open_pdf_viewer.
    """
    # Container for filter handling + divider
    row = QWidget()
    row_lay = QVBoxLayout(row)
    row_lay.setContentsMargins(0, 0, 0, 0)
    row_lay.setSpacing(6)

    # Card frame with directional background
    card = QFrame()
    card.setFrameShape(QFrame.NoFrame)
    direction = (entry.get("direction", "") or "").lower()
    bg = "#f5fbff" if direction == "inbound" else "#fff8f5"
    card.setStyleSheet(
        f"QFrame {{ background: {bg}; border: 1px solid #e5e5e5; border-radius: 8px; }}"
        "QFrame:hover { border-color: #c9d4e8; }"
    )
    lay = QVBoxLayout(card)
    lay.setContentsMargins(10, 10, 10, 10)
    lay.setSpacing(8)

    # Top row: direction (pill), status, unread badge
    top = QHBoxLayout()
    lbl_dir = QLabel(entry.get("direction", ""))
    lbl_dir.setStyleSheet(
        "padding: 2px 8px; border-radius: 10px; font-weight: bold; background: rgba(0,0,0,0.06);"
    )
    top.addWidget(lbl_dir)
    top.addStretch()
    if entry.get("unread", False):
        lbl_new = QLabel("NEW")
        lbl_new.setStyleSheet("color: #1a73e8; font-weight: bold;")
        top.addWidget(lbl_new)
    # Status label with colored indicator
    status_text = str(entry.get("status", ""))
    status_lc = status_text.lower()
    # Map common statuses to colors
    if any(k in status_lc for k in ["fail", "error", "undeliv"]):
        status_color = "#b71c1c"  # red
    elif any(k in status_lc for k in ["pend", "queue", "sending", "process"]):
        status_color = "#b58900"  # yellow
    elif any(k in status_lc for k in ["deliv", "success", "sent", "ok"]):
        status_color = "#2e7d32"  # green
    else:
        status_color = "#555"      # default/unknown
    lbl_status = QLabel(status_text)
    lbl_status.setStyleSheet(f"color: {status_color}; font-weight: bold;")
    top.addWidget(lbl_status)
    lay.addLayout(top)

    # Meta lines
    from_num = str(entry.get("caller_id", ""))
    to_num = str(entry.get("destination", ""))
    created_iso = entry.get("created_at", "")

    # Localize
    try:
        from datetime import datetime, timezone
        dt = None
        if created_iso:
            if created_iso.endswith("Z"):
                created_iso = created_iso.replace("Z", "+00:00")
            dt = datetime.fromisoformat(created_iso)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            dt = dt.astimezone()
        ts_local = dt.strftime('%Y-%m-%d %H:%M:%S %Z') if dt else ""
    except Exception:
        ts_local = created_iso

    # Resolve contact names for inbound/outbound
    name_from = ""
    name_to = ""
    link_from = None
    link_to = None
    try:
        addr_mgr = getattr(panel, 'addr_mgr', None)
        if addr_mgr:
            addr_mgr.refresh_contacts()
            if direction == "inbound":
                idx, c = addr_mgr.find_contact_by_phone(from_num)
                if c:
                    name_from = (c.get('name') or c.get('company') or '').strip()
                    link_from = AddressBookManager._sanitize_phone(from_num)
            elif direction == "outbound":
                idx, c = addr_mgr.find_contact_by_phone(to_num)
                if c:
                    name_to = (c.get('name') or c.get('company') or '').strip()
                    link_to = AddressBookManager._sanitize_phone(to_num)
    except Exception:
        pass

    # Build rich text for meta1
    if name_from:
        from_part = f"From: <a href='contact:{link_from}'>{name_from}</a> ({from_num})"
    else:
        from_part = f"From: {from_num}"
    if name_to:
        to_part = f"To: <a href='contact:{link_to}'>{name_to}</a> ({to_num})"
    else:
        to_part = f"To: {to_num}"
    meta1 = QLabel(f"{from_part}    {to_part}")
    try:
        meta1.setTextFormat(Qt.RichText)
        meta1.setTextInteractionFlags(Qt.TextBrowserInteraction)
        meta1.setOpenExternalLinks(False)
        meta1.linkActivated.connect(panel._on_contact_link)
    except Exception:
        pass
    meta2 = QLabel(f"Time: {ts_local}    Pages: {entry.get('pages', '')}")
    meta1.setStyleSheet("color: #333;")
    meta2.setStyleSheet("color: #666;")
    lay.addWidget(meta1)
    lay.addWidget(meta2)

    # Preview area
    pdf_path = None
    if direction == "inbound":
        pdf_path = panel._resolve_local_pdf(entry)

    mid = QHBoxLayout()
    mid.setSpacing(10)

    preview = QLabel()
    preview.setAlignment(Qt.AlignCenter)
    preview.setStyleSheet("background:#fff; color:#555; border: none; border-radius: 4px;")
    preview.setToolTip("Click to open full preview")
    preview.setCursor(Qt.PointingHandCursor)
    try:
        vpw = panel.scroll.viewport().width()
    except Exception:
        vpw = panel.width()
    preview_w = max(180, min(320, vpw - 260))
    preview_h = int(preview_w * 1.3)
    preview.setFixedSize(preview_w, preview_h)

    if pdf_path and os.path.exists(pdf_path):
        thumb = thumb_helper.render_pdf_thumbnail(pdf_path, preview_w)
        if thumb:
            preview.setPixmap(thumb)
            preview.mousePressEvent = lambda _e, ent=entry, p=pdf_path: open_pdf_viewer(panel, ent, p, panel.app_state, panel.base_dir, panel.exe_dir)
        else:
            preview.setText("No preview")
            preview.setStyleSheet("background:#fafafa; color:#888; border: 1px dashed #ddd; border-radius: 4px;")
    else:
        thumb_url = entry.get("thumbnail") or thumb_helper.thumbnail_url_for(entry)
        if thumb_url:
            thumb_helper.fetch_remote_thumbnail(preview, thumb_url)
            preview.mousePressEvent = lambda _e, ent=entry: open_pdf_viewer(panel, ent, None, panel.app_state, panel.base_dir, panel.exe_dir)
        else:
            preview.setText("No preview")
            preview.setStyleSheet("background:#fafafa; color:#888; border: 1px dashed #ddd; border-radius: 4px;")
    mid.addWidget(preview, 0)

    # Actions column
    actions_col = QVBoxLayout()
    actions_col.setSpacing(6)

    from utils.history_index import is_downloaded
    fax_id = str(entry.get("id") or entry.get("fax_id") or entry.get("uuid") or "")
    downloaded_logged = is_downloaded(panel.base_dir, fax_id) if fax_id else False
    has_local = bool(pdf_path and os.path.exists(pdf_path))
    has_thumb = bool(entry.get("thumbnail"))
    available = bool(has_local or has_thumb)

    if not available:
        lbl_dl = QLabel("Unavailable")
        lbl_dl.setStyleSheet("color: #b58900;")
    elif downloaded_logged or has_local:
        lbl_dl = QLabel("Downloaded")
        lbl_dl.setStyleSheet("color: #2e7d32;")
    else:
        lbl_dl = QLabel("Not downloaded")
        lbl_dl.setStyleSheet("color: #b71c1c;")
    actions_col.addWidget(lbl_dl)

    btn_view = QPushButton("View")
    btn_view.setEnabled(available)
    btn_view.setToolTip("Open the fax in the built-in viewer")
    btn_view.clicked.connect(lambda _, ent=entry, p=pdf_path: open_pdf_viewer(panel, ent, p, panel.app_state, panel.base_dir, panel.exe_dir))
    actions_col.addWidget(btn_view)

    btn_dl = QPushButton("Download PDF")
    btn_dl.setEnabled(available)
    btn_dl.setToolTip("Choose a location to save the fax PDF")
    btn_dl.clicked.connect(lambda _, ent=entry: panel._download_pdf(ent))
    actions_col.addWidget(btn_dl)

    if direction == "outbound" and entry.get("confirmation"):
        btn_conf_view = QPushButton("View Confirmation")
        btn_conf_view.setToolTip("Open the confirmation receipt in the viewer")
        btn_conf_view.clicked.connect(lambda _, ent=entry: panel._on_view_confirmation(ent))
        actions_col.addWidget(btn_conf_view)

        btn_conf = QPushButton("Download Confirmation")
        btn_conf.setToolTip("Choose a location to save the confirmation receipt")
        btn_conf.clicked.connect(lambda _, ent=entry: panel._download_confirmation(ent))
        actions_col.addWidget(btn_conf)

    actions_col.addStretch(1)
    mid.addLayout(actions_col, 1)

    lay.addLayout(mid)

    # Add the card to the row and a divider beneath
    row_lay.addWidget(card)
    divider = QFrame()
    divider.setFrameShape(QFrame.HLine)
    divider.setFrameShadow(QFrame.Sunken)
    divider.setStyleSheet("color: #e9ecef; background: #e9ecef;")
    divider.setFixedHeight(1)
    row_lay.addWidget(divider)

    # Filtering props
    num_text = f"{from_num} {to_num} {str(entry.get('remote_number',''))}"
    name_parts = f"{name_from} {name_to}".strip()
    match_text = f"{entry.get('direction','')} {num_text} {entry.get('status','')} {name_parts}".lower()
    row.setProperty("match_text", match_text)
    row.setProperty("direction", direction)
    return row
