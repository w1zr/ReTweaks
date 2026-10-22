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

# Full-UI themes (v1.4.1, owner choice): each recolors the background, sidebar, cards, borders,
# text and accent. "logo" is the chip/logo color: grey/white on dark themes, dark on Light.
FULL_THEMES = {
    "Super Black": {"bg": "#000000", "sidebar": "#000000", "card": "#0a0a0a", "card_hover": "#141414",
                    "input": "#101010", "border": "#1f1f1f", "text": "#f2f2f2", "subtext": "#a3a3a3",
                    "muted": "#6b6b6b", "good": "#3fb950", "warn": "#d29922", "bad": "#f85149",
                    "accent": "#a3a3a3"},
    "Galaxy": {"bg": "#0c0a1d", "sidebar": "#100d24", "card": "#171334", "card_hover": "#1e1940",
               "input": "#1d1840", "border": "#2b2452", "text": "#eeebff", "subtext": "#aaa4d8",
               "muted": "#726c9f", "good": "#4ade80", "warn": "#fbbf24", "bad": "#f87171",
               "accent": "#8b5cf6", "stars": True},
    "Ocean": {"bg": "#0a1220", "sidebar": "#0d1628", "card": "#111d33", "card_hover": "#16243d",
              "input": "#15233d", "border": "#1f3050", "text": "#e6f0ff", "subtext": "#9db2cf",
              "muted": "#647a99", "good": "#34d399", "warn": "#fbbf24", "bad": "#f87171",
              "accent": "#22d3ee"},
    "Ember": {"bg": "#120e0c", "sidebar": "#17120f", "card": "#1e1814", "card_hover": "#261f1a",
              "input": "#251d18", "border": "#352820", "text": "#f5ece6", "subtext": "#c2ad9f",
              "muted": "#857266", "good": "#4ade80", "warn": "#facc15", "bad": "#f87171",
              "accent": "#f97316"},
    "Forest": {"bg": "#0b120f", "sidebar": "#0e1713", "card": "#131e19", "card_hover": "#18261f",
               "input": "#17251f", "border": "#22342b", "text": "#e7f3ec", "subtext": "#a1b9ad",
               "muted": "#677d72", "good": "#4ade80", "warn": "#fbbf24", "bad": "#f87171",
               "accent": "#10b981"},
    "Light": {"bg": "#f4f5f7", "sidebar": "#eceef1", "card": "#ffffff", "card_hover": "#f0f2f5",
              "input": "#e9ecf0", "border": "#d6dae0", "text": "#16181c", "subtext": "#4b5260",
              "muted": "#7a8190", "good": "#15803d", "warn": "#a16207", "bad": "#b91c1c",
              "accent": "#4b5563", "logo": "#16181c", "light": True},
}
THEMES.update(FULL_THEMES)


# ---------------------------------------------------------------- theme maker (v1.4.3)

import base64 as _b64
import json as _json
import re as _re

EDITABLE = [("bg", "Background"), ("sidebar", "Sidebar"), ("card", "Cards"), ("border", "Borders"),
            ("text", "Text"), ("subtext", "Secondary text"), ("accent", "Accent"),
            ("good", "Good"), ("warn", "Warning"), ("bad", "Error")]
EDITABLE_KEYS = [k for k, _ in EDITABLE]
SHARE_PREFIX = "RET1-"
OLD_SHARE_PREFIXES = ("RYT1-",)   # codes shared before the rename still import
_HEX = _re.compile(r"^#[0-9a-fA-F]{6}$")
_custom = {}          # name -> full palette, filled from settings by MainWindow


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(v))) for v in rgb)


def mix(a, b, t):
    """Blend color a toward b by t (0..1)."""
    ra, rb = _rgb(a), _rgb(b)
    return _hex([x + (y - x) * t for x, y in zip(ra, rb)])


def luminance(h):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG contrast ratio, 1..21. 4.5 or more is comfortable for normal text."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def build_palette(colors):
    """Full theme from the 10 editable colors (the rest are derived so everything stays consistent)."""
    c = {k: colors[k].lower() for k in EDITABLE_KEYS}
    light = luminance(c["bg"]) > 0.4
    c["card_hover"] = mix(c["card"], c["text"], 0.06)
    c["input"] = mix(c["card"], c["text"], 0.05)
    c["muted"] = mix(c["subtext"], c["bg"], 0.35)
    c["logo"] = c["text"] if light else "#e8eaed"
    if light:
        c["light"] = True
    return c


def validate_colors(colors):
    """Returns (ok, message). All 10 colors must be #rrggbb."""
    if not isinstance(colors, dict):
        return False, "The theme has no colors."
    for k in EDITABLE_KEYS:
        v = colors.get(k)
        if not isinstance(v, str) or not _HEX.match(v):
            return False, f"'{dict(EDITABLE)[k]}' must be a color like #1a2b3c."
    return True, ""


def clean_theme_name(name):
    name = " ".join(str(name or "").split())[:32]
    return name


def export_code(name, colors):
    """A short code people can paste into RETWEAKS to get the same theme."""
    data = {"n": clean_theme_name(name), "c": {k: colors[k].lower() for k in EDITABLE_KEYS}}
    raw = _json.dumps(data, separators=(",", ":")).encode("utf-8")
    return SHARE_PREFIX + _b64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def parse_code(code):
    """Returns (ok, name_or_message, colors). Never raises on bad input."""
    code = "".join(str(code or "").split())
    prefix = next((p for p in (SHARE_PREFIX,) + OLD_SHARE_PREFIXES if code.startswith(p)), None)
    if prefix is None or len(code) > 2000:
        return False, f"That isn't a RETWEAKS theme code (it should start with {SHARE_PREFIX}).", None
    body = code[len(prefix):]
    try:
        data = _json.loads(_b64.urlsafe_b64decode(body + "=" * (-len(body) % 4)).decode("utf-8"))
    except Exception:
        return False, "The theme code is damaged or incomplete.", None
    if not isinstance(data, dict):
        return False, "The theme code is damaged or incomplete.", None
    colors = data.get("c")
    ok, msg = validate_colors(colors)
    if not ok:
        return False, msg, None
    name = clean_theme_name(data.get("n")) or "Shared theme"
    return True, name, {k: colors[k].lower() for k in EDITABLE_KEYS}


def set_custom_themes(saved):
    """saved: {name: {10 editable colors}} from settings. Bad entries are skipped, never deleted."""
    _custom.clear()
    for name, colors in (saved or {}).items():
        if name in THEMES or not validate_colors(colors)[0]:
            continue
        _custom[name] = build_palette(colors)


def custom_theme_names():
    return list(_custom)


def editable_colors(theme_name):
    """The 10 editable colors of any theme (built-in or custom), as a starting point."""
    t = get_theme(theme_name)
    return {k: t[k] for k in EDITABLE_KEYS}


def _on_accent(hex_color):
    """Black or white text, whichever reads better on the accent color."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#0f1115" if (0.299 * r + 0.587 * g + 0.114 * b) > 150 else "#ffffff"


def get_theme(theme_name="Midnight", custom_accent=None):
    t = dict(THEMES.get(theme_name) or _custom.get(theme_name) or THEMES["Midnight"])
    if custom_accent:
        t["accent"] = custom_accent
    t["on_accent"] = _on_accent(t["accent"])
    t.setdefault("logo", "#e8eaed")      # chip/logo color: grey/white except on Light
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
    QMenu {{ background-color: {t['card']}; color: {t['text']}; border: 1px solid {t['border']};
             border-radius: 8px; padding: 4px; font-size: 13px; }}
    QMenu::item {{ background: transparent; padding: 5px 22px 5px 10px; border-radius: 5px; min-width: 140px; }}
    QMenu::item:selected {{ background-color: {t['card_hover']}; color: {t['text']}; }}
    QMenu::item:disabled {{ color: {t['subtext']}; }}
    QMenu::separator {{ height: 1px; background: {t['border']}; margin: 3px 6px; }}
    QMenu::indicator {{ width: 14px; height: 14px; left: 8px; }}
    QPushButton[role="nav"] {{ background: transparent; color: {t['subtext']}; border: none;
        border-radius: 8px; padding: 7px 12px; text-align: left; font-size: 13px; }}
    QPushButton[role="nav"]:hover {{ background-color: {t['card_hover']}; color: {t['text']}; }}
    QPushButton[role="nav"]:checked {{ background-color: {t['card']}; color: {t['text']}; font-weight: 600; }}
    QFrame#updateBar {{ background-color: {t['card']}; border-bottom: 1px solid {t['border']};
        border-left: 3px solid {t['accent']}; }}
    QFrame#updateBar QLabel {{ background-color: transparent; }}
    QLabel#updateBarText {{ color: {t['text']}; font-weight: 600; }}
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
