from PyQt5.QtCore import QObject, QSettings, Qt, QThread, QTimer, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (QAction, QApplication, QButtonGroup, QHBoxLayout,
                             QInputDialog, QLabel, QMainWindow, QPushButton,
                             QStatusBar, QTabWidget, QToolButton, QVBoxLayout,
                             QWidget)

from core.api_client import ApiClient
from ui.tabs.client_tab import ClientTab
from ui.tabs.log_viewer import LogViewerTab
from ui.tabs.reseller_tab import ResellerTab
from ui.tabs.integrations_tab import IntegrationsTab
from ui.theme import app_stylesheet, set_windows_dark_titlebar


class _PingWorker(QObject):
    finished = pyqtSignal(bool, str)

    def __init__(self, api: ApiClient):
        super().__init__()
        self.api = api

    def run(self):
        ok = False
        err = ""
        try:
            ok = self.api.ping()
        except Exception as e:
            ok = False
            try:
                err = str(e)
            except Exception:
                err = ""
        self.finished.emit(ok, err)


class MainWindow(QMainWindow):
    def __init__(self, base_dir=None, exe_dir=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_dir = base_dir
        self.exe_dir = exe_dir
        self.setWindowTitle("FaxRetriever Admin")
        self.setWindowIcon(QIcon("images/logo.ico"))
        self.setMinimumSize(1100, 760)

        # FRAAPI client and connectivity state
        settings = QSettings("ClinicNetworking", "FRA")
        saved_base_url = settings.value("fraapi_base_url", None)
        self.api = ApiClient(base_url=saved_base_url) if saved_base_url else ApiClient()
        self._connected = False

        # Theme state
        self._theme = "light"
        qapp = QApplication.instance()
        qapp.setStyleSheet(app_stylesheet(self._theme))
        qapp.setProperty("fra_theme", self._theme)
        set_windows_dark_titlebar(int(self.winId()), enable=False)  # starting in light

        # Async helpers
        self._ping_thread = None
        self._ping_worker = None
        self._load_queue = []
        # Busy state tracking to avoid stacking override cursors
        self._busy_active = False

        # ---- Single Pane of Glass: Side Navigation + Content ----
        content = QWidget(self)
        root = QHBoxLayout(content)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # Left: Side navigation
        self.side_nav = QWidget()
        self.side_nav.setObjectName("sideNav")
        nav_layout = QVBoxLayout(self.side_nav)
        nav_layout.setContentsMargins(10, 10, 10, 10)
        nav_layout.setSpacing(8)

        self.btn_clients = QToolButton(self)
        self.btn_clients.setText("Clients")
        self.btn_clients.setCheckable(True)
        self.btn_clients.setObjectName("nav")
        self.btn_resellers = QToolButton(self)
        self.btn_resellers.setText("Resellers")
        self.btn_resellers.setCheckable(True)
        self.btn_resellers.setObjectName("nav")
        self.btn_integrations = QToolButton(self)
        self.btn_integrations.setText("Integrations")
        self.btn_integrations.setCheckable(True)
        self.btn_integrations.setObjectName("nav")
        self.btn_logs = QToolButton(self)
        self.btn_logs.setText("Logs")
        self.btn_logs.setCheckable(True)
        self.btn_logs.setObjectName("nav")

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.nav_group.addButton(self.btn_clients, 0)
        self.nav_group.addButton(self.btn_resellers, 1)
        self.nav_group.addButton(self.btn_integrations, 2)
        self.nav_group.addButton(self.btn_logs, 3)

        nav_layout.addWidget(self.btn_clients)
        nav_layout.addWidget(self.btn_resellers)
        nav_layout.addWidget(self.btn_integrations)
        nav_layout.addWidget(self.btn_logs)
        nav_layout.addStretch()

        # Right: Content area: add a connectivity banner above the tabs
        self._right_container = QWidget()
        right_v = QVBoxLayout(self._right_container)
        right_v.setContentsMargins(0, 0, 0, 0)
        right_v.setSpacing(8)

        # Connectivity banner (hidden by default)
        self.conn_banner = QWidget()
        self.conn_banner.setObjectName("connBanner")
        banner_layout = QHBoxLayout(self.conn_banner)
        banner_layout.setContentsMargins(8, 8, 8, 8)
        banner_layout.setSpacing(8)
        self.conn_label = QLabel(
            "Cannot connect to FRAAPI. Please ensure the FRAAPI service is running."
        )
        self.btn_retry = QPushButton("Retry Connection")
        self.btn_retry.clicked.connect(self._retry_connect)
        banner_layout.addWidget(self.conn_label)
        banner_layout.addStretch()
        banner_layout.addWidget(self.btn_retry)
        self.conn_banner.setVisible(False)

        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.North)
        self.tabs.setMovable(False)
        self.tabs.setDocumentMode(False)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.addTab(ClientTab(), "Clients")
        self.tabs.addTab(ResellerTab(), "Resellers")
        self.tabs.addTab(IntegrationsTab(), "Integrations")
        self.tabs.addTab(LogViewerTab(), "Logs")
        self.tabs.tabBar().hide()
        # Track current tab index for on_show/on_hide notifications
        self._current_tab_index = 0

        right_v.addWidget(self.conn_banner)
        right_v.addWidget(self.tabs, 1)

        root.addWidget(self.side_nav)
        root.addWidget(self._right_container, 1)

        self.setCentralWidget(content)

        # Wire navigation
        self.btn_clients.clicked.connect(lambda: self.tabs.setCurrentIndex(0))
        self.btn_resellers.clicked.connect(lambda: self.tabs.setCurrentIndex(1))
        self.btn_integrations.clicked.connect(lambda: self.tabs.setCurrentIndex(2))
        self.btn_logs.clicked.connect(lambda: self.tabs.setCurrentIndex(3))
        self.tabs.currentChanged.connect(self._sync_nav)
        self.btn_clients.setChecked(True)

        # ---- Bottom-right mini controls (Status Bar) ----
        sb = QStatusBar(self)
        self.setStatusBar(sb)

        right_box = QWidget()
        right_layout = QHBoxLayout(right_box)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        btn_refresh = QToolButton(self)
        btn_refresh.setIcon(QIcon("images/refresh.png"))
        btn_refresh.setToolTip("Refresh current tab")
        btn_refresh.setAutoRaise(True)
        btn_refresh.clicked.connect(self.refresh_current_tab)

        self.btn_theme = QToolButton(self)
        self.btn_theme.setIcon(QIcon("images/light_theme.png"))  # start in light mode
        self.btn_theme.setToolTip("Switch to Dark Theme")
        self.btn_theme.setAutoRaise(True)
        self.btn_theme.clicked.connect(self.toggle_theme)

        right_layout.addWidget(btn_refresh)
        right_layout.addWidget(self.btn_theme)
        sb.addPermanentWidget(right_box)

        # Left side of status bar: activity label
        self.activity_label = QLabel("")
        sb.addWidget(self.activity_label, 1)

        # Settings menu
        menubar = self.menuBar()
        settings_menu = menubar.addMenu("&Settings")
        act_update_conn = QAction("Update connection string...", self)
        act_update_conn.triggered.connect(self._update_connection_string)
        settings_menu.addAction(act_update_conn)

        # Ensure all tabs use the same API base URL
        try:
            self._apply_api_base_url_to_tabs(self.api.base_url)
        except Exception:
            pass

        # Initial connectivity check and UI state (deferred to avoid blocking initial paint)
        QTimer.singleShot(0, self._initialize_connectivity_async)

    # ---- Async initialization and loading ----
    def _initialize_connectivity_async(self):
        # Disable tabs and show connecting message; do not block UI
        self._set_busy(True, "Connecting to FRAAPI…")
        self.tabs.setEnabled(False)
        self.conn_label.setText("Connecting to FRAAPI…")
        self.conn_banner.setVisible(False)  # hide until we know it failed
        self._start_ping_thread()

    def _start_ping_thread(self):
        if self._ping_thread is not None:
            try:
                self._ping_thread.quit()
                self._ping_thread.wait(100)
            except Exception:
                pass
        self._ping_thread = QThread(self)
        self._ping_worker = _PingWorker(self.api)
        self._ping_worker.moveToThread(self._ping_thread)
        self._ping_thread.started.connect(self._ping_worker.run)
        self._ping_worker.finished.connect(self._on_ping_finished)
        self._ping_worker.finished.connect(self._ping_thread.quit)
        self._ping_worker.finished.connect(self._ping_worker.deleteLater)
        self._ping_thread.finished.connect(self._ping_thread.deleteLater)
        self._ping_thread.start()

    def _on_ping_finished(self, ok: bool, err: str = ""):
        self._set_conn_state(ok)
        if ok:
            # Begin non-blocking tab loading
            self._load_all_tabs_async()
        else:
            self._set_busy(False)
            self.conn_label.setText(
                "Cannot connect to FRAAPI. Please ensure the FRAAPI service is running."
            )

    def _retry_connect(self):
        self.conn_label.setText("Retrying connection to FRAAPI…")
        self._set_busy(True, "Retrying connection to FRAAPI…")
        self.tabs.setEnabled(False)
        self._start_ping_thread()

    def _set_conn_state(self, connected: bool):
        self._connected = connected
        self.conn_banner.setVisible(not connected)
        self.tabs.setEnabled(connected)

    def _load_all_tabs_async(self):
        # Queue each tab's loader method name in display order
        self._load_queue = []
        for idx in range(self.tabs.count()):
            w = self.tabs.widget(idx)
            for meth in ("load_clients", "load_resellers", "load_logs"):
                if hasattr(w, meth):
                    self._load_queue.append((idx, meth))
                    break
        # Disable tabs while loading; start chain
        self.tabs.setEnabled(False)
        QTimer.singleShot(0, self._process_next_load)

    def _process_next_load(self):
        if not self._load_queue:
            # Done
            self._set_busy(False, "Ready")
            self.tabs.setEnabled(True)
            return
        idx, meth = self._load_queue.pop(0)
        w = self.tabs.widget(idx)
        # Update status indicator
        tab_name = self.tabs.tabText(idx) or "Tab"
        action = {
            "load_clients": "Loading Clients…",
            "load_resellers": "Loading Resellers…",
            "load_logs": "Loading Logs…",
        }.get(meth, f"Loading {tab_name}…")
        self._set_busy(True, action)
        try:
            getattr(w, meth)()
        except Exception:
            pass
        # Schedule next load step to keep UI responsive
        QTimer.singleShot(0, self._process_next_load)

    def _set_busy(self, busy: bool, message: str = ""):
        # Update status bar message and cursor with guard to avoid stacking
        if hasattr(self, "activity_label"):
            self.activity_label.setText(message or ("Busy" if busy else ""))
        if busy and not getattr(self, "_busy_active", False):
            try:
                QApplication.setOverrideCursor(Qt.WaitCursor)
            except Exception:
                pass
            self._busy_active = True
        elif not busy and getattr(self, "_busy_active", False):
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
            self._busy_active = False

    def toggle_theme(self):
        if self._theme == "light":
            self._theme = "dark"
            self.btn_theme.setIcon(QIcon("images/dark_theme.png"))
            self.btn_theme.setToolTip("Switch to Light Theme")
            enable_dark_title = True
        else:
            self._theme = "light"
            self.btn_theme.setIcon(QIcon("images/light_theme.png"))
            self.btn_theme.setToolTip("Switch to Dark Theme")
            enable_dark_title = False

        qapp = QApplication.instance()
        qapp.setStyleSheet(app_stylesheet(self._theme))
        qapp.setProperty("fra_theme", self._theme)
        set_windows_dark_titlebar(int(self.winId()), enable_dark_title)

    def refresh_current_tab(self):
        w = self.tabs.currentWidget()
        for meth in ("load_clients", "load_resellers", "load_logs"):
            if hasattr(w, meth):
                getattr(w, meth)()
                break

    def _sync_nav(self, index):
        # Update nav button checked state
        if index == 0:
            self.btn_clients.setChecked(True)
        elif index == 1:
            self.btn_resellers.setChecked(True)
        elif index == 2:
            self.btn_integrations.setChecked(True)
        elif index == 3:
            self.btn_logs.setChecked(True)
        # Notify tabs about hide/show to support async lifecycle
        try:
            prev = getattr(self, "_current_tab_index", None)
            if prev is not None and prev != index:
                prev_w = self.tabs.widget(prev)
                if hasattr(prev_w, "on_hide"):
                    try:
                        prev_w.on_hide()
                    except Exception:
                        pass
            self._current_tab_index = index
            cur_w = self.tabs.widget(index)
            # Ensure tab has the current ApiClient and notify on_show
            if hasattr(cur_w, "set_api"):
                try:
                    cur_w.set_api(self.api)
                except Exception:
                    pass
            if hasattr(cur_w, "on_show"):
                try:
                    cur_w.on_show()
                except Exception:
                    pass
        except Exception:
            pass

    def _apply_api_base_url_to_tabs(self, base_url: str):
        try:
            # Update MainWindow client first
            if hasattr(self, "api") and isinstance(self.api, ApiClient):
                self.api.base_url = (base_url or self.api.base_url or "").rstrip("/")
            # Update all tabs
            for idx in range(self.tabs.count()):
                w = self.tabs.widget(idx)
                if hasattr(w, "api"):
                    try:
                        if isinstance(w.api, ApiClient):
                            w.api.base_url = (base_url or w.api.base_url or "").rstrip(
                                "/"
                            )
                        else:
                            setattr(w, "api", ApiClient(base_url=base_url))
                    except Exception:
                        setattr(w, "api", ApiClient(base_url=base_url))
        except Exception:
            pass

    def _update_connection_string(self):
        current = (
            getattr(self.api, "base_url", "https://licensing.clinicnetworking.com")
            or "https://licensing.clinicnetworking.com"
        )
        new_url, ok = QInputDialog.getText(
            self, "Update connection string", "FRAAPI base URL:", text=current
        )
        if not ok:
            return
        new_url = (new_url or "").strip().rstrip("/")
        if not new_url:
            return
        # Basic scheme validation; accept http/https only
        if not (new_url.startswith("http://") or new_url.startswith("https://")):
            new_url = "http://" + new_url
        # Persist
        settings = QSettings("ClinicNetworking", "FRA")
        settings.setValue("fraapi_base_url", new_url)
        # Apply to clients and tabs
        self._apply_api_base_url_to_tabs(new_url)
        # Update banner text to reflect endpoint for clarity (optional)
        if hasattr(self, "conn_label"):
            self.conn_label.setText(
                "Cannot connect to FRAAPI. Please ensure the FRAAPI service is running."
            )
        # Retry connection
        self._retry_connect()
