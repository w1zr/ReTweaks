"""Game config files: RETWEAKS' game presets, ported from the original RETWEAKS app (ui/pages/games.py).

Different from the Game profiles page: this edits the game's OWN settings file (for example Fortnite's
GameUserSettings.ini): Low / High / Ultra / Ultra Performance presets, a Custom editor for every value,
your own presets (save, rename, duplicate, edit, export, import), any game's file you choose yourself,
backups before every change with restore, and a read-only lock for games that reset their file.
All logic is core/game_presets.py (unchanged): it previews, backs up first, only changes keys that
already exist in the file and refuses while the game is running."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from core import game_presets as gp
from rt_pages.common import run_bg


# ---------------------------------------------------------------- small dialogs
def ask_choice(parent, title, prompt, items):
    """Pick one item from a list. Returns the item or None."""
    if not items:
        return None
    top = tk.Toplevel(parent)
    top.title(title)
    top.transient(parent)
    top.resizable(False, False)
    tk.Label(top, text=prompt, anchor="w").pack(fill="x", padx=12, pady=(10, 4))
    lb = tk.Listbox(top, height=min(12, len(items)), width=48, exportselection=False)
    for it in items:
        lb.insert("end", it)
    lb.selection_set(0)
    lb.pack(fill="both", expand=True, padx=12)
    out = {"v": None}

    def ok(_e=None):
        sel = lb.curselection()
        out["v"] = items[sel[0]] if sel else None
        top.destroy()

    row = tk.Frame(top)
    row.pack(fill="x", padx=12, pady=10)
    tk.Button(row, text="Cancel", command=top.destroy).pack(side="right")
    tk.Button(row, text="OK", command=ok).pack(side="right", padx=6)
    lb.bind("<Double-Button-1>", ok)
    top.grab_set()
    parent.wait_window(top)
    return out["v"]


def ask_buttons(parent, title, text, buttons):
    """Message with labelled buttons. Returns the label pressed, or None if closed."""
    top = tk.Toplevel(parent)
    top.title(title)
    top.transient(parent)
    top.resizable(False, False)
    tk.Label(top, text=text, justify="left", anchor="w", wraplength=420).pack(fill="x", padx=14, pady=(12, 8))
    out = {"v": None}
    row = tk.Frame(top)
    row.pack(fill="x", padx=12, pady=(0, 12))
    for b in reversed(buttons):
        tk.Button(row, text=b, command=lambda b=b: (out.__setitem__("v", b), top.destroy())).pack(side="right", padx=3)
    top.grab_set()
    parent.wait_window(top)
    return out["v"]


class PresetEditor(tk.Toplevel):
    """Key/value table for one user preset. Keys can only be ones RETWEAKS knows for the game (or, for
    your own file, ones in that file); values are free text."""

    def __init__(self, parent, name, settings, allowed_keys):
        super().__init__(parent)
        self.title(f"Edit preset “{name}”")
        self.geometry("560x480")
        self.transient(parent)
        self.allowed = list(allowed_keys)
        self.result = None
        tk.Label(self, text="Double-click a value to change it. Settings are written only if they already exist "
                            "in the game's file.", justify="left", anchor="w", wraplength=520).pack(fill="x", padx=12, pady=8)
        self.tree = ttk.Treeview(self, columns=("k", "v"), show="headings", selectmode="extended")
        self.tree.heading("k", text="Setting")
        self.tree.heading("v", text="Value")
        self.tree.pack(fill="both", expand=True, padx=12)
        for k, v in settings.items():
            self.tree.insert("", "end", values=(k, str(v)))
        self.tree.bind("<Double-Button-1>", self._edit)
        row = tk.Frame(self)
        row.pack(fill="x", padx=12, pady=6)
        tk.Button(row, text="Add a setting…", command=self.add_key).pack(side="left")
        tk.Button(row, text="Remove selected", command=self.remove_selected).pack(side="left", padx=6)
        tk.Button(row, text="Cancel", command=self.destroy).pack(side="right")
        tk.Button(row, text="Save", command=self._save).pack(side="right", padx=6)
        self.grab_set()

    def keys(self):
        return [self.tree.item(i, "values")[0] for i in self.tree.get_children()]

    def _edit(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        k, v = self.tree.item(sel[0], "values")
        new = simpledialog.askstring("Value", f"Value for {k}:", initialvalue=v, parent=self)
        if new is not None:
            self.tree.item(sel[0], values=(k, new))

    def add_key(self):
        free = [k for k in self.allowed if k not in self.keys()]
        if not free:
            messagebox.showinfo("Add a setting", "Every setting RETWEAKS knows for this game is already in the preset.",
                                parent=self)
            return
        key = ask_choice(self, "Add a setting", "Setting:", free)
        if key:
            item = self.tree.insert("", "end", values=(key, ""))
            self.tree.selection_set(item)
            self._edit()

    def remove_selected(self):
        for i in self.tree.selection():
            self.tree.delete(i)

    def _save(self):
        self.result = [tuple(self.tree.item(i, "values")) for i in self.tree.get_children()]
        self.destroy()

    def result_settings(self, original):
        """Edited values. A value that still equals the old value keeps its original type."""
        out = {}
        for k, val in self.result or []:
            old = original.get(k)
            out[k] = old if old is not None and str(old) == val else val
        return out


# ---------------------------------------------------------------- page
class GameFilesPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self.path = self.fmt = self.entry_id = None
        self.edited = {}            # key -> new value (Custom table)
        self.original = {}          # key -> value read from the file
        self._backup_list = []
        g["page_header"](tab, "RETWEAKS", "Game config files",
                         "Edits the game's own settings file (unlike Game profiles, which changes Windows and app "
                         "settings for a game). Pick a game and a preset: RETWEAKS shows exactly what will change, "
                         "backs up the file first, and only changes settings that already exist in it. Close the game first.")
        body = hub._scroll_area(tab)
        P, FG, MUTED, UI = g["PANEL"], g["FG"], g["MUTED"], g["UI"]

        # ---- game picker
        top = tk.Frame(body, bg=g["BG"])
        top.pack(fill="x", pady=(0, 6))
        tk.Label(top, text="Game", bg=g["BG"], fg=MUTED, font=(UI, 9)).pack(side="left", padx=(0, 8))
        self.combo = g["RSelect"](top, [""], width=300, command=lambda v: self.select())
        self.combo.pack(side="left", padx=(0, 8))
        g["RButton"](top, "Choose your own file…", self.add_own_file).pack(side="left", padx=(0, 6))
        self.b_remove = g["RButton"](top, "Remove from list", self.remove_own_file)

        # ---- file card
        self.file_card = g["Card"](body)
        self.file_card.pack(fill="x", pady=6, padx=(0, 12))
        fb = self.file_card.body
        tk.Label(fb, text="Settings file", bg=P, fg=FG, font=(UI, 14, "bold"), anchor="w").pack(fill="x", padx=16, pady=(12, 2))
        self.file_lbl = tk.Label(fb, text="", bg=P, fg=FG, font=(UI, 9), anchor="w", justify="left", wraplength=900)
        self.file_lbl.pack(fill="x", padx=16)
        self.file_card.wrap(self.file_lbl, 40)
        row = tk.Frame(fb, bg=P)
        row.pack(fill="x", padx=16, pady=8)
        self.b_pick = g["RButton"](row, "Use a different file…", self.pick_file)
        self.b_pick.pack(side="left")
        self.b_open = g["RButton"](row, "Open folder", self.open_folder)
        self.b_open.pack(side="left", padx=6)
        self.b_lock = g["RButton"](row, "Lock file (read-only)", self.toggle_lock)
        self.b_lock.pack(side="left")
        self.note = tk.Label(fb, text="", bg=P, fg="#ffb020", font=(UI, 9), anchor="w", justify="left", wraplength=900)
        self.note.pack(fill="x", padx=16, pady=(0, 12))
        self.file_card.wrap(self.note, 40)

        # ---- presets card
        self.preset_card = g["Card"](body)
        self.preset_card.pack(fill="x", pady=6, padx=(0, 12))
        pb = self.preset_card.body
        tk.Label(pb, text="Presets", bg=P, fg=FG, font=(UI, 14, "bold"), anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        self.tier_row = tk.Frame(pb, bg=P)
        self.tier_row.pack(fill="x", padx=16)
        self.tier_buttons = []
        for tier in gp.TIERS:
            b = g["RButton"](self.tier_row, tier, lambda t=tier: self.apply_tier(t), kind="primary")
            b.pack(side="left", padx=(0, 6))
            self.tier_buttons.append(b)
        self.tier_help = tk.Label(pb, text="Low: weaker PCs · High: balanced · Ultra: best visuals · Ultra Performance: "
                                           "competitive, low effects but full resolution. FPS caps are never changed by "
                                           "presets (use Custom).", bg=P, fg=MUTED, font=(UI, 9), anchor="w",
                                  justify="left", wraplength=900)
        self.tier_help.pack(fill="x", padx=16, pady=(4, 6))
        self.preset_card.wrap(self.tier_help, 40)
        urow = tk.Frame(pb, bg=P)
        urow.pack(fill="x", padx=16, pady=4)
        tk.Label(urow, text="Your presets", bg=P, fg=MUTED, font=(UI, 9)).pack(side="left", padx=(0, 8))
        self.user_presets = g["RSelect"](urow, [""], width=240)
        self.user_presets.pack(side="left", padx=(0, 6))
        g["RButton"](urow, "Apply", self.apply_user_preset).pack(side="left", padx=(0, 6))
        g["RButton"](urow, "Delete", self.delete_user_preset).pack(side="left")
        arow = tk.Frame(pb, bg=P)
        arow.pack(fill="x", padx=16, pady=(4, 12))
        for text, fn in (("Rename…", self.rename_user_preset), ("Duplicate…", self.duplicate_user_preset),
                         ("Edit…", self.edit_user_preset), ("Export…", self.export_user_preset),
                         ("Import…", self.import_user_preset)):
            g["RButton"](arow, text, fn, height=30).pack(side="left", padx=(0, 6))
        self.b_copy_builtin = g["RButton"](arow, "Copy a built-in preset…", self.copy_builtin_preset, height=30)
        self.b_copy_builtin.pack(side="left")

        # ---- custom editor
        self.custom_card = g["Card"](body)
        self.custom_card.pack(fill="x", pady=6, padx=(0, 12))
        cb = self.custom_card.body
        tk.Label(cb, text="Custom", bg=P, fg=FG, font=(UI, 14, "bold"), anchor="w").pack(fill="x", padx=16, pady=(12, 0))
        tk.Label(cb, text="Every setting in the file. Double-click a value to change it, then Apply or save it as one "
                          "of your presets. Changed values are marked with *.", bg=P, fg=MUTED, font=(UI, 9),
                 anchor="w", justify="left").pack(fill="x", padx=16, pady=(0, 6))
        style = ttk.Style(hub)
        style.configure("RTGame.Treeview", background=P, fieldbackground=P, foreground=FG, rowheight=26, borderwidth=0,
                        font=(UI, 10))
        style.configure("RTGame.Treeview.Heading", background=g["PANEL2"], foreground=FG, font=(UI, 10, "bold"),
                        relief="flat")
        style.map("RTGame.Treeview", background=[("selected", g["PANEL2"])], foreground=[("selected", FG)])
        tf = tk.Frame(cb, bg=P)
        tf.pack(fill="x", padx=16)
        self.table = ttk.Treeview(tf, columns=("k", "v"), show="headings", height=12, style="RTGame.Treeview")
        self.table.heading("k", text="Setting")
        self.table.heading("v", text="Value")
        self.table.column("k", width=380)
        self.table.column("v", width=380)
        sb = ttk.Scrollbar(tf, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=sb.set)
        self.table.pack(side="left", fill="x", expand=True)
        sb.pack(side="right", fill="y")
        self.table.bind("<Double-Button-1>", self._edit_cell)
        self.table.wheel_target = self.table
        crow = tk.Frame(cb, bg=P)
        crow.pack(fill="x", padx=16, pady=(8, 12))
        g["RButton"](crow, "Apply changes", self.apply_custom, kind="primary").pack(side="left")
        g["RButton"](crow, "Save changes as a preset…", self.save_user_preset).pack(side="left", padx=6)
        g["RButton"](crow, "Reload from file", self.load_table).pack(side="left")

        # ---- backups
        self.backup_card = g["Card"](body)
        self.backup_card.pack(fill="x", pady=6, padx=(0, 12))
        bb = self.backup_card.body
        tk.Label(bb, text="Backups", bg=P, fg=FG, font=(UI, 14, "bold"), anchor="w").pack(fill="x", padx=16, pady=(12, 4))
        brow = tk.Frame(bb, bg=P)
        brow.pack(fill="x", padx=16, pady=(0, 12))
        self.backups = g["RSelect"](brow, [""], width=520)
        self.backups.pack(side="left", padx=(0, 8))
        g["RButton"](brow, "Restore this backup", self.restore).pack(side="left")

        self.msg = tk.Label(body, text="", bg=g["BG"], fg=FG, font=(UI, 10), anchor="w", justify="left", wraplength=980)
        self.msg.pack(fill="x", pady=8)
        self.fill_combo()

    # ------------------------------------------------------------ helpers
    def _set_values(self, select, values):
        select.values = list(values) or [""]
        select.set(select.values[0])

    def _game_name(self):
        return self.combo.get()

    # ------------------------------------------------------------ game list
    def fill_combo(self, select_id=None):
        self._entries = [(g.name, g.id) for g in gp.GAMES]
        self._entries += [(f"{f['name']} (your file)", f["id"]) for f in gp.load_custom()["files"]]
        self._set_values(self.combo, [n for n, _ in self._entries])
        if select_id:
            for n, i in self._entries:
                if i == select_id:
                    self.combo.set(n)
        self.select()

    def _custom_entry(self, eid):
        return next((f for f in gp.load_custom()["files"] if f["id"] == eid), None)

    def select(self):
        name = self.combo.get()
        self.entry_id = next((i for n, i in self._entries if n == name), None)
        game = gp.BY_ID.get(self.entry_id)
        self.msg.configure(text="")
        if game:
            saved = gp.load_custom().get("paths", {}).get(game.id)
            files = game.find_files()
            self.path = saved if saved and os.path.isfile(saved) else (files[0] if files else None)
            self.fmt = game.fmt
            self.note.configure(text=game.note or "")
            self.b_remove.pack_forget()
            self._lock_visible(game.lockable)
            self.tier_row.pack(fill="x", padx=16, before=self.tier_help)
            self.tier_help.pack(fill="x", padx=16, pady=(4, 6))
            self.b_copy_builtin.pack(side="left")
        else:
            entry = self._custom_entry(self.entry_id) or {}
            self.path, self.fmt = entry.get("path"), entry.get("fmt")
            self.note.configure(text="Your own file: use Custom to change values and save your own presets.")
            self.b_remove.pack(side="left")
            self._lock_visible(True)
            self.tier_row.pack_forget()
            self.tier_help.pack_forget()
            self.b_copy_builtin.pack_forget()
        self.refresh_file()

    def _lock_visible(self, flag):
        if flag:
            self.b_lock.pack(side="left")
        else:
            self.b_lock.pack_forget()

    def refresh_file(self):
        ok = bool(self.path and os.path.isfile(self.path))
        self.file_lbl.configure(text=self.path if ok else "Settings file not found. Start the game once so it creates the "
                                "file, or use “Use a different file…” to pick it.")
        for b in self.tier_buttons:
            b.set_enabled(ok)
        self.b_open.set_enabled(ok)
        self.b_lock.set_enabled(ok)
        if ok:
            try:
                ro = gp.is_read_only(self.path)
            except Exception:
                ro = False
            self.b_lock.set_text("Unlock file" if ro else "Lock file (read-only)")
            self.custom_card.pack(fill="x", pady=6, padx=(0, 12), before=self.backup_card)
        else:
            self.custom_card.pack_forget()
        self.load_table()
        self.load_user_presets()
        self.load_backups()

    # ------------------------------------------------------------ file selection
    def open_folder(self):
        if self.path:
            try:
                os.startfile(os.path.dirname(self.path))
            except (OSError, AttributeError) as e:
                messagebox.showerror("Open folder", str(e), parent=self.hub)

    def pick_file(self):
        start = os.path.dirname(self.path) if self.path else os.path.expanduser("~")
        path = filedialog.askopenfilename(parent=self.hub, title="Choose the settings file", initialdir=start,
                                          filetypes=[("Settings files", "*.ini *.txt *.cfg *.vcfg *.json"),
                                                     ("All files", "*")])
        if not path:
            return
        data = gp.load_custom()
        if gp.BY_ID.get(self.entry_id):
            data.setdefault("paths", {})[self.entry_id] = path
        else:
            for f in data["files"]:
                if f["id"] == self.entry_id:
                    f["path"] = path
        gp.save_custom(data)
        self.select()

    def add_own_file(self):
        path = filedialog.askopenfilename(parent=self.hub, title="Choose a game's settings file",
                                          initialdir=os.path.expanduser("~"),
                                          filetypes=[("Settings files", "*.ini *.txt *.cfg *.vcfg"), ("All files", "*")])
        if not path:
            return
        name = simpledialog.askstring("Name", "Name for this file (e.g. the game):", parent=self.hub,
                                      initialvalue=os.path.basename(os.path.dirname(path)) or os.path.basename(path))
        if name is None:
            return
        try:
            entry, msg = gp.add_custom_file(path, name.strip() or None)
        except Exception as e:
            entry, msg = None, str(e)
        if not entry:
            messagebox.showwarning("Choose your own file", msg, parent=self.hub)
            return
        self.hub.log_action("Game config files", f"Added file {path}", "Success")
        self.fill_combo(entry["id"])
        self.msg.configure(text=msg)

    def remove_own_file(self):
        data = gp.load_custom()
        data["files"] = [f for f in data["files"] if f["id"] != self.entry_id]
        gp.save_custom(data)          # presets for it are kept in case it's added again
        self.fill_combo()

    def toggle_lock(self):
        if gp.game_running(self.entry_id):
            messagebox.showwarning("Lock file", "Close the game first.", parent=self.hub)
            return
        locked = gp.is_read_only(self.path)
        try:
            gp.set_read_only(self.path, not locked)
            self.hub.log_action("Game config files", f"{'Unlock' if locked else 'Lock'} {self.path}", "Success")
            self.msg.configure(text="File unlocked: the game can save its own changes again." if locked else
                               "File locked: the game can't overwrite your settings, but changes you make in the "
                               "game's menu won't save until you unlock it.")
        except Exception as e:
            messagebox.showwarning("Lock file", str(e), parent=self.hub)
        self.refresh_file()

    # ------------------------------------------------------------ apply
    def _confirm_and_apply(self, title, changes):
        if not changes:
            return
        try:
            rows, missing = gp.preview(self.path, self.fmt, changes)
        except Exception as e:
            messagebox.showwarning(title, f"Couldn't read the file: {e}", parent=self.hub)
            return
        real = [(k, a, b) for k, a, b in rows if a != b]
        if not real:
            self.msg.configure(text="Nothing to change: the file already has these values.")
            return
        lines = "\n".join(f"{k}:  {a}  →  {b}" for k, a, b in real[:40])
        if len(real) > 40:
            lines += f"\n… and {len(real) - 40} more"
        extra = f"\n\nNot in your file (skipped): {', '.join(missing)}" if missing else ""
        if not messagebox.askyesno(title, f"These settings will change:\n\n{lines}{extra}\n\nA backup is saved first. "
                                          "Continue?", parent=self.hub):
            return
        game_id, name = self.entry_id, self._game_name()
        self.msg.configure(text="Applying…")

        def done(result):
            ok, msg, _applied, _skipped = result if isinstance(result, tuple) and len(result) == 4 \
                else (False, str(result), {}, [])
            self.msg.configure(text=msg)
            self.hub.log_action(f"Game config files: {name}", title, "Success" if ok else "Failed", "" if ok else msg)
            if not ok:
                messagebox.showwarning(title, msg, parent=self.hub)
            self.refresh_file()

        run_bg(self.hub, gp.apply_changes, done, game_id, self.path, self.fmt, changes)

    def apply_tier(self, tier):
        game = gp.BY_ID.get(self.entry_id)
        if game:
            self._confirm_and_apply(f"{tier} preset", game.presets[tier])

    def apply_custom(self):
        if not self.edited:
            self.msg.configure(text="Change a value in the table first (double-click it).")
            return
        self._confirm_and_apply("Custom changes", dict(self.edited))

    # ------------------------------------------------------------ custom table
    def load_table(self):
        self.table.delete(*self.table.get_children())
        self.edited, self.original = {}, {}
        if not (self.path and os.path.isfile(self.path)):
            return
        try:
            settings = gp.read_settings(self.path, self.fmt)
        except Exception as e:
            self.msg.configure(text=f"Couldn't read the file: {e}")
            return
        self.original = dict(settings)
        for k, v in settings.items():
            self.table.insert("", "end", iid=f"k{len(self.table.get_children())}", values=(k, v))

    def _edit_cell(self, _e=None):
        sel = self.table.selection()
        if not sel:
            return
        k, v = self.table.item(sel[0], "values")[:2]
        key = k.rstrip(" *")
        new = simpledialog.askstring("Change value", f"{key}:", initialvalue=self.edited.get(key, self.original.get(key, v)),
                                     parent=self.hub)
        if new is None:
            return
        if new == str(self.original.get(key)):
            self.edited.pop(key, None)
            self.table.item(sel[0], values=(key, new))
        else:
            self.edited[key] = new
            self.table.item(sel[0], values=(key + " *", new))

    # ------------------------------------------------------------ user presets
    def load_user_presets(self):
        presets = gp.load_custom()["presets"].get(self.entry_id, {})
        self._set_values(self.user_presets, sorted(presets))

    def _ask_new_name(self, title, text="", exclude=None):
        while True:
            name = simpledialog.askstring(title, "Preset name:", initialvalue=text, parent=self.hub)
            if name is None:
                return None, False
            good, name = gp.clean_name(name)
            if not good:
                messagebox.showwarning(title, name, parent=self.hub)
                continue
            if name in gp.user_presets(self.entry_id) and name != exclude:
                choice = ask_buttons(self.hub, title, f"You already have a preset called “{name}”.",
                                     ["Replace it", "Choose another name", "Cancel"])
                if choice == "Replace it":
                    return name, True
                if choice == "Choose another name":
                    text = name
                    continue
                return None, False
            return name, False

    def _selected_user_preset(self):
        name = self.user_presets.get()
        if not name:
            self.msg.configure(text="Pick one of your presets first.")
        return name

    def save_user_preset(self):
        changes = dict(self.edited)
        if not changes:
            self.msg.configure(text="Change some values in the table first, then save them as a preset.")
            return
        name, replace = self._ask_new_name("Save preset")
        if not name:
            return
        status, msg = gp.save_user_preset(self.entry_id, name, changes, replace)
        self.load_user_presets()
        if status == "ok":
            self.user_presets.set(name)
            self.msg.configure(text=f"Saved preset “{name}” ({len(changes)} settings). Use Apply to write it to the file.")
        else:
            messagebox.showwarning("Save preset", msg, parent=self.hub)

    def rename_user_preset(self):
        old = self._selected_user_preset()
        if not old:
            self.msg.configure(text="Pick one of your presets first (or save one with Custom). There are none for this game yet.")
            return
        new, replace = self._ask_new_name("Rename preset", old, exclude=old)
        if not new:
            return
        status, msg = gp.rename_user_preset(self.entry_id, old, new, replace)
        self.msg.configure(text=msg)
        if status == "error":
            messagebox.showwarning("Rename preset", msg, parent=self.hub)
        else:
            self.hub.log_action(f"Game config files: {self._game_name()}", f"Rename preset {old} → {new}", "Success")
        self.load_user_presets()
        self.user_presets.set(new)

    def duplicate_user_preset(self):
        src = self._selected_user_preset()
        if not src:
            self.msg.configure(text="Pick one of your presets first (or save one with Custom). There are none for this game yet.")
            return
        new, replace = self._ask_new_name("Duplicate preset", f"{src} copy")
        if not new:
            return
        status, msg = gp.duplicate_preset(self.entry_id, src, new, replace)
        self.msg.configure(text=msg)
        if status == "error":
            messagebox.showwarning("Duplicate preset", msg, parent=self.hub)
        self.load_user_presets()
        self.user_presets.set(new)

    def copy_builtin_preset(self):
        if not gp.BY_ID.get(self.entry_id):
            self.msg.configure(text="Your own files have no built-in presets.")
            return
        tier = ask_choice(self.hub, "Copy a built-in preset", "Built-in preset:", list(gp.TIERS))
        if not tier:
            return
        new, replace = self._ask_new_name("Copy a built-in preset", f"My {tier}")
        if not new:
            return
        status, msg = gp.duplicate_preset(self.entry_id, tier, new, replace)
        self.msg.configure(text=msg)
        if status == "error":
            messagebox.showwarning("Copy a built-in preset", msg, parent=self.hub)
        self.load_user_presets()
        self.user_presets.set(new)

    def _file_keys(self):
        try:
            return list(gp.read_settings(self.path, self.fmt)) if self.path and os.path.isfile(self.path) else []
        except Exception:
            return []

    def edit_user_preset(self):
        name = self._selected_user_preset()
        if not name:
            self.msg.configure(text="Pick one of your presets first (or save one with Custom). There are none for this game yet.")
            return
        original = gp.user_presets(self.entry_id).get(name, {})
        dlg = PresetEditor(self.hub, name, original, gp.known_keys(self.entry_id, self._file_keys()))
        self.hub.wait_window(dlg)
        if dlg.result is None:
            return
        ok, msg = gp.update_user_preset(self.entry_id, name, dlg.result_settings(original), self._file_keys())
        self.msg.configure(text=msg)
        if ok:
            self.hub.log_action(f"Game config files: {self._game_name()}", f"Edit preset {name}", "Success")
        else:
            messagebox.showwarning("Edit preset", msg, parent=self.hub)

    def export_user_preset(self):
        name = self._selected_user_preset()
        if not name:
            self.msg.configure(text="Pick one of your presets first (or save one with Custom). There are none for this game yet.")
            return
        safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in name).strip() or "preset"
        path = filedialog.asksaveasfilename(parent=self.hub, title="Export preset", initialdir=os.path.expanduser("~"),
                                            initialfile=f"{safe}.json", defaultextension=".json",
                                            filetypes=[("RETWEAKS preset", "*.json")])
        if not path:
            return
        ok, msg = gp.export_preset(self.entry_id, name, path)
        self.msg.configure(text=msg)
        self.hub.log_action(f"Game config files: {self._game_name()}", f"Export preset {name}",
                            "Success" if ok else "Failed", "" if ok else msg)
        if not ok:
            messagebox.showwarning("Export preset", msg, parent=self.hub)

    def import_user_preset(self):
        path = filedialog.askopenfilename(parent=self.hub, title="Import preset", initialdir=os.path.expanduser("~"),
                                          filetypes=[("RETWEAKS preset", "*.json"), ("All files", "*")])
        if not path:
            return
        status, msg, name = gp.import_preset(self.entry_id, path)
        while status == "clash":
            choice = ask_buttons(self.hub, "Import preset", msg, ["Replace it", "Import under another name", "Cancel"])
            if choice == "Replace it":
                status, msg, name = gp.import_preset(self.entry_id, path, name, replace=True)
            elif choice == "Import under another name":
                new = simpledialog.askstring("Import preset", "New name:", initialvalue=f"{name} (imported)",
                                             parent=self.hub)
                if new is None:
                    return
                status, msg, name = gp.import_preset(self.entry_id, path, new.strip())
            else:
                self.msg.configure(text="Import cancelled. Nothing was changed.")
                return
        if status != "ok":
            messagebox.showwarning("Import preset", msg, parent=self.hub)
            self.msg.configure(text=msg)
            return
        self.load_user_presets()
        self.user_presets.set(name)
        self.msg.configure(text=msg)
        self.hub.log_action(f"Game config files: {self._game_name()}", f"Import preset {name}", "Success")

    def apply_user_preset(self):
        name = self.user_presets.get()
        preset = gp.load_custom()["presets"].get(self.entry_id, {}).get(name)
        if preset:
            self._confirm_and_apply(f"Preset “{name}”", preset)
        else:
            self.msg.configure(text="Pick one of your presets first (or save one with Custom). There are none for this game yet.")

    def delete_user_preset(self):
        name = self.user_presets.get()
        if not name:
            self.msg.configure(text="Pick one of your presets first (or save one with Custom). There are none for this game yet.")
            return
        if not messagebox.askyesno("Delete preset", f"Delete your preset “{name}”?", parent=self.hub):
            return
        gp.delete_user_preset(self.entry_id, name)
        self.load_user_presets()

    # ------------------------------------------------------------ backups
    def load_backups(self):
        self._backup_list = gp.list_backups(self.entry_id) if self.entry_id else []
        labels = [f"{b['when']}  ({os.path.basename(b['original'])})" for b in self._backup_list]
        self._set_values(self.backups, labels or ["No backups yet. One is made before every change."])

    def restore(self):
        if not self._backup_list:
            self.msg.configure(text="No backups yet for this game. RETWEAKS makes one before every change it applies.")
            return
        labels = self.backups.values
        try:
            i = labels.index(self.backups.get())
        except ValueError:
            return
        b = self._backup_list[i]
        if not messagebox.askyesno("Restore backup", f"Replace the current settings file with the backup from "
                                                     f"{b['when']}?\n(The current file is backed up first.)",
                                   parent=self.hub):
            return
        ok, msg = gp.restore_backup(self.entry_id, b)
        self.msg.configure(text=msg)
        self.hub.log_action(f"Game config files: {self._game_name()}", "Restore backup",
                            "Success" if ok else "Failed", "" if ok else msg)
        self.refresh_file()
