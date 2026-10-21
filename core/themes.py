# C:\pc_optimizer\core\themes.py

THEMES = {
    "Midnight": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#888888", "text": "#f1f1f1", "subtext": "#aaaaaa"},
    "Pink": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#e91e63", "text": "#f1f1f1", "subtext": "#aaaaaa"},
    "Blue": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#2196f3", "text": "#f1f1f1", "subtext": "#aaaaaa"},
    "Purple": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#9c27b0", "text": "#f1f1f1", "subtext": "#aaaaaa"},
    "Red": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#f44336", "text": "#f1f1f1", "subtext": "#aaaaaa"},
    "Green": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#4caf50", "text": "#f1f1f1", "subtext": "#aaaaaa"},
    "Cyan": {"bg": "#121212", "sidebar": "#181818", "card": "#181818", "border": "#2a2a2a", "accent": "#00bcd4", "text": "#f1f1f1", "subtext": "#aaaaaa"}
}

def get_stylesheet(theme_name="Midnight", custom_accent=None):
    t = THEMES.get(theme_name, THEMES["Midnight"]).copy()
    if custom_accent:
        t["accent"] = custom_accent

    return f"""
        QMainWindow {{ background-color: {t['bg']}; color: {t['text']}; }}
        QWidget {{ background-color: {t['bg']}; color: {t['text']}; font-family: 'Segoe UI', sans-serif; font-size: 13px; }}
        QFrame#sidebar {{ background-color: {t['sidebar']}; border-right: 1px solid {t['border']}; }}
        QPushButton.nav-btn {{
            background-color: transparent; color: {t['subtext']}; border: 1px solid transparent;
            border-radius: 8px; padding: 10px 14px; font-weight: 500; text-align: left; font-size: 13px;
        }}
        QPushButton.nav-btn:hover {{ background-color: #222222; color: {t['text']}; border: 1px solid {t['border']}; }}
        QPushButton.nav-btn:checked {{
            background-color: #2a2a2a; color: {t['text']}; font-weight: bold; border-left: 4px solid {t['accent']};
        }}
        QPushButton.action-btn {{
            background-color: {t['accent']}; color: #ffffff; border: none; border-radius: 8px; padding: 8px 16px; font-weight: bold; font-size: 13px;
        }}
        QPushButton.action-btn:hover {{ opacity: 0.9; border: 1px solid #ffffff; }}
        QFrame.card {{ background-color: {t['card']}; border: 1px solid {t['border']}; border-radius: 14px; padding: 18px; }}
        QLabel {{ color: {t['text']}; background: transparent; }}
        QTableWidget {{ background-color: #161616; border: 1px solid {t['border']}; border-radius: 10px; gridline-color: #222222; color: {t['text']}; selection-background-color: #2c2c2c; }}
        QHeaderView::section {{ background-color: #1c1c1c; color: {t['subtext']}; padding: 8px; border: 1px solid {t['border']}; font-weight: bold; }}
        QProgressBar {{ background-color: #1a1a1a; border: 1px solid {t['border']}; border-radius: 6px; text-align: center; color: {t['text']}; font-weight: bold; height: 16px; }}
        QProgressBar::chunk {{ background-color: {t['accent']}; border-radius: 4px; }}
        QLineEdit, QComboBox {{ background-color: #181818; border: 1px solid {t['border']}; border-radius: 8px; padding: 6px; color: {t['text']}; }}
        QTextEdit {{ background-color: #181818; border: 1px solid {t['border']}; color: {t['text']}; border-radius: 8px; }}
    """