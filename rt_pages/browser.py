# rt_pages/browser.py
"""Browser page: the RETWEAKS Browser (the base app's v1.5 browser with RETWEAKS branding; owner request
2026-10-22: the v1.5 browser with RETWEAKS branding).

The browser itself is ai/EmbeddedBrowser.exe (embedded_browser.py), its own program shown inside this page,
edge to edge like the base app's website tabs. Before, Microsoft's Edge engine ran inside RETWEAKS' own process
(pythonnet), and a native fault there closed the whole app ("browser crashes when you click on it"). Now a
browser failure only stops the browser: this page says so and offers Restart browser.

Kept from the RETWEAKS browser: tabs, private tabs, bookmarks (the New tab shortcuts), history, downloads,
search engines (Google, DuckDuckGo, Brave Search, Bing, Startpage, Custom), download folder / ask where to
save, clear site data, print, zoom, fullscreen video. Data: bookmarks and history stay in
%APPDATA%\\RETWEAKS\\browser.json (core/browser_data.py) and the settings browser_search_engine,
browser_custom_search, browser_download_dir, browser_ask_download stay in config.json; the browser program
reports changes and this page saves them. Cookies and sign-ins: %LOCALAPPDATA%\\RETWEAKS\\Browser (same
folder as before, so sign-ins carry over). The browser starts the first time this page is opened.
"""
import json
import os
import queue
import time
import tkinter as tk
import webbrowser
from pathlib import Path

from core import browser_data as bd

WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
SETTING_KEYS = ("browser_search_engine", "browser_custom_search", "browser_download_dir", "browser_ask_download")
DEFAULT_SHORTCUTS = [("Google", "https://www.google.com/"), ("YouTube", "https://www.youtube.com/"),
                     ("Discord", "https://discord.com/app"), ("GitHub", "https://github.com/"),
                     ("Steam", "https://store.steampowered.com/")]
AUTO_RESTART_GAP = 30.0        # restart by itself once; a second stop within this many seconds asks the user


def profile_dir():
    return Path(bd.user_data_dir())


class BrowserPage:
    def __init__(self, hub, tab, g):
        self.hub, self.tab, self.g = hub, tab, g
        self.data = bd.BrowserData()
        self.events = queue.Queue()
        self.bridge = None
        self.closed = False
        self.visible = False
        self.last_stop = 0.0
        self.failed = False            # the browser reported it can't start: keep that message, don't loop
        self._theme_sig = None
        self._job = None
        tab.configure(bg=g["BG"])
        self.status = tk.Label(tab, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 9), anchor="w", padx=12)
        self.frame = tk.Frame(tab, bg=g["BG"], highlightthickness=0, takefocus=0)
        self.frame.pack(fill="both", expand=True)
        # Shown inside the frame when the browser isn't running (the browser window covers it otherwise).
        self.overlay = tk.Frame(self.frame, bg=g["BG"])
        self.o_title = tk.Label(self.overlay, text="", bg=g["BG"], fg=g["FG"], font=(g["UI"], 15, "bold"))
        self.o_title.pack(pady=(0, 6))
        self.o_text = tk.Label(self.overlay, text="", bg=g["BG"], fg=g["MUTED"], font=(g["UI"], 10),
                               wraplength=560, justify="center")
        self.o_text.pack(pady=(0, 14))
        row = tk.Frame(self.overlay, bg=g["BG"])
        row.pack()
        self.b_restart = g["RButton"](row, "Restart browser", self.restart, kind="primary")
        self.b_restart.pack(side="left", padx=4)
        self.b_runtime = g["RButton"](row, "Get WebView2 Runtime ↗", lambda: webbrowser.open(WEBVIEW2_URL),
                                      kind="ghost")
        self._show_overlay("Starting the browser…", "", buttons=False)
        self._migrate_once()
        if self.data.load_note:
            self._set_status(self.data.load_note)
        tab.bind("<Destroy>", lambda e: self.close() if e.widget is tab else None, add="+")
        self._poll()

    # ------------------------------------------------------------ data shared with the browser program
    def _migrate_once(self):
        """First run of this browser: bookmarks = RETWEAKS bookmarks + the base app browser shortcuts (copied into
        %LOCALAPPDATA%\\RETWEAKS\\Browser\\shortcuts.json by the base app migration), or the default five
        shortcuts if there are none. Runs once (setting browser_v15_merged); nothing is deleted."""
        s = getattr(self.hub, "settings", {})
        if s.get("browser_v15_merged"):
            return
        items = [{"name": b["title"], "url": b["url"]} for b in self.data.bookmarks]
        try:
            raw = json.loads((profile_dir() / "shortcuts.json").read_text(encoding="utf-8"))
            for it in raw if isinstance(raw, list) else []:
                if isinstance(it, dict) and isinstance(it.get("url"), str):
                    items.append({"name": it.get("name") or "", "url": it["url"]})
        except (OSError, ValueError):
            pass
        if not items:
            items = [{"name": n, "url": u} for n, u in DEFAULT_SHORTCUTS]
        self.data.set_bookmarks(items)
        s["browser_v15_merged"] = True
        self._save_settings()

    def _cfg(self):
        return bd.clean_settings(getattr(self.hub, "settings", {}))

    def _engines(self, cfg):
        out = [{"name": n, "template": t} for n, t in bd.SEARCH_ENGINES.items()]
        if bd.valid_custom_search(cfg["browser_custom_search"])[0]:
            out.append({"name": bd.CUSTOM, "template": cfg["browser_custom_search"].strip()})
        return out

    def settings_payload(self):
        cfg = self._cfg()
        return {"engines": self._engines(cfg), "engine": cfg["browser_search_engine"],
                "customSearch": cfg["browser_custom_search"], "downloadPrompt": cfg["browser_ask_download"],
                "downloadFolder": cfg["browser_download_dir"]}

    def payload(self):
        d = self.settings_payload()
        d["bookmarks"] = [{"name": b["title"], "url": b["url"]} for b in self.data.bookmarks]
        d["history"] = self.data.history[-1000:]
        return d

    def colors(self):
        g = self.g
        return {k: g[k] for k in ("BG", "PANEL", "FG", "MUTED", "LINE", "ACC")}

    def _save_settings(self):
        try:
            self.hub.save_settings()
        except Exception:
            pass

    # ------------------------------------------------------------ page shown / hidden
    def on_shown(self):
        self.visible = True
        try:                                   # full-size, like the base app's website tabs
            self.tab.pack_configure(padx=0, pady=0)
        except tk.TclError:
            pass
        if self.bridge is None:
            from embedded_browser import EmbeddedBrowser
            self.bridge = EmbeddedBrowser(self.frame, self.colors, self.events, data=self.payload)
        if not self.bridge.running():
            self.tab.update_idletasks()
            self.bridge.start()
        else:
            self.bridge.send({"op": "data", **self.settings_payload()})
            self.bridge.send({"op": "visibility", "visible": True})
        self._check_theme()

    def on_hidden(self):
        self.visible = False
        if self.bridge is not None:
            self.bridge.send({"op": "visibility", "visible": False})

    # ------------------------------------------------------------ events from the browser (Tk thread)
    def _poll(self):
        self._job = None
        if self.closed:
            return
        try:
            while True:
                self.handle(self.events.get_nowait())
        except queue.Empty:
            pass
        except tk.TclError:
            return
        self._check_theme()
        try:
            self._job = self.tab.after(100, self._poll)
        except tk.TclError:
            pass

    def handle(self, d):
        kind = d.get("type")
        if kind in ("ready", "loaded"):
            self.failed = False
            self._hide_overlay()
            self._set_status("")
            if self.bridge is not None:
                self.bridge.send({"op": "visibility", "visible": self.visible})
        elif kind == "error":
            msg = d.get("message") or "The browser couldn't start."
            self.failed = True
            self._show_overlay("The browser can't start", msg, buttons=True, runtime=True)
            self._log("Start the browser", "Failed", msg)
        elif kind == "stopped":
            if self.failed:
                return                 # it already said why it can't start; Restart browser is on screen
            now = time.monotonic()
            if now - self.last_stop > AUTO_RESTART_GAP and self.visible:
                self.last_stop = now
                self._show_overlay("Restarting the browser…", "It stopped unexpectedly. RETWEAKS is fine.",
                                   buttons=False)
                self.tab.after(600, self.restart)
            else:
                self.last_stop = now
                self._show_overlay("The browser stopped", "RETWEAKS is still running. Your bookmarks and history "
                                   "are saved.", buttons=True)
            self._log("Browser", "Stopped", d.get("message", ""))
        elif kind == "bookmarks":
            self.data.set_bookmarks(d.get("items") or [])
        elif kind == "visit":
            if isinstance(d.get("url"), str):
                self.data.add_history(d.get("title") or "", d["url"])
        elif kind == "title":
            if isinstance(d.get("url"), str):
                self.data.update_title(d["url"], d.get("title") or "")
        elif kind == "clear-history":
            n = self.data.clear_history()
            self._log("Clear browser history", "Success", f"{n} entries")
        elif kind == "setting":
            self._apply_setting(d.get("key"), d.get("value"))

    def _apply_setting(self, key, value):
        if key not in SETTING_KEYS:
            return
        s = self.hub.settings
        if key == "browser_search_engine":
            if value not in bd.SEARCH_ENGINES and not (value == bd.CUSTOM and
                                                       bd.valid_custom_search(s.get("browser_custom_search"))[0]):
                return
        elif key == "browser_custom_search":
            value = (value or "").strip()
            if value and not bd.valid_custom_search(value)[0]:
                return
        elif key == "browser_ask_download":
            value = bool(value)
        elif key == "browser_download_dir":
            value = value if isinstance(value, str) else ""
        s[key] = value
        self._save_settings()

    # ------------------------------------------------------------ theme
    def _check_theme(self):
        sig = tuple(self.colors().values())
        if sig != self._theme_sig:
            self._theme_sig = sig
            g = self.g
            for w in (self.tab, self.frame, self.overlay, self.o_title, self.o_text, self.status):
                try:
                    w.configure(bg=g["BG"])
                except tk.TclError:
                    pass
            self.o_title.configure(fg=g["FG"])
            self.o_text.configure(fg=g["MUTED"])
            self.status.configure(fg=g["MUTED"])
            if self.bridge is not None and self.bridge.running():
                self.bridge.update_theme()

    # ------------------------------------------------------------ overlay / status
    def _show_overlay(self, title, text, buttons=True, runtime=False):
        self.o_title.configure(text=title)
        self.o_text.configure(text=text)
        if buttons:
            self.b_restart.pack(side="left", padx=4)
        else:
            self.b_restart.pack_forget()
        if runtime:
            self.b_runtime.pack(side="left", padx=4)
        else:
            self.b_runtime.pack_forget()
        self.overlay.place(relx=0.5, rely=0.42, anchor="center")
        self.overlay.lift()

    def _hide_overlay(self):
        self.overlay.place_forget()

    def overlay_shown(self):
        return bool(self.overlay.winfo_manager())

    def _set_status(self, text):
        if text:
            self.status.configure(text=text)
            if not self.status.winfo_manager():
                self.status.pack(fill="x", before=self.frame)
        else:
            self.status.pack_forget()

    def _log(self, what, result, detail=""):
        try:
            self.hub.log_action("Browser", what, result, detail if result != "Success" else "")
        except Exception:
            pass

    # ------------------------------------------------------------ actions
    def restart(self):
        if self.closed:
            return
        self.failed = False
        self._show_overlay("Starting the browser…", "", buttons=False)
        if self.bridge is None:
            self.on_shown()
            return
        self.bridge.restart()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self._job:
            try:
                self.tab.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None
        if self.bridge is not None:
            self.bridge.close()

    shutdown = close
