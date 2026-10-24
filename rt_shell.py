"""App shell for RETWEAKS v2: everything RETWEAKS v1.5-1.6 did around the window.

- One copy at a time (winutil.single_instance mutex). A second launch talks to the running copy over the
  same named pipe the Qt RETWEAKS used (\\\\.\\pipe\\RETWEAKS_show_<user>, commands "ver" -> "ver X",
  "show" -> "ok", "quit" -> "bye"), so it also works against RETWEAKS v1.5.1-1.6: same version -> bring
  it back (with the startup animation if it was in the tray); different version -> ask, quit it
  normally and start; no answer -> it's stuck: offer "Close it and start".
- A running copy of the app under its previous name is offered to be closed first; data from earlier
  versions is carried over (core.rename_migration) before any setting is read.
- System tray (setting tray_on_close, default on): closing hides to the tray; Quit really ends the app.
- Update check (setting check_updates) with an update bar at the top of every page (Update now / Later).
- Discord status, auto game mode / background calming services, and a 6 s exit watchdog.
"""
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from core.version import APP_NAME, BRAND, __version__

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"
IS_WINDOWS = sys.platform == "win32"


# ------------------------------------------------------------------ named pipe (same protocol as v1.5.1+)
def pipe_name(prefix="RETWEAKS_show_"):
    import getpass
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return prefix + "".join(c for c in user if c.isalnum())[:40]


def talk(command, timeout=1.5, name=None):
    """Sends one command to the running copy; returns its reply (bytes, stripped) or None if it
    doesn't answer in time. Never blocks longer than `timeout`."""
    if not IS_WINDOWS:
        return None
    path = r"\\.\pipe\\" + (name or pipe_name())
    box = {}

    def go():
        try:
            with open(path, "r+b", buffering=0) as f:
                f.write(command + b"\n")
                box["reply"] = f.read(64).strip()
        except OSError:
            box["reply"] = None

    t = threading.Thread(target=go, daemon=True)
    t.start()
    t.join(timeout)
    return box.get("reply")


class PipeServer:
    """Answers ver/show/quit from later launches. Commands are handed to the Tk thread via a queue."""

    def __init__(self, hub, name=None):
        self.hub, self.name = hub, name or pipe_name()
        self.q = queue.Queue()
        self.stopped = False
        self.thread = None
        if IS_WINDOWS:
            self.thread = threading.Thread(target=self._serve, name="RetweaksPipe", daemon=True)
            self.thread.start()
        hub.after(100, self._poll)

    def _serve(self):
        try:
            import win32pipe
            import win32file
        except ImportError:
            return
        path = r"\\.\pipe\\" + self.name
        while not self.stopped:
            try:
                h = win32pipe.CreateNamedPipe(path, win32pipe.PIPE_ACCESS_DUPLEX,
                                              win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_WAIT,
                                              win32pipe.PIPE_UNLIMITED_INSTANCES, 512, 512, 0, None)
            except Exception:
                return
            try:
                win32pipe.ConnectNamedPipe(h, None)
                if self.stopped:
                    break
                _, data = win32file.ReadFile(h, 64)
                cmd = bytes(data).strip()
                reply = threading.Event()
                box = {}
                self.q.put((cmd, box, reply))
                reply.wait(3.0)
                if box.get("out"):
                    win32file.WriteFile(h, box["out"])
                    win32file.FlushFileBuffers(h)
            except Exception:
                pass
            finally:
                try:
                    win32pipe.DisconnectNamedPipe(h)
                    win32file.CloseHandle(h)
                except Exception:
                    pass

    def _poll(self):
        try:
            while True:
                cmd, box, ev = self.q.get_nowait()
                if cmd.startswith(b"ver"):
                    box["out"] = b"ver " + __version__.encode() + b"\n"
                elif cmd.startswith(b"show"):
                    reopen(self.hub)
                    box["out"] = b"ok\n"
                elif cmd.startswith(b"quit"):
                    box["out"] = b"bye\n"
                    self.hub.after(50, lambda: quit_app(self.hub))
                ev.set()
        except queue.Empty:
            pass
        except tk.TclError:
            return
        if not self.stopped:
            try:
                self.hub.after(100, self._poll)
            except tk.TclError:
                pass

    def stop(self):
        self.stopped = True
        if IS_WINDOWS:
            talk(b"noop", 0.3, self.name)       # wake the blocking ConnectNamedPipe so the thread ends


# ------------------------------------------------------------------ before the window exists
def _ask(title, text, yes, no, icon="question"):
    root = tk.Tk()
    root.withdraw()
    try:
        return messagebox.askyesno(title, text + f"\n\nYes: {yes}\nNo: {no}", icon=icon, parent=root)
    finally:
        root.destroy()


def _tell(text, error=False):
    root = tk.Tk()
    root.withdraw()
    try:
        (messagebox.showwarning if error else messagebox.showinfo)(APP_NAME, text, parent=root)
    finally:
        root.destroy()


def _wait_for_lock(seconds):
    from core.winutil import single_instance
    end = time.time() + seconds
    while True:
        lock = single_instance()
        if lock is not None or time.time() >= end:
            return lock
        time.sleep(0.15)


def acquire_single_instance():
    """Returns the instance lock, or exits after bringing the running copy to the front."""
    from core.winutil import single_instance, other_instances, close_other_instances
    lock = single_instance()
    if lock is not None:
        return lock
    reply = talk(b"ver", 1.0)
    theirs = reply[4:].decode("utf-8", "replace").strip() if reply and reply.startswith(b"ver ") else None
    if theirs == __version__:
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)      # ASFW_ANY: let it take the foreground
        except Exception:
            pass
        if (talk(b"show", 2.0) or b"").startswith(b"ok"):
            sys.exit(0)
    if theirs and theirs != __version__:
        if not _ask(APP_NAME, f"{APP_NAME} v{theirs} is already running (this is v{__version__}).",
                    f"close v{theirs} and open v{__version__}", f"keep v{theirs}"):
            talk(b"show", 2.0)
            sys.exit(0)
        lock = _wait_for_lock(10) if talk(b"quit", 2.0) == b"bye" else None
        if lock is None:
            close_other_instances()
            lock = _wait_for_lock(4)
        if lock is None:
            _tell(f"{APP_NAME} v{theirs} didn't close. Right-click its tray icon, choose Quit, then open "
                  f"{APP_NAME} again.", error=True)
            sys.exit(0)
        return lock
    if not other_instances():
        _tell(f"{APP_NAME} is already running. Check the taskbar or the system tray (it may have started "
              "minimized with Windows).")
        sys.exit(0)
    if not _ask(APP_NAME, f"Another {APP_NAME} is running but isn't responding (an older version, or it's "
                "stuck in the background).", "close it and start", "cancel", icon="warning"):
        sys.exit(0)
    ok, msg = close_other_instances()
    lock = _wait_for_lock(3) if ok else None
    if lock is None:
        _tell(msg if not ok else "The other copy closed, but Windows hasn't released its lock yet. "
              f"Open {APP_NAME} again in a few seconds.", error=True)
        sys.exit(0)
    return lock


def close_legacy_copy():
    """An older version (previous app name) still running: offer to close it before its data is copied."""
    from core import rename_migration as rm
    if not rm.legacy_processes():
        return
    if not _ask(APP_NAME, "An older version of RETWEAKS is still running. Your settings move over to "
                "this version.", f"close it and open {APP_NAME}", "cancel"):
        sys.exit(0)
    talk(b"quit", 2.0, rm.OLD_SHOW_SERVER_PREFIX + pipe_name()[len("RETWEAKS_show_"):])
    end = time.time() + 10
    while rm.legacy_processes() and time.time() < end:
        time.sleep(0.2)
    left = rm.legacy_processes()
    if left:
        try:
            import psutil
            for p in left:
                p.kill()
            psutil.wait_procs(left, timeout=5)
        except Exception:
            pass
    if rm.legacy_processes():
        _tell("The older version didn't close. Right-click its tray icon, choose Quit, then open "
              f"{APP_NAME} again.", error=True)
        sys.exit(0)


def migrate():
    from core.rename_migration import migrate_all
    try:
        return migrate_all()
    except Exception as e:
        return [f"Could not carry over old data: {e}"]


# ------------------------------------------------------------------ window behaviour
def reopen(hub):
    """Opened again while running: from the tray / minimized play the startup animation (owner choice
    2026-10-22) and fade in; a window already on screen is just brought to the front."""
    intro = getattr(hub, "_reopen_intro", None)
    if intro is not None and not intro.closed:
        return
    try:
        hidden = hub.state() in ("withdrawn", "iconic")
    except tk.TclError:
        return
    if not hidden:
        bring_to_front(hub)
        return
    from appearance import Intro
    g = hub._g

    def done():
        hub._reopen_intro = None
        bring_to_front(hub)
    hub._reopen_intro = Intro(hub, {k: g[k] for k in ("BG", "ACC")}, status="Ready", on_done=done)
    hub._reopen_intro.ready()
    # safety net: whatever happens to the animation, the window ends up visible after 8 s
    hub.after(8000, lambda: (not hub._reopen_intro or hub._reopen_intro.closed) or hub._reopen_intro.finish())


def bring_to_front(hub):
    try:
        hub.attributes("-alpha", 1.0)
        hub.deiconify()
        hub.lift()
        hub.focus_force()
        hub.attributes("-topmost", True)
        hub.after(200, lambda: hub.attributes("-topmost", False))
    except tk.TclError:
        pass


class Tray:
    """Notification-area icon (pystray). Menu: Open RETWEAKS / Quit RETWEAKS."""

    def __init__(self, hub):
        self.hub = hub
        self.icon = None
        self.error = None
        # pystray calls its menu items on its own thread; Tk may only be used from the Tk thread,
        # so the menu only queues the action and _poll (on the Tk thread) carries it out.
        self.actions = queue.Queue()
        self._poll()

    def _poll(self):
        try:
            while True:
                a = self.actions.get_nowait()
                if a == "open":
                    reopen(self.hub)
                elif a == "quit":
                    quit_app(self.hub)
                    return
                elif isinstance(a, tuple) and a[0] == "menu":
                    self.show_menu(a[1], a[2])
        except queue.Empty:
            pass
        except tk.TclError:
            return
        try:
            self.hub.after(150, self._poll)
        except tk.TclError:
            pass

    def start(self):
        if self.icon is not None:
            return True
        try:
            import pystray
            from PIL import Image
            img = Image.open(ASSETS / "icon.ico")          # owner's pick for the tray (2026-10-22)
            menu = pystray.Menu(
                pystray.MenuItem(f"Open {APP_NAME}", lambda: self.actions.put("open"), default=True),
                pystray.MenuItem(f"Quit {APP_NAME}", lambda: self.actions.put("quit")))
            self.icon = self._icon_class(pystray)(APP_NAME, img, APP_NAME, menu)
            self.icon.run_detached()
            return True
        except Exception as e:
            self.icon = None
            self.error = f"{type(e).__name__}: {e}"
            return False

    def _icon_class(self, pystray):
        """On Windows: left-click opens RETWEAKS and right-click opens RETWEAKS' own themed, rounded menu
        (rt_traymenu) instead of the standard Windows menu, which can't be themed (owner feedback
        2026-10-22). Anything unexpected falls back to pystray's normal behaviour and menu."""
        base = pystray.Icon
        if sys.platform != "win32" or not hasattr(base, "_on_notify"):
            return base
        actions = self.actions

        class ThemedMenuIcon(base):
            def _on_notify(icon, wparam, lparam):
                try:
                    if lparam == 0x0202:                     # WM_LBUTTONUP
                        actions.put("open")
                        return
                    if lparam == 0x0205:                     # WM_RBUTTONUP
                        import ctypes
                        from ctypes import wintypes
                        pt = wintypes.POINT()
                        ctypes.windll.user32.GetCursorPos(ctypes.byref(pt))
                        actions.put(("menu", pt.x, pt.y))
                        return
                except Exception:
                    pass
                return base._on_notify(icon, wparam, lparam)
        return ThemedMenuIcon

    def show_menu(self, x, y):
        from rt_traymenu import TrayMenu
        hub = self.hub

        def settings():
            reopen(hub)
            tab = getattr(hub, "rt_tabs", {}).get("Settings")
            if tab is not None:
                hub.show_tab(tab)
        TrayMenu(hub, x, y, [(f"Open {APP_NAME}", lambda: reopen(hub)), ("Settings", settings), None,
                             (f"Quit {APP_NAME}", lambda: quit_app(hub))])

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None

    def notify(self, title, text):
        try:
            if self.icon is not None:
                self.icon.notify(text, title)
        except Exception:
            pass


def tray_active(hub):
    return bool(hub.settings.get("tray_on_close", True) and hub.shell.tray.icon is not None)


def request_close(hub):
    """Window close button / Alt+F4: hide to the tray when that's on, otherwise quit."""
    if tray_active(hub):
        hub.withdraw()
        if not hub.shell.tray_tip_shown:
            hub.shell.tray_tip_shown = True
            hub.shell.tray.notify(f"{APP_NAME} is still running",
                                  "Volume lock and auto game mode keep working. Right-click the tray icon and "
                                  f"choose Quit {APP_NAME} to close it.")
        return
    quit_app(hub)


def quit_app(hub):
    """Really closes: hides the window and tray icon at once (so Quit feels instant), stops every service,
    then ends the Tk loop; main() then ends the process right away (no waiting on stray threads).
    How long each step took goes into crash.log, so a slow step can be found."""
    if getattr(hub, "_quitting", False):
        return
    hub._quitting = True
    shell = hub.shell
    try:
        hub.withdraw()
        hub.update_idletasks()
    except tk.TclError:
        pass
    try:
        if shell.tray.icon is not None:
            shell.tray.icon.visible = False
    except Exception:
        pass
    steps = []

    def step(name, fn):
        t = time.monotonic()
        try:
            fn()
        except Exception as e:
            name += f" (failed: {type(e).__name__})"
        steps.append(f"{name} {time.monotonic() - t:.2f}s")

    for key, page in list(getattr(hub, "rt_pages", {}).items()):
        if page is not None and hasattr(page, "close"):
            step(key, page.close)

    def rules_stop():
        from rt_pages import rules
        rules.stop_services(hub)
    step("program rules", rules_stop)
    if shell.discord is not None:
        step("discord", shell.discord.stop)
    step("tray", shell.tray.stop)
    step("single-instance pipe", shell.server.stop)
    try:
        import rt_crashlog
        rt_crashlog.write("QUIT", "Quit requested. Shutdown steps: " + ", ".join(steps) + "\n")
    except Exception:
        pass
    try:
        hub.destroy()
    except tk.TclError:
        pass


class Shell:
    def __init__(self, hub, g, migration_log=()):
        self.hub, self.g = hub, g
        hub.shell = self
        hub._g = g
        self.tray_tip_shown = False
        self.tray = Tray(hub)
        self.discord = None
        self.server = PipeServer(hub)
        hub.request_close = lambda: request_close(hub)
        hub.protocol("WM_DELETE_WINDOW", hub.request_close)
        for line in migration_log or []:
            hub.log_action("Rename to RETWEAKS", "Carry over old data", line)
        self.set_tray(hub.settings.get("tray_on_close", True))
        self._start_services()
        self._build_update_bar()
        if hub.settings.get("check_updates", True):
            hub.after(3000, self.check_updates)

    # tray
    def set_tray(self, on):
        on = bool(on)
        self.hub.settings["tray_on_close"] = on
        self.hub.save_settings()
        if on:
            ok = self.tray.start()
            if not ok:
                self.hub.log_action("Tray", "Show tray icon", "Failed", self.tray.error or "")
            return ok
        self.tray.stop()
        return True

    # services
    def _start_services(self):
        hub = self.hub
        try:
            from rt_pages import rules
            rules.start_services(hub)
        except Exception as e:
            hub.log_action("Program rules", "Start auto game mode", "Failed", str(e))
        try:
            from core.discord_rpc import DiscordPresence
            self.discord = DiscordPresence()
            self.discord.configure(hub.settings.get("discord_status", True),
                                   hub.settings.get("discord_show_game", True))
            self.discord.start()
        except Exception as e:
            self.discord = None
            hub.log_action("Discord status", "Start", "Failed", str(e))

    # update bar (RETWEAKS v1.4+: at the top of every page)
    def _build_update_bar(self):
        hub, g = self.hub, self.g
        bar = tk.Frame(hub.content, bg=g["PANEL"], highlightthickness=1, highlightbackground=g["LINE"])
        self.bar = bar
        self.bar_text = tk.Label(bar, text="", bg=g["PANEL"], fg=g["FG"], font=(g["UI"], 10), anchor="w")
        self.bar_text.pack(side="left", fill="x", expand=True, padx=14, pady=8)
        self.bar_later = g["RButton"](bar, "Later", self.hide_update_bar, kind="ghost")
        self.bar_later.pack(side="right", padx=(0, 10), pady=6)
        self.bar_now = g["RButton"](bar, "Update now", self.update_now, kind="primary")
        self.bar_now.pack(side="right", padx=6, pady=6)
        self.update_info = None

    def show_update_bar(self, info):
        self.update_info = info
        self.bar_text.configure(text=f"{BRAND} {info['version']} is available (you have {__version__}).")
        if not self.bar.winfo_ismapped():
            packed = [w for w in self.hub.content.pack_slaves() if w is not self.bar]
            opts = {"before": packed[0]} if packed else {}
            self.bar.pack(side="top", fill="x", padx=(26, 12), pady=(12, 0), **opts)

    def hide_update_bar(self):
        self.bar.pack_forget()

    def check_updates(self, done=None):
        from core import updater
        from rt_pages.common import run_bg

        def finished(info):
            if isinstance(info, Exception):
                info = {"error": str(info)}
            if info.get("available") and info.get("exe_url") and info.get("sha_url"):
                self.show_update_bar(info)
            if done:
                done(info)
        run_bg(self.hub, updater.check_for_update, finished)

    def update_now(self):
        from core import updater
        from rt_pages.common import run_bg
        info = self.update_info
        if not info:
            return
        if not updater.can_self_update():
            messagebox.showinfo(APP_NAME, "In-app updates only work in RETWEAKS.exe. When running from source, "
                                "use git pull.", parent=self.hub)
            return
        if not messagebox.askyesno(APP_NAME, f"Download {info['version']} from GitHub, check it, and restart "
                                   f"{APP_NAME}?\n\nYour settings are kept. The current version is saved as "
                                   "RETWEAKS.old.exe.", parent=self.hub):
            return
        self.bar_now.set_enabled(False)
        self.bar_text.configure(text=f"Downloading {info['version']}\u2026")

        def got(res):
            if isinstance(res, Exception):
                res = (False, str(res))
            ok, payload = res if isinstance(res, tuple) else (False, "Unexpected result")
            if not ok:
                self.bar_text.configure(text=f"Update failed: {payload}")
                self.bar_now.set_enabled(True)
                return
            self.bar_text.configure(text=f"Installing and restarting {APP_NAME}\u2026")
            ok2, msg = updater.install_and_restart(payload)
            if ok2:
                quit_app(self.hub)
            else:
                self.bar_text.configure(text=f"Update failed: {msg}")
                self.bar_now.set_enabled(True)
        run_bg(self.hub, updater.download_update, got, info)


def exit_watchdog(code=0):
    """Leave the process for sure: if shutdown hangs (e.g. a .NET/WebView2 thread), end it after 6 s so no
    invisible copy keeps the instance lock or locks the .exe."""
    t = threading.Timer(6.0, os._exit, args=(int(code or 0),))
    t.daemon = True
    t.start()
