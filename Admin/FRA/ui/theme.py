# ui/theme.py
import ctypes
from ctypes import wintypes

from PyQt5.QtGui import QColor, QPalette

LIGHT = {
    "bg": "#f6f7fb",
    "panel": "#ffffff",
    "panel_border": "#e5e7ee",
    "text": "#111318",
    "muted": "#6b7280",
    "primary": "#0b5fff",  # can swap to your #000099 accent if you want
    "primary_fg": "#ffffff",
    "success": "#2ea44f",
    "warning": "#b45309",
    "danger": "#b00020",
    "row_alt": "#fafbff",
}

DARK = {
    "bg": "#0f1115",
    "panel": "#161a20",
    "panel_border": "#3a4150",
    "text": "#e5e7eb",
    "muted": "#b0bac8",
    "primary": "#3b82f6",
    "primary_fg": "#ffffff",
    "success": "#22c55e",
    "warning": "#f59e0b",
    "danger": "#ef4444",
    "row_alt": "#12161d",
}


def app_stylesheet(theme="light"):
    c = LIGHT if theme == "light" else DARK
    return f"""
    QMainWindow {{
        background: {c['bg']};
    }}

    /* Tabs ------------------------------------------------------------ */
    QTabWidget::pane {{
        border: 0;
        margin-top: 6px;
    }}
    QTabWidget::tab-bar {{
        left: 12px; /* keep first tab off the window edge */
    }}
    QTabBar::tab {{
        padding: 7px 14px;
        margin: 0 6px;
        min-width: 50px;
        max-width: none;
        border-radius: 10px 10px 0 0;
        font-weight: 600;
        border: 1px solid {c['panel_border']};
        border-bottom: 0;
        color: {c['muted']};
        background: {c['row_alt']};  /* << give unselected tabs a subtle pill */
    }}
    QTabBar::tab:selected {{
        color: {c['text']};
        background: {c['panel']};
        border: 1px solid {c['panel_border']};
        border-bottom: 0;
    }}
    QTabBar::tab:!selected:hover {{
        background: {c['panel']};
        color: {c['text']};
    }}

    /* Side Navigation -------------------------------------------------- */
    QWidget#sideNav {{
        background: {c['panel']};
        border: 1px solid {c['panel_border']};
        border-radius: 12px;
        padding: 6px;
        min-width: 180px;
    }}
    QToolButton#nav {{
        background: transparent;
        color: {c['muted']};
        border: 0;
        padding: 8px 12px;
        border-radius: 8px;
        text-align: left;
    }}
    QToolButton#nav:hover {{
        background: {c['row_alt']};
        color: {c['text']};
    }}
    QToolButton#nav:checked {{
        background: {c['primary']};
        color: {c['primary_fg']};
    }}

    /* Panels / Inputs ------------------------------------------------- */
    QFrame#panel, QWidget#panel {{
        background: {c['panel']};
        border: 1px solid {c['panel_border']};
        border-radius: 12px;
    }}

    /* Connection banner (prominent red alert) */
    QWidget#connBanner {{
        background: {c['danger']};
        border: 1px solid {c['danger']};
        border-radius: 10px;
        padding: 8px 10px;
    }}
    QWidget#connBanner QLabel {{
        color: #ffffff;
        font-weight: 700;
    }}
    QWidget#connBanner QPushButton {{
        background: transparent;
        color: #ffffff;
        border: 1px solid #ffffff;
        border-radius: 6px;
        padding: 6px 12px;
    }}
    QWidget#connBanner QPushButton:hover {{
        background: rgba(255, 255, 255, 0.12);
    }}

    QLabel#title {{
        font-size: 16px;
        font-weight: 700;
        color: {c['text']};
        padding: 4px 0 6px 0;
    }}
    /* Ensure core text widgets inherit theme text color */
    QLabel, QCheckBox, QRadioButton {{
        color: {c['text']};
    }}
    QLineEdit, QComboBox, QTextEdit, QPlainTextEdit {{
        background: {c['panel']};
        border: 1px solid {c['panel_border']};
        border-radius: 8px;
        padding: 6px 8px;
        color: {c['text']};
    }}
    /* Muted placeholders for better affordance */
    QLineEdit::placeholder {{
        color: {c['muted']};
    }}
    QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
        border: 1px solid {c['primary']};
        outline: none;
    }}
    /* Read-only editors (e.g., Log Viewer payload) */
    QTextEdit[readOnly="true"], QPlainTextEdit[readOnly="true"] {{
        background: {c['panel']};
        color: {c['text']};
    }}

    /* Buttons --------------------------------------------------------- */
    QPushButton {{
        border-radius: 8px;
        padding: 7px 12px;
        font-weight: 600;
        border: 1px solid {c['panel_border']};
        background: {c['panel']};
        color: {c['text']};
    }}
    QPushButton:hover {{
        border-color: {c['primary']};
    }}
    QPushButton#primary {{
        background: {c['primary']};
        color: {c['primary_fg']};
        border: 0;
    }}
    QPushButton#danger {{
        background: {c['danger']};
        color: white;
        border: 0;
    }}
    QPushButton#warning {{
        background: {c['warning']};
        color: black;
        border: 0;
    }}
    QPushButton#refreshButton {{
    background: {c['panel']};
    color: {c['text']};
    border: 1px solid {c['panel_border']};
    }}
    QPushButton#refreshButton:hover {{
        background: {c['row_alt']};
    }}
    QTextEdit#payloadView {{
        background: {c['panel']};
        color: {c['text']};
    }}

    /* Dialogs ---------------------------------------------------------- */
    QDialog, QMessageBox, QInputDialog, QFileDialog {{
        background: {c['panel']};
        color: {c['text']};
        border: 1px solid {c['panel_border']};
        border-radius: 12px;
    }}
    QMessageBox QLabel, QInputDialog QLabel {{
        color: {c['text']};
    }}
    QDialogButtonBox {{
        background: transparent;
    }}
    QFileDialog QWidget {{
        background: {c['panel']};
        color: {c['text']};
    }}
    QFileDialog QLineEdit, QFileDialog QComboBox, QFileDialog QTreeView, QFileDialog QListView {{
        background: {c['panel']};
        color: {c['text']};
        border: 1px solid {c['panel_border']};
        selection-background-color: {c['primary']};
        selection-color: {c['primary_fg']};
    }}

    /* Tables ---------------------------------------------------------- */
    /* Base item views (covers empty areas/viewport too) */
    QAbstractItemView {{
        background: {c['panel']};
        alternate-background-color: {c['row_alt']};
        color: {c['text']};
        border: 1px solid {c['panel_border']};
        selection-background-color: {c['primary']};
        selection-color: {c['primary_fg']};
        gridline-color: {c['panel_border']};
    }}
    QTableView, QTableWidget {{
        background: {c['panel']};
        alternate-background-color: {c['row_alt']};
        color: {c['text']};
        gridline-color: {c['panel_border']};
        border: 1px solid {c['panel_border']};
    }}
    QTableView::item:selected, QTableWidget::item:selected {{
        background: {c['primary']};
        color: {c['primary_fg']};
    }}
    QHeaderView {{
        background: {c['panel']};
        border: 0;
    }}
    QHeaderView::section {{
        background: {c['panel']};
        border: 0;
        border-bottom: 1px solid {c['panel_border']};
        border-right: 1px solid {c['panel_border']};
        padding: 8px;
        font-weight: 700;
        color: {c['text']};
    }}
    QHeaderView::section:horizontal {{
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
    }}
    QTableCornerButton::section {{
        background: {c['panel']};
        border: 0;
        border-bottom: 1px solid {c['panel_border']};
        border-right: 1px solid {c['panel_border']};
    }}

    /* Status bar + tiny buttons -------------------------------------- */
    QStatusBar {{ background: {c['panel']}; border-top: 1px solid {c['panel_border']}; }}
    QToolButton {{ border: 0; padding: 2px; border-radius: 6px; }}
    QToolButton:hover {{ background: {c['row_alt']}; }}
    """


def set_windows_dark_titlebar(hwnd: int, enable: bool) -> None:
    """
    Toggle Windows immersive dark mode for the title bar (Win10 1809+).
    Safe no-op on older Windows/Qt builds.
    """
    try:
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20  # 19 on older builds
        value = wintypes.BOOL(1 if enable else 0)
        dwmapi = ctypes.windll.dwmapi
        # try 20 first
        res = dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
        if res != 0:  # fallback to 19 for older builds
            DWMWA_USE_IMMERSIVE_DARK_MODE = 19
            dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                wintypes.DWORD(DWMWA_USE_IMMERSIVE_DARK_MODE),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
    except Exception:
        # swallow errors on unsupported systems
        pass
