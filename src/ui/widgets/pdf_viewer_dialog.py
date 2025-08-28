import os
from typing import Optional
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QMessageBox, QGraphicsView, QGraphicsScene
from PyQt5.QtPrintSupport import QPrinter, QPrintDialog


def open_pdf_viewer(parent, entry: dict, local_pdf_path: Optional[str], app_state, base_dir: str, exe_dir: Optional[str]):
    """
    Open a full PDF viewer with page navigation, zoom controls, and download.
    If local_pdf_path is None or missing, fetch the remote PDF first using bearer token.
    """
    try:
        from tempfile import mkstemp
        from pdf2image import convert_from_path

        # Prepare dialog UI
        dlg = QDialog(parent)
        dlg.setWindowTitle("Fax Document")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        layout = QVBoxLayout(dlg)

        # Graphics view
        view = QGraphicsView()
        scene = QGraphicsScene()
        view.setScene(scene)
        view.setStyleSheet("border: 1px solid #ccc; background: white;")
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setDragMode(QGraphicsView.NoDrag)
        layout.addWidget(view)

        # Controls row similar to Send Fax: prev/next, zoom in/out, download
        controls = QHBoxLayout()
        btn_prev = QPushButton()
        btn_prev.setText("Prev")
        btn_next = QPushButton()
        btn_next.setText("Next")
        btn_zoom_in = QPushButton("Zoom+")
        btn_zoom_out = QPushButton("Zoom-")
        btn_download = QPushButton("Download PDF")
        btn_print = QPushButton("Print")
        controls.addWidget(btn_prev)
        controls.addWidget(btn_next)
        controls.addStretch()
        controls.addWidget(btn_zoom_in)
        controls.addWidget(btn_zoom_out)
        controls.addStretch()
        controls.addWidget(btn_print)
        controls.addWidget(btn_download)
        layout.addLayout(controls)

        # State
        page_images: list[QPixmap] = []
        current_page = {"i": 0}
        zoomed = {"on": False}
        original_pixmap = {"pm": None}

        def update_view():
            scene.clear()
            pm = original_pixmap["pm"]
            if not pm:
                return
            if zoomed["on"]:
                scene.addPixmap(pm)
                from PyQt5.QtCore import QRectF
                view.setSceneRect(QRectF(pm.rect()))
            else:
                viewport_size = view.viewport().size()
                scaled = pm.scaled(viewport_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scene.addPixmap(scaled)
                from PyQt5.QtCore import QRectF
                view.setSceneRect(QRectF(scaled.rect()))

        def set_page(index: int):
            if 0 <= index < len(page_images):
                current_page["i"] = index
                original_pixmap["pm"] = page_images[index]
                update_view()
                btn_prev.setEnabled(index > 0)
                btn_next.setEnabled(index < len(page_images) - 1)

        def render_pdf(path: str):
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
                        from io import BytesIO
                        qimg = QImage.fromData(img_bytes)
                        imgs.append(QPixmap.fromImage(qimg))
                except Exception:
                    # Fallback to pdf2image + Poppler if PyMuPDF is unavailable
                    from pdf2image import convert_from_path
                    # Prefer MEIPASS/base_dir (onefile extraction) for Poppler, then fallback to exe_dir
                    candidates = [
                        os.path.join(base_dir, "poppler", "bin"),
                        os.path.join(exe_dir or base_dir, "poppler", "bin"),
                    ]
                    poppler_bin = next((p for p in candidates if os.path.isdir(p)), None)
                    kwargs = {"dpi": 200}
                    if poppler_bin:
                        kwargs["poppler_path"] = poppler_bin
                    pages = convert_from_path(path, **kwargs)
                    from io import BytesIO
                    for pil_image in pages:
                        buf = BytesIO()
                        pil_image.save(buf, format='PNG')
                        qimg = QImage.fromData(buf.getvalue())
                        imgs.append(QPixmap.fromImage(qimg))
                page_images.clear()
                page_images.extend(imgs)
                set_page(0)
            except Exception as e:
                scene.addText(f"Failed to render PDF: {e}")

        def do_download():
            try:
                # parent should expose _download_pdf(entry)
                if hasattr(parent, '_download_pdf'):
                    parent._download_pdf(entry)
            except Exception:
                pass

        def do_print():
            try:
                if not page_images:
                    QMessageBox.information(dlg, "Print", "Document is not ready to print yet.")
                    return
                printer = QPrinter(QPrinter.HighResolution)
                # Show a print dialog so user can pick printer/settings
                dlg_print = QPrintDialog(printer, dlg)
                dlg_print.setWindowTitle("Print Fax Document")
                if dlg_print.exec_() != QDialog.Accepted:
                    return
                from PyQt5.QtGui import QPainter
                painter = QPainter()
                if not painter.begin(printer):
                    QMessageBox.warning(dlg, "Print", "Failed to start printer.")
                    return
                try:
                    for idx, pm in enumerate(page_images):
                        # Scale pixmap to fit printable area while preserving aspect
                        page_rect = printer.pageRect()
                        if pm.isNull() or page_rect.width() <= 0 or page_rect.height() <= 0:
                            if idx < len(page_images) - 1:
                                printer.newPage()
                            continue
                        scaled = pm.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        x = page_rect.x() + (page_rect.width() - scaled.width()) // 2
                        y = page_rect.y() + (page_rect.height() - scaled.height()) // 2
                        painter.drawPixmap(x, y, scaled)
                        if idx < len(page_images) - 1:
                            printer.newPage()
                finally:
                    painter.end()
                QMessageBox.information(dlg, "Print", "Document sent to printer.")
            except Exception as pe:
                QMessageBox.warning(dlg, "Print", f"Printing failed: {pe}")

        btn_prev.clicked.connect(lambda: set_page(current_page["i"] - 1))
        btn_next.clicked.connect(lambda: set_page(current_page["i"] + 1))
        btn_zoom_in.clicked.connect(lambda: (zoomed.__setitem__('on', True), view.setDragMode(QGraphicsView.ScrollHandDrag), update_view()))
        btn_zoom_out.clicked.connect(lambda: (zoomed.__setitem__('on', False), view.setDragMode(QGraphicsView.NoDrag), update_view()))
        btn_download.clicked.connect(do_download)
        btn_print.clicked.connect(do_print)

        # Acquire PDF path (local or remote)
        def start_with_path(path: str):
            if not path or not os.path.exists(path):
                scene.addText("Unable to load PDF.")
            else:
                render_pdf(path)

        if local_pdf_path and os.path.exists(local_pdf_path):
            start_with_path(local_pdf_path)
        else:
            # Fetch remote PDF and then render
            url = entry.get("pdf")
            if not url:
                scene.addText("No PDF URL available.")
            else:
                try:
                    from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
                    mgr = QNetworkAccessManager(dlg)
                    req = QNetworkRequest(QUrl(url))
                    token = app_state.global_cfg.bearer_token or ""
                    if token:
                        req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
                    reply = mgr.get(req)

                    def _save_and_render():
                        try:
                            if reply.error() == 0:
                                data = reply.readAll().data()
                                fd, tmp_path = mkstemp(suffix='.pdf')
                                os.close(fd)
                                with open(tmp_path, 'wb') as f:
                                    f.write(data)
                                start_with_path(tmp_path)
                            else:
                                scene.addText("Failed to fetch PDF.")
                        finally:
                            reply.deleteLater()

                    reply.finished.connect(_save_and_render)
                except Exception as e:
                    scene.addText(f"Failed to start download: {e}")

        dlg.resize(800, 600)
        dlg.exec_()
    except Exception as e:
        QMessageBox.warning(parent, "Viewer", f"Failed to open PDF viewer: {e}")



def open_pdf_viewer_confirmation(parent, entry: dict, local_pdf_path: Optional[str], app_state, base_dir: str, exe_dir: Optional[str]):
    """
    Open a PDF viewer for fax confirmation receipts. Behaves like open_pdf_viewer but
    fetches entry['confirmation'] and uses _download_confirmation for the download action.
    """
    try:
        from tempfile import mkstemp
        from pdf2image import convert_from_path  # noqa: F401 (import parity with open_pdf_viewer)

        dlg = QDialog(parent)
        dlg.setWindowTitle("Fax Confirmation")
        dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        layout = QVBoxLayout(dlg)

        view = QGraphicsView()
        scene = QGraphicsScene()
        view.setScene(scene)
        view.setStyleSheet("border: 1px solid #ccc; background: white;")
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        view.setDragMode(QGraphicsView.NoDrag)
        layout.addWidget(view)

        controls = QHBoxLayout()
        btn_prev = QPushButton(); btn_prev.setText("Prev")
        btn_next = QPushButton(); btn_next.setText("Next")
        btn_zoom_in = QPushButton("Zoom+")
        btn_zoom_out = QPushButton("Zoom-")
        btn_download = QPushButton("Download PDF")
        btn_print = QPushButton("Print")
        controls.addWidget(btn_prev)
        controls.addWidget(btn_next)
        controls.addStretch()
        controls.addWidget(btn_zoom_in)
        controls.addWidget(btn_zoom_out)
        controls.addStretch()
        controls.addWidget(btn_print)
        controls.addWidget(btn_download)
        layout.addLayout(controls)

        page_images: list[QPixmap] = []
        current_page = {"i": 0}
        zoomed = {"on": False}
        original_pixmap = {"pm": None}

        def update_view():
            scene.clear()
            pm = original_pixmap["pm"]
            if not pm:
                return
            if zoomed["on"]:
                scene.addPixmap(pm)
                from PyQt5.QtCore import QRectF
                view.setSceneRect(QRectF(pm.rect()))
            else:
                viewport_size = view.viewport().size()
                scaled = pm.scaled(viewport_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                scene.addPixmap(scaled)
                from PyQt5.QtCore import QRectF
                view.setSceneRect(QRectF(scaled.rect()))

        def set_page(index: int):
            if 0 <= index < len(page_images):
                current_page["i"] = index
                original_pixmap["pm"] = page_images[index]
                update_view()
                btn_prev.setEnabled(index > 0)
                btn_next.setEnabled(index < len(page_images) - 1)

        def render_pdf(path: str):
            try:
                imgs = []
                try:
                    import fitz  # PyMuPDF
                    doc = fitz.open(path)
                    if doc.page_count <= 0:
                        raise RuntimeError("Empty PDF")
                    for i in range(doc.page_count):
                        page = doc.load_page(i)
                        pix = page.get_pixmap(dpi=200, alpha=False)
                        img_bytes = pix.tobytes("png")
                        from io import BytesIO
                        qimg = QImage.fromData(img_bytes)
                        imgs.append(QPixmap.fromImage(qimg))
                except Exception:
                    from pdf2image import convert_from_path
                    candidates = [
                        os.path.join(base_dir, "poppler", "bin"),
                        os.path.join(exe_dir or base_dir, "poppler", "bin"),
                    ]
                    poppler_bin = next((p for p in candidates if os.path.isdir(p)), None)
                    kwargs = {"dpi": 200}
                    if poppler_bin:
                        kwargs["poppler_path"] = poppler_bin
                    pages = convert_from_path(path, **kwargs)
                    from io import BytesIO
                    for pil_image in pages:
                        buf = BytesIO()
                        pil_image.save(buf, format='PNG')
                        qimg = QImage.fromData(buf.getvalue())
                        imgs.append(QPixmap.fromImage(qimg))
                page_images.clear()
                page_images.extend(imgs)
                set_page(0)
            except Exception as e:
                scene.addText(f"Failed to render PDF: {e}")

        def do_download():
            try:
                if hasattr(parent, '_download_confirmation'):
                    parent._download_confirmation(entry)
            except Exception:
                pass

        def do_print():
            try:
                if not page_images:
                    QMessageBox.information(dlg, "Print", "Document is not ready to print yet.")
                    return
                printer = QPrinter(QPrinter.HighResolution)
                dlg_print = QPrintDialog(printer, dlg)
                dlg_print.setWindowTitle("Print Fax Confirmation")
                if dlg_print.exec_() != QDialog.Accepted:
                    return
                from PyQt5.QtGui import QPainter
                painter = QPainter()
                if not painter.begin(printer):
                    QMessageBox.warning(dlg, "Print", "Failed to start printer.")
                    return
                try:
                    for idx, pm in enumerate(page_images):
                        page_rect = printer.pageRect()
                        if pm.isNull() or page_rect.width() <= 0 or page_rect.height() <= 0:
                            if idx < len(page_images) - 1:
                                printer.newPage()
                            continue
                        scaled = pm.scaled(page_rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        x = page_rect.x() + (page_rect.width() - scaled.width()) // 2
                        y = page_rect.y() + (page_rect.height() - scaled.height()) // 2
                        painter.drawPixmap(x, y, scaled)
                        if idx < len(page_images) - 1:
                            printer.newPage()
                finally:
                    painter.end()
                QMessageBox.information(dlg, "Print", "Document sent to printer.")
            except Exception as pe:
                QMessageBox.warning(dlg, "Print", f"Printing failed: {pe}")

        btn_prev.clicked.connect(lambda: set_page(current_page["i"] - 1))
        btn_next.clicked.connect(lambda: set_page(current_page["i"] + 1))
        btn_zoom_in.clicked.connect(lambda: (zoomed.__setitem__('on', True), view.setDragMode(QGraphicsView.ScrollHandDrag), update_view()))
        btn_zoom_out.clicked.connect(lambda: (zoomed.__setitem__('on', False), view.setDragMode(QGraphicsView.NoDrag), update_view()))
        btn_download.clicked.connect(do_download)
        btn_print.clicked.connect(do_print)

        def start_with_path(path: str):
            if not path or not os.path.exists(path):
                scene.addText("Unable to load PDF.")
            else:
                render_pdf(path)

        if local_pdf_path and os.path.exists(local_pdf_path):
            start_with_path(local_pdf_path)
        else:
            url = entry.get("confirmation")
            if not url:
                scene.addText("No confirmation URL available.")
            else:
                try:
                    from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
                    mgr = QNetworkAccessManager(dlg)
                    req = QNetworkRequest(QUrl(url))
                    token = app_state.global_cfg.bearer_token or ""
                    if token:
                        req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
                    reply = mgr.get(req)

                    def _save_and_render():
                        try:
                            if reply.error() == 0:
                                data = reply.readAll().data()
                                fd, tmp_path = mkstemp(suffix='.pdf')
                                os.close(fd)
                                with open(tmp_path, 'wb') as f:
                                    f.write(data)
                                start_with_path(tmp_path)
                            else:
                                scene.addText("Failed to fetch PDF.")
                        finally:
                            reply.deleteLater()

                    reply.finished.connect(_save_and_render)
                except Exception as e:
                    scene.addText(f"Failed to start download: {e}")

        dlg.resize(800, 600)
        dlg.exec_()
    except Exception as e:
        QMessageBox.warning(parent, "Viewer", f"Failed to open PDF viewer: {e}")
