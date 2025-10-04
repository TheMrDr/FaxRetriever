import os
from typing import Optional
from PyQt5.QtCore import QUrl, Qt
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtWidgets import QLabel


class ThumbnailHelper:
    """
    Handles thumbnail caching, local PDF to image rendering, and async remote thumbnail fetches.
    Keeps track of active QNetworkReply objects to support aborts on panel refresh/teardown.
    """
    def __init__(self, base_dir: str, exe_dir: Optional[str], app_state, parent_widget):
        self.base_dir = base_dir
        self.exe_dir = exe_dir or base_dir
        self.app_state = app_state
        self.parent = parent_widget
        self._active_replies = set()
        self._net_mgr = None

    # ---- Cache helpers ----
    def _thumb_cache_dir(self) -> str:
        try:
            cache_dir = os.path.join(self.base_dir, "cache", "thumbnails")
            os.makedirs(cache_dir, exist_ok=True)
            return cache_dir
        except Exception:
            return os.path.join(self.base_dir, "cache")

    def _thumb_cache_path(self, url: str) -> str:
        try:
            import hashlib
            key = hashlib.md5((url or "").encode("utf-8")).hexdigest()
            return os.path.join(self._thumb_cache_dir(), f"{key}.png")
        except Exception:
            safe = (url or "").replace(":", "_").replace("/", "_").replace("?", "_")
            return os.path.join(self._thumb_cache_dir(), f"{safe}.png")

    # ---- Public API ----
    def abort_active(self):
        try:
            for r in list(self._active_replies):
                try:
                    r.abort()
                except Exception:
                    pass
            self._active_replies.clear()
        except Exception:
            pass

    def thumbnail_url_for(self, entry: dict) -> Optional[str]:
        try:
            import sys
            fax_id = entry.get("id") or entry.get("fax_id") or entry.get("uuid")
            if not fax_id:
                return None
            fax_user = getattr(self.app_state.global_cfg, 'fax_user', None)
            if not fax_user:
                # Do not attempt API calls without fax_user; skip thumbnail.
                try:
                    from utils.logging_utils import get_logger
                    get_logger("thumb_loader").warning("fax_user missing while building thumbnail URL; skipping thumbnail request.")
                except Exception:
                    pass
                return None
            base_url = "https://telco-api.skyswitch.com"
            return f"{base_url}/users/{fax_user}/faxes/{fax_id}/thumbnail"
        except Exception:
            return None

    def render_pdf_thumbnail(self, pdf_path: str, target_max_w: int) -> Optional[QPixmap]:
        try:
            # First, try rendering with PyMuPDF (fitz) to avoid spawning Poppler subprocesses (no console windows)
            try:
                import fitz  # PyMuPDF
                doc = fitz.open(pdf_path)
                if doc.page_count <= 0:
                    return None
                page = doc.load_page(0)
                # Render at approximately 120 DPI
                pix = page.get_pixmap(dpi=120, alpha=False)
                img_bytes = pix.tobytes("png")
                from io import BytesIO
                qimg = QImage.fromData(img_bytes)
                pm = QPixmap.fromImage(qimg)
                max_w = max(260, min(480, int(target_max_w)))
                max_h = int(max_w * 1.3)
                return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                # Fallback to pdf2image + Poppler if PyMuPDF is unavailable
                from pdf2image import convert_from_path
                # Prefer MEIPASS/base_dir (onefile extraction) for Poppler, then fallback to exe_dir
                candidates = [
                    os.path.join(self.base_dir, "poppler", "bin"),
                    os.path.join(self.exe_dir or self.base_dir, "poppler", "bin"),
                ]
                poppler_bin = next((p for p in candidates if os.path.isdir(p)), None)
                kwargs = {"dpi": 120}
                if poppler_bin:
                    kwargs["poppler_path"] = poppler_bin
                pages = convert_from_path(pdf_path, **kwargs)
                if not pages:
                    return None
                img = pages[0]
                from io import BytesIO
                buf = BytesIO()
                img.save(buf, format='PNG')
                qimg = QImage.fromData(buf.getvalue())
                pm = QPixmap.fromImage(qimg)
                max_w = max(260, min(480, int(target_max_w)))
                max_h = int(max_w * 1.3)
                return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        except Exception:
            return None

    def _load_cached_thumbnail(self, label: QLabel, cache_path: str) -> bool:
        try:
            if os.path.exists(cache_path):
                data_bytes = None
                try:
                    with open(cache_path, 'rb') as f:
                        data_bytes = f.read()
                except Exception:
                    data_bytes = None
                if not data_bytes or len(data_bytes) < 64:
                    return False
                pm = QPixmap()
                if not pm.loadFromData(data_bytes):
                    return False
                try:
                    target_w = label.width() or 0
                    if not isinstance(target_w, int) or target_w <= 0:
                        target_w = 320
                    target_h = int(target_w * 1.3)
                    label.setPixmap(pm.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                except Exception:
                    return False
                return True
        except Exception:
            return False
        return False

    def fetch_remote_thumbnail(self, label: QLabel, url: str):
        cache_path = self._thumb_cache_path(url)
        if self._load_cached_thumbnail(label, cache_path):
            return
        try:
            from PyQt5.QtNetwork import QNetworkAccessManager, QNetworkRequest
            import weakref
            try:
                import sip
            except Exception:
                sip = None
            if self._net_mgr is None:
                self._net_mgr = QNetworkAccessManager(self.parent)
            req = QNetworkRequest(QUrl(url))
            token = self.app_state.global_cfg.bearer_token or ""
            if token:
                req.setRawHeader(b"Authorization", f"Bearer {token}".encode("utf-8"))
            reply = self._net_mgr.get(req)
            try:
                self._active_replies.add(reply)
            except Exception:
                pass
            label_ref = weakref.ref(label)

            def _on_finished():
                try:
                    lbl = label_ref()
                    if lbl is None:
                        return
                    if sip is not None:
                        try:
                            if sip.isdeleted(lbl):
                                return
                        except Exception:
                            pass
                    if reply.error() == 0:
                        qb = reply.readAll()
                        data_bytes = bytes(qb)
                        # Cache atomically
                        try:
                            tmp_path = cache_path + ".part"
                            with open(tmp_path, 'wb') as f:
                                f.write(data_bytes)
                            try:
                                os.replace(tmp_path, cache_path)
                            except Exception:
                                pass
                        except Exception:
                            pass
                        pm = QPixmap()
                        if not pm.loadFromData(data_bytes):
                            try:
                                lbl.setVisible(False)
                            except Exception:
                                pass
                            return
                        try:
                            target_w = lbl.width() or 320
                            target_h = int(target_w * 1.3)
                            lbl.setPixmap(pm.scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                        except Exception:
                            try:
                                lbl.setVisible(False)
                            except Exception:
                                pass
                            return
                    else:
                        try:
                            lbl.setVisible(False)
                        except Exception:
                            return
                finally:
                    try:
                        self._active_replies.discard(reply)
                    except Exception:
                        pass
                    reply.deleteLater()

            reply.finished.connect(_on_finished)
        except Exception:
            try:
                label.setVisible(False)
            except Exception:
                pass

