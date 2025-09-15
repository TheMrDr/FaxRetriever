"""
ui/status_panel.py

Contains status bar visual elements including:
- TokenLifespanProgressBar: Tracks access token validity
- FaxPollTimerProgressBar: Visual countdown until next poll trigger
These widgets integrate with polling logic but do not perform polling themselves.
"""

from datetime import datetime, timezone

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import QProgressBar

from core.app_state import app_state
from core.config_loader import device_config, global_config
from utils.logging_utils import get_logger


class TokenLifespanProgressBar(QProgressBar):
    """
    Progress bar showing time until token expiration.
    Updates every 10 seconds. Emits a signal when nearing expiration.
    """

    token_expiring_soon = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = get_logger("token_bar")
        self.setFormat("Expires in --:--:--")
        self.setMinimum(0)
        self.setMaximum(100)
        self.token_lifetime_sec = 3600  # default fallback: 1 hour
        self.warning_threshold_sec = 3600  # 1 hour
        self.warned_already = False

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._update_progress)
        self.timer.start(10000)  # 10 seconds

    def restart_progress(self):
        self.warned_already = False
        self._update_progress()

    def _update_progress(self):
        try:
            retrieved_str = app_state.global_cfg.bearer_token_retrieved
            expire_str = app_state.global_cfg.bearer_token_expiration
            if not retrieved_str or not expire_str:
                self.log.warning("No token data found. Setting progress to 0.")
                self.setValue(0)
                return

            start_time = datetime.fromisoformat(retrieved_str)
            exp_time = datetime.fromisoformat(expire_str)

            # Normalize if either datetime is naive
            if start_time.tzinfo is None:
                start_time = start_time.replace(tzinfo=timezone.utc)
            if exp_time.tzinfo is None:
                exp_time = exp_time.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)

            if now >= exp_time:
                self.setValue(0)
                return

            total = (exp_time - start_time).total_seconds()
            remaining = (exp_time - now).total_seconds()
            if total <= 0:
                self.setValue(0)
                return

            pct = int((remaining / total) * 100)
            self.setValue(min(max(pct, 0), 100))
            # Update countdown label
            hrs = int(remaining // 3600)
            mins = int((remaining % 3600) // 60)
            secs = int(remaining % 60)
            self.setFormat(f"Expires in {hrs:02d}:{mins:02d}:{secs:02d}")

            if remaining <= self.warning_threshold_sec and not self.warned_already:
                self.warned_already = True
                self.log.warning("Token expires soon. Triggering refresh.")
                self.token_expiring_soon.emit()

        except Exception as e:
            self.log.exception(f"Failed to update token progress: {e}")
            self.setValue(0)


class FaxPollTimerProgressBar(QProgressBar):
    """
    Progress bar for visualizing polling interval countdown.
    Intended to be reset every successful poll cycle.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.log = get_logger("poll_bar")
        self.setFormat("Next poll in --:--")
        self.setMinimum(0)
        self.setMaximum(100)
        self.refresh_bearer_cb = None  # callable set by MainWindow

        try:
            self.interval_secs = (
                int(app_state.device_cfg.polling_frequency) * 60
            )  # convert minutes to seconds
        except (TypeError, ValueError):
            self.interval_secs = 300  # fallback to 5 minutes
            self.log.warning(
                "Invalid polling_frequency in config; using default 300 seconds."
            )

        self.elapsed = 0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)

        if not app_state.device_cfg.save_path:
            self.setValue(0)
            self.timer.stop()
            self.log.warning(
                "Polling disabled: save_location not set at initialization."
            )

    def restart_progress(self):
        if not app_state.device_cfg.save_path:
            self.log.warning(
                "Cannot restart polling progress: save_location is not set."
            )
            self.setValue(0)
            self.timer.stop()
            return

        self.elapsed = 0
        self.timer.start(1000)
        self._update_display()

    def _remaining_token_seconds(self):
        try:
            exp = app_state.global_cfg.bearer_token_expiration
            if not exp:
                return -1
            from datetime import datetime, timezone

            exp_dt = datetime.fromisoformat(exp)
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=timezone.utc)
            now = datetime.now(timezone.utc)
            return int((exp_dt - now).total_seconds())
        except Exception:
            return -1

    def _tick(self):
        if not app_state.device_cfg.save_path:
            self.log.warning("Polling disabled: No save location configured.")
            self.timer.stop()
            self.setValue(0)
            return

        # If we’re inside the 1‑hour window and a hook exists, request refresh before the poll
        remaining = self._remaining_token_seconds()
        if self.refresh_bearer_cb and remaining != -1 and remaining <= 3600:
            try:
                self.refresh_bearer_cb()
            except Exception as e:
                self.log.warning(f"Bearer refresh hook failed: {e}")

        self.elapsed += 1
        if self.elapsed >= self.interval_secs:
            self.retrieveFaxes()
            self.elapsed = 0
        self._update_display()

    def _update_display(self):
        pct = int((self.elapsed / self.interval_secs) * 100)
        remaining = max(self.interval_secs - self.elapsed, 0)
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        self.setFormat(f"Next poll in {mins:02d}:{secs:02d}")
        self.setValue(min(pct, 100))

    def retrieveFaxes(self):
        """Stub method to be connected by caller to polling logic."""
        self.log.info("Polling event should trigger now.")
        # Caller must override this method or connect externally
