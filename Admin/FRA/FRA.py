"""FRA — FaxRetriever Admin GUI (private)

Purpose
- GUI-only application for administrative staff. Displays and manages data via FRAAPI.
- Does NOT host the API and does NOT talk to MongoDB directly.

How to run (development)
- From Admin\licensing_server: python FRA.py
- Requirements: FRAAPI should be running (use fraapi_host.py). If it is not reachable,
  a prominent red banner appears at the top with a "Retry Connection" button. No blocking popups on launch.

Connecting to FRAAPI
- The GUI communicates with the public FRAAPI over HTTP(S). It reads the base URL from:
  1) User setting (QSettings) key: ClinicNetworking/FRA/fraapi_base_url
  2) Otherwise defaults to http://localhost:8000 (or environment FRAAPI_BASE_URL for internal defaults)
- To change the endpoint at runtime, use the menu: Settings → "Update connection string…"
  This persists the base URL and updates all tabs immediately.

Separation of concerns
- FRA (this GUI) is private; it only calls FRAAPI.
- FRAAPI (public) is the only component that connects to MongoDB and applies business rules.
- The Logs tab uses FRAAPI admin endpoints to list log types and entries; no direct DB access occurs in the GUI.
"""

import sys

if __name__ == "__main__":
    # Defer heavy GUI imports until runtime to keep app importable in headless/test environments
    from PyQt5.QtCore import QSettings, Qt
    from PyQt5.QtWidgets import QApplication

    from ui.main_window import MainWindow
    from ui.theme import app_stylesheet

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

    qt_app = QApplication(sys.argv)

    settings = QSettings("ClinicNetworking", "FRA")
    theme = settings.value("theme", "light")
    qt_app.setStyleSheet(app_stylesheet(theme))

    win = MainWindow(base_dir=None, exe_dir=getattr(sys, "_MEIPASS", None))
    win.show()
    sys.exit(qt_app.exec())
