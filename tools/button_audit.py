"""Linux test helper: clicks every button on every page of the Tk app and reports the ones that do
nothing or fail.
    xvfb-run -a -s "-screen 0 1600x1000x24" python3.12 tools/linux_shim.py tools/button_audit.py [page ...]

What counts as a failure:
  NO COMMAND   an enabled RButton / tk.Button with no command at all (a dead button)
  ERROR        the command (or anything it scheduled in the next ~0.5 s, incl. run_bg results)
               raised an exception
  NO EFFECT    it ran without error but nothing observable happened: no setting changed, no page change,
               no text/state change anywhere in the window, no dialog, no command/web/file call, no
               background job started, no new window, nothing logged (owner report 2026-10-22: buttons
               and settings that "don't work"). Checkboxes (RCheck) and dropdowns (RSelect: picks
               another value) are audited too. Each NO EFFECT still needs a human look: some controls
               only act on Windows hardware/APIs that are faked here.
Dialogs are answered with Cancel/No, file pickers return nothing, and every subprocess / os.system /
web-open call is recorded instead of run, so the audit never changes this machine. Windows APIs are
the inert fakes from linux_shim, so a "works" here means "wired up and doesn't crash", not "the
Windows action succeeded" -- that still needs a real PC.
Each result names the file:line where the button was created."""
import inspect
import os
import subprocess
import sys
import time
import tkinter as tk
import traceback
import webbrowser
from tkinter import filedialog, messagebox, simpledialog
from unittest.mock import Mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Clicking every control changes settings: use a throw-away settings folder, never the real one.
import tempfile  # noqa: E402
_TMP = tempfile.mkdtemp(prefix="rt_audit_")
os.environ["APPDATA"] = _TMP
os.environ["LOCALAPPDATA"] = _TMP

import retweaks as app  # noqa: E402
import hubplus  # noqa: E402
import automation  # noqa: E402

# ---------------------------------------------------------------- nothing leaves the sandbox
SIDE_EFFECTS = []


class _Proc:
    returncode = 0
    stdout = ""
    stderr = ""
    pid = 0

    def __init__(self, *a, **k):
        SIDE_EFFECTS.append(("process", a[0] if a else k.get("args")))
        self.stdout = "" if k.get("text") or k.get("universal_newlines") or k.get("encoding") else b""
        self.stderr = self.stdout

    def communicate(self, *a, **k): return self.stdout, self.stderr
    def wait(self, *a, **k): return 0
    def poll(self): return 0
    def kill(self): pass
    def terminate(self): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False


subprocess.Popen = _Proc
subprocess.run = lambda *a, **k: _Proc(*a, **k)
subprocess.call = lambda *a, **k: (SIDE_EFFECTS.append(("process", a[0] if a else None)), 0)[1]
subprocess.check_output = lambda *a, **k: (SIDE_EFFECTS.append(("process", a[0] if a else None)), "")[1]
os.system = lambda cmd: (SIDE_EFFECTS.append(("os.system", cmd)), 0)[1]
os.startfile = lambda *a, **k: SIDE_EFFECTS.append(("startfile", a))
webbrowser.open = webbrowser.open_new = webbrowser.open_new_tab = \
    lambda url, *a, **k: (SIDE_EFFECTS.append(("web", url)), True)[1]
for name in ("askyesno", "askokcancel", "askretrycancel", "askyesnocancel", "askquestion"):
    setattr(messagebox, name, lambda *a, _n=name, **k: (SIDE_EFFECTS.append(("dialog", _n)), False)[1])
for name in ("showinfo", "showwarning", "showerror"):
    setattr(messagebox, name, lambda *a, _n=name, **k: (SIDE_EFFECTS.append(("dialog", _n)), "ok")[1])
for name in ("askopenfilename", "asksaveasfilename", "askdirectory", "askopenfilenames"):
    setattr(filedialog, name, lambda *a, _n=name, **k: (SIDE_EFFECTS.append(("dialog", _n)), "")[1])
for name in ("askstring", "askinteger", "askfloat"):
    setattr(simpledialog, name, lambda *a, _n=name, **k: (SIDE_EFFECTS.append(("dialog", _n)), None)[1])
import threading as _threading  # noqa: E402
_thread_start = _threading.Thread.start


def _counted_start(self, *a, **k):
    SIDE_EFFECTS.append(("thread", self.name))
    return _thread_start(self, *a, **k)


_threading.Thread.start = _counted_start


class Hotkeys:
    def __init__(self, *a): self.thread = Mock()
    def update(self, *a): pass
    def close(self): pass


automation.Hotkeys = Hotkeys
app.Hub._load_info = lambda self: None
hubplus.write_json = lambda *a: None

# ---------------------------------------------------------------- remember where buttons are made
HERE = {"retweaks.py", "button_audit.py", "tkinter", "__init__.py"}
_origin = {}


def _site():
    for fr in inspect.stack()[2:]:
        fn = fr.filename
        rel = os.path.relpath(fn, ROOT)
        if rel.startswith("..") or os.sep + "tkinter" + os.sep in fn:
            continue
        if rel == "retweaks.py" and fr.function in ("__init__", "_draw"):
            continue
        return f"{rel}:{fr.lineno}"
    return "?"


def _track(cls):
    orig = cls.__init__

    def init(self, *a, **k):
        orig(self, *a, **k)
        _origin[str(self)] = _site()
    cls.__init__ = init


_track(app.RButton)
_track(tk.Button)
_track(app.RCheck)
_track(app.RSelect)

hubplus.install(vars(app))

ERRORS = []


def report(exc, val, tb):
    ERRORS.append("".join(traceback.format_exception(exc, val, tb)).strip())


tk.Tk.report_callback_exception = lambda self, exc, val, tb: report(exc, val, tb)

hub = app.Hub(show_intro=False, enable_ai=False)
hub.geometry("1500x940+0+0")
hub.destroy_real = hub.destroy
hub.destroy = lambda *a: SIDE_EFFECTS.append(("hub.destroy", None))
hub.quit = lambda *a: SIDE_EFFECTS.append(("hub.quit", None))
_real_exit = sys.exit
sys.exit = lambda *a: SIDE_EFFECTS.append(("sys.exit", a))
os._exit_real = os._exit
os._exit = lambda *a: SIDE_EFFECTS.append(("os._exit", a))


def pump(sec):
    end = time.time() + sec
    while time.time() < end:
        try:
            hub.update()
        except tk.TclError:
            pass
        time.sleep(0.01)


def buttons(w):
    out = []
    for c in w.winfo_children():
        if isinstance(c, (app.RButton, tk.Button, app.RCheck, app.RSelect)):
            out.append(c)
        out.extend(buttons(c))
    return out


def _all(w):
    for c in w.winfo_children():
        yield c
        yield from _all(c)


def signature():
    """Everything a user could notice: widget texts/states/visibility, canvas texts and fills, the clipboard."""
    sig = {}
    for c in _all(hub):
        row = [str(c)]
        try:
            row.append(c.winfo_ismapped())
        except tk.TclError:
            continue
        for opt in ("text", "state", "fg", "bg", "image", "value"):
            try:
                row.append(str(c.cget(opt)))
            except (tk.TclError, ValueError):
                pass
        if isinstance(c, tk.Canvas):
            try:
                for item in c.find_all():
                    t = c.type(item)
                    row.append(t)
                    if t == "text":
                        row.append(c.itemcget(item, "text"))
                    elif t in ("polygon", "rectangle", "oval", "line", "arc"):
                        row.append(c.itemcget(item, "fill"))
            except tk.TclError:
                pass
        if isinstance(c, (tk.Entry, tk.Text)):
            try:
                row.append(c.get() if isinstance(c, tk.Entry) else c.get("1.0", "end"))
            except tk.TclError:
                pass
        sig[str(c)] = tuple(row)
    try:
        sig["<clipboard>"] = hub.clipboard_get()
    except tk.TclError:
        sig["<clipboard>"] = None
    return sig


def differs(a, b, volatile):
    keys = (set(a) | set(b)) - volatile
    return any(a.get(k) != b.get(k) for k in keys)


def volatile_now(sec=0.6):
    """Widgets that change by themselves (live readings, animations) don't count as a click's effect."""
    a = signature()
    pump(sec)
    b = signature()
    return {k for k in set(a) | set(b) if a.get(k) != b.get(k)}


def label_of(b):
    if isinstance(b, app.RButton):
        return b.label
    if isinstance(b, app.RCheck):
        return "[x] " + b.cb_text
    if isinstance(b, app.RSelect):
        return "[v] " + str(b.value)
    try:
        return b.cget("text")
    except tk.TclError:
        return "?"


def command_of(b):
    if isinstance(b, app.RButton):
        return b.command
    if isinstance(b, app.RCheck):
        return (lambda: b._click(None)) if b.cmd else None
    if isinstance(b, app.RSelect):
        other = [v for v in b.values if v != b.value]
        if not b.command:
            return None
        return (lambda: b._pick(other[0])) if other else (lambda: None)
    try:
        return b.cget("command") or None
    except tk.TclError:
        return None


def enabled(b):
    if isinstance(b, app.RButton):
        return b.enabled
    if isinstance(b, app.RCheck):
        return not b.disabled
    if isinstance(b, app.RSelect):
        return True
    try:
        return str(b.cget("state")) != "disabled"
    except tk.TclError:
        return False


def close_new_windows(before):
    for w in hub.winfo_children():
        if isinstance(w, tk.Toplevel) and str(w) not in before:
            try:
                w.destroy()
            except tk.TclError:
                pass


pages = {}
for n, i in getattr(getattr(hub, "sidebar_nav", None), "targets", {}).items():
    pages.setdefault(i, n)
for k, v in getattr(hub, "rt_tabs", {}).items():
    pages.setdefault(v, k)
want = [a.lower() for a in sys.argv[1:] if not a.startswith("-")]
SKIP_LABELS = {"quit retweaks", "restart now", "exit"}

results = []
pump(0.5)
for idx, name in sorted(pages.items()):
    if want and name.lower() not in want:
        continue
    print(f"-- {name}", flush=True)
    hub.show_tab(idx)
    pump(0.6)
    seen = set()
    for _ in range(3):                       # pages that rebuild after a click get rescanned
        todo = [b for b in buttons(hub.tabs[idx]) if str(b) not in seen]
        if not todo:
            break
        for b in todo:
            try:
                if not b.winfo_exists():
                    seen.add(str(b))
                    continue
                if not b.winfo_viewable():
                    continue          # not on screen (another sub-tab / hidden until needed): checked when shown
            except tk.TclError:
                continue
            seen.add(str(b))
            lbl, site = label_of(b), _origin.get(str(b), "?")
            if not enabled(b):
                results.append((name, lbl, site, "disabled", ""))
                continue
            cmd = command_of(b)
            if cmd is None:
                results.append((name, lbl, site, "NO COMMAND", ""))
                continue
            if lbl.strip().lower() in SKIP_LABELS:
                results.append((name, lbl, site, "skipped", "ends the app"))
                continue
            before_err, before_fx = len(ERRORS), len(SIDE_EFFECTS)
            wins = {str(w) for w in hub.winfo_children()}
            import json as _json
            before_settings = _json.dumps(getattr(hub, "settings", {}), sort_keys=True, default=str)
            vol = volatile_now(0.5)
            before_tab, before_sig = hub.cur_tab, signature()
            try:
                if isinstance(b, (app.RButton, app.RCheck, app.RSelect)):
                    cmd()
                else:
                    b.invoke()
            except Exception:
                ERRORS.append(traceback.format_exc().strip())
            pump(0.5)
            new_windows = {str(w) for w in hub.winfo_children() if isinstance(w, tk.Toplevel)} - wins
            changed = (new_windows or hub.cur_tab != before_tab or differs(before_sig, signature(), vol) or
                       _json.dumps(getattr(hub, "settings", {}), sort_keys=True, default=str) != before_settings)
            close_new_windows(wins)
            new_err = ERRORS[before_err:]
            fx = SIDE_EFFECTS[before_fx:]
            status = "ERROR" if new_err else ("ok" if (fx or changed) else "NO EFFECT")
            detail = new_err[-1].splitlines()[-1] if new_err else (f"{len(fx)} side effect(s) blocked" if fx else "")
            results.append((name, lbl, site, status, detail))
            if status in ("ERROR", "NO EFFECT"):
                print(f"{status:10} {name:22} {lbl!r:34} {site}  {detail}", flush=True)
            if hub.cur_tab != idx:
                hub.show_tab(idx)
                pump(0.4)

bad = [r for r in results if r[3] in ("ERROR", "NO COMMAND")]
noeffect = [r for r in results if r[3] == "NO EFFECT"]
for page, lbl, site, status, detail in results:
    if status in ("ERROR", "NO COMMAND", "NO EFFECT") or "-v" in sys.argv:
        print(f"{status:10} {page:22} {lbl!r:34} {site}  {detail}")
print(f"\n{len(results)} buttons checked on {len({r[0] for r in results})} pages: "
      f"{sum(r[3] == 'ok' for r in results)} ok, {len(bad)} failing, {len(noeffect)} no visible effect, "
      f"{sum(r[3] == 'disabled' for r in results)} disabled, {sum(r[3] == 'skipped' for r in results)} skipped.")
if bad and ERRORS:
    with open(os.path.join(ROOT, "button_audit_errors.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(ERRORS))
    print("Full tracebacks: button_audit_errors.txt")
try:
    hub.destroy_real()
except tk.TclError:
    pass
os._exit_real(1 if bad else 0)
