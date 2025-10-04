from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QProgressDialog, QApplication


class BusyDialog:
    """
    Lightweight indeterminate progress dialog to indicate background work that may block UI updates.
    Use as a context manager:
        with BusyDialog(parent, "Working..."):
            do_blocking_work()
    Or manually call show()/close().
    """
    def __init__(self, parent=None, text: str = "Working...", modal: bool = True):
        self.parent = parent
        self.text = text
        self.modal = modal
        self._dlg = None

    def show(self):
        try:
            self._dlg = QProgressDialog(self.text, None, 0, 0, self.parent)
            # Allow caller to choose modality: default ApplicationModal (blocking), or NonModal for passive indicator
            try:
                self._dlg.setWindowModality(Qt.ApplicationModal if self.modal else Qt.NonModal)
            except Exception:
                # Fallback: ignore if platform doesn't support modality change
                pass
            self._dlg.setCancelButton(None)
            self._dlg.setMinimumDuration(0)
            self._dlg.setWindowTitle("Please wait")
            # Optional: frameless for a cleaner look; fallback if unsupported
            try:
                self._dlg.setWindowFlags(self._dlg.windowFlags() | Qt.FramelessWindowHint)
            except Exception:
                pass
            self._dlg.show()
            QApplication.processEvents()
        except Exception:
            # As a fallback, set busy cursor if dialog fails
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
            except Exception:
                pass

    def close(self):
        try:
            if self._dlg is not None:
                self._dlg.reset()
                self._dlg.close()
                self._dlg = None
                QApplication.processEvents()
        except Exception:
            pass
        finally:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def __enter__(self):
        self.show()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        # Do not suppress exceptions
        return False
