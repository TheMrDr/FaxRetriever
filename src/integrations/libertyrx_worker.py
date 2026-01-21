"""
libertyrx_worker.py

Background worker that sends LibertyRx jobs using existing FaxSender.
- Polls the store for next pending job.
- Calls FaxSender to send the saved PDF.
- Updates job status to success/error.
- Periodically sweeps expired jobs and leftover files.
"""
from __future__ import annotations

import threading
import time
from typing import Optional

from utils.logging_utils import get_logger
from integrations.libertyrx_store import LibertyStore, Job
from fax_io.sender import FaxSender

log = get_logger("libertyrx.worker")


class LibertyWorker(threading.Thread):
    def __init__(self, store: LibertyStore, base_dir: str, sweep_interval_sec: int = 300):
        super().__init__(name="LibertyRxWorker", daemon=True)
        self.store = store
        self.base_dir = base_dir
        self.sweep_interval_sec = sweep_interval_sec
        self._stop_ev = threading.Event()
        self._last_sweep = 0

    def stop(self):
        try:
            self._stop_ev.set()
        except Exception:
            pass

    def run(self):
        log.info("Liberty worker started")
        while not self._stop_ev.is_set():
            try:
                job: Optional[Job] = self.store.next_pending()
                if not job:
                    # Periodic sweep
                    now = time.time()
                    if now - self._last_sweep > self.sweep_interval_sec:
                        try:
                            removed = self.store.sweep_expired()
                            if removed:
                                log.info(f"Liberty sweep removed {removed} expired jobs")
                        except Exception:
                            pass
                        self._last_sweep = now
                    # Sleep briefly
                    self._stop_ev.wait(1.0)
                    continue

                # Attempt to send
                ok = False
                error_msg = None
                try:
                    ok = FaxSender.send_fax(
                        base_dir=self.base_dir,
                        recipient=job.to_number,
                        attachments=[job.pdf_path],
                        include_cover=False,
                        progress_callback=None,
                    )
                    if not ok:
                        error_msg = "send_failed"
                except Exception as e:
                    try:
                        log.exception(f"Liberty send failed id={job.id}: {e}")
                    except Exception:
                        pass
                    ok = False
                    error_msg = str(e)

                if ok:
                    try:
                        self.store.update_status(job.id, "success", message=None)
                        self.store.delete_file_if_exists(job.pdf_path)
                        log.info(f"Liberty job success id={job.id} to={job.to_number}")
                    except Exception:
                        pass
                else:
                    try:
                        # For MVP, we don't retry, so it goes straight to error.
                        # Statuses: pending, success, error.
                        self.store.update_status(job.id, "error", message=error_msg or "unknown_error")
                        log.warning(f"Liberty job error id={job.id} to={job.to_number} msg={error_msg}")
                    except Exception:
                        pass

                # small pause to prevent tight loop
                self._stop_ev.wait(0.2)
            except Exception:
                # Avoid thread death
                try:
                    log.exception("Liberty worker loop error")
                except Exception:
                    pass
                self._stop_ev.wait(1.0)
        log.info("Liberty worker stopped")
