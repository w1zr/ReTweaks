# ui/pages/tweaks.py
"""Individual tweaks, grouped by category (Gaming, Privacy, Interface, Services, Maintenance),
with safe (Standard) ones first and Advanced ones marked. Each row shows the setting's REAL
current state, its trade-off, and has its own Undo. Plus restore point and Undo everything."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

from core import tweaks as T
from core.optimizer import WindowsOptimizer as W
from core.winutil import elevated_as_other_user, is_admin
from ui.widgets.common import Card, Notice, Page, label, set_role, set_status_style


class TweakRow(QWidget):
    """Name, description and trade-off on the left; live status and buttons on the right."""

    def __init__(self, page, name, description, tradeoff, get_status, actions, badges=(),
                 key=None, targets=()):
        super().__init__()
        self.page, self.name, self.get_status = page, name, get_status
        self.key = key                  # tweak id or "power"; None = can't be selected
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 8, 0, 8)
        self.check = None
        if key is not None:
            # Selection (v1.4.3): a preset ticks rows; the user reviews, unticks or adds, then applies.
            self.check = QCheckBox()
            self.check.setToolTip("Select this tweak. Selected tweaks change only when you press "
                                  "“Apply selected”.")
            self.check.toggled.connect(self._toggled)
            lay.addWidget(self.check, 0, Qt.AlignTop)
            self.target = QComboBox()
            for text_, value in targets:
                self.target.addItem(text_, value)
            self.target.setToolTip("What “Apply selected” will set this tweak to.")
            self.target.setVisible(False)
        text = QVBoxLayout()
        title = name + ("   " + "  ·  ".join(badges) if badges else "")
        text.addWidget(label(title, "sectionTitle"))
        text.addWidget(label(description, "cardLine", wrap=True))
        if tradeoff:
            text.addWidget(label("Trade-off: " + tradeoff, "muted", wrap=True))
        lay.addLayout(text, 1)
        self.status = label("Checking…", "cardLine")
        self.status.setMinimumWidth(150)
        self.status.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        lay.addWidget(self.status)
        if self.check is not None:
            lay.addWidget(self.target)
        self.buttons = []
        for text_, fn in actions:
            b = QPushButton(text_)
            b.clicked.connect(lambda _=False, f=fn, t=text_: self.page.run(self, t, f))
            lay.addWidget(b)
            self.buttons.append(b)

    def _toggled(self, on):
        self.target.setVisible(on)
        self.page.selection_changed()

    def select(self, value):
        """Tick this row and set its target (used by presets)."""
        i = self.target.findData(value)
        if i >= 0:
            self.target.setCurrentIndex(i)
        self.check.setChecked(True)

    def selected(self):
        return self.check is not None and self.check.isChecked()

    def set_busy(self, busy):
        for b in self.buttons:
            b.setEnabled(not busy)
        if busy:
            self.status.setText("Working…")

    def show_status(self, value):
        value = value if isinstance(value, str) else "Unknown"
        self.status.setText(value)
        set_status_style(self.status, "good" if value.lower().startswith(("on", "enabled", "active")) else None)


def _sep():
    s = QWidget()
    s.setFixedHeight(1)
    s.setStyleSheet("background-color: rgba(128,128,128,0.18);")
    return s


class TweaksPage(Page):
    title = "Tweaks"
    subtitle = ("Apply tweaks one at a time. Status is read from Windows, every change is written to "
                "Logs, and RYTWEAKS saves the original setting so Undo puts it back exactly.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        if not is_admin():
            self.content.addWidget(Notice(
                "RYTWEAKS isn't running as administrator, so tweaks marked “Admin” will fail. "
                "Right-click RYTWEAKS.exe → Run as administrator."))

        if elevated_as_other_user():
            self.content.addWidget(Notice(
                "RYTWEAKS was started with a different administrator account than the one signed in. "
                "Tweaks for “your” settings would change that other account instead. Sign in to the "
                "administrator account, or make your account an administrator, then start RYTWEAKS again."))
        top = QHBoxLayout()
        self.b_restore = QPushButton("Create restore point")
        self.b_restore.setToolTip("Windows System Restore point, so you can roll back the whole PC.")
        self.b_restore.clicked.connect(self.restore_point)
        self.b_undo_all = set_role(QPushButton("Undo everything RYTWEAKS changed"), "danger")
        self.b_undo_all.clicked.connect(self.undo_everything)
        top.addWidget(self.b_restore)
        top.addWidget(self.b_undo_all)
        top.addStretch()
        self.top_msg = label("", "muted", wrap=True)
        self.content.addLayout(top)
        self.content.addWidget(self.top_msg)

        # ---- Search and presets (v1.4.3)
        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tweaks, e.g. sticky keys, mouse, telemetry, notifications…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.filter_rows)
        bar.addWidget(self.search, 1)
        bar.addSpacing(12)
        bar.addWidget(label("Preset", "cardLine"))
        from core.profiles import SELECTABLE_PRESETS
        self.preset = QComboBox()
        self.preset.addItems(list(SELECTABLE_PRESETS.keys()))
        last = self.ctx.settings.get("last_preset") if isinstance(getattr(self.ctx, "settings", None), dict) else None
        if last in SELECTABLE_PRESETS:
            self.preset.setCurrentText(last)
        bar.addWidget(self.preset)
        self.b_preset = QPushButton("Select its tweaks")
        self.b_preset.setToolTip("Ticks every tweak in this preset and sets each one to On or Off the way the "
                                 "preset does. Nothing changes until you press “Apply selected”.")
        self.b_preset.clicked.connect(self.select_preset)
        bar.addWidget(self.b_preset)
        self.content.addLayout(bar)
        sel = QHBoxLayout()
        self.sel_msg = label("No tweaks selected. Tick tweaks below, or pick a preset and press "
                             "“Select its tweaks”.", "muted", wrap=True)
        sel.addWidget(self.sel_msg, 1)
        self.b_sel_shown = QPushButton("Select all shown")
        self.b_sel_shown.setToolTip("Ticks every tweak the search is showing (each keeps its On/Off choice).")
        self.b_sel_shown.clicked.connect(self.select_shown)
        self.b_clear = QPushButton("Clear selection")
        self.b_clear.clicked.connect(self.clear_selection)
        self.b_apply_sel = set_role(QPushButton("Apply selected"), "primary")
        self.b_apply_sel.clicked.connect(self.apply_selected)
        for b in (self.b_sel_shown, self.b_clear, self.b_apply_sel):
            sel.addWidget(b)
        self.content.addLayout(sel)
        self.match_msg = label("", "muted")
        self.match_msg.setVisible(False)
        self.content.addWidget(self.match_msg)

        self.rows = []
        self.cards = []            # (card, [(row, separator or None)])
        intros = {
            "Gaming": "Responsiveness and gaming features. None of these promise more FPS; test with the FPS test.",
            "Privacy": "What Windows collects and sends, and the ads and suggestions it shows.",
            "Interface": "How Windows looks and behaves on the desktop.",
            "Services": "Windows background services. Turning one off sets it to Disabled after a restart; "
                        "Undo puts back its exact original start type. Only turn off what you don't use.",
            "Maintenance": "Updates, storage and power features.",
        }
        for cat in T.CATEGORY_ORDER:
            card = Card(cat)
            card.body.addWidget(label(intros.get(cat, ""), "muted", wrap=True))
            entries = []
            first = True
            if cat == "Gaming":
                row = TweakRow(self, "Power plan",
                               "Ultimate Performance stops the CPU from saving power, so it ramps up faster.",
                               "Uses more electricity; laptops drain faster and run warmer. Your current plan "
                               "is saved first, so “Restore previous” switches back.",
                               W.get_active_power_plan,
                               [("Ultimate Performance", W.enable_ultimate_power_plan),
                                ("Balanced", W.set_balanced_power_plan),
                                ("Restore previous", W.restore_previous_power_plan)],
                               key="power", targets=(("→ Ultimate", "ultimate"), ("→ Balanced", "balanced")))
                card.body.addWidget(row)
                self.rows.append(row)
                row.search_text = "power plan ultimate performance balanced battery cpu"
                entries.append((row, None))
                first = False
            items = [t for t in T.TWEAKS if getattr(t, "category", "Gaming") == cat]
            items.sort(key=lambda t: 0 if t.level == T.STANDARD else 1)   # safe ones first
            for t in items:
                sep = None
                if not first:
                    sep = _sep()
                    card.body.addWidget(sep)
                first = False
                badges = (["Advanced"] if t.level == T.ADVANCED else []) + \
                         (["Admin"] if t.admin else []) + \
                         (["Restart needed"] if t.restart == "restart" else []) + \
                         (["Sign out needed"] if t.restart == "signout" else [])
                row = TweakRow(self, t.name, t.description, t.tradeoff, t.get_state,
                               [("On", lambda t=t: t.apply(True)), ("Off", lambda t=t: t.apply(False)),
                                ("Undo", t.undo)], badges,
                               key=t.id, targets=(("→ Turn on", True), ("→ Turn off", False)))
                card.body.addWidget(row)
                self.rows.append(row)
                row.search_text = " ".join((t.name, t.description, t.tradeoff, cat, " ".join(badges),
                                            T.KEYWORDS.get(t.id, ""))).lower()
                entries.append((row, sep))
            self.content.addWidget(card)
            self.cards.append((card, entries))

        # ---- Essentials: one-click actions with real results
        ess = Card("Essentials")
        self.ess = ess
        self.ess_text = ("essentials dns cache flush windows update download cache sfc system file checker "
                         "repair scannow corrupt")
        ess.body.addWidget(label("Quick maintenance actions. Each one shows its real result when it finishes.",
                                 "muted", wrap=True))
        self.quick_msg = label("", "cardLine", wrap=True)
        for n, (name, desc, fn) in enumerate((
                ("Clear DNS cache", "Forgets saved website addresses so they're looked up fresh. Can fix "
                 "“site can't be reached” after a DNS change. Harmless.", self.flush_dns),
                ("Clear Windows Update download cache", "Deletes downloaded update files Windows keeps. Can "
                 "fix stuck updates and free space. Shows the size first; Windows re-downloads what it "
                 "still needs. Admin.", self.clear_wu),
                ("Check and repair system files (SFC)", "Runs Windows' System File Checker, which finds and "
                 "repairs damaged Windows files. Takes 5–20 minutes; you can keep using the PC. Admin.",
                 self.run_sfc))):
            if n:
                ess.body.addWidget(_sep())
            r = QHBoxLayout()
            r.setContentsMargins(0, 6, 0, 6)
            col = QVBoxLayout()
            col.addWidget(label(name, "sectionTitle"))
            col.addWidget(label(desc, "cardLine", wrap=True))
            r.addLayout(col, 1)
            b = QPushButton("Run")
            b.clicked.connect(lambda _=False, f=fn, btn=b: f(btn))
            r.addWidget(b, 0, Qt.AlignVCenter)
            ess.body.addLayout(r)
        ess.body.addWidget(self.quick_msg)
        self.content.addWidget(ess)
        self.selection_changed()
        self.finish()

    # ------------------------------------------------------------ Essentials

    def _quick(self, btn, title, fn):
        btn.setEnabled(False)
        self.quick_msg.setText(f"{title}…")

        def done(result):
            btn.setEnabled(True)
            ok, msg = result if isinstance(result, tuple) and len(result) == 2 else (False, str(result))
            self.quick_msg.setText(f"{'✔' if ok else '✖'} {title}: {msg}")
            self.ctx.log_action("Essentials", title, "Success" if ok else "Failed", "" if ok else msg)

        self.run_task(fn, on_done=done)

    def flush_dns(self, btn):
        from core import quick_actions as Q
        self._quick(btn, "Clear DNS cache", Q.flush_dns)

    def clear_wu(self, btn):
        from core import quick_actions as Q
        btn.setEnabled(False)
        self.quick_msg.setText("Measuring the Windows Update download cache…")

        def previewed(res):
            btn.setEnabled(True)
            if not (isinstance(res, tuple) and len(res) == 4):
                self.quick_msg.setText(f"✖ Couldn't read the cache: {res}")
                return
            _ok, size, count, text = res
            if count == 0:
                self.quick_msg.setText("Nothing to clear: " + text)
                return
            if QMessageBox.question(self, "Clear Windows Update download cache",
                                    f"Delete these downloaded update files?\n\n{text}\n\n"
                                    "Windows Update is paused while this runs and started again after. "
                                    "Files in use are skipped.") != QMessageBox.Yes:
                self.quick_msg.setText("Cancelled. Nothing was deleted.")
                return
            self._quick(btn, "Clear Windows Update download cache", Q.clear_wu_cache)

        self.run_task(Q.wu_cache_preview, on_done=previewed)

    def run_sfc(self, btn):
        from core import quick_actions as Q
        if QMessageBox.question(self, "System File Checker",
                                "Run sfc /scannow now? It takes 5–20 minutes and uses some CPU and disk.") \
                != QMessageBox.Yes:
            return
        self._quick(btn, "System File Checker (running, 5–20 min)", Q.sfc_scan)

    # ------------------------------------------------------------ search and presets

    def filter_rows(self, text):
        words = text.lower().split()
        total = 0
        for card, entries in self.cards:
            shown = 0
            for row, sep in entries:
                hit = all(w in row.search_text for w in words)
                row.setVisible(hit)
                if sep is not None:
                    sep.setVisible(hit and shown > 0)
                shown += hit
            # the first visible row never gets a line above it
            card.setVisible(shown > 0)
            total += shown
        ess_hit = all(w in self.ess_text for w in words)
        self.ess.setVisible(ess_hit)
        if words:
            self.match_msg.setText(f"{total} tweak{'s' if total != 1 else ''} match “{text.strip()}”."
                                   + ("" if total or ess_hit else " Try another word."))
        self.match_msg.setVisible(bool(words))

    def _selectable(self):
        return [r for r in self.rows if r.check is not None]

    def selection_changed(self):
        rows = [r for r in self._selectable() if r.selected()]
        n = len(rows)
        if n:
            self.sel_msg.setText(f"{n} tweak{'s' if n != 1 else ''} selected. Review the ticks and On/Off "
                                 "choices below, then press “Apply selected”.")
        else:
            self.sel_msg.setText("No tweaks selected. Tick tweaks below, or pick a preset and press "
                                 "“Select its tweaks”.")
        self.b_apply_sel.setText(f"Apply selected ({n})" if n else "Apply selected")
        self.b_apply_sel.setEnabled(n > 0)
        self.b_clear.setEnabled(n > 0)

    def select_preset(self):
        from core.profiles import preset_selection
        name = self.preset.currentText()
        by_key = {r.key: r for r in self._selectable()}
        self.clear_selection()
        for key, target in preset_selection(name):
            if key in by_key:
                by_key[key].select(target)
        if self.search.text():
            self.search.clear()          # show everything so all ticked tweaks are visible
        self.top_msg.setText(f"Selected the {name} tweaks. Untick any you don't want, or tick more, then "
                             "press “Apply selected”. Nothing has changed yet.")

    def select_shown(self):
        for r in self._selectable():
            if r.isVisible() or not self.search.text():
                r.check.setChecked(True)

    def clear_selection(self):
        for r in self._selectable():
            r.check.setChecked(False)

    def apply_selected(self):
        from core.profiles import apply_selection, selection_preview
        selection = [(r.key, r.target.currentData()) for r in self._selectable() if r.selected()]
        if not selection:
            return
        self.b_apply_sel.setEnabled(False)
        self.top_msg.setText("Checking your current settings…")

        def previewed(items):
            if isinstance(items, tuple):
                self.selection_changed()
                self.top_msg.setText(f"✖ Couldn't read your current settings: {items[1]}")
                return
            change = [(sel, i) for sel, i in zip(selection, items) if i[3]]
            same = [i for i in items if not i[3]]
            if not change:
                self.selection_changed()
                self.top_msg.setText("Everything you selected is already set. Nothing to change.")
                return
            lines = "\n".join(f"• {lbl}: {cur or '?'} → {want}" for _, (lbl, cur, want, _c) in change)
            text = f"Change {len(change)} setting{'s' if len(change) != 1 else ''}?\n\n{lines}"
            if same:
                text += f"\n\nAlready set ({len(same)}): " + ", ".join(i[0] for i in same)
            text += "\n\nEach one can be undone on its row, or all at once with “Undo everything”."
            if QMessageBox.question(self, "Apply selected tweaks", text) != QMessageBox.Yes:
                self.selection_changed()
                self.top_msg.setText("Cancelled. Nothing was changed.")
                return
            self.top_msg.setText("Applying…")
            self.run_task(apply_selection, [sel for sel, _ in change], on_done=applied)

        def applied(results):
            if isinstance(results, tuple):
                results = [("Apply selected", False, results[1])]
            for step, ok, msg in results:
                self.ctx.log_action("Tweaks: apply selected", step, "Success" if ok else "Failed", "" if ok else msg)
            failed = sum(1 for _, ok, _ in results if not ok)
            self.top_msg.setText(f"{len(results) - failed} of {len(results)} changes succeeded.\n"
                                 + "\n".join(f"{'✔' if ok else '✖'}  {s}: {m}" for s, ok, m in results))
            if not failed:
                self.clear_selection()
            self.selection_changed()
            self.on_shown()              # re-read every row from Windows

        self.run_task(selection_preview, selection, on_done=previewed)

    def on_shown(self):
        for row in self.rows:
            self._refresh(row)

    def _refresh(self, row):
        self.run_task(row.get_status, on_done=row.show_status)

    def run(self, row, action_text, fn):
        row.set_busy(True)

        def done(result):
            ok, msg = result
            row.set_busy(False)
            self.ctx.log_action(row.name, action_text, "Success" if ok else "Failed", "" if ok else msg)
            self.top_msg.setText(msg)
            if not ok:
                QMessageBox.warning(self, row.name, msg)
            self._refresh(row)

        self.run_task(fn, on_done=done)

    def restore_point(self):
        self.b_restore.setEnabled(False)
        self.top_msg.setText("Creating a restore point… (can take a minute)")

        def done(result):
            ok, msg = result
            self.b_restore.setEnabled(True)
            self.top_msg.setText(msg)
            self.ctx.log_action("Restore point", "Create", "Success" if ok else "Failed", "" if ok else msg)

        self.run_task(T.create_restore_point, on_done=done)

    def undo_everything(self):
        names = [t.name for t in T.changed_tweaks()]
        listing = "\n".join(f"• {n}" for n in names) or "• (no individual tweaks)"
        if QMessageBox.question(
                self, "Undo everything",
                "Put these back to how they were before RYTWEAKS changed them?\n\n"
                f"{listing}\n• Power plan and DNS, if RYTWEAKS saved them") != QMessageBox.Yes:
            return
        self.b_undo_all.setEnabled(False)
        self.top_msg.setText("Restoring…")

        def done(results):
            self.b_undo_all.setEnabled(True)
            if isinstance(results, tuple):
                results = [("Undo everything", False, results[1])]
            if not results:
                self.top_msg.setText("Nothing to undo: RYTWEAKS hasn't changed anything yet.")
            else:
                ok_count = sum(1 for _, ok, _ in results if ok)
                lines = [f"{'✔' if ok else '✖'} {name}: {msg}" for name, ok, msg in results]
                self.top_msg.setText(f"Restored {ok_count} of {len(results)}.\n" + "\n".join(lines))
                for name, ok, msg in results:
                    self.ctx.log_action(name, "Undo", "Success" if ok else "Failed", "" if ok else msg)
            self.on_shown()

        self.run_task(T.undo_everything, on_done=done)
