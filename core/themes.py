# core/themes.py
"""App colors and the Qt stylesheet.

Every color in the UI comes from these tokens, so a theme changes the whole app.
Theme names are unchanged from v1.1, so saved settings keep working.
"""

BASE = {
    "bg": "#0f1115",        # window background
    "sidebar": "#13161b",
    "card": "#171a20",      # cards / panels
    "card_hover": "#1c2027",
    "input": "#1b1f26",
    "border": "#262b33",
    "text": "#e8eaed",
    "subtext": "#9aa0a6",
    "muted": "#6b717a",
    "good": "#3fb950",
    "warn": "#d29922",
    "bad": "#f85149",
}

ACCENTS = {
    "Midnight": "#8b95a5",
    "Pink": "#e91e63",
    "Blue": "#3b82f6",
    "Purple": "#a855f7",
    "Red": "#ef4444",
    "Green": "#22c55e",
    "Cyan": "#06b6d4",
}

THEMES = {name: {**BASE, "accent": accent} for name, accent in ACCENTS.items()}


def _on_accent(hex_color):
    """Black or white text, whichever reads better on the accent color."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#0f1115" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def get_theme(theme_name="Midnight", custom_accent=None):
    t = dict(THEMES.get(theme_name, THEMES["Midnight"]))
    if custom_accent:
        t["accent"] = custom_accent
    t["on_accent"] = _on_accent(t["accent"])
    return t


def get_stylesheet(theme_name="Midnight", custom_accent=None):
    t = get_theme(theme_name, custom_accent)
    return f"""
    QWidget {{ background-color: {t['bg']}; color: {t['text']};
               font-family: 'Segoe UI Variable Text', 'Segoe UI', sans-serif; font-size: 13px; }}
    QLabel {{ background: transparent; }}
    QToolTip {{ background-color: {t['card']}; color: {t['text']}; border: 1px solid {t['border']}; padding: 6px; }}

    /* Sidebar */
    QFrame#sidebar {{ background-color: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
    QFrame#sidebar QWidget {{ background-color: transparent; }}
    QLabel#brand {{ font-size: 20px; font-weight: 800; letter-spacing: 2px; color: {t['text']}; }}
    QLabel#brandVersion {{ font-size: 11px; color: {t['muted']}; }}
    QLabel#navSection {{ font-size: 10px; font-weight: 700; letter-spacing: 1px; color: {t['muted']};
                          padding: 14px 10px 4px 10px; }}
    QPushButton[role="nav"] {{ background: transparent; color: {t['subtext']}; border: none;
        border-radius: 8px; padding: 7px 12px; text-align: left; font-size: 13px; }}
    QPushButton[role="nav"]:hover {{ background-color: {t['card_hover']}; color: {t['text']}; }}
    QPushButton[role="nav"]:checked {{ background-color: {t['card']}; color: {t['text']}; font-weight: 600; }}
    QFrame#sidebar QFrame#navIndicator {{ background-color: {t['accent']}; border-radius: 2px; }}
    QScrollArea#navScroll {{ background: transparent; border: none; }}
    QLabel#sidebarFooter {{ color: {t['muted']}; font-size: 11px; }}

    /* Page headers */
    QLabel#pageTitle {{ font-size: 22px; font-weight: 700; }}
    QLabel#pageSubtitle {{ color: {t['subtext']}; font-size: 13px; }}
    QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}

    /* Cards */
    QFrame[role="card"] {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 12px; }}
    QFrame[role="card"] QWidget {{ background-color: transparent; }}
    QFrame[role="card"] QPushButton {{ background-color: {t['input']}; }}
    QFrame[role="card"] QPushButton[role="primary"] {{ background-color: {t['accent']}; }}
    QFrame[role="card"] QPushButton[role="primary"]:disabled {{ background-color: {t['border']}; }}
    QFrame[role="card"] QLineEdit, QFrame[role="card"] QComboBox {{ background-color: {t['input']}; }}
    QFrame[role="card"] QProgressBar {{ background-color: {t['input']}; }}
    QFrame[role="card"] QTableWidget {{ background-color: {t['bg']}; }}
    QLabel#cardTitle {{ color: {t['subtext']}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
    QLabel#bigValue {{ font-size: 28px; font-weight: 700; }}
    QLabel#cardLine {{ color: {t['subtext']}; font-size: 12px; }}
    QLabel#muted {{ color: {t['muted']}; font-size: 12px; }}
    QLabel#good {{ color: {t['good']}; font-weight: 600; }}
    QLabel#warn {{ color: {t['warn']}; font-weight: 600; }}
    QLabel#bad {{ color: {t['bad']}; font-weight: 600; }}
    QFrame#notice {{ background-color: {t['card']}; border: 1px solid {t['border']};
                     border-left: 3px solid {t['accent']}; border-radius: 8px; }}
    QFrame#notice QWidget {{ background-color: transparent; }}

    /* Buttons */
    QPushButton {{ background-color: {t['input']}; color: {t['text']}; border: 1px solid {t['border']};
                   border-radius: 8px; padding: 7px 14px; }}
    QPushButton:hover {{ border-color: {t['subtext']}; }}
    QPushButton:disabled {{ color: {t['muted']}; border-color: {t['border']}; }}
    QPushButton[role="primary"] {{ background-color: {t['accent']}; color: {t['on_accent']}; border: none; font-weight: 600; }}
    QPushButton[role="primary"]:hover {{ background-color: {t['accent']}; border: 1px solid {t['text']}; }}
    QPushButton[role="primary"]:disabled {{ background-color: {t['border']}; color: {t['muted']}; }}
    QPushButton[role="danger"] {{ color: {t['bad']}; }}

    /* Inputs */
    QLineEdit, QComboBox, QSpinBox {{ background-color: {t['input']}; border: 1px solid {t['border']};
        border-radius: 8px; padding: 6px 8px; color: {t['text']}; }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {t['accent']}; }}
    QComboBox QAbstractItemView {{ background-color: {t['card']}; border: 1px solid {t['border']};
        selection-background-color: {t['card_hover']}; color: {t['text']}; }}
    QTextEdit, QPlainTextEdit {{ background-color: {t['card']}; border: 1px solid {t['border']};
        border-radius: 8px; color: {t['text']}; padding: 6px; }}
    QCheckBox {{ background: transparent; spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['muted']}; border-radius: 4px;
                            background-color: {t['input']}; }}
    QCheckBox::indicator:hover {{ border-color: {t['accent']}; }}
    QCheckBox::indicator:checked {{ background-color: {t['accent']}; border-color: {t['accent']}; }}
    QCheckBox::indicator:disabled {{ border-color: {t['border']}; }}

    /* Tables */
    QTableWidget {{ background-color: {t['card']}; alternate-background-color: {t['bg']};
        border: 1px solid {t['border']}; border-radius: 10px; gridline-color: {t['border']};
        color: {t['text']}; selection-background-color: {t['card_hover']}; selection-color: {t['text']}; }}
    QHeaderView::section {{ background-color: {t['sidebar']}; color: {t['subtext']}; padding: 8px;
        border: none; border-bottom: 1px solid {t['border']}; font-weight: 600; }}
    QTableCornerButton::section {{ background-color: {t['sidebar']}; border: none; }}

    /* Progress bars */
    QProgressBar {{ background-color: {t['input']}; border: none; border-radius: 4px; height: 8px;
        text-align: center; color: transparent; }}
    QProgressBar::chunk {{ background-color: {t['accent']}; border-radius: 4px; }}

    /* Scrollbars */
    QScrollArea {{ border: none; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 4px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QMessageBox {{ background-color: {t['card']}; }}
    """
