"""Exact-undo tweaks: the RETWEAKS tweaks the base app's own tweak list doesn't have.

The base app's 117 tweaks (retweaks_data.TWEAKS) stay on its Individual tweaks / Windows tweaks pages; their
Undo puts Windows defaults back. This page holds only the RETWEAKS tweaks (core.tweaks) that the base app
has no individual tweak for. They save the ORIGINAL value before the first change, so Undo puts back
exactly what was there (CLAUDE.md section 8).

How ONLY_HERE was worked out (2026-10-22): for every core.tweaks tweak, the registry values / service
it writes were searched for in the apply and undo commands of every the base app tweak.
- Covered individually by the base app tweak (not shown here): game_mode (gamemode), xbox_capture (gamedvr),
  mouse_accel, transparency, sticky_keys_popup (sticky), hags, fast_startup (faststart), hibernation
  (hibernate), background_apps (bg_apps), animations (visual_fx), ad_id (adid), diag_data (telemetry),
  activity_history (activity), web_search_start (bing), start_suggestions / tips / silent_apps (ads),
  file_ext / hidden_files (fileext), classic_menu, taskbar_left, task_view_btn, widgets, dark_mode,
  end_task, svc_diagtrack, svc_sysmain (sysmain), svc_wsearch (wsearch), storage_sense, delivery_p2p
  (delivery), power_throttling (power_throttle), mmcss_reserve (mmcss).
- Not in the base app at all: windowed_games, suggested_content, lockscreen_tips, svc_spooler, svc_fax,
  svc_wer, update_restart, wu_drivers, narrator_shortcut, game_bar_button, clock_seconds.
- Only inside a larger the base app bundle (CTT telemetry set, CTT services set, CTT visual-effects set,
  Edge debloat, Windows AI removal, tray notifications & calendar), so not available on their own:
  menu_delay, key_repeat_fast, tailored, online_speech, inking_typing, explorer_this_pc, svc_maps,
  notification_banners, edge_background, recall. Kept here so each can be changed and undone alone.
"""
import tkinter as tk

from core import tweaks as T
from rt_pages.common import NA, run_bg

ONLY_HERE = [
    # not in the base app
    "windowed_games", "suggested_content", "lockscreen_tips", "svc_spooler", "svc_fax", "svc_wer",
    "update_restart", "wu_drivers", "narrator_shortcut", "game_bar_button", "clock_seconds",
    # only inside the base app bundle
    "menu_delay", "key_repeat_fast", "tailored", "online_speech", "inking_typing", "explorer_this_pc",
    "svc_maps", "notification_banners", "edge_background", "recall",
]

# RETWEAKS profiles the base app's presets don't cover (the base app has MAX FPS, Esports, Balanced, Streamer,
# Low-end, Laptop, Privacy, Clean, All safe and the CTT presets).
EXTRA_PROFILES = ["High quality", "Ultra quality", "Max Performance", "Windows Default"]

INTROS = {
    "Gaming": "Responsiveness and gaming features. None of these promise more FPS; measure with the FPS test.",
    "Privacy": "What Windows collects and sends, and the ads and suggestions it shows.",
    "Interface": "How Windows looks and behaves on the desktop.",
    "Services": "Windows background services. Turning one off sets it to Disabled after a restart; Undo puts "
                "back its exact original start type. Only turn off what you don't use.",
    "Maintenance": "Updates, storage and power features.",
}


def tweaks_here():
    return [T.BY_ID[i] for i in ONLY_HERE if i in T.BY_ID]


class ExactTweaksPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        g["page_header"](tab, "RETWEAKS", "Exact-undo tweaks",
                         "Before the first change RETWEAKS saves your original setting, so Undo puts back exactly "
                         "what was there (not just the Windows default). Status is read from Windows.")
        body = hub._scroll_area(tab)
        self.body = body
        P, FG, MUTED = g["PANEL"], g["FG"], g["MUTED"]

        from core.winutil import elevated_as_other_user, is_admin
        notes = []
        if not is_admin():
            notes.append("RETWEAKS isn't running as administrator, so tweaks marked Admin will fail.")
        try:
            if elevated_as_other_user():
                notes.append("RETWEAKS was started with a different administrator account than the one signed in. "
                             "Tweaks for your settings would change that other account instead.")
        except Exception:
            pass
        for n in notes:
            c = g["Card"](body, edge="#ffb020")
            c.pack(fill="x", pady=4, padx=(0, 12))
            tk.Label(c.body, text=n, bg=P, fg="#ffb020", font=(g["UI"], 9), justify="left", anchor="w",
                     wraplength=900).pack(fill="x", padx=14, pady=10)

        # ---- top actions
        top = tk.Frame(body, bg=g["BG"])
        top.pack(fill="x", pady=(0, 4))
        self.b_restore = g["RButton"](top, "Create restore point", self.restore_point)
        self.b_restore.pack(side="left", padx=(0, 8))
        self.b_undo_all = g["RButton"](top, "Undo everything RETWEAKS changed", self.undo_everything)
        self.b_undo_all.pack(side="left")
        self.top_msg = tk.Label(body, text="", bg=g["BG"], fg=MUTED, font=(g["UI"], 9), justify="left", anchor="w",
                                wraplength=980)
        self.top_msg.pack(fill="x", pady=(2, 6))

        # ---- search, preset selection
        bar = tk.Frame(body, bg=g["BG"])
        bar.pack(fill="x", pady=(0, 4))
        self.query = tk.StringVar()
        e = g["REntry"](bar, self.query, width_px=420)
        e.pack(side="left", padx=(0, 12))
        self.query.trace_add("write", lambda *a: self.filter_rows())
        tk.Label(bar, text="Preset", bg=g["BG"], fg=MUTED, font=(g["UI"], 9)).pack(side="left", padx=(0, 6))
        from core.profiles import SELECTABLE_PRESETS
        names = list(SELECTABLE_PRESETS)
        self.preset = g["RSelect"](bar, names, width=190)
        last = hub.settings.get("last_preset")
        if last in names:
            self.preset.set(last)
        self.preset.pack(side="left", padx=(0, 8))
        g["RButton"](bar, "Select its tweaks", self.select_preset).pack(side="left")

        sel = tk.Frame(body, bg=g["BG"])
        sel.pack(fill="x", pady=(2, 4))
        self.sel_msg = tk.Label(sel, text="", bg=g["BG"], fg=MUTED, font=(g["UI"], 9), anchor="w", justify="left",
                                wraplength=560)
        self.sel_msg.pack(side="left", fill="x", expand=True)
        self.b_apply_sel = g["RButton"](sel, "Apply selected", self.apply_selected, kind="primary")
        self.b_apply_sel.pack(side="right")
        self.b_clear = g["RButton"](sel, "Clear selection", self.clear_selection)
        self.b_clear.pack(side="right", padx=6)
        g["RButton"](sel, "Select all shown", self.select_shown).pack(side="right")
        self.match_msg = tk.Label(body, text="", bg=g["BG"], fg=MUTED, font=(g["UI"], 9), anchor="w")

        # ---- tweak cards by category
        self.rows, self.cards = [], []
        self.cards_holder = tk.Frame(body, bg=g["BG"])
        self.cards_holder.pack(fill="x")
        here = tweaks_here()
        for cat in T.CATEGORY_ORDER:
            items = [t for t in here if getattr(t, "category", "Gaming") == cat]
            if not items:
                continue
            items.sort(key=lambda t: 0 if t.level == T.STANDARD else 1)    # safe ones first
            card = g["Card"](self.cards_holder)
            tk.Label(card.body, text=cat, bg=P, fg=FG, font=(g["UI"], 14, "bold"), anchor="w").pack(
                fill="x", padx=16, pady=(12, 0))
            intro = tk.Label(card.body, text=INTROS.get(cat, ""), bg=P, fg=MUTED, font=(g["UI"], 9), anchor="w",
                             justify="left", wraplength=900)
            intro.pack(fill="x", padx=16, pady=(0, 6))
            card.wrap(intro, 40)
            holder = tk.Frame(card.body, bg=P)
            holder.pack(fill="x", padx=10, pady=(0, 10))
            entries = [self._row(holder, t, cat, card) for t in items]
            self.rows += entries
            self.cards.append((card, holder, entries))
        self._pack_cards()

        # ---- profiles the base app's presets don't have
        self._profiles_card(body)
        self._essentials_card(body)
        self.selection_changed()
        self.refresh_all()

    # ------------------------------------------------------------ rows
    def _row(self, parent, t, cat, card):
        g, P = self.g, self.g["PANEL"]
        row = tk.Frame(parent, bg=P)
        row.tweak = t
        badges = (["Advanced"] if t.level == T.ADVANCED else []) + (["Admin"] if t.admin else []) + \
                 (["Restart needed"] if t.restart == "restart" else []) + \
                 (["Sign out needed"] if t.restart == "signout" else [])
        row.search_text = " ".join((t.name, t.description, t.tradeoff, cat, " ".join(badges),
                                    T.KEYWORDS.get(t.id, ""))).lower()
        sep = tk.Frame(parent, bg=g["LINE"], height=1)
        row.sep = sep
        top = tk.Frame(row, bg=P)
        top.pack(fill="x")
        row.var = tk.BooleanVar(value=False)
        g["RCheck"](top, t.name, row.var, command=self.selection_changed, outer=P).pack(side="left")
        for b in badges:
            color = "#ffb020" if b in ("Advanced", "Admin") else g["MUTED"]
            g["pill"](top, b, color, outer=P).pack(side="left", padx=(6, 0))
        right = tk.Frame(top, bg=P)
        right.pack(side="right")
        row.buttons = []
        for text, fn in (("On", lambda t=t: t.apply(True)), ("Off", lambda t=t: t.apply(False)), ("Undo", t.undo)):
            b = g["RButton"](right, text, (lambda r=row, tx=text, f=fn: self.run(r, tx, f)), height=30)
            b.pack(side="left", padx=(6, 0))
            row.buttons.append(b)
        row.target = g["RSelect"](right, ["Turn on", "Turn off"], width=118, height=30)
        row.status = tk.Label(right, text="Checking…", bg=P, fg=g["MUTED"], font=(g["UI"], 9, "bold"), width=16,
                              anchor="e")
        row.status.pack(side="left", padx=(0, 6), before=row.buttons[0])
        d = tk.Label(row, text=t.description, bg=P, fg=g["FG"], font=(g["UI"], 9), justify="left", anchor="w",
                     wraplength=760)
        d.pack(fill="x", padx=(30, 6))
        card.wrap(d, 80)
        if t.tradeoff:
            tr = tk.Label(row, text="Trade-off: " + t.tradeoff, bg=P, fg=g["MUTED"], font=(g["UI"], 9),
                          justify="left", anchor="w", wraplength=760)
            tr.pack(fill="x", padx=(30, 6), pady=(1, 0))
            card.wrap(tr, 80)
        return row

    def _pack_cards(self):
        words = self.query.get().lower().split()
        total = 0
        for card, holder, entries in self.cards:
            for r in entries:
                r.pack_forget()
                r.sep.pack_forget()
            shown = 0
            for r in entries:
                if all(w in r.search_text for w in words):
                    if shown:
                        r.sep.pack(fill="x", padx=6, pady=4)
                    r.pack(fill="x", pady=4)
                    shown += 1
            if shown:
                card.pack(fill="x", pady=6, padx=(0, 12))
            else:
                card.pack_forget()
            total += shown
        if words:
            self.match_msg.configure(text=f"{total} tweak{'s' if total != 1 else ''} match “{self.query.get().strip()}”."
                                     + ("" if total else " Try another word, or search the Individual tweaks page."))
            self.match_msg.pack(fill="x", before=self.cards_holder)
        else:
            self.match_msg.pack_forget()

    def filter_rows(self):
        self._pack_cards()

    def _visible(self, row):
        words = self.query.get().lower().split()
        return all(w in row.search_text for w in words)

    # ------------------------------------------------------------ selection
    def selection_changed(self):
        for r in self.rows:
            if r.var.get():
                if not r.target.winfo_ismapped():
                    r.target.pack(side="left", padx=(0, 6), before=r.status)
            else:
                r.target.pack_forget()
        n = sum(1 for r in self.rows if r.var.get())
        self.sel_msg.configure(text=(f"{n} tweak{'s' if n != 1 else ''} selected. Review the ticks and On/Off "
                                     "choices, then press Apply selected.") if n else
                               "No tweaks selected. Tick tweaks below, or pick a preset and press Select its tweaks.")
        self.b_apply_sel.set_text(f"Apply selected ({n})" if n else "Apply selected")
        self.b_apply_sel.set_enabled(n > 0)
        self.b_clear.set_enabled(n > 0)

    def select_preset(self):
        from core.profiles import preset_selection
        name = self.preset.get()
        by_id = {r.tweak.id: r for r in self.rows}
        self.clear_selection()
        picked, elsewhere = 0, []
        for key, target in preset_selection(name):
            r = by_id.get(key)
            if r is None:
                elsewhere.append("power plan" if key == "power" else T.BY_ID[key].name)
                continue
            r.var.set(True)
            r.target.set("Turn on" if target else "Turn off")
            picked += 1
        self.query.set("")
        self.selection_changed()
        msg = f"Selected {picked} of the {name} tweaks that are on this page. Nothing has changed yet."
        if elsewhere:
            msg += (" The rest of this preset (" + ", ".join(elsewhere) + ") are on the Presets and Individual "
                    "tweaks pages: use those pages for them.")
        self.top_msg.configure(text=msg)

    def select_shown(self):
        for r in self.rows:
            if self._visible(r):
                r.var.set(True)
        self.selection_changed()

    def clear_selection(self):
        for r in self.rows:
            r.var.set(False)
        self.selection_changed()

    def apply_selected(self):
        from core.profiles import apply_selection, selection_preview
        selection = [(r.tweak.id, r.target.get() == "Turn on") for r in self.rows if r.var.get()]
        if not selection:
            return
        self.b_apply_sel.set_enabled(False)
        self.top_msg.configure(text="Checking your current settings…")

        def previewed(items):
            if isinstance(items, Exception):
                self.selection_changed()
                self.top_msg.configure(text=f"Couldn't read your current settings: {items}")
                return
            change = [(sel, i) for sel, i in zip(selection, items) if i[3]]
            same = [i for i in items if not i[3]]
            if not change:
                self.selection_changed()
                self.top_msg.configure(text="Everything you selected is already set. Nothing to change.")
                return
            lines = "\n".join(f"• {lbl}: {cur or '?'} → {want}" for _, (lbl, cur, want, _c) in change)
            text = f"Change {len(change)} setting{'s' if len(change) != 1 else ''}?\n\n{lines}"
            if same:
                text += f"\n\nAlready set ({len(same)}): " + ", ".join(i[0] for i in same)
            text += "\n\nEach one can be undone on its row, or all at once with Undo everything."
            from tkinter import messagebox
            if not messagebox.askyesno("Apply selected tweaks", text, parent=self.hub):
                self.selection_changed()
                self.top_msg.configure(text="Cancelled. Nothing was changed.")
                return
            self.top_msg.configure(text="Applying…")
            run_bg(self.hub, apply_selection, applied, [sel for sel, _ in change])

        def applied(results):
            if isinstance(results, Exception):
                results = [("Apply selected", False, str(results))]
            for step, ok, msg in results:
                self.hub.log_action("Exact-undo tweaks: apply selected", step, "Success" if ok else "Failed",
                                    "" if ok else msg)
            failed = sum(1 for _, ok, _ in results if not ok)
            self.top_msg.configure(text=f"{len(results) - failed} of {len(results)} changes succeeded.\n"
                                   + "\n".join(f"{'✔' if ok else '✖'}  {s}: {m}" for s, ok, m in results))
            if not failed:
                self.clear_selection()
            self.selection_changed()
            self.refresh_all()

        run_bg(self.hub, selection_preview, previewed, selection)

    # ------------------------------------------------------------ actions
    def on_shown(self):
        self.refresh_all()

    def refresh_all(self):
        rows = list(self.rows)

        def read():
            out = []
            for r in rows:
                try:
                    out.append(r.tweak.get_state())
                except Exception:
                    out.append("Unknown")
            return out

        def show(states):
            if isinstance(states, Exception):
                states = ["Unknown"] * len(rows)
            for r, s in zip(rows, states):
                self._show_status(r, s)

        run_bg(self.hub, read, show)

    def _show_status(self, row, value):
        value = value if isinstance(value, str) and value else NA
        try:
            row.status.configure(text=value, fg=self.g["GREEN"] if value.lower().startswith("on") else self.g["MUTED"])
        except tk.TclError:
            pass

    def run(self, row, action, fn):
        for b in row.buttons:
            b.set_enabled(False)
        row.status.configure(text="Working…")

        def done(result):
            if isinstance(result, Exception):
                result = (False, str(result))
            ok, msg = result
            for b in row.buttons:
                b.set_enabled(True)
            self.hub.log_action(row.tweak.name, action, "Success" if ok else "Failed", "" if ok else msg)
            self.top_msg.configure(text=msg)
            if not ok:
                from tkinter import messagebox
                messagebox.showwarning(row.tweak.name, msg, parent=self.hub)
            run_bg(self.hub, row.tweak.get_state, lambda s: self._show_status(row, s if isinstance(s, str) else "Unknown"))

        run_bg(self.hub, fn, done)

    def restore_point(self):
        self.b_restore.set_enabled(False)
        self.top_msg.configure(text="Creating a restore point… (can take a minute)")

        def done(result):
            ok, msg = (False, str(result)) if isinstance(result, Exception) else result
            self.b_restore.set_enabled(True)
            self.top_msg.configure(text=msg)
            self.hub.log_action("Restore point", "Create", "Success" if ok else "Failed", "" if ok else msg)

        run_bg(self.hub, T.create_restore_point, done)

    def undo_everything(self):
        from tkinter import messagebox
        names = [t.name for t in T.changed_tweaks()]
        listing = "\n".join(f"• {n}" for n in names) or "• (no individual tweaks)"
        if not messagebox.askyesno(
                "Undo everything",
                "Put these back to how they were before RETWEAKS changed them?\n\n"
                f"{listing}\n• Power plan and DNS, if RETWEAKS saved them\n\n"
                "Tweaks from the Individual tweaks page are undone on that page.", parent=self.hub):
            return
        self.b_undo_all.set_enabled(False)
        self.top_msg.configure(text="Restoring…")

        def done(results):
            self.b_undo_all.set_enabled(True)
            if isinstance(results, Exception):
                results = [("Undo everything", False, str(results))]
            if not results:
                self.top_msg.configure(text="Nothing to undo: RETWEAKS hasn't changed anything yet.")
            else:
                ok_count = sum(1 for _, ok, _ in results if ok)
                lines = [f"{'✔' if ok else '✖'} {n}: {m}" for n, ok, m in results]
                self.top_msg.configure(text=f"Restored {ok_count} of {len(results)}.\n" + "\n".join(lines))
                for n, ok, m in results:
                    self.hub.log_action(n, "Undo", "Success" if ok else "Failed", "" if ok else m)
            self.refresh_all()

        run_bg(self.hub, T.undo_everything, done)

    # ------------------------------------------------------------ profiles (preview, then apply)
    def _profiles_card(self, body):
        from core.profiles import PROFILES
        g, P = self.g, self.g["PANEL"]
        card = g["Card"](body)
        card.pack(fill="x", pady=6, padx=(0, 12))
        tk.Label(card.body, text="More RETWEAKS profiles", bg=P, fg=g["FG"], font=(g["UI"], 14, "bold"),
                 anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        sub = tk.Label(card.body, text="Profiles the Presets page doesn't have. RETWEAKS reads what each one would "
                                       "change from Windows and shows it before anything is applied. Every step "
                                       "can be undone with Undo everything.",
                       bg=P, fg=g["MUTED"], font=(g["UI"], 9), justify="left", anchor="w", wraplength=900)
        sub.pack(fill="x", padx=16, pady=(0, 6))
        card.wrap(sub, 40)
        for name in EXTRA_PROFILES:
            if name not in PROFILES:
                continue
            r = tk.Frame(card.body, bg=P)
            r.pack(fill="x", padx=16, pady=4)
            g["RButton"](r, f"Apply {name}…", lambda n=name: self.apply_profile(n)).pack(side="right")
            tk.Label(r, text=name, bg=P, fg=g["FG"], font=(g["UI"], 10, "bold"), anchor="w").pack(fill="x")
            d = tk.Label(r, text=PROFILES[name]["description"], bg=P, fg=g["MUTED"], font=(g["UI"], 9),
                         justify="left", anchor="w", wraplength=760)
            d.pack(fill="x")
            card.wrap(d, 220)
        self.profile_msg = tk.Label(card.body, text="", bg=P, fg=g["FG"], font=(g["UI"], 9), justify="left",
                                    anchor="w", wraplength=900)
        self.profile_msg.pack(fill="x", padx=16, pady=(4, 12))
        card.wrap(self.profile_msg, 40)

    def apply_profile(self, name):
        from core.profiles import apply_profile, preview
        from tkinter import messagebox
        self.profile_msg.configure(text=f"Checking what {name} would change…")

        def previewed(items):
            if isinstance(items, Exception):
                self.profile_msg.configure(text=f"Couldn't read your current settings: {items}")
                return
            change = [i for i in items if i[3]]
            same = [i for i in items if not i[3]]
            if not change:
                self.profile_msg.configure(text=f"{name}: everything is already set. Nothing to change.")
                return
            lines = [f"• {lbl}: {cur or '?'} → {want}" if want else f"• {lbl}" for lbl, cur, want, _ in change]
            text = f"{name} will change {len(change)} setting{'s' if len(change) != 1 else ''}:\n\n" + "\n".join(lines)
            if same:
                text += f"\n\nAlready set ({len(same)}): " + ", ".join(lbl for lbl, *_ in same)
            text += "\n\nEverything can be undone with Undo everything."
            if not messagebox.askyesno(f"Apply {name}?", text, parent=self.hub):
                self.profile_msg.configure(text="Cancelled. Nothing was changed.")
                return
            self.profile_msg.configure(text=f"Applying {name}…")
            run_bg(self.hub, apply_profile, applied, name)

        def applied(results):
            if isinstance(results, Exception):
                results = [("Profile", False, str(results))]
            for step, ok, msg in results:
                self.hub.log_action(f"Profile: {name}", step, "Success" if ok else "Failed", "" if ok else msg)
            failed = sum(1 for _, ok, _ in results if not ok)
            self.hub.settings["last_preset"] = name
            self.hub.save_settings()
            self.profile_msg.configure(text=f"{name}: {len(results) - failed} of {len(results)} steps succeeded.\n"
                                       + "\n".join(f"{'✔' if ok else '✖'}  {s}: {m}" for s, ok, m in results))
            self.refresh_all()

        run_bg(self.hub, preview, previewed, name)

    # ------------------------------------------------------------ Windows Update cache (not in the base app)
    def _essentials_card(self, body):
        g, P = self.g, self.g["PANEL"]
        card = g["Card"](body)
        card.pack(fill="x", pady=6, padx=(0, 12))
        tk.Label(card.body, text="Clear Windows Update download cache", bg=P, fg=g["FG"],
                 font=(g["UI"], 14, "bold"), anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        d = tk.Label(card.body, text="Deletes downloaded update files Windows keeps. Can fix stuck updates and free "
                                     "space. Shows the size first; Windows re-downloads what it still needs. Admin. "
                                     "(Clear DNS cache and SFC are on the Individual tweaks page.)",
                     bg=P, fg=g["MUTED"], font=(g["UI"], 9), justify="left", anchor="w", wraplength=900)
        d.pack(fill="x", padx=16)
        card.wrap(d, 40)
        row = tk.Frame(card.body, bg=P)
        row.pack(fill="x", padx=16, pady=(6, 12))
        self.b_wu = g["RButton"](row, "Check size…", self.clear_wu)
        self.b_wu.pack(side="left")
        self.wu_msg = tk.Label(row, text="", bg=P, fg=g["FG"], font=(g["UI"], 9), justify="left", anchor="w",
                               wraplength=700)
        self.wu_msg.pack(side="left", padx=10, fill="x")

    def clear_wu(self):
        from core import quick_actions as Q
        from tkinter import messagebox
        self.b_wu.set_enabled(False)
        self.wu_msg.configure(text="Measuring the Windows Update download cache…")

        def previewed(res):
            self.b_wu.set_enabled(True)
            if not (isinstance(res, tuple) and len(res) == 4):
                self.wu_msg.configure(text=f"Couldn't read the cache: {res}")
                return
            _ok, size, count, text = res
            if count == 0:
                self.wu_msg.configure(text="Nothing to clear: " + text)
                return
            if not messagebox.askyesno("Clear Windows Update download cache",
                                       f"Delete these downloaded update files?\n\n{text}\n\nWindows Update is paused "
                                       "while this runs and started again after. Files in use are skipped.",
                                       parent=self.hub):
                self.wu_msg.configure(text="Cancelled. Nothing was deleted.")
                return
            self.b_wu.set_enabled(False)
            self.wu_msg.configure(text="Clearing…")
            run_bg(self.hub, Q.clear_wu_cache, cleared)

        def cleared(res):
            self.b_wu.set_enabled(True)
            ok, msg = (False, str(res)) if isinstance(res, Exception) else res
            self.wu_msg.configure(text=("✔ " if ok else "✖ ") + msg)
            self.hub.log_action("Windows Update cache", "Clear", "Success" if ok else "Failed", "" if ok else msg)

        run_bg(self.hub, Q.wu_cache_preview, previewed)
