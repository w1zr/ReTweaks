"""NVIDIA custom resolution (v1.5): struct layouts match NVIDIA's nvapi.h (sizes checked by compiling
the SDK's own definitions: NV_TIMINGEXT 64, NV_TIMING 96, NV_TIMING_INPUT 32, NV_CUSTOM_DISPLAY 144),
and the Keep/Revert flow, using fakes so it runs on any OS."""
import ctypes
import os

import pytest

from core import nvidia_display as nvd


def test_struct_sizes_and_offsets_match_nvapi_h():
    assert ctypes.sizeof(nvd.NV_TIMINGEXT) == 64
    assert ctypes.sizeof(nvd.NV_TIMING) == 96
    assert nvd.NV_TIMING.pclk.offset == 28 and nvd.NV_TIMING.etc.offset == 32
    assert ctypes.sizeof(nvd.NV_TIMING_INPUT) == 32 and nvd.NV_TIMING_INPUT.type.offset == 28
    assert ctypes.sizeof(nvd.NV_CUSTOM_DISPLAY) == 144
    assert nvd.NV_CUSTOM_DISPLAY.xRatio.offset == 36 and nvd.NV_CUSTOM_DISPLAY.timing.offset == 44


def test_version_and_custom_display():
    assert nvd.make_version(nvd.NV_CUSTOM_DISPLAY, 1) == 144 | (1 << 16)
    t = nvd.NV_TIMING(HVisible=1920, VVisible=1080, HTotal=2080, VTotal=1111, pclk=38100)
    cd = nvd.build_custom(1720, 1080, t)
    assert (cd.width, cd.height, cd.depth) == (1720, 1080, 32)
    assert cd.timing.HVisible == 1920                     # output stays the monitor's native timing
    assert (cd.srcPartition.w, cd.srcPartition.h, cd.xRatio) == (1.0, 1.0, 1.0)


def test_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(nvd.sys, "platform", "linux")
    with pytest.raises(OSError):
        nvd.NvApi()


class FakeNv:
    calls = []

    def __init__(self):
        FakeNv.calls = []

    def display_id(self, name):
        FakeNv.calls.append(("id", name))
        return 7

    def timing(self, did, w, h, hz):
        FakeNv.calls.append(("timing", w, h, hz))
        return nvd.NV_TIMING(HVisible=w, VVisible=h, pclk=1)

    def try_custom(self, did, cd):
        FakeNv.calls.append(("try", cd.width, cd.height, cd.timing.HVisible))

    def save_custom(self, did):
        FakeNv.calls.append(("save", did))

    def revert_trial(self, did):
        FakeNv.calls.append(("revert", did))


@pytest.mark.parametrize("keep", [True, False])
def test_setup_flow(monkeypatch, keep):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
    app = QApplication.instance() or QApplication([])
    from core import display
    from ui.pages import games
    monkeypatch.setattr(nvd, "NvApi", FakeNv)
    monkeypatch.setattr(nvd, "primary_display", lambda: ("\\\\.\\DISPLAY1", 1920, 1080, 165))
    restored = []
    monkeypatch.setattr(display, "restore_saved_mode", lambda dev: (restored.append(dev), (True, "Desktop back."))[1])
    monkeypatch.setattr(display, "stretch_mode_status", lambda w, h: (False, None, "missing"))
    monkeypatch.setattr(games.gp, "game_running", lambda gid: False)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(games.KeepDialog, "exec", lambda self: QDialog.Accepted if keep else QDialog.Rejected)

    class Ctx:
        settings = {}
        logs = []
        def log_action(self, *a): self.logs.append(a)

    page = games.GamesPage(Ctx())
    page.nvidia_setup()
    assert ("try", 1720, 1080, 1920) in FakeNv.calls
    if keep:
        assert ("save", 7) in FakeNv.calls and restored == ["\\\\.\\DISPLAY1"]
        assert "added to your NVIDIA card" in page.msg.text()
    else:
        assert ("revert", 7) in FakeNv.calls and not any(c[0] == "save" for c in FakeNv.calls)
    app.processEvents()


def test_keep_dialog_counts_down_and_reverts():
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from ui.pages.games import KeepDialog
    d = KeepDialog(None, 1720, 1080)
    assert "15 seconds" in d.text.text()
    for _ in range(KeepDialog.SECONDS):
        d._tick()
    assert d.result() == 0 and not d.timer.isActive()        # rejected = switch back
    app.processEvents()


def test_setup_skipped_when_mode_exists(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from core import display
    from ui.pages import games
    monkeypatch.setattr(nvd, "NvApi", FakeNv)
    monkeypatch.setattr(display, "stretch_mode_status", lambda w, h: (True, 165, "ok"))
    monkeypatch.setattr(games.gp, "game_running", lambda gid: False)
    FakeNv.calls = []

    class Ctx:
        settings = {}
        def log_action(self, *a): pass

    page = games.GamesPage(Ctx())
    page.nvidia_setup()
    assert FakeNv.calls == [] and "already offers" in page.stretch_check.text()
    app.processEvents()
