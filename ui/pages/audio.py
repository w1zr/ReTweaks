# ui/pages/audio.py
"""Audio mixer: master volume, output devices, microphone (input) volume and devices,
per-app volume (Windows Core Audio)."""

import os

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QMessageBox, QPushButton, QSlider,
                               QVBoxLayout, QWidget)

from core import audio
from ui.widgets.common import Card, Notice, Page, label, set_role

POLL_MS = 1000


class VolumeRow(QWidget):
    """Name + slider + percent + mute checkbox. Dragging blocks refreshes of this row."""

    def __init__(self, name, on_volume, on_mute, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 2, 0, 2)
        self.name = label(name, "cardLine")
        self.name.setMinimumWidth(180)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.pct = label("0%", "muted")
        self.pct.setMinimumWidth(42)
        self.mute = QCheckBox("Mute")
        lay.addWidget(self.name)
        lay.addWidget(self.slider, 1)
        lay.addWidget(self.pct)
        lay.addWidget(self.mute)
        self._dragging = False
        self.slider.sliderPressed.connect(lambda: setattr(self, "_dragging", True))
        self.slider.sliderReleased.connect(lambda: setattr(self, "_dragging", False))
        self.slider.valueChanged.connect(self._changed)
        self.mute.clicked.connect(lambda checked: on_mute(checked))
        self._on_volume = on_volume
        self._updating = False

    def _changed(self, value):
        self.pct.setText(f"{value}%")
        if not self._updating:
            self._on_volume(value)

    def show_state(self, percent, muted):
        """Apply a polled value, unless the user is interacting with this row."""
        if self._dragging or self.slider.isSliderDown():
            return
        self._updating = True
        try:
            if self.slider.value() != percent:
                self.slider.setValue(percent)
            self.pct.setText(f"{percent}%")
            if self.mute.isChecked() != muted:
                self.mute.setChecked(muted)
        finally:
            self._updating = False


class AudioPage(Page):
    title = "Audio mixer"
    subtitle = ("Master volume, output device, microphone and per-app volume, read live from Windows "
                "Core Audio. Changes made in Windows or in other apps show up here within "
                "a second.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.backend = None
        self.timer = None
        self._device_key = None
        self._session_key = None
        self._sessions = []
        self._master_row = None
        self._input_row = None
        self._input_key = None
        self._session_rows = []
        self._error_shown = False

        if not audio.AVAILABLE:
            self.content.addWidget(Notice(
                f"The audio mixer is unavailable. {audio.UNAVAILABLE_REASON}"))
            self.finish()
            return
        try:
            self.backend = self._make_backend()
        except Exception as exc:
            self.content.addWidget(Notice(f"The audio mixer is unavailable. {exc}"))
            self.finish()
            return

        self.status = label("", "muted", wrap=True)
        self.content.addWidget(self.status)

        # master
        self.master_card = Card("Master volume (default output)")
        self.master_holder = QVBoxLayout()
        self.master_card.body.addLayout(self.master_holder)
        self.content.addWidget(self.master_card)

        # devices
        self.dev_card = Card("Output devices")
        self.dev_holder = QVBoxLayout()
        self.dev_card.body.addLayout(self.dev_holder)
        note = label(
            "Switching the default device uses IPolicyConfig, an undocumented Windows "
            "interface that many audio tools rely on. RYTWEAKS checks afterwards whether "
            "Windows really changed the default and tells you if it did not.",
            "muted", wrap=True)
        self.dev_card.body.addWidget(note)
        btn = QPushButton("Open Windows Sound settings")
        btn.clicked.connect(self._open_sound_settings)
        row = QHBoxLayout()
        row.addWidget(btn)
        row.addStretch(1)
        self.dev_card.body.addLayout(row)
        self.content.addWidget(self.dev_card)

        # input (microphones), v1.5
        self.in_card = Card("Microphone (default input)")
        self.in_master_holder = QVBoxLayout()
        self.in_card.body.addLayout(self.in_master_holder)
        self.in_card.body.addWidget(label("Input devices", "sectionTitle"))
        self.in_holder = QVBoxLayout()
        self.in_card.body.addLayout(self.in_holder)
        self.in_card.body.addWidget(label(
            "Volume and mute here are the same switches as Windows Sound settings → Input, so they "
            "affect every app that uses the microphone (Discord, games, OBS). Switching the default "
            "input uses the same undocumented interface as output switching.", "muted", wrap=True))
        self.content.addWidget(self.in_card)

        # sessions
        self.app_card = Card("App volume")
        self.app_holder = QVBoxLayout()
        self.app_card.body.addLayout(self.app_holder)
        self.app_empty = label(
            "No app is using audio right now. Apps appear here once they play sound.",
            "muted", wrap=True)
        self.app_card.body.addWidget(self.app_empty)
        self.content.addWidget(self.app_card)
        self.finish()

    # overridable for tests
    def _make_backend(self):
        return audio.AudioBackend()

    # ------------------------------------------------------------ lifecycle
    def on_shown(self):
        if self.backend is None:
            return
        self.refresh()
        if self.timer is None:
            self.timer = QTimer(self)
            self.timer.setInterval(POLL_MS)
            self.timer.timeout.connect(self.refresh)
        self.timer.start()

    def hideEvent(self, event):
        if self.timer is not None:
            self.timer.stop()
        super().hideEvent(event)

    def wait_for_tasks(self):
        if self.timer is not None:
            self.timer.stop()
        return super().wait_for_tasks()

    # ------------------------------------------------------------ refresh
    def refresh(self):
        if self.backend is None:
            return
        try:
            self._refresh_devices()
            self._refresh_master()
            self._refresh_input()
            self._refresh_sessions()
            self.status.setText("")
            self._error_shown = False
        except Exception as exc:
            # Device unplugged mid-read, audio service restarting, stale COM object...
            self._device_key = None
            self._input_key = None
            self._session_key = None
            if not self._error_shown:
                self._error_shown = True
            self.status.setText(f"Windows audio is not responding right now ({exc}). "
                                "Trying again every second.")

    def _clear(self, layout):
        while layout.count():
            item = layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
            elif item.layout() is not None:
                self._clear(item.layout())

    def _refresh_devices(self):
        devices = self.backend.devices()
        key = tuple((d.id, d.name, d.is_default) for d in devices)
        if key == self._device_key:
            return
        self._device_key = key
        self._clear(self.dev_holder)
        if not devices:
            self.dev_holder.addWidget(label(
                "No active output device found. Plug in or enable one in Windows.",
                "warn", wrap=True))
            return
        for d in devices:
            row = QHBoxLayout()
            row.addWidget(label(d.name, "cardLine"), 1)
            if d.is_default:
                row.addWidget(label("Default", "good"))
            else:
                b = QPushButton("Set as default")
                b.clicked.connect(lambda _=False, dev=d: self._switch_device(dev))
                row.addWidget(b)
            self.dev_holder.addLayout(row)

    def _refresh_master(self):
        state = self.backend.master_state()
        if state is None:
            if self._master_row is not None:
                self._master_row = None
                self._clear(self.master_holder)
            if self.master_holder.count() == 0:
                self.master_holder.addWidget(label(
                    "No default output device, so there is no master volume to control.",
                    "warn", wrap=True))
            return
        if self._master_row is None:
            self._clear(self.master_holder)
            self._master_row = VolumeRow("Master", self._set_master_volume,
                                         self._set_master_mute)
            self.master_holder.addWidget(self._master_row)
        self._master_row.show_state(*state)

    def _refresh_input(self):
        devices = self.backend.input_devices()
        key = tuple((d.id, d.name, d.is_default) for d in devices)
        if key != self._input_key:
            self._input_key = key
            self._clear(self.in_holder)
            if not devices:
                self.in_holder.addWidget(label(
                    "No active microphone found. Plug one in or enable it in Windows Sound settings.",
                    "warn", wrap=True))
            for d in devices:
                row = QHBoxLayout()
                row.addWidget(label(d.name, "cardLine"), 1)
                if d.is_default:
                    row.addWidget(label("Default", "good"))
                else:
                    b = QPushButton("Set as default")
                    b.clicked.connect(lambda _=False, dev=d: self._switch_device(dev, inp=True))
                    row.addWidget(b)
                self.in_holder.addLayout(row)
        state = self.backend.input_state()
        if state is None:
            if self._input_row is not None or self.in_master_holder.count() == 0:
                self._input_row = None
                self._clear(self.in_master_holder)
                self.in_master_holder.addWidget(label(
                    "No default microphone, so there is no input volume to control.", "warn", wrap=True))
            return
        if self._input_row is None:
            self._clear(self.in_master_holder)
            self._input_row = VolumeRow("Microphone", self._set_input_volume, self._set_input_mute)
            self.in_master_holder.addWidget(self._input_row)
        self._input_row.show_state(*state)

    def _set_input_volume(self, percent):
        try:
            self.backend.set_input_volume(percent)
        except Exception as exc:
            self._fail("Setting the microphone volume", exc)

    def _set_input_mute(self, muted):
        what = "Microphone " + ("mute" if muted else "unmute")
        try:
            self.backend.set_input_mute(muted)
            self.ctx.log_action("Audio mixer", what, "OK")
        except Exception as exc:
            self.ctx.log_action("Audio mixer", what, "Failed", str(exc))
            self._fail("Changing microphone mute", exc)

    def _refresh_sessions(self):
        sessions = self.backend.sessions()
        key = audio.sessions_key(sessions)
        if key != self._session_key:
            self._session_key = key
            self._sessions = sessions
            self._clear(self.app_holder)
            self._session_rows = []
            for s in sessions:
                name = s.name if s.active else f"{s.name} (idle)"
                r = VolumeRow(name,
                              lambda v, info=s: self._set_session_volume(info, v),
                              lambda m, info=s: self._set_session_mute(info, m))
                r.show_state(s.volume, s.muted)
                self.app_holder.addWidget(r)
                self._session_rows.append(r)
            self.app_empty.setVisible(not sessions)
            return
        # same sessions: just refresh values from fresh handles
        self._sessions = sessions
        for r, s in zip(self._session_rows, sessions):
            r.show_state(s.volume, s.muted)
        # keep callbacks pointing at the newest handles
        for r, s in zip(self._session_rows, sessions):
            r._on_volume = lambda v, info=s: self._set_session_volume(info, v)

    # ------------------------------------------------------------ actions
    def _fail(self, what, exc):
        self.status.setText(f"{what} failed: {exc}")
        self._device_key = None
        self._input_key = None
        self._session_key = None

    def _set_master_volume(self, percent):
        try:
            self.backend.set_master_volume(percent)
        except Exception as exc:
            self._fail("Setting the master volume", exc)

    def _set_master_mute(self, muted):
        try:
            self.backend.set_master_mute(muted)
            self.ctx.log_action("Audio mixer",
                                "Master " + ("mute" if muted else "unmute"), "OK")
        except Exception as exc:
            self.ctx.log_action("Audio mixer",
                                "Master " + ("mute" if muted else "unmute"), "Failed", str(exc))
            self._fail("Changing master mute", exc)

    def _session_info(self, info):
        # find the newest handle for the same session
        for s in self._sessions:
            if (s.pid, s.identifier) == (info.pid, info.identifier):
                return s
        return info

    def _set_session_volume(self, info, percent):
        try:
            self.backend.set_session_volume(self._session_info(info), percent)
        except Exception as exc:
            self._fail(f"Setting the volume of {info.name}", exc)

    def _set_session_mute(self, info, muted):
        what = f"{info.name} " + ("mute" if muted else "unmute")
        try:
            self.backend.set_session_mute(self._session_info(info), muted)
            self.ctx.log_action("Audio mixer", what, "OK")
        except Exception as exc:
            self.ctx.log_action("Audio mixer", what, "Failed", str(exc))
            self._fail(f"Changing mute for {info.name}", exc)

    def _switch_device(self, dev, inp=False):
        kind = "input" if inp else "output"
        ok = QMessageBox.question(
            self, f"Switch default {kind}",
            f"Make \"{dev.name}\" the default {kind} device?\n\n"
            "This uses an undocumented Windows interface (IPolicyConfig). If it fails, "
            "use Windows Sound settings.")
        if ok != QMessageBox.Yes:
            return
        requested = f"Set default {kind} to {dev.name}"
        try:
            success, msg = (self.backend.set_default_input(dev.id) if inp
                            else self.backend.set_default_device(dev.id))
        except Exception as exc:
            success, msg = False, str(exc)
        self.ctx.log_action("Audio mixer", requested, "OK" if success else "Failed",
                            "" if success else msg)
        self.status.setText(msg)
        self._device_key = None
        self._input_key = None
        self.refresh()
        if not success:
            self.status.setText(msg + " Switch the default device in Windows Sound settings.")

    def _open_sound_settings(self):
        try:
            os.startfile("ms-settings:sound")  # Windows only
        except Exception:
            QDesktopServices.openUrl(QUrl("ms-settings:sound"))
