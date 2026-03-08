"""
ui/theme.py

Centralized theme engine for FaxRetriever.
Provides light and dark theme palettes, QSS generation, and runtime switching.
Palette derived from the FaxRetriever logo: dark navy + sky blue.
"""

from __future__ import annotations

from PyQt5.QtGui import QColor, QPalette
from PyQt5.QtWidgets import QApplication

# ---------------------------------------------------------------------------
# Theme token dictionaries  (logo-inspired: navy #1E2D3D + sky blue #5DADE2)
# ---------------------------------------------------------------------------

LIGHT_THEME: dict[str, str] = {
    "name": "light",
    # Brand / accent  (sky blue from the logo cloud — decorative only)
    "primary": "#5DADE2",
    "primary_hover": "#4A9BD0",
    "primary_pressed": "#3889BE",
    "primary_light": "#E8F4FD",
    # Buttons — dark navy for AAA contrast (≥7:1) with white text
    # #2C3E50 on white = ~11.4:1 contrast ratio
    "button_bg": "#2C3E50",
    "button_hover": "#34495E",
    "button_pressed": "#1A252F",
    "button_text": "#FFFFFF",
    # Semantic
    "success": "#27AE60",
    "error": "#E74C3C",
    "warning": "#F39C12",
    # Card backgrounds
    "inbound_card_bg": "#F0F7FF",
    "outbound_card_bg": "#FFF9F0",
    # Surfaces
    "surface": "#FFFFFF",
    "background": "#F4F6F8",
    # Borders
    "border": "#D5DCE1",
    "border_hover": "#A0B0BC",
    "border_focus": "#5DADE2",
    # Text  (dark navy from the logo wordmark)
    "text_primary": "#1E2D3D",
    "text_secondary": "#5A6C7D",
    "text_muted": "#95A5A6",
    "text_on_primary": "#FFFFFF",
    # Misc
    "scrim": "rgba(0, 0, 0, 160)",
    "separator": "#D5DCE1",
    "input_bg": "#FFFFFF",
    "sidebar_bg": "#EDF1F3",
    "sidebar_selected": "#2C3E50",
    "sidebar_selected_text": "#FFFFFF",
    "badge_new": "#2980B9",
    "link": "#2E86C1",
    "scrollbar_handle": "#B0BEC5",
    "scrollbar_bg": "#F4F6F8",
    "tooltip_bg": "#1E2D3D",
    "tooltip_text": "#ECF0F1",
}

DARK_THEME: dict[str, str] = {
    "name": "dark",
    # Brand / accent  (same sky blue — decorative only)
    "primary": "#5DADE2",
    "primary_hover": "#7EC8F0",
    "primary_pressed": "#4A9BD0",
    "primary_light": "#1A2D3D",
    # Buttons — lighter steel for contrast against dark surfaces
    # #5B8BA8 on #1E2530 surface ≈ 3.8:1  (not enough)
    # Use #ECEFF1 bg + dark text for maximum readability in dark mode
    # Or: medium blue #3A7CA5 with white text ≈ 4.6:1 (AA)
    # Best: #4A90B8 w/ white = ~3.5:1 — not great
    # Going with light button approach: #D5E8F0 bg + #1A252F text ≈ 12:1
    "button_bg": "#D5E8F0",
    "button_hover": "#B8D4E3",
    "button_pressed": "#A0C4D6",
    "button_text": "#1A252F",
    # Semantic
    "success": "#2ECC71",
    "error": "#E74C3C",
    "warning": "#F1C40F",
    # Card backgrounds
    "inbound_card_bg": "#1A2530",
    "outbound_card_bg": "#2A2520",
    # Surfaces
    "surface": "#1E2530",
    "background": "#141A22",
    # Borders
    "border": "#2E3A45",
    "border_hover": "#4A5A6A",
    "border_focus": "#5DADE2",
    # Text
    "text_primary": "#ECF0F1",
    "text_secondary": "#B0BEC5",
    "text_muted": "#607D8B",
    "text_on_primary": "#FFFFFF",
    # Misc
    "scrim": "rgba(0, 0, 0, 200)",
    "separator": "#2E3A45",
    "input_bg": "#253040",
    "sidebar_bg": "#161D26",
    "sidebar_selected": "#D5E8F0",
    "sidebar_selected_text": "#1A252F",
    "badge_new": "#5DADE2",
    "link": "#5DADE2",
    "scrollbar_handle": "#4A5A6A",
    "scrollbar_bg": "#1E2530",
    "tooltip_bg": "#1E2D3D",
    "tooltip_text": "#ECF0F1",
}

_THEMES = {"light": LIGHT_THEME, "dark": DARK_THEME}
_current_theme_name: str = "light"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_theme(name: str | None = None) -> dict[str, str]:
    """Return the requested (or currently active) theme dict."""
    return _THEMES.get(name or _current_theme_name, LIGHT_THEME)


def current_theme_name() -> str:
    return _current_theme_name


def set_theme(name: str) -> None:
    """Switch theme and apply to the running QApplication."""
    global _current_theme_name
    _current_theme_name = name if name in _THEMES else "light"
    t = get_theme()
    app = QApplication.instance()
    if app is None:
        return
    # Clear stylesheet first — Qt sometimes skips recalculation when the
    # stylesheet object identity hasn't changed.
    app.setStyleSheet("")
    app.setStyleSheet(build_stylesheet(t))
    _apply_palette(app, t)


def toggle_theme() -> str:
    """Flip between light and dark. Returns the new theme name."""
    new = "dark" if _current_theme_name == "light" else "light"
    set_theme(new)
    return new


# ---------------------------------------------------------------------------
# Semantic color helpers (for dynamic per-item styling)
# ---------------------------------------------------------------------------

def color_for_status(status_text: str) -> str:
    """Return themed hex color for a fax status string."""
    t = get_theme()
    s = (status_text or "").lower()
    if any(k in s for k in ("fail", "error", "undeliv")):
        return t["error"]
    if any(k in s for k in ("pend", "queue", "sending", "process")):
        return t["warning"]
    if any(k in s for k in ("deliv", "success", "sent", "ok")):
        return t["success"]
    return t["text_secondary"]


def color_for_direction(direction: str) -> str:
    """Return themed card background for inbound/outbound."""
    t = get_theme()
    return t["inbound_card_bg"] if (direction or "").lower() == "inbound" else t["outbound_card_bg"]


def avatar_color() -> str:
    return get_theme()["primary"]


# ---------------------------------------------------------------------------
# QSS generator
# ---------------------------------------------------------------------------

def build_stylesheet(t: dict[str, str]) -> str:
    """Generate a full application QSS string from theme tokens."""
    return f"""
/* ===== Global ===== */
* {{
    font-family: "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 10pt;
    color: {t["text_primary"]};
}}

QMainWindow, QDialog {{
    background-color: {t["background"]};
}}

QLabel {{
    background: transparent;
}}

/* ===== Buttons (high-contrast for accessibility) ===== */
QPushButton {{
    background-color: {t["button_bg"]};
    color: {t["button_text"]};
    border: none;
    border-radius: 4px;
    padding: 6px 18px;
    min-height: 24px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {t["button_hover"]};
}}
QPushButton:pressed {{
    background-color: {t["button_pressed"]};
}}
QPushButton:disabled {{
    background-color: {t["border"]};
    color: {t["text_muted"]};
}}
QPushButton[flat="true"], QPushButton#flatButton {{
    background: transparent;
    color: {t["text_primary"]};
    border: 1px solid {t["border"]};
}}
QPushButton[flat="true"]:hover, QPushButton#flatButton:hover {{
    background: {t["primary_light"]};
    border-color: {t["primary"]};
}}

/* ===== Inputs ===== */
QLineEdit, QSpinBox, QComboBox, QDateEdit {{
    background-color: {t["input_bg"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border"]};
    border-radius: 4px;
    padding: 5px 8px;
    selection-background-color: {t["primary"]};
    selection-color: {t["text_on_primary"]};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
    border-color: {t["border_focus"]};
}}
QLineEdit:read-only {{
    background-color: {t["background"]};
    color: {t["text_secondary"]};
}}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{
    background-color: {t["background"]};
    color: {t["text_muted"]};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {t["surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border"]};
    selection-background-color: {t["primary_light"]};
    selection-color: {t["text_primary"]};
}}

/* ===== Check/Radio ===== */
QCheckBox, QRadioButton {{
    background: transparent;
    spacing: 6px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {t["border_hover"]};
    border-radius: 3px;
    background: {t["input_bg"]};
}}
QRadioButton::indicator {{
    border-radius: 9px;
}}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{
    background: {t["primary"]};
    border-color: {t["primary"]};
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: {t["background"]};
    border-color: {t["border"]};
}}

/* ===== GroupBox ===== */
QGroupBox {{
    background-color: {t["surface"]};
    border: 1px solid {t["border"]};
    border-radius: 6px;
    margin-top: 14px;
    padding: 18px 12px 12px 12px;
    font-weight: bold;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 2px 8px;
    color: {t["primary"]};
}}

/* ===== Progress Bars ===== */
QProgressBar {{
    background-color: {t["background"]};
    border: 1px solid {t["border"]};
    border-radius: 4px;
    text-align: center;
    color: {t["text_secondary"]};
    min-height: 18px;
    max-height: 18px;
}}
QProgressBar::chunk {{
    background-color: {t["primary"]};
    border-radius: 3px;
}}

/* ===== Scroll ===== */
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: {t["scrollbar_bg"]};
    width: 10px;
    margin: 0;
    border-radius: 5px;
}}
QScrollBar::handle:vertical {{
    background: {t["scrollbar_handle"]};
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {t["border_hover"]};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {t["scrollbar_bg"]};
    height: 10px;
    margin: 0;
    border-radius: 5px;
}}
QScrollBar::handle:horizontal {{
    background: {t["scrollbar_handle"]};
    border-radius: 5px;
    min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {t["border_hover"]};
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== Tabs (generous padding to prevent text clipping) ===== */
QTabWidget::pane {{
    background-color: {t["surface"]};
    border: 1px solid {t["border"]};
    border-top: none;
    border-radius: 0 0 6px 6px;
}}
QTabBar::tab {{
    background-color: {t["background"]};
    color: {t["text_secondary"]};
    border: 1px solid {t["border"]};
    border-bottom: none;
    padding: 8px 24px;
    min-width: 80px;
    margin-right: 2px;
    border-radius: 4px 4px 0 0;
}}
QTabBar::tab:selected {{
    background-color: {t["surface"]};
    color: {t["button_bg"]};
    font-weight: bold;
    border-bottom: 2px solid {t["button_bg"]};
}}
QTabBar::tab:hover:!selected {{
    background-color: {t["primary_light"]};
    color: {t["text_primary"]};
}}

/* ===== Menu ===== */
QMenuBar {{
    background-color: {t["surface"]};
    color: {t["text_primary"]};
    border-bottom: 1px solid {t["border"]};
}}
QMenuBar::item:selected {{
    background-color: {t["primary_light"]};
    color: {t["primary"]};
}}
QMenu {{
    background-color: {t["surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border"]};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 6px 24px;
}}
QMenu::item:selected {{
    background-color: {t["primary_light"]};
    color: {t["primary"]};
}}
QMenu::separator {{
    height: 1px;
    background: {t["border"]};
    margin: 4px 8px;
}}

/* ===== ToolButton ===== */
QToolButton {{
    background-color: {t["button_bg"]};
    color: {t["button_text"]};
    border: none;
    border-radius: 4px;
    padding: 5px 12px;
}}
QToolButton:hover {{
    background-color: {t["button_hover"]};
}}
QToolButton::menu-indicator {{
    subcontrol-position: right center;
    subcontrol-origin: padding;
    width: 12px;
}}

/* ===== Text displays ===== */
QTextBrowser, QTextEdit {{
    background-color: {t["surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border"]};
    border-radius: 4px;
    padding: 8px;
    selection-background-color: {t["primary"]};
    selection-color: {t["text_on_primary"]};
}}

/* ===== List/Table ===== */
QListWidget, QTableWidget {{
    background-color: {t["surface"]};
    color: {t["text_primary"]};
    border: 1px solid {t["border"]};
    border-radius: 4px;
    alternate-background-color: {t["background"]};
}}
QListWidget::item:selected, QTableWidget::item:selected {{
    background-color: {t["primary_light"]};
    color: {t["text_primary"]};
}}
QListWidget::item:hover, QTableWidget::item:hover {{
    background-color: {t["primary_light"]};
}}
QHeaderView::section {{
    background-color: {t["background"]};
    color: {t["text_primary"]};
    border: none;
    border-bottom: 1px solid {t["border"]};
    padding: 6px 8px;
    font-weight: bold;
}}

/* ===== Splitter ===== */
QSplitter::handle {{
    background-color: {t["border"]};
    width: 2px;
}}
QSplitter::handle:hover {{
    background-color: {t["primary"]};
}}

/* ===== StatusBar ===== */
QStatusBar {{
    background-color: {t["surface"]};
    color: {t["text_secondary"]};
    border-top: 1px solid {t["border"]};
}}

/* ===== Tooltip ===== */
QToolTip {{
    background-color: {t["tooltip_bg"]};
    color: {t["tooltip_text"]};
    border: 1px solid {t["border"]};
    border-radius: 4px;
    padding: 4px 8px;
}}

/* ===== Frame ===== */
QFrame[frameShape="4"] {{
    color: {t["separator"]};
}}

/* ===== DialogButtonBox ===== */
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}

/* ===== Stacked pages (ensure background propagates) ===== */
QStackedWidget > QWidget {{
    background-color: {t["background"]};
}}

/* ===== Overlay scrim (used by main_window._show_overlay) ===== */
#overlayScrim {{
    background: {t["scrim"]};
}}

/* ===== Named widget styles ===== */
#panelHeader {{
    font-weight: bold;
    font-size: 12pt;
    background: transparent;
}}
#dialogTitle {{
    font-weight: bold;
    font-size: 14pt;
    background: transparent;
}}
#sectionHeader {{
    font-size: 12pt;
    font-weight: bold;
    padding: 2px 4px;
    background: transparent;
}}
#recipientGroup {{
    font-size: 11pt;
}}
#hint {{
    color: {t["text_secondary"]};
    background: transparent;
}}
#pdfPreview {{
    border: 1px solid {t["border"]};
    background: {t["surface"]};
}}
#markdownViewer {{
    padding: 12px;
}}

/* ===== Options Sidebar ===== */
#optionsSidebar {{
    background-color: {t["sidebar_bg"]};
    border: none;
    border-right: 1px solid {t["border"]};
    border-radius: 0;
    outline: none;
    font-size: 10pt;
}}
#optionsSidebar::item {{
    padding: 12px 20px;
    border: none;
    border-radius: 0;
}}
#optionsSidebar::item:selected {{
    background-color: {t["button_bg"]};
    color: {t["button_text"]};
    font-weight: bold;
}}
#optionsSidebar::item:hover:!selected {{
    background-color: {t["primary_light"]};
}}
"""


# ---------------------------------------------------------------------------
# QPalette (for native dialogs like QMessageBox, QFileDialog)
# ---------------------------------------------------------------------------

def _apply_palette(app: QApplication, t: dict[str, str]) -> None:
    """Set QPalette so native dialogs also respect the theme."""
    p = QPalette()
    p.setColor(QPalette.Window, QColor(t["background"]))
    p.setColor(QPalette.WindowText, QColor(t["text_primary"]))
    p.setColor(QPalette.Base, QColor(t["surface"]))
    p.setColor(QPalette.AlternateBase, QColor(t["background"]))
    p.setColor(QPalette.Text, QColor(t["text_primary"]))
    p.setColor(QPalette.Button, QColor(t["surface"]))
    p.setColor(QPalette.ButtonText, QColor(t["text_primary"]))
    p.setColor(QPalette.Highlight, QColor(t["primary"]))
    p.setColor(QPalette.HighlightedText, QColor(t["text_on_primary"]))
    p.setColor(QPalette.ToolTipBase, QColor(t["tooltip_bg"]))
    p.setColor(QPalette.ToolTipText, QColor(t["tooltip_text"]))
    p.setColor(QPalette.Link, QColor(t["link"]))
    p.setColor(QPalette.PlaceholderText, QColor(t["text_muted"]))
    # Disabled state
    p.setColor(QPalette.Disabled, QPalette.WindowText, QColor(t["text_muted"]))
    p.setColor(QPalette.Disabled, QPalette.Text, QColor(t["text_muted"]))
    p.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(t["text_muted"]))
    app.setPalette(p)
