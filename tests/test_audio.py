# tests/test_audio.py
from core import audio


def test_clamp_percent():
    assert audio.clamp_percent(-5) == 0
    assert audio.clamp_percent(150) == 100
    assert audio.clamp_percent(42.6) == 43
    assert audio.clamp_percent(None) == 0
    assert audio.clamp_percent("abc") == 0
    assert audio.clamp_percent(float("nan")) == 0
    assert audio.clamp_percent("55") == 55


def test_percent_scalar_roundtrip():
    assert audio.percent_to_scalar(0) == 0.0
    assert audio.percent_to_scalar(100) == 1.0
    assert audio.percent_to_scalar(250) == 1.0
    assert audio.percent_to_scalar(50) == 0.5
    for p in range(0, 101):
        assert audio.scalar_to_percent(audio.percent_to_scalar(p)) == p


def test_scalar_to_percent_edges():
    assert audio.scalar_to_percent(0.504) == 50
    assert audio.scalar_to_percent(-1) == 0
    assert audio.scalar_to_percent(3) == 100
    assert audio.scalar_to_percent(None) == 0


def test_session_label():
    assert audio.session_label(0, "", "") == "System sounds"
    assert audio.session_label(10, "spotify.exe", "x") == "spotify.exe"
    assert audio.session_label(10, "", "Chrome") == "Chrome"
    assert audio.session_label(10, "", "") == "Process 10"


def test_sessions_key():
    a = audio.SessionInfo(1, "a", "n", 10, False, True, None)
    b = audio.SessionInfo(2, "b", "m", 20, True, False, None)
    assert audio.sessions_key([a, b]) == ((1, "a"), (2, "b"))
    assert audio.sessions_key([]) == ()


def test_unavailable_off_windows():
    import sys
    if sys.platform != "win32":
        assert audio.AVAILABLE is False
        assert audio.UNAVAILABLE_REASON


class FakeBackend:
    """Stands in for Windows Core Audio so the page logic runs on any OS."""

    def __init__(self):
        self.out = [audio.DeviceInfo("o1", "Speakers", True), audio.DeviceInfo("o2", "Headset", False)]
        self.inp = [audio.DeviceInfo("i1", "USB Mic", True), audio.DeviceInfo("i2", "Webcam Mic", False)]
        self.master, self.mic = [50, False], [70, False]
        self.calls = []

    def devices(self): return self.out
    def master_state(self): return tuple(self.master)
    def input_devices(self): return self.inp
    def input_state(self): return tuple(self.mic) if any(d.is_default for d in self.inp) else None
    def sessions(self): return []
    def set_master_volume(self, p): self.master[0] = p
    def set_master_mute(self, m): self.master[1] = m
    def set_input_volume(self, p): self.calls.append(("in_vol", p)); self.mic[0] = p
    def set_input_mute(self, m): self.calls.append(("in_mute", m)); self.mic[1] = m

    def set_default_input(self, dev_id):
        self.calls.append(("default_in", dev_id))
        for d in self.inp:
            d.is_default = d.id == dev_id
        return True, "Default input device changed."

    def set_default_device(self, dev_id, flow=0):
        self.calls.append(("default_out", dev_id))
        return True, "Default output device changed."


def test_microphone_card(monkeypatch):
    import pytest
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    from ui.pages import audio as page_mod
    monkeypatch.setattr(page_mod.audio, "AVAILABLE", True)
    fake = FakeBackend()
    monkeypatch.setattr(page_mod.AudioPage, "_make_backend", lambda self: fake)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))

    class Ctx:
        settings = {}
        logs = []
        def log_action(self, *a): self.logs.append(a)

    ctx = Ctx()
    p = page_mod.AudioPage(ctx)
    p.refresh()
    assert p._input_row is not None and p._input_row.slider.value() == 70
    p._input_row.slider.setValue(35)                      # user drags the mic slider
    assert ("in_vol", 35) in fake.calls
    p._set_input_mute(True)
    assert ("in_mute", True) in fake.calls and ctx.logs[-1][1] == "Microphone mute"
    p._switch_device(fake.inp[1], inp=True)
    assert ("default_in", "i2") in fake.calls and fake.inp[1].is_default
    assert ctx.logs[-1][1] == "Set default input to Webcam Mic"
    fake.inp = []                                          # mic unplugged
    p.refresh()
    assert p._input_row is None
    app.processEvents()


def test_lock_switches(monkeypatch):
    import pytest
    pytest.importorskip("PySide6")
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.pages import audio as page_mod
    monkeypatch.setattr(page_mod.audio, "AVAILABLE", True)
    fake = FakeBackend()
    monkeypatch.setattr(page_mod.AudioPage, "_make_backend", lambda self: fake)

    class Ctx:
        settings = {}
        logs = []
        locks = {"output": None, "input": None}
        def log_action(self, *a): self.logs.append(a)
        def lock_value(self, k): return self.locks[k]
        def set_volume_lock(self, k, p): self.locks[k] = p

    ctx = Ctx()
    p = page_mod.AudioPage(ctx)
    p.refresh()
    assert p._input_row.lock is not None and not p._input_row.lock.isChecked()
    p._input_row.lock.click()                      # lock the mic at its current 70%
    assert ctx.locks["input"] == 70 and "locked at 70%" in p.status.text()
    p._input_row.slider.setValue(85)               # moving the locked slider moves the lock
    assert ctx.locks["input"] == 85 and fake.mic[0] == 85
    p._input_row.lock.click()
    assert ctx.locks["input"] is None
    p._master_row.lock.click()
    assert ctx.locks["output"] == 50
    app.processEvents()
