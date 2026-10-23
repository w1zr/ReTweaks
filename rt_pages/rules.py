"""Program rules (choose your own .exe), auto game mode and background calming.

Tk port of RETWEAKS' ui/pages/rules.py, same logic (core.app_rules) and setting keys (calm_enabled).
The auto game mode service (ui/workers.AutoGameWorker in the Qt app) is start_services(hub) /
stop_services(hub) here; the app shell starts it at launch and stops it on exit, which also puts
the power plan and calmed priorities back."""
import os
import threading
import tkinter as tk
import traceback
from tkinter import filedialog, simpledialog

from core import app_rules as R
from rt_pages.common import NA, confirm, info

POLL_SECONDS = 3


# ---------------------------------------------------------------- background service
class AutoGameService:
    """Checks every few seconds whether a watched program started or closed (core.app_rules.AutoGameMode).
    Events are delivered to listeners on the Tk thread."""

    def __init__(self, hub):
        self.hub = hub
        self.listeners = []
        self._stop = threading.Event()
        self._events = []
        self._lock = threading.Lock()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="RetweaksAutoGame", daemon=True)
        self._thread.start()
        self.hub.after(250, self._deliver)

    def _emit(self, e):
        with self._lock:
            self._events.append(e)

    def _run(self):
        mode = R.AutoGameMode()
        while not self._stop.is_set():
            try:
                for e in mode.poll(R.load_rules()):
                    self._emit(e)
            except Exception:
                traceback.print_exc()
            self._stop.wait(POLL_SECONDS)
        for e in mode.restore():          # RETWEAKS is closing: power plan and calmed priorities back
            self._emit(e)

    def _deliver(self):
        with self._lock:
            events, self._events = self._events, []
        for e in events:
            for fn in list(self.listeners):
                try:
                    fn(e)
                except Exception:
                    traceback.print_exc()
        if self._thread and (self._thread.is_alive() or self._events):
            try:
                self.hub.after(250, self._deliver)
            except tk.TclError:
                pass

    def stop(self, timeout=10):
        """Stops polling and waits for the restore (power plan, priorities) to finish."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)


def start_services(hub, on_event=None):
    """Start auto game mode + background calming (call once when the app starts)."""
    svc = getattr(hub, "rt_auto_game", None)
    if svc is None:
        svc = hub.rt_auto_game = AutoGameService(hub)
        page = (getattr(hub, "rt_pages", {}) or {}).get("Program rules")
        if page is not None:
            svc.listeners.append(page.on_auto_event)
    if on_event and on_event not in svc.listeners:
        svc.listeners.append(on_event)
    svc.start()
    return svc


def stop_services(hub, timeout=10):
    """Stop it on exit; switches the power plan back if a game was boosted and restores calmed apps."""
    svc = getattr(hub, "rt_auto_game", None)
    if svc is not None:
        svc.stop(timeout)


# ---------------------------------------------------------------- page
class RuleCard:
    def __init__(self, page, parent, rule):
        g = page.g
        self.page, self.rule = page, rule
        self.card = g["Card"](parent)
        self.card.pack(fill="x", pady=6, padx=(0, 12))
        b = self.card.body
        tk.Label(b, text=rule["name"], bg=b.cget("bg"), fg=g["FG"], font=(g["UI"], 13, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(b, text=rule["exe"], bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="w",
                 wraplength=820, justify="left").pack(fill="x", padx=16)
        row = tk.Frame(b, bg=b.cget("bg"))
        row.pack(fill="x", padx=16, pady=(8, 2))
        tk.Label(row, text="Graphics card:", bg=b.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left")
        self.gpu = g["RSelect"](row, list(R.GPU_CHOICES), width=200,
                                command=lambda v: page.change(self, "gpu", v))
        self.gpu.pack(side="left", padx=(6, 18))
        tk.Label(row, text="CPU priority while running:", bg=b.cget("bg"), fg=g["FG"],
                 font=(g["UI"], 10)).pack(side="left")
        self.prio = g["RSelect"](row, R.PRIORITY_CHOICES, width=200,
                                 command=lambda v: page.change(self, "priority", v))
        self.prio.set(rule.get("priority") or R.PRIORITY_CHOICES[0])
        self.prio.pack(side="left", padx=6)
        tk.Label(b, text="Graphics card is the same setting as Windows Settings → System → Display → Graphics. "
                 "Priority is applied when the program starts, while RETWEAKS is open; \"High\" can make other "
                 "apps less responsive.", bg=b.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="w",
                 justify="left", wraplength=820).pack(fill="x", padx=16)
        self.fso = tk.BooleanVar()
        self.boost = tk.BooleanVar(value=bool(rule.get("boost")))
        g["RCheck"](b, "Disable fullscreen optimizations (same as the .exe's Compatibility tab)", self.fso,
                    command=lambda: page.change(self, "fso_off", bool(self.fso.get()))).pack(anchor="w", padx=12, pady=(6, 0))
        g["RCheck"](b, "Auto game mode: switch to the Ultimate Performance power plan while it runs, then switch back",
                    self.boost, command=lambda: page.change(self, "boost", bool(self.boost.get()))).pack(
            anchor="w", padx=12)
        g["RButton"](b, "Remove rule and restore settings", lambda: page.remove(self)).pack(anchor="w", padx=16,
                                                                                            pady=(8, 14))
        self.refresh()

    def refresh(self):
        """Show the real current Windows values."""
        try:
            self.gpu.set(R.get_gpu(self.rule) or "Let Windows decide")
        except Exception:
            self.gpu.set(NA)
        try:
            self.fso.set(bool(R.get_fso_off(self.rule)))
        except Exception:
            self.fso.set(False)

    def destroy(self):
        self.card.destroy()


class RulesPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        g["page_header"](tab, "RETWEAKS", "Program rules",
                         "Pick any game or program (.exe) and choose how Windows should run it. Graphics card and "
                         "fullscreen settings are saved in Windows. Priority and auto game mode work while RETWEAKS "
                         "is open (Settings → start with Windows, minimized).")
        body = hub._scroll_area(tab)
        bg = body.cget("bg")
        top = tk.Frame(body, bg=bg)
        top.pack(fill="x", pady=(0, 4))
        g["RButton"](top, "Add a program (.exe)…", self.add, kind="primary").pack(side="left")
        self.msg = tk.Label(body, text="", bg=bg, fg=g["FG"], font=(g["UI"], 10), anchor="w", justify="left",
                            wraplength=860)
        self.msg.pack(fill="x", pady=2)
        self.rules_box = tk.Frame(body, bg=bg)
        self.rules_box.pack(fill="x")
        self.empty = tk.Label(self.rules_box, text="No programs yet. Add a game's .exe to set its rules.", bg=bg,
                              fg=g["MUTED"], font=(g["UI"], 10), anchor="w")
        self.cards = []
        self._build_calm_card(body)
        self._build_activity(body)
        for rule in R.load_rules():
            self._add_card(rule)
        self._update_empty()

    # ------------------------------------------------------------ background calming
    def _build_calm_card(self, body):
        g = self.g
        cfg = R.load_calm_config()
        enabled = bool(self.hub.settings.get("calm_enabled", False))
        cfg["enabled"] = enabled
        R.save_calm_config(cfg)            # the background worker reads this copy
        self.calm_cfg = cfg
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body
        bg = b.cget("bg")
        tk.Label(b, text="Background calming", bg=bg, fg=g["FG"], font=(g["UI"], 13, "bold"), anchor="w").pack(
            fill="x", padx=16, pady=(12, 2))
        tk.Label(b, text="While a game from the list above is running (one with auto game mode or a CPU priority set), "
                 "temporarily lower the CPU priority of only the programs you pick here, then put it back when the "
                 "game closes (or RETWEAKS closes). If you change a program's priority yourself in the meantime, "
                 "RETWEAKS leaves it alone. System-critical programs, anti-cheat services, programs that have their "
                 "own rule above and RETWEAKS itself are never lowered. This never closes or pauses anything.",
                 bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w", justify="left", wraplength=820).pack(
            fill="x", padx=16)
        self.calm_on = tk.BooleanVar(value=enabled)
        g["RCheck"](b, "Enable background calming", self.calm_on, command=self._calm_enabled).pack(
            anchor="w", padx=12, pady=(8, 2))
        row = tk.Frame(b, bg=bg)
        row.pack(fill="x", padx=16, pady=4)
        tk.Label(row, text="Priority to use:", bg=bg, fg=g["FG"], font=(g["UI"], 10)).pack(side="left")
        self.calm_level = g["RSelect"](row, list(R.CALM_LEVELS), width=180, command=self._calm_level)
        self.calm_level.set(cfg["priority"])
        self.calm_level.pack(side="left", padx=6)
        tk.Label(row, text="Below normal is gentle. Idle only gives the program CPU time nobody else wants.",
                 bg=bg, fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left", padx=8)
        lf = tk.Frame(b, bg=g["LINE"])
        lf.pack(fill="x", padx=16, pady=4)
        self.calm_list = tk.Listbox(lf, height=5, bg=g["PANEL2"], fg=g["FG"], selectbackground=g["ACC"],
                                    selectforeground=g.get("ACC_D", "#141416"), relief="flat", bd=0,
                                    highlightthickness=0, font=(g["UI"], 10), activestyle="none")
        self.calm_list.pack(fill="x", padx=1, pady=1)
        row = tk.Frame(b, bg=bg)
        row.pack(fill="x", padx=16, pady=(4, 2))
        g["RButton"](row, "Add from running programs…", self._calm_add_running).pack(side="left", padx=(0, 6))
        g["RButton"](row, "Type a name…", self._calm_add_typed).pack(side="left", padx=6)
        g["RButton"](row, "Remove selected", self._calm_remove).pack(side="left", padx=6)
        self.calm_status = tk.Label(b, text="", bg=bg, fg=g["FG"], font=(g["UI"], 10), anchor="w", justify="left",
                                    wraplength=820)
        self.calm_status.pack(fill="x", padx=16, pady=(4, 14))
        self._fill_calm_list()
        self._refresh_calm_status(loop=True)

    def _build_activity(self, body):
        g = self.g
        c = g["Card"](body)
        c.pack(fill="x", pady=6, padx=(0, 12))
        b = c.body
        tk.Label(b, text="Auto game mode activity", bg=b.cget("bg"), fg=g["FG"], font=(g["UI"], 13, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 2))
        self.activity = tk.Text(b, height=6, bg=g["PANEL2"], fg=g["FG"], relief="flat", bd=0, highlightthickness=0,
                                font=(g["UI"], 9), wrap="word", insertbackground=g["ACC"])
        self.activity.pack(fill="x", padx=16, pady=(4, 14))
        self.activity.insert("end", "When a program with auto game mode starts or closes, it shows here.\n")
        self.activity.config(state="disabled")
        self._activity_empty = True

    def _fill_calm_list(self):
        self.calm_list.delete(0, "end")
        for a in self.calm_cfg["apps"]:
            self.calm_list.insert("end", a)

    def _calm_save(self):
        R.save_calm_config(self.calm_cfg)

    def _calm_enabled(self):
        on = bool(self.calm_on.get())
        self.hub.settings["calm_enabled"] = on
        self.hub.save_settings()
        self.calm_cfg["enabled"] = on
        self._calm_save()
        self.msg.config(text="Background calming " + ("on. It starts the next time a game from the list runs."
                                                      if on else "off. Anything already lowered is restored within a few seconds."))
        self.hub.log_action("Background calming", "Enabled" if on else "Disabled", "Success")
        self._refresh_calm_status()

    def _calm_level(self, level):
        self.calm_cfg["priority"] = level
        self._calm_save()
        self.hub.log_action("Background calming", f"Priority set to {level}", "Success")

    def calm_add(self, name):
        ok, result = R.validate_calm_name(name)
        if not ok:
            info(self.hub, "Background calming", result, error=True)
            return False
        if result in self.calm_cfg["apps"]:
            self.msg.config(text=f"{result} is already in the list.")
            return False
        self.calm_cfg["apps"].append(result)
        self._calm_save()
        self._fill_calm_list()
        self.hub.log_action("Background calming", f"Added {result}", "Success")
        return True

    def _calm_add_typed(self):
        name = simpledialog.askstring("Add a program", "Program name (for example discord or chrome):",
                                      parent=self.hub)
        if name and name.strip():
            self.calm_add(name)

    def _calm_add_running(self):
        import psutil
        names = set()
        for p in psutil.process_iter(["name"]):
            n = R.normalize_name(p.info.get("name") or "")
            if n and n not in R.PROTECTED:
                names.add(n)
        if not names:
            info(self.hub, "Background calming", "Unavailable: no running programs could be listed.")
            return
        self._pick_from_list("Add a running program", sorted(names), self.calm_add)

    def _pick_from_list(self, title, items, on_pick):
        g = self.g
        top = tk.Toplevel(self.hub)
        top.title(title)
        top.configure(bg=g["PANEL"])
        top.transient(self.hub)
        tk.Label(top, text="Program:", bg=g["PANEL"], fg=g["FG"], font=(g["UI"], 10)).pack(anchor="w", padx=14, pady=(12, 4))
        lb = tk.Listbox(top, height=14, width=40, bg=g["PANEL2"], fg=g["FG"], selectbackground=g["ACC"],
                        relief="flat", bd=0, highlightthickness=0, font=(g["UI"], 10), activestyle="none")
        for i in items:
            lb.insert("end", i)
        lb.pack(fill="both", expand=True, padx=14)

        def ok(_e=None):
            sel = lb.curselection()
            if sel:
                name = lb.get(sel[0])
                top.destroy()
                on_pick(name)
        row = tk.Frame(top, bg=g["PANEL"])
        row.pack(fill="x", padx=14, pady=12)
        g["RButton"](row, "Add", ok, kind="primary").pack(side="left")
        g["RButton"](row, "Cancel", top.destroy).pack(side="left", padx=8)
        lb.bind("<Double-Button-1>", ok)
        top.grab_set()

    def _calm_remove(self):
        sel = self.calm_list.curselection()
        if not sel:
            return
        name = self.calm_list.get(sel[0])
        if name in self.calm_cfg["apps"]:
            self.calm_cfg["apps"].remove(name)
        self._calm_save()
        self._fill_calm_list()
        self.hub.log_action("Background calming", f"Removed {name}", "Success")

    def _refresh_calm_status(self, loop=False):
        try:
            recs = R.load_calm_records()
        except Exception:
            recs = []
        if recs:
            text = "Calmed right now: " + ", ".join(f"{r['name']} (PID {r['pid']})" for r in recs)
        elif self.calm_cfg["enabled"]:
            text = "Nothing is calmed right now. Waiting for a game from the list above to run."
        else:
            text = "Off."
        try:
            self.calm_status.config(text=text)
            if loop:
                self.hub.after(3000, lambda: self._refresh_calm_status(loop=True))
        except tk.TclError:
            pass

    # ------------------------------------------------------------ rules
    def _update_empty(self):
        if self.cards:
            self.empty.pack_forget()
        else:
            self.empty.pack(fill="x", pady=6)

    def _add_card(self, rule):
        self.cards.append(RuleCard(self, self.rules_box, rule))
        self._update_empty()

    def _save(self):
        R.save_rules([c.rule for c in self.cards])

    def add(self, path=None):
        path = path or filedialog.askopenfilename(parent=self.hub, title="Choose a program",
                                                  initialdir=os.path.expanduser("~"),
                                                  filetypes=[("Programs", "*.exe")])
        if not path:
            return
        norm = os.path.normcase(os.path.normpath(path))
        if any(os.path.normcase(os.path.normpath(c.rule["exe"])) == norm for c in self.cards):
            self.msg.config(text="That program already has a rule.")
            return
        rule = R.new_rule(path)
        self._add_card(rule)
        self._save()
        self.hub.log_action("Program rules", f"Added {path}", "Success")

    def change(self, card, field, value):
        rule = card.rule
        if field == "gpu":
            ok, msg = R.set_gpu(rule, value)
        elif field == "fso_off":
            ok, msg = R.set_fso(rule, value)
        else:
            rule[field] = value
            ok, msg = True, (f"{rule['name']}: {'auto game mode on' if value else 'auto game mode off'}."
                             if field == "boost" else f"{rule['name']}: CPU priority {value}.")
        self._save()
        self.msg.config(text=msg)
        self.hub.log_action("Program rules", f"{rule['name']}: {field} = {value}", "Success" if ok else "Failed",
                            "" if ok else msg)
        if not ok:
            info(self.hub, "Program rules", msg, error=True)
        card.refresh()

    def remove(self, card, ask=True):
        if ask and not confirm(self.hub, "Remove rule",
                               f"Remove the rule for {card.rule['name']} and put its Windows settings back?"):
            return
        ok, msg = R.remove_rule_settings(card.rule)
        if not ok:
            info(self.hub, "Remove rule", msg, error=True)
            return
        self.cards.remove(card)
        card.destroy()
        self._save()
        self._update_empty()
        self.msg.config(text=msg)
        self.hub.log_action("Program rules", f"Removed {card.rule['name']}", "Success")

    def on_auto_event(self, text):
        self.activity.config(state="normal")
        if self._activity_empty:
            self.activity.delete("1.0", "end")
            self._activity_empty = False
        self.activity.insert("end", text + "\n")
        self.activity.see("end")
        self.activity.config(state="disabled")
        self.hub.log_action("Auto game mode", text, "Info")
