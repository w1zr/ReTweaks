"""About RETWEAKS (Tk port of ui/pages/about.py): chip logo, version, what's new, links, credits."""
import sys
import tkinter as tk
import webbrowser
from pathlib import Path

from PIL import Image, ImageTk

from core.version import APP_NAME, BRAND, __version__
from rt_pages.common import button_row, card, label

REPO_URL = "https://github.com/w1zr/ReTweaks"
GPL_URL = "https://www.gnu.org/licenses/gpl-3.0.html"
ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"

# Short, factual list (full notes are in release-notes/ on GitHub)
WHATS_NEW = [
    ("Welcome tour", "A short tour the first time you open v2.0: how RETWEAKS works, °C or °F, language, "
                     "automatic updates, tray and a desktop shortcut. Replay it from Settings."),
    ("Languages", "English, Español, Français, Deutsch and Português (Brasil), switchable at the top of Settings."),
    ("Search everything", "Search pages, settings and tweaks from the top bar (Ctrl+K)."),
    ("Temperatures, fans and RGB", "Live temperatures, fan speeds and fan curves, and fan + RAM lighting."),
    ("Crosshair overlay", "Built-in crosshairs, an editor, share codes and a gallery. F9 shows or hides it."),
    ("New browser", "Runs as its own program, so a browser problem can't close RETWEAKS."),
    ("Your settings carry over", "Settings and data from earlier versions are copied over once; the old folders "
                                 "are kept as a backup."),
    ("Still here", "Health Check, FPS overlay and FPS test, Display and stretched resolution, Network (DNS and "
                   "ping), Startup apps, Program rules with auto game mode, Cleanup, Snapshots, Fun tools, tray, "
                   "Start with Windows, updates and Discord status."),
]


class AboutPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        g["page_header"](tab, "RETWEAKS", "About", None)
        root = hub._scroll_area(tab)

        head = card(root, g)
        row = tk.Frame(head, bg=head.cget("bg"))
        row.pack(fill="x", padx=16, pady=14)
        try:
            img = Image.open(ASSETS / "chip-96.png").convert("RGBA").resize((88, 88), Image.LANCZOS)
            self._logo = ImageTk.PhotoImage(img, master=tab)
            tk.Label(row, image=self._logo, bg=row.cget("bg")).pack(side="left", anchor="n", padx=(0, 20))
        except Exception:
            self._logo = None
        col = tk.Frame(row, bg=row.cget("bg"))
        col.pack(side="left", fill="x", expand=True)
        tk.Label(col, text=BRAND, bg=col.cget("bg"), fg=g["FG"], font=(g["UI"], 22, "bold"), anchor="w").pack(fill="x")
        tk.Label(col, text=f"Version {__version__}", bg=col.cget("bg"), fg=g["MUTED"], font=(g["UI"], 10),
                 anchor="w").pack(fill="x")
        tk.Label(col, text="Windows PC diagnostics and optimization. Real readings, reversible tweaks, honest "
                           "results.", bg=col.cget("bg"), fg=g["FG"], font=(g["UI"], 10), anchor="w",
                 justify="left", wraplength=640).pack(fill="x", pady=(4, 8))
        links = tk.Frame(col, bg=col.cget("bg"))
        links.pack(fill="x")
        from core.version import WEBSITE
        g["RButton"](links, "Website", lambda: webbrowser.open(WEBSITE), kind="default").pack(
            side="left", padx=(0, 6))
        from core.version import DISCORD_INVITE
        g["RButton"](links, "Discord", lambda: webbrowser.open(DISCORD_INVITE), kind="default").pack(
            side="left", padx=(0, 6))
        g["RButton"](links, "Open on GitHub", lambda: webbrowser.open(REPO_URL), kind="default").pack(
            side="left", padx=(0, 6))
        g["RButton"](links, "All release notes", lambda: webbrowser.open(REPO_URL + "/releases"),
                     kind="default").pack(side="left")

        news = card(root, g, f"What's new in {__version__}")
        for title, text in WHATS_NEW:
            label(news, title, g, 11, bold=True, pady=(8, 0))
            label(news, text, g, 10, g["MUTED"])
        tk.Frame(news, height=8, bg=news.cget("bg")).pack()

        cr = card(root, g, "License")
        label(cr, "RETWEAKS by Ryder (w1zr).", g, 10)
        label(cr, f"{APP_NAME} is free software under the GNU General Public License version 3 only "
                  "(GPL-3.0-only): you may use, share and change it under that license. The full text is the "
                  "LICENSE file in the source code. Third-party parts (for example Microsoft WebView2) keep their "
                  "own licenses.", g, 9, g["MUTED"])
        bar = button_row(cr, g)
        g["RButton"](bar, "Read the GPL-3.0", lambda: webbrowser.open(GPL_URL), kind="ghost").pack(side="left")

        note = card(root, g, "Good to know")
        label(note, "RETWEAKS isn't code-signed, so Windows SmartScreen or antivirus may warn when you download it. "
                    "CPU and motherboard temperatures and most fan control need the free PawnIO driver (button on "
                    "Hardware & cooling → Temperatures).", g, 10,
              pady=(4, 12))
        import rt_i18n
        label(note, rt_i18n.NOTE, g, 9, g["MUTED"], pady=(0, 12))
