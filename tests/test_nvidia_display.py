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


class FakeDialog:
    result = True

    def __init__(self, *a, **k):
        pass

    def exec(self):
        from PySide6.QtWidgets import QDialog
        return QDialog.Accepted if FakeDialog.result else QDialog.Rejected


@pytest.mark.parametrize("keep", [True, False])
def test_stretch_flow_adds_mode_then_applies(monkeypatch, keep):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    from core import display as dsp
    from ui.pages import display as page_mod
    monkeypatch.setattr(nvd, "NvApi", FakeNv)
    FakeDialog.result = keep
    monkeypatch.setattr(page_mod, "KeepSettingsDialog", FakeDialog)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: None))
    d = {"device": "\\\\.\\DISPLAY1", "width": 1920, "height": 1080, "bpp": 32, "hz": 165, "max_hz": 165,
         "modes": [(1920, 1080, 32, 165)]}
    added = dict(d, modes=d["modes"] + [(1720, 1080, 32, 165)])
    monkeypatch.setattr(dsp, "list_displays", lambda: [added])
    calls = []
    monkeypatch.setattr(dsp, "set_resolution", lambda dev, w, h, hz, stretch, persist: (calls.append((w, h, hz, persist)), (True, "ok"))[1])
    monkeypatch.setattr(dsp, "restore_saved_mode", lambda dev: (calls.append("restore"), (True, "back"))[1])

    class Ctx:
        settings = {}
        static = {}
        logs = []
        def log_action(self, *a): self.logs.append(a)

    page = page_mod.DisplayPage(Ctx())
    monkeypatch.setattr(page, "refresh", lambda: None)
    page._stretch(d, 1720, 1080, None)
    assert ("try", 1720, 1080, 1920) in FakeNv.calls     # source 1720x1080, native 1920-wide timing
    if keep:
        assert ("save", 7) in FakeNv.calls
        assert (1720, 1080, 165, False) in calls and (1720, 1080, 165, True) in calls   # trial, then saved
    else:
        assert ("revert", 7) in FakeNv.calls and not any(isinstance(c, tuple) for c in calls)
    app.processEvents()


def test_stretch_existing_mode_skips_nvidia(monkeypatch):
    pytest.importorskip("PySide6")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication, QMessageBox
    app = QApplication.instance() or QApplication([])
    from core import display as dsp
    from ui.pages import display as page_mod
    FakeNv.calls = []
    monkeypatch.setattr(nvd, "NvApi", FakeNv)
    FakeDialog.result = False                            # not confirmed in time -> back to saved mode
    monkeypatch.setattr(page_mod, "KeepSettingsDialog", FakeDialog)
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.Yes))
    calls = []
    monkeypatch.setattr(dsp, "set_resolution", lambda dev, w, h, hz, stretch, persist: (calls.append(persist), (True, "ok"))[1])
    monkeypatch.setattr(dsp, "restore_saved_mode", lambda dev: (calls.append("restore"), (True, "back"))[1])

    class Ctx:
        settings = {}
        static = {}
        def log_action(self, *a): pass

    page = page_mod.DisplayPage(Ctx())
    monkeypatch.setattr(page, "refresh", lambda: None)
    page._stretch({"device": "D1", "width": 1920, "height": 1080, "modes": []}, 1720, 1080, 144)
    assert FakeNv.calls == [] and calls == [False, "restore"]
    app.processEvents()
