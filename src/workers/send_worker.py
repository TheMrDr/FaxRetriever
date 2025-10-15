import traceback
from typing import List

from PyQt5.QtCore import QObject, pyqtSignal

from fax_io.sender import FaxSender


class SendWorker(QObject):
    finished = pyqtSignal()
    success = pyqtSignal(bool)
    error = pyqtSignal(str)
    progress = pyqtSignal(int, int)  # current_session, total_sessions

    def __init__(self, base_dir: str, recipient: str, attachments: List[str], include_cover: bool, parent=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.recipient = recipient
        # Use a shallow copy to avoid UI thread mutating while we work
        self.attachments = list(attachments or [])
        self.include_cover = include_cover

    def _progress_cb(self, current: int, total: int):
        try:
            self.progress.emit(int(current), int(total))
        except Exception:
            # Silently ignore signal issues
            pass

    def run(self):
        try:
            ok = FaxSender.send_fax(
                self.base_dir,
                self.recipient,
                self.attachments,
                self.include_cover,
                progress_callback=self._progress_cb,
            )
            self.success.emit(bool(ok))
        except Exception:
            try:
                self.error.emit(traceback.format_exc())
            except Exception:
                pass
        finally:
            self.finished.emit()
