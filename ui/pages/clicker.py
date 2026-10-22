# ui/pages/clicker.py
"""Auto clicker: real SendInput clicks, global hotkeys and an always-working emergency stop."""

import sys

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QGridLayout, QHBoxLayout,
                               QPushButton, QSpinBox)

from core import autoclicker as AC
from ui.widgets.common import NA, Card, KeyValueGrid, Notice, Page, label, set_role

PREFIX = "clicker_"
REASONS = {
    "user": "Stopped by you",
    "emergency": "Emergency stop",
    "count": "Reached the click limit",
    "time": "Reached the time limit",
    "error": "Stopped because of an error",
}


class ClickerPage(Page):
    title = "Auto clicker"
    subtitle = "Sends real mouse clicks at the current cursor position, on your command only."

    toggle_requested = Signal()
    emergency_requested = Signal()
    engine_finished = Signal()

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.engine = None
        self.watcher = None
        self._logged_engine = None
        self.windows = sys.platform == "win32"
        s = ctx.settings
        cfg = AC.config_from_dict({k: s.get(PREFIX + k) for k in AC.ClickerConfig().as_dict()})

        self.content.addWidget(Notice(
            "You're responsible for following the rules of each game or service. "
            "Many online games ban auto clickers."))
        if not self.windows:
            self.content.addWidget(Notice("Auto clicking and global hotkeys are Unavailable: "
                                          "they need Windows."))

        # ---- settings
        self.settings_card = Card("Click settings")
        g = QGridLayout()
        g.setHorizontalSpacing(14)
        g.setVerticalSpacing(10)
        self.settings_card.body.addLayout(g)

        self.button = QComboBox()
        self.button.addItems(["Left", "Right", "Middle"])
        self.button.setCurrentText(cfg.button.capitalize())
        self.click_type = QComboBox()
        self.click_type.addItems(["Single click", "Double click"])
        self.click_type.setCurrentIndex(1 if cfg.click_type == "double" else 0)
        self.click_type.setToolTip("A double click sends two clicks per action. "
                                   "Both count towards the click limit.")
        self.speed_mode = QComboBox()
        self.speed_mode.addItems(["Clicks per second (CPS)", "Interval (ms)"])
        self.speed_mode.setCurrentIndex(1 if cfg.speed_mode == "interval" else 0)
        self.cps = QDoubleSpinBox()
        self.cps.setRange(AC.CPS_MIN, AC.CPS_MAX)
        self.cps.setDecimals(1)
        self.cps.setSuffix(" CPS")
        self.cps.setValue(cfg.cps)
        self.cps.setToolTip(f"{AC.CPS_MIN:g} to {AC.CPS_MAX:g} clicks per second.")
        self.interval = QDoubleSpinBox()
        self.interval.setRange(AC.INTERVAL_MIN_MS, AC.INTERVAL_MAX_MS)
        self.interval.setDecimals(0)
        self.interval.setSuffix(" ms")
        self.interval.setValue(cfg.interval_ms)
        self.interval.setToolTip(f"{AC.INTERVAL_MIN_MS} to {AC.INTERVAL_MAX_MS} ms between clicks.")

        rows = [("Mouse button", self.button), ("Click type", self.click_type),
                ("Speed", self.speed_mode), ("CPS", self.cps), ("Interval", self.interval)]
        for r, (text, w) in enumerate(rows):
            g.addWidget(label(text, "muted"), r, 0)
            g.addWidget(w, r, 1)
        g.setColumnStretch(2, 1)

        # random interval
        self.rand_on = QCheckBox("Use a random interval between a minimum and a maximum")
        self.rand_on.setChecked(cfg.random_enabled)
        self.rand_on.setToolTip("When on, each click waits a random time in this range "
                                "instead of the fixed speed above.")
        self.rand_min = QDoubleSpinBox()
        self.rand_max = QDoubleSpinBox()
        for w, v, pre in ((self.rand_min, cfg.random_min_ms, "min "), (self.rand_max, cfg.random_max_ms, "max ")):
            w.setRange(AC.INTERVAL_MIN_MS, AC.INTERVAL_MAX_MS)
            w.setDecimals(0)
            w.setPrefix(pre)
            w.setSuffix(" ms")
            w.setValue(v)
        rr = QHBoxLayout()
        rr.addWidget(self.rand_on)
        rr.addWidget(self.rand_min)
        rr.addWidget(self.rand_max)
        rr.addStretch()
        self.settings_card.body.addLayout(rr)

        # limits and delay
        self.limit_clicks_on = QCheckBox("Stop after")
        self.limit_clicks_on.setChecked(bool(cfg.stop_after_clicks))
        self.limit_clicks = QSpinBox()
        self.limit_clicks.setRange(AC.COUNT_MIN, AC.COUNT_MAX)
        self.limit_clicks.setSuffix(" clicks")
        self.limit_clicks.setValue(int(cfg.stop_after_clicks) or 100)
        self.limit_time_on = QCheckBox("Stop after")
        self.limit_time_on.setChecked(bool(cfg.stop_after_seconds))
        self.limit_time = QSpinBox()
        self.limit_time.setRange(AC.SECONDS_MIN, AC.SECONDS_MAX)
        self.limit_time.setSuffix(" seconds")
        self.limit_time.setValue(int(cfg.stop_after_seconds) or 60)
        self.delay = QDoubleSpinBox()
        self.delay.setRange(AC.DELAY_MIN_S, AC.DELAY_MAX_S)
        self.delay.setDecimals(1)
        self.delay.setSingleStep(0.5)
        self.delay.setSuffix(" s")
        self.delay.setValue(cfg.start_delay_s)
        self.delay.setToolTip(f"Wait this long after Start before the first click "
                              f"({AC.DELAY_MIN_S:g} to {AC.DELAY_MAX_S:g} s).")
        for r, (a, b) in enumerate(((self.limit_clicks_on, self.limit_clicks),
                                    (self.limit_time_on, self.limit_time)), start=0):
            row = QHBoxLayout()
            row.addWidget(a)
            row.addWidget(b)
            row.addStretch()
            self.settings_card.body.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(label("Start delay", "muted"))
        row.addWidget(self.delay)
        row.addStretch()
        self.settings_card.body.addLayout(row)
        self.content.addWidget(self.settings_card)

        # ---- hotkeys
        hk = Card("Hotkeys (work in any window)")
        self.start_key = QComboBox()
        self.stop_key = QComboBox()
        for c in (self.start_key, self.stop_key):
            c.addItems(list(AC.HOTKEY_VKS))
        sk = s.get(PREFIX + "start_key", AC.DEFAULT_START_KEY)
        ek = s.get(PREFIX + "stop_key", AC.DEFAULT_STOP_KEY)
        if AC.validate_hotkeys(sk, ek):
            sk, ek = AC.DEFAULT_START_KEY, AC.DEFAULT_STOP_KEY
        self.start_key.setCurrentText(sk)
        self.stop_key.setCurrentText(ek)
        row = QHBoxLayout()
        row.addWidget(label("Start / stop", "muted"))
        row.addWidget(self.start_key)
        row.addSpacing(16)
        row.addWidget(label("Emergency stop", "muted"))
        row.addWidget(self.stop_key)
        row.addStretch()
        hk.body.addLayout(row)
        self.hk_msg = label("", "cardLine", wrap=True)
        hk.body.addWidget(self.hk_msg)
        self.content.addWidget(hk)

        # ---- control + status
        run = Card("Control")
        row = QHBoxLayout()
        self.btn_start = set_role(QPushButton("Start"), "primary")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        row.addWidget(self.btn_start)
        row.addWidget(self.btn_stop)
        row.addStretch()
        run.body.addLayout(row)
        run.body.addWidget(label(
            "Clicks go to wherever the mouse cursor is. If you press Start with the mouse, the "
            "cursor is on this window: use a start delay or the hotkey to click elsewhere.",
            "muted", wrap=True))
        self.msg = label("", "cardLine", wrap=True)
        run.body.addWidget(self.msg)
        self.stats = KeyValueGrid()
        run.body.addWidget(self.stats)
        self.content.addWidget(run)
        self.finish()

        self.btn_start.clicked.connect(self.start_clicking)
        self.btn_stop.clicked.connect(lambda: self.stop_clicking("user"))
        self.toggle_requested.connect(self._on_toggle)
        self.emergency_requested.connect(lambda: self.stop_clicking("emergency"))
        self.engine_finished.connect(self._on_engine_finished)
        for w in (self.button, self.click_type, self.speed_mode, self.rand_on, self.limit_clicks_on,
                  self.limit_time_on):
            sig = w.currentIndexChanged if isinstance(w, QComboBox) else w.toggled
            sig.connect(lambda *_: self._save_and_sync())
        for w in (self.cps, self.interval, self.rand_min, self.rand_max, self.limit_clicks,
                  self.limit_time, self.delay):
            w.valueChanged.connect(lambda *_: self._save_and_sync())
        self.start_key.currentIndexChanged.connect(lambda *_: self._hotkeys_changed())
        self.stop_key.currentIndexChanged.connect(lambda *_: self._hotkeys_changed())

        self._sync_enabled()
        self._show_stats(None)
        self._timer = QTimer(self)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self._tick)
        self._timer.start()
        self._start_watcher()

    # ------------------------------------------------------------ settings

    def current_config(self):
        return AC.ClickerConfig(
            button=self.button.currentText().lower(),
            click_type="double" if self.click_type.currentIndex() == 1 else "single",
            speed_mode="interval" if self.speed_mode.currentIndex() == 1 else "cps",
            cps=self.cps.value(), interval_ms=self.interval.value(),
            random_enabled=self.rand_on.isChecked(),
            random_min_ms=self.rand_min.value(), random_max_ms=self.rand_max.value(),
            stop_after_clicks=self.limit_clicks.value() if self.limit_clicks_on.isChecked() else 0,
            stop_after_seconds=self.limit_time.value() if self.limit_time_on.isChecked() else 0,
            start_delay_s=self.delay.value())

    def _save_and_sync(self):
        cfg = self.current_config()
        for key, value in cfg.as_dict().items():
            self.ctx.set_setting(PREFIX + key, value)
        self._sync_enabled()

    def _sync_enabled(self):
        interval_mode = self.speed_mode.currentIndex() == 1
        rand = self.rand_on.isChecked()
        self.cps.setEnabled(not interval_mode and not rand)
        self.interval.setEnabled(interval_mode and not rand)
        self.rand_min.setEnabled(rand)
        self.rand_max.setEnabled(rand)
        self.limit_clicks.setEnabled(self.limit_clicks_on.isChecked())
        self.limit_time.setEnabled(self.limit_time_on.isChecked())

    # ------------------------------------------------------------ hotkeys

    def _start_watcher(self):
        if not self.windows:
            self.hk_msg.setText("Hotkeys: Unavailable (need Windows).")
            return
        try:
            self.watcher = AC.HotkeyWatcher(self.start_key.currentText(), self.stop_key.currentText(),
                                            self.toggle_requested.emit, self.emergency_requested.emit)
            self.watcher.start()
            self._show_hotkey_msg()
        except Exception as exc:
            self.watcher = None
            self.hk_msg.setText(f"Hotkeys: Unavailable ({exc}).")

    def _show_hotkey_msg(self):
        self.hk_msg.setText(f"{self.start_key.currentText()} starts or stops clicking. "
                            f"{self.stop_key.currentText()} is the emergency stop and always stops it.")

    def _hotkeys_changed(self):
        sk, ek = self.start_key.currentText(), self.stop_key.currentText()
        errs = AC.validate_hotkeys(sk, ek)
        if errs:
            # Not saved and not applied: the previous working hotkeys stay active
            self.hk_msg.setText(errs[0] + " The previous hotkeys are still active.")
            return
        if self.watcher:
            self.watcher.set_keys(sk, ek)
        self.ctx.set_setting(PREFIX + "start_key", sk)
        self.ctx.set_setting(PREFIX + "stop_key", ek)
        if self.windows and self.watcher:
            self._show_hotkey_msg()

    # ------------------------------------------------------------ running

    def _active(self):
        return bool(self.engine and self.engine.is_active())

    def _on_toggle(self):
        if self._active():
            self.stop_clicking("user")
        else:
            self.start_clicking()

    def start_clicking(self):
        if self._active():
            return
        if not self.windows:
            self.msg.setText("Auto clicking is Unavailable: it needs Windows.")
            return
        cfg = self.current_config()
        errors = AC.validate_config(cfg)
        if errors:
            self.msg.setText("Can't start: " + " ".join(errors))
            return
        try:
            clicker = AC.SendInputClicker()
        except Exception as exc:
            self.msg.setText(f"Can't start: {exc}")
            return
        self.engine = AC.ClickEngine(cfg, clicker, on_finish=lambda e: self.engine_finished.emit())
        self.engine.state = "delay" if cfg.start_delay_s > 0 else "running"
        self.engine.start()
        self.msg.setText("Waiting for the start delay…" if cfg.start_delay_s > 0 else "Clicking.")
        self._set_running(True)

    def stop_clicking(self, reason="user"):
        if self.engine and self.engine.is_active():
            self.engine.stop(reason)

    def _set_running(self, running):
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)
        self.settings_card.setEnabled(not running)

    def _on_engine_finished(self):
        eng = self.engine
        if not eng or eng is self._logged_engine:
            return
        self._logged_engine = eng
        snap = eng.snapshot()
        why = REASONS.get(snap["reason"], "Stopped")
        text = f"{why}. {snap['clicks']} clicks sent."
        if snap["error"]:
            text += f" Error: {snap['error']}"
        self.msg.setText(text)
        self._set_running(False)
        self._show_stats(snap)
        self.ctx.log_action("Auto clicker", f"{eng.cfg.button} {eng.cfg.click_type} click",
                            f"{why}: {snap['clicks']} clicks sent", snap["error"])

    def _tick(self):
        if not self.engine:
            return
        snap = self.engine.snapshot()
        self._show_stats(snap)
        if snap["state"] == "stopped" and self.btn_stop.isEnabled():
            self._on_engine_finished()  # in case the signal was missed

    def _show_stats(self, snap):
        if not snap:
            self.stats.set_rows([("State", "Stopped"), ("Clicks sent", "0"),
                                 ("Elapsed", "0.0 s"), ("Measured speed", NA)])
            return
        state = {"idle": "Stopped", "delay": "Waiting for start delay", "running": "Running",
                 "stopped": "Stopped"}[snap["state"]]
        cps = f"{snap['cps']:.1f} CPS" if snap["cps"] is not None else NA
        self.stats.set_rows([("State", state), ("Clicks sent", f"{snap['clicks']:,}"),
                             ("Elapsed", f"{snap['elapsed']:.1f} s"), ("Measured speed", cps)])

    # ------------------------------------------------------------ shutdown

    def wait_for_tasks(self):
        """App is closing: stop clicking and the hotkey thread; nothing may click afterwards."""
        self._timer.stop()
        if self.engine:
            self.engine.on_finish = None
            self.engine.stop("user")
            self.engine.join(2.0)
        if self.watcher:
            self.watcher.stop()
        super().wait_for_tasks()
