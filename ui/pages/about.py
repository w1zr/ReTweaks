# ui/pages/about.py
"""About RYTWEAKS and what's new in this version."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout

from core.version import APP_NAME, __version__
from ui.widgets.brand import ChipLogo
from ui.widgets.common import Card, Page, label

REPO_URL = "https://github.com/w1zr/rytweaks"

# Short, factual list; the full notes are in release-notes/v1.4.md on GitHub
WHATS_NEW = [
    ("Browser", "A browser with RYTWEAKS's own design on Microsoft's Edge engine: tabs, private tabs, "
                "bookmarks, history, downloads, and your choice of search engine."),
    ("Microphone and volume lock", "The Audio mixer now controls your microphone too, and can lock the speaker or "
                                   "mic volume so apps can't change it."),
    ("Stretched resolution", "Set a stretched desktop resolution like 1720×1080 on Display & drivers (like NVIDIA "
                             "Control Panel), with a 15-second Keep test and one-click Back to native."),
    ("Tray", "Optionally keep RYTWEAKS running in the system tray when you close the window (Settings → Behavior)."),
    ("Built-in FPS overlay", "The in-game overlay reads Windows' own frame events, so it no longer needs "
                             "PresentMon. Nothing is injected into the game."),
    ("44 new tweaks and search", "Now 53 individual tweaks in five groups (Gaming, Privacy, Interface, "
                                 "Services, Maintenance) with a search box. Each one explains what it does and "
                                 "its trade-off, and has its own Undo."),
    ("Presets", "Esports, Max FPS, Balanced, Low-end PC, High quality, Ultra quality, Streamer and Privacy. "
                "On the Tweaks page a preset ticks its tweaks; untick or add any, then apply only what you selected."),
    ("Essentials", "Clear the DNS cache, clear the Windows Update download cache (shows the size first) "
                   "and check and repair system files (SFC), from the Tweaks page."),
    ("Theme maker", "Pick every color yourself, preview it live, save it, and share it as a code."),
    ("Discord status", "Show \"Optimizing with RYTWEAKS\" or the game you're playing on Discord (off until "
                       "you turn it on in Settings)."),
    ("Themes", "Seven full-UI themes: Midnight, Super Black, Galaxy, Ocean, Ember, Forest and Light. "
               "Pick one in Settings → Appearance."),
    ("Dashboard banner", "CPU cores (live load per thread), Load wave (live), Circuit traces or Galaxy. "
                         "Change or turn it off in Settings."),
    ("Header and icon", "The chip logo next to the wordmark (or wordmark only, in Settings) and a sharper "
                        "icon for the .exe file."),
    ("New look", "Chip logo and startup animation, new app icon, line icons in the sidebar, "
                 "a sliding accent bar and smooth page fades."),
    ("Health Check", "One scan of startup apps, temp files, power plan, disk health, free space, "
                     "pending restarts, Windows Update, Game Mode, refresh rate and RAM, with a Fix "
                     "button where RYTWEAKS can help."),
    ("FPS test", "Real average FPS and 1% / 0.1% lows measured with Intel PresentMon, with saved runs "
                 "you can compare."),
    ("In-game FPS overlay", "Live FPS, 1% low and frame time over games in borderless or windowed "
                            "fullscreen. Nothing is injected into the game."),
    ("Display & drivers", "Shows whether each monitor runs at its highest refresh rate, and your "
                          "GPU driver version and age."),
    ("Audio mixer", "Master volume, output devices and per-app volume."),
    ("Auto clicker", "Configurable clicks with hotkeys and an emergency stop."),
    ("AI Assistant", "Ask Gemini about your PC with your own free API key (18+, Google's terms apply)."),
    ("Fun tools", "Mouse polling-rate test, clicks-per-second test and reaction-time test."),
    ("More", "Background calming while you game, sensor logging to CSV, a disk space analyzer, "
             "Storage Explorer upgrades, scheduled tasks in Startup apps, and renaming, duplicating, "
             "exporting and importing game presets."),
]


class AboutPage(Page):
    title = "About"
    subtitle = ""

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        head = Card()
        row = QHBoxLayout()
        row.setSpacing(20)
        row.addWidget(ChipLogo(88), 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(4)
        name = label(APP_NAME, "brand")
        col.addWidget(name)
        col.addWidget(label(f"Version {__version__}", "muted"))
        col.addWidget(label("Windows PC diagnostics and optimization. Real readings, reversible tweaks, "
                            "honest results.", "cardLine", wrap=True))
        links = QHBoxLayout()
        gh = QPushButton("Open on GitHub")
        gh.clicked.connect(lambda: self._open(REPO_URL))
        rel = QPushButton("All release notes")
        rel.clicked.connect(lambda: self._open(REPO_URL + "/releases"))
        links.addWidget(gh)
        links.addWidget(rel)
        links.addStretch(1)
        col.addSpacing(6)
        col.addLayout(links)
        row.addLayout(col, 1)
        head.body.addLayout(row)
        self.content.addWidget(head)

        news = Card(f"What's new in {__version__}")
        for title, text in WHATS_NEW:
            news.body.addWidget(label(title, "sectionTitle"))
            news.body.addWidget(label(text, "cardLine", wrap=True))
        self.content.addWidget(news)

        note = Card("Good to know")
        note.body.addWidget(label("RYTWEAKS isn't code-signed, so Windows SmartScreen or antivirus may warn "
                                  "when you download it. Temperatures and fans need LibreHardwareMonitor "
                                  "running (see Settings).", "cardLine", wrap=True))
        self.content.addWidget(note)
        self.finish()

    def _open(self, url):
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        QDesktopServices.openUrl(QUrl(url))
