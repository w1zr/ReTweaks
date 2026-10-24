"""RETWEAKS Settings (Tk port of ui/pages/settings.py): appearance, Discord status, behaviour, updates,
temperatures & fans help, about / report a problem. Same setting keys as RETWEAKS v1.x; nothing is reset.
Appearance holds everything (owner request 2026-10-22): theme, custom accent, the base app's background accent,
the theme maker, sidebar header and dashboard banner. The base app's separate Appearance page is gone."""
import re
import tkinter as tk
import webbrowser
from urllib.parse import quote

import appearance as ap
from core import autostart, updater
from core.version import APP_NAME, __version__
from rt_pages.common import NA, button_row, card, label, run_bg

HEADER_STYLES = [("Small chip + wordmark", "chip"), ("Wordmark only", "wordmark")]
BANNER_STYLES = [("CPU cores (live)", "cores"), ("Load wave (live)", "wave"), ("Circuit traces", "circuit"),
                 ("Galaxy", "galaxy"), ("Off", "off")]
BANNER_COLORS = [("Original", "original"), ("Black & white", "mono"), ("Theme accent", "accent"),
                 ("Custom (HEX)", "custom")]
INTERVALS = {"Every second": 1.0, "Every 2 seconds": 2.0, "Every 5 seconds": 5.0}
LHM_URL = "https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases"
REPO_URL = "https://github.com/w1zr/ReTweaks"
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _interval_seconds(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 1.0
    return v / 1000.0 if v > 30 else v


class SettingsPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self.update_info = None
        self._lhm_job = None
        self._discord_job = None
        s = hub.settings
        g["page_header"](tab, "RETWEAKS", "Settings", "Appearance, behavior, updates and help. Changes are saved "
                         "right away; nothing you set before is reset.")
        root = hub._scroll_area(tab)

        # ---------------- Language (first, one click per language; see rt_pages/language_card.py)
        from rt_pages.language_card import LanguageCard
        self.language_card = LanguageCard(hub, root, g)

        # ---------------- Appearance
        b = card(root, g, "Appearance")
        row = self._row(b)
        self._lbl(row, "Theme")
        self.theme = g["RSelect"](row, ap.theme_names(), width=200, command=self.set_theme)
        self.theme.set(hub.theme_name)
        self.theme.pack(side="left", padx=(8, 20))
        hub._theme_selectors = getattr(hub, "_theme_selectors", [])
        hub._theme_selectors.append(self.theme)
        hub.theme_selector = self.theme
        self._lbl(row, "Custom accent (HEX)")
        self.hex = tk.StringVar(value=s.get("custom_accent") or "")
        e = g["REntry"](row, self.hex, width_px=110)
        e.pack(side="left", padx=8)
        e.entry.bind("<Return>", lambda ev: self.apply_hex())
        g["RButton"](row, "Apply", self.apply_hex, kind="default").pack(side="left", padx=(0, 6))
        g["RButton"](row, "Use theme color", self.clear_hex, kind="ghost").pack(side="left")
        self.hex_msg = label(b, "", g, 9, g["MUTED"])
        row = self._row(b)
        self._lbl(row, "Sidebar header")
        self.header = g["RSelect"](row, [t for t, _ in HEADER_STYLES], width=200, command=self.set_header)
        self.header.set(HEADER_STYLES[1][0] if s.get("header_style") == "wordmark" else HEADER_STYLES[0][0])
        self.header.pack(side="left", padx=(8, 20))
        self._lbl(row, "Dashboard banner")
        cur = s.get("banner_style", "cores")
        self.banner = g["RSelect"](row, [t for t, _ in BANNER_STYLES], width=180, command=self.set_banner)
        self.banner.set(next((t for t, k in BANNER_STYLES if k == cur), BANNER_STYLES[0][0]))
        self.banner.pack(side="left", padx=8)
        # banner colour (v2.0.6): settings banner_color / banner_custom_color
        row = self._row(b)
        self._lbl(row, "Banner color")
        cur_col = s.get("banner_color", "original")
        self.banner_color = g["RSelect"](row, [t for t, _ in BANNER_COLORS], width=180, command=self.set_banner_color)
        self.banner_color.set(next((t for t, k in BANNER_COLORS if k == cur_col), BANNER_COLORS[0][0]))
        self.banner_color.pack(side="left", padx=(8, 20))
        self._lbl(row, "Custom banner color (HEX)")
        self.banner_hex = tk.StringVar(value=s.get("banner_custom_color") or "")
        e = g["REntry"](row, self.banner_hex, width_px=110)
        e.pack(side="left", padx=8)
        e.entry.bind("<Return>", lambda ev: self.apply_banner_hex())
        g["RButton"](row, "Apply", self.apply_banner_hex, kind="default").pack(side="left")
        self.banner_hex_msg = label(b, "", g, 9, g["MUTED"])
        label(b, "Banners only animate while the Dashboard is open and RETWEAKS isn't minimized. CPU cores and Load "
                 "wave show real live readings; Circuit and Galaxy are decoration.", g, 9, g["MUTED"])
        from rt_pages.background_controls import BackgroundControls
        self.background_controls = BackgroundControls(self, b, g)
        # RETWEAKS theme maker + share codes (RET1- / RYT1-)
        from rt_pages.theme_maker_tk import ThemeMaker
        hub.theme_maker = ThemeMaker(hub, b, g)

        dep = card(root, g, 'Feature dependencies',
                   'Missing WebView2, PawnIO and PresentMon install when their feature is opened. Lively installs when you use animated wallpaper actions. Windows may ask for administrator permission or a restart.')
        self.auto_dependencies = tk.BooleanVar(value=bool(s.get('automatic_dependencies', True)))
        g['RCheck'](dep, 'Automatically install missing feature software', self.auto_dependencies,
                    lambda:self.set_setting('automatic_dependencies', bool(self.auto_dependencies.get()))).pack(anchor='w',padx=16,pady=(4,12))

        # ---------------- Discord status (v1.4.3)
        d = card(root, g, "Discord status")
        self.discord_on = tk.BooleanVar(value=bool(s.get("discord_status", True)))
        self.discord_game = tk.BooleanVar(value=bool(s.get("discord_show_game", True)))
        g["RCheck"](d, "Show RETWEAKS on my Discord status", self.discord_on, self.discord_changed).pack(
            anchor="w", padx=16, pady=2)
        self.discord_game_cb = g["RCheck"](d, "Show which game I'm playing", self.discord_game,
                                           self.discord_changed)
        self.discord_game_cb.pack(anchor="w", padx=16, pady=2)
        label(d, "Get Retweaks opens the ReTweaks website. Discord shows this button to other people, not on your own profile.", g, 9,
              wrap=640, pady=2)
        self.discord_line = label(d, "", g, 10)
        label(d, "Shows the ReTweaks logo, Optimizing with RETWEAKS and Windows PC tweaks. Requires Discord on this PC.", g, 9,
              g["MUTED"], pady=(0, 12))

        # ---------------- Behavior
        be = card(root, g, "Behavior")
        row = self._row(be)
        self._lbl(row, "Refresh")
        cur = _interval_seconds(s.get("interval", 1.0))
        self.interval = g["RSelect"](row, list(INTERVALS), width=170, command=self.set_interval)
        self.interval.set(next((k for k, v in INTERVALS.items() if v == cur), "Every second"))
        self.interval.pack(side="left", padx=(8, 20))
        self._lbl(row, "Temperature")
        from rt_pages.unit_switch import UnitSwitch
        self.unit = UnitSwitch(row, hub, g,
                               on_change=lambda u: hub.log_action("Settings", "Temperature unit °" + u, "Applied"))
        self.unit.pack(side="left", padx=(8, 20))
        self._lbl(row, "Open on")
        self.start_page = g["RSelect"](row, [s.get("startup_page", "Dashboard")], width=190,
                                       command=lambda t: self.set_setting("startup_page", t))
        self.start_page.set(s.get("startup_page", "Dashboard"))
        self.start_page.pack(side="left", padx=8)
        self.autostart = tk.BooleanVar(value=False)
        self.autostart_cb = g["RCheck"](be, "Start RETWEAKS when I sign in to Windows", self.autostart,
                                        self.toggle_autostart, disabled=not autostart.available())
        self.autostart_cb.pack(anchor="w", padx=16, pady=(8, 2))
        if not autostart.available():
            label(be, "Start with Windows is only available in RETWEAKS.exe.", g, 9, g["MUTED"])
        self.minimized = tk.BooleanVar(value=bool(s.get("start_minimized", True)))
        g["RCheck"](be, "Start minimized when started with Windows", self.minimized, self.toggle_minimized).pack(
            anchor="w", padx=16, pady=2)
        self.tray = tk.BooleanVar(value=bool(s.get("tray_on_close", True)))
        g["RCheck"](be, "Keep running in the system tray when I close the window", self.tray,
                    self.toggle_tray).pack(anchor="w", padx=16, pady=2)
        label(be, "Closing the window hides RETWEAKS next to the clock instead of quitting, so the volume lock and "
                  "auto game mode keep working. Right-click the tray icon → Quit RETWEAKS to close it fully.",
              g, 9, g["MUTED"])
        self.beh_msg = label(be, "", g, 9, g["MUTED"], pady=(0, 12))
        wbar = button_row(be, g)
        g["RButton"](wbar, "Show the welcome tour again", self.show_welcome, kind="default").pack(side="left")

        # ---------------- Updates
        u = card(root, g, "Updates")
        label(u, f"You have {APP_NAME} v{__version__}.", g, 10)
        self.auto_check = tk.BooleanVar(value=bool(s.get("check_updates", True)))
        g["RCheck"](u, "Check for updates when RETWEAKS starts (asks before downloading anything)",
                    self.auto_check, lambda: self.set_setting("check_updates", bool(self.auto_check.get()))).pack(
            anchor="w", padx=16, pady=2)
        self.auto_update = tk.BooleanVar(value=bool(s.get("auto_update", False)))
        g["RCheck"](u, "Automatic updates: download and check new versions, then ask before restarting",
                    self.auto_update, self.toggle_auto_update).pack(anchor="w", padx=16, pady=2)
        bar = button_row(u, g)
        self.b_check = g["RButton"](bar, "Check now", self.check_updates, kind="default")
        self.b_check.pack(side="left", padx=(0, 6))
        self.b_install = g["RButton"](bar, "Download and install", self.install_update, kind="primary")
        self.b_page = g["RButton"](bar, "Open release page", self.open_release_page, kind="ghost")
        self.bar = bar
        self.upd_msg = label(u, "", g, 10, pady=(0, 12))

        # ---------------- Temperatures & fans
        t = card(root, g, "Temperatures & fans")
        self.lhm_status = label(t, "LibreHardwareMonitor: checking…", g, 10)
        label(t, "Windows has no built-in way for apps to read CPU temperature, fan speeds or motherboard sensors. "
                 "That needs a hardware driver, which RETWEAKS does not install. RETWEAKS has LibreHardwareMonitor "
                 "0.9.6 built in (Temperatures, Fan control pages); it reads CPU and motherboard sensors once you "
                 "install the free PawnIO driver from its official page. Or run your own copy:\n"
                 "1. Download LibreHardwareMonitor (free, open source).\n"
                 "2. Run it as administrator and leave it open (it can start minimized).\n"
                 "3. In LibreHardwareMonitor, turn on Options → Remote Web Server → Run (keep the default "
                 "port 8085).\n"
                 "4. RETWEAKS finds it within a few seconds and shows temperatures and fans.\n\n"
                 "Step 3 is needed for LibreHardwareMonitor 0.9.5 and newer. Older versions (0.9.4 and before) are "
                 "detected without it. NVIDIA GPU temperature works without LibreHardwareMonitor, through the "
                 "NVIDIA driver.", g, 9, g["MUTED"])
        bar = button_row(t, g)
        g["RButton"](bar, "Download LibreHardwareMonitor", lambda: webbrowser.open(LHM_URL),
                     kind="default").pack(side="left")
        from rt_pages.cooling import PAWNIO_URL
        g["RButton"](bar, "PawnIO download page \u2197", lambda: webbrowser.open(PAWNIO_URL),
                     kind="ghost").pack(side="left", padx=(8, 0))
        rt = getattr(hub, "rt_tabs", {})
        if "Temperatures" in rt:
            g["RButton"](bar, "Open Temperatures", lambda: hub.show_tab(hub.rt_tabs["Temperatures"]),
                         kind="ghost").pack(side="left", padx=(8, 0))

        # ---------------- About
        a = card(root, g, "About")
        from core.version import WEBSITE
        label(a, f"{APP_NAME} v{__version__}. Website: {WEBSITE}  ·  Open source (GPL-3.0): {REPO_URL}", g, 10)
        bar = button_row(a, g)
        g["RButton"](bar, "Website", lambda: webbrowser.open(WEBSITE), kind="default").pack(side="left", padx=(0, 6))
        g["RButton"](bar, "Open on GitHub", lambda: webbrowser.open(REPO_URL), kind="default").pack(
            side="left", padx=(0, 6))
        g["RButton"](bar, "Report a problem", self.report_problem, kind="default").pack(side="left", padx=(0, 6))
        if "About" in getattr(hub, "rt_tabs", {}):
            g["RButton"](bar, "About RETWEAKS", lambda: hub.show_tab(hub.rt_tabs["About"]), kind="ghost").pack(
                side="left")
        label(a, "Report a problem copies your hardware report (no personal info) and opens a new GitHub issue. "
                 "Nothing is sent automatically.", g, 9, g["MUTED"], pady=(0, 12))

    # ------------------------------------------------------------ small helpers
    def _row(self, parent):
        r = tk.Frame(parent, bg=parent.cget("bg"))
        r.pack(fill="x", padx=16, pady=6)
        return r

    def _lbl(self, row, text):
        tk.Label(row, text=text, bg=row.cget("bg"), fg=self.g["MUTED"], font=(self.g["UI"], 9)).pack(side="left")

    def set_setting(self, key, value):
        self.hub.settings[key] = value
        self.hub.save_settings()

    # ------------------------------------------------------------ appearance
    def set_theme(self, name):
        self.hub.apply_theme(name)
        self.hub.log_action("Settings", f"Theme {name}", "Applied")

    def apply_hex(self):
        text = self.hex.get().strip()
        if text and not text.startswith("#"):
            text = "#" + text
        if not HEX_RE.match(text):
            self.hex_msg.configure(text="Enter a color like #3b82f6 (6 hex digits).", fg="#e07e81")
            return False
        text = text.lower()
        self.hex.set(text)
        self.hex_msg.configure(text="", fg=self.g["MUTED"])
        self.set_setting("custom_accent", text)
        ap.set_custom_accent(text)
        self.hub.apply_theme(self.hub.theme_name)
        return True

    def clear_hex(self):
        self.hex.set("")
        self.hex_msg.configure(text="")
        self.set_setting("custom_accent", None)
        ap.set_custom_accent(None)
        self.hub.apply_theme(self.hub.theme_name)

    def set_header(self, text):
        key = dict(HEADER_STYLES).get(text, "chip")
        self.set_setting("header_style", key)
        nav = getattr(self.hub, "sidebar_nav", None)
        if nav is not None:
            nav.apply_header_style(key)

    def set_banner(self, text):
        key = dict(BANNER_STYLES).get(text, "cores")
        self.set_setting("banner_style", key)
        dash = (getattr(self.hub, "rt_pages", {}) or {}).get("Dashboard")
        if dash is not None and hasattr(dash, "on_banner_changed"):
            dash.on_banner_changed(key)

    def _banner_color_changed(self):
        dash = (getattr(self.hub, "rt_pages", {}) or {}).get("Dashboard")
        if dash is not None and hasattr(dash, "on_banner_color_changed"):
            dash.on_banner_color_changed()

    def set_banner_color(self, text):
        key = dict(BANNER_COLORS).get(text, "original")
        if key == "custom" and not HEX_RE.match(self.hub.settings.get("banner_custom_color") or ""):
            self.banner_hex_msg.configure(text="Enter a color like #ffffff, then press Apply.", fg=self.g["MUTED"])
        else:
            self.banner_hex_msg.configure(text="", fg=self.g["MUTED"])
        self.set_setting("banner_color", key)
        self._banner_color_changed()

    def apply_banner_hex(self):
        text = self.banner_hex.get().strip()
        if text and not text.startswith("#"):
            text = "#" + text
        if not HEX_RE.match(text):
            self.banner_hex_msg.configure(text="Enter a color like #ffffff (6 hex digits).", fg="#e07e81")
            return
        self.banner_hex.set(text)
        self.banner_hex_msg.configure(text="", fg=self.g["MUTED"])
        self.hub.settings["banner_custom_color"] = text
        self.banner_color.set(dict((k, t) for t, k in BANNER_COLORS)["custom"])
        self.set_setting("banner_color", "custom")
        self._banner_color_changed()

    def set_interval(self, text):
        self.set_setting("interval", INTERVALS.get(text, 1.0))
        # the live service reads the setting on every sample; pages that show it update their text now
        for page in list((getattr(self.hub, "rt_pages", {}) or {}).values()):
            fn = getattr(page, "on_interval_changed", None)
            if callable(fn):
                try:
                    fn(INTERVALS.get(text, 1.0))
                except Exception:
                    pass

    def set_unit(self, text):
        """°C / °F for the whole app at once (Dashboard, Temperatures, Fan control, Snapshots, Quick start)."""
        self.unit.choose("F" if "F" in str(text).upper() else "C")

    def on_temp_unit(self, unit):
        """Called by settings_store.set_temp_unit when the unit is changed anywhere (e.g. the Temperatures page)."""
        self.unit.draw()

    # ------------------------------------------------------------ discord
    def discord_changed(self):
        on, show = bool(self.discord_on.get()), bool(self.discord_game.get())
        self.set_setting("discord_status", on)
        self.set_setting("discord_show_game", show)
        presence = getattr(getattr(self.hub, "shell", None), "discord", None)
        if presence is not None:
            presence.configure(on, show)
            if on:
                presence.start()
        self.hub.log_action("Discord status", "On" if on else "Off", "OK")
        self.refresh_discord()

    def refresh_discord(self):
        presence = getattr(getattr(self.hub, "shell", None), "discord", None)
        if presence is None:
            self.discord_line.configure(text="Status: Discord status isn't available in this session.")
            return
        from core.discord_rpc import status_text
        self.discord_line.configure(text="Status: " + status_text(presence.status))

    # ------------------------------------------------------------ behavior
    def toggle_autostart(self):
        on = bool(self.autostart.get())
        self.beh_msg.configure(text="Updating…")

        def done(res):
            if isinstance(res, Exception):
                res = (False, str(res))
            ok, msg = res
            self.beh_msg.configure(text=msg)
            self.hub.log_action("Start with Windows", "On" if on else "Off", "Success" if ok else "Failed",
                                "" if ok else msg)
            if not ok:
                self.autostart.set(not on)
        run_bg(self.hub, autostart.set_enabled, done, on, bool(self.minimized.get()))

    def toggle_minimized(self):
        self.set_setting("start_minimized", bool(self.minimized.get()))
        if self.autostart.get():            # re-create the sign-in task with/without --minimized
            self.toggle_autostart()

    def show_welcome(self):
        import rt_welcome
        rt_welcome.show(self.hub, replay=True)

    def toggle_auto_update(self):
        on = bool(self.auto_update.get())
        self.set_setting("auto_update", on)
        if on and not self.auto_check.get():
            self.auto_check.set(True)
            self.set_setting("check_updates", True)
        if on:
            import rt_autoupdate
            rt_autoupdate.start(self.hub, delay=500)

    def toggle_tray(self):
        on = bool(self.tray.get())
        shell = getattr(self.hub, "shell", None)
        ok = shell.set_tray(on) if shell is not None else False
        if shell is None:
            self.set_setting("tray_on_close", on)
        if on and not ok:
            self.beh_msg.configure(text="Windows didn't give RETWEAKS a tray icon, so closing the window still quits.")
        else:
            self.beh_msg.configure(text="Closing the window now keeps RETWEAKS running in the tray." if on else
                                   "Closing the window now quits RETWEAKS.")
        self.hub.log_action("Settings", "Keep running in the tray " + ("on" if on else "off"), "OK" if ok else "Failed")

    # ------------------------------------------------------------ updates
    def check_updates(self):
        self.b_check.set_enabled(False)
        self.upd_msg.configure(text="Checking GitHub…")
        shell = getattr(self.hub, "shell", None)
        if shell is not None:
            shell.check_updates(self._show_update)
        else:
            run_bg(self.hub, updater.check_for_update, self._show_update)

    def _show_update(self, info):
        self.b_check.set_enabled(True)
        if isinstance(info, Exception):
            info = {"error": str(info)}
        if not isinstance(info, dict) or "error" in info:
            self.upd_msg.configure(text=(info or {}).get("error", "Update check failed.") if isinstance(info, dict)
                                   else "Update check failed.")
            return
        self.update_info = info
        if info.get("available"):
            self.b_page.pack(side="left", padx=(0, 6))
            if updater.can_download_release() and info.get("exe_url") and info.get("sha_url"):
                self.upd_msg.configure(text=f"{info['version']} is available.")
                self.b_install.pack(side="left", padx=(0, 6), before=self.b_page)
            else:
                self.upd_msg.configure(text=f"{info['version']} is available. Download RETWEAKS.exe from the "
                                            "release page.")
        else:
            self.upd_msg.configure(text=f"You're up to date (latest release is {info.get('version') or NA}).")

    def install_update(self):
        shell = getattr(self.hub, "shell", None)
        if shell is None or not self.update_info:
            return
        shell.update_info = self.update_info
        shell.show_update_bar(self.update_info)
        shell.update_now()

    def open_release_page(self):
        if self.update_info and self.update_info.get("page"):
            webbrowser.open(self.update_info["page"])

    # ------------------------------------------------------------ about
    def report_problem(self):
        try:
            from core.report import build_report, report_to_text
            text = report_to_text(build_report(getattr(self.hub, "rt_static", None) or {},
                                               getattr(self.hub, "rt_last_sample", None) or {},
                                               getattr(self.hub, "rt_sources", None) or {}))
        except Exception as e:
            text = f"(Hardware report unavailable: {e})"
        self.hub.clipboard_clear()
        self.hub.clipboard_append(text)
        body = ("**What happened?**\n\n\n**What did you expect?**\n\n\n"
                "**Hardware report:** RETWEAKS copied it to your clipboard. Paste it below (Ctrl+V).\n\n")
        webbrowser.open(f"{REPO_URL}/issues/new?title={quote(f'[v{__version__}] ')}&body={quote(body)}")

    # ------------------------------------------------------------ page lifecycle
    def on_shown(self):
        nav = getattr(getattr(self.hub, "sidebar_nav", None), "targets", {})
        names = list(nav) or ["Dashboard"]
        cur = self.hub.settings.get("startup_page", "Dashboard")
        self.start_page.values = names
        self.start_page.set(cur if cur in names else "Dashboard")
        self.theme.values = ap.theme_names()
        self.theme.set(self.hub.theme_name)
        self.background_controls.refresh()
        if autostart.available():
            run_bg(self.hub, autostart.is_enabled, lambda r: self.autostart.set(r is True))
        self.check_lhm()
        self._tick_discord()

    def on_hidden(self):
        if self._discord_job:
            try:
                self.hub.after_cancel(self._discord_job)
            except tk.TclError:
                pass
            self._discord_job = None

    def _tick_discord(self):
        self.refresh_discord()
        self._discord_job = self.hub.after(2000, self._tick_discord)

    def check_lhm(self):
        def read():
            from core.sensors_lhm import LhmReader
            r = LhmReader().read()
            return (r or {}).get("source")

        def done(src):
            if isinstance(src, Exception) or not src:
                self.lhm_status.configure(text="LibreHardwareMonitor: no sensor readings yet (built-in monitor "
                                               "starting, or PawnIO not installed)")
            else:
                self.lhm_status.configure(text=f"{src}: connected ✔")
        run_bg(self.hub, read, done)

    def close(self):
        self.on_hidden()
