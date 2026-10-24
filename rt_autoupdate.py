"""Automatic updates (owner choice 2026-10-22, welcome tour / setting `auto_update`).

ON: shortly after start RETWEAKS checks GitHub (the same check as the update bar, rt_shell.Shell.check_updates),
downloads the new RETWEAKS.exe, verifies it against the release's SHA-256 file (core.updater.download_update),
then asks before restarting into it (core.updater.install_and_restart + the normal Quit). Saying "Later" keeps
the usual Update now bar. OFF: only the update bar (check_updates setting), as before.
From source (v2.0.6) the released, verified RETWEAKS.exe is saved in %LOCALAPPDATA%\RETWEAKS\app and started
instead (core.updater.install_update); the source folder is never changed. Never installs without asking."""
import tkinter as tk
from tkinter import messagebox

from core.version import APP_NAME

DELAY_MS = 4000


def start(hub, delay=DELAY_MS):
    if getattr(hub, "_autoupdate_started", False):
        return False
    if not hub.settings.get("auto_update"):
        return False
    hub._autoupdate_started = True
    hub.after(delay, lambda: _check(hub))
    return True


def _check(hub):
    shell = getattr(hub, "shell", None)
    if shell is None or getattr(hub, "_quitting", False):
        return

    def found(info):
        if not isinstance(info, dict) or not info.get("available"):
            return
        if not (info.get("exe_url") and info.get("sha_url")):
            return
        from core import updater
        if not updater.can_download_release():
            return                                    # the update bar (shown by check_updates) is all we can do
        _download(hub, shell, info)
    try:
        shell.check_updates(done=found)
    except tk.TclError:
        pass


def _download(hub, shell, info):
    from core import updater
    from rt_pages.common import run_bg
    try:
        shell.bar_text.configure(text=f"Downloading {info['version']} in the background…")
    except Exception:
        pass

    def got(res):
        if isinstance(res, Exception):
            res = (False, str(res))
        ok, payload = res if isinstance(res, tuple) else (False, "Unexpected result")
        if not ok:
            try:
                hub.log_action("Automatic update", f"Download {info['version']}", "Failed", str(payload))
                shell.bar_text.configure(text=f"Automatic update failed: {payload}")
            except Exception:
                pass
            return
        try:
            hub.log_action("Automatic update", f"Download {info['version']}", "Success (SHA-256 verified)")
        except Exception:
            pass
        if messagebox.askyesno(APP_NAME, f"{APP_NAME} {info['version']} was downloaded and checked (SHA-256).\n\n"
                               "Restart now to finish updating? Your settings are kept.", parent=hub):
            ok2, msg = updater.install_update(payload)
            if ok2:
                import rt_shell
                rt_shell.quit_app(hub)
                return
            try:
                shell.bar_text.configure(text=f"Update failed: {msg}")
            except Exception:
                pass
        else:
            try:
                shell.bar_text.configure(text=f"{APP_NAME} {info['version']} is ready. Press Update now to restart "
                                              "into it.")
            except Exception:
                pass
    run_bg(hub, updater.download_update, got, info)
