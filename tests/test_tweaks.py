"""Tweak backup/undo logic with a fake registry (runs on any OS)."""
import core.tweaks as tw


class FakeReg:
    def __init__(self):
        self.d = {}

    def get(self, path, name):
        return self.d.get((path, name))

    def set(self, path, name, typ, data):
        self.d[(path, name)] = (typ, data)

    def delete(self, path, name):
        self.d.pop((path, name), None)


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    fake = FakeReg()
    monkeypatch.setattr(tw, "REG", fake)
    return fake


def test_undo_restores_exact_previous_values(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    t = tw.BY_ID["transparency"]
    key = list(t.values_on)[0]
    reg.set(*key, tw.REG_DWORD, 1)
    assert t.get_state() == "On"
    assert t.apply(False)[0] and t.get_state() == "Off"
    t.apply(True)
    t.apply(False)                       # second change must NOT overwrite the original backup
    assert t.undo()[0]
    assert reg.get(*key) == (tw.REG_DWORD, 1)
    assert not t.undo()[0]               # nothing left to undo


def test_undo_deletes_values_that_did_not_exist(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    t = tw.BY_ID["xbox_capture"]
    assert t.get_state() == "Windows default"
    t.apply(False)
    assert len(reg.d) == 3
    t.undo()
    assert reg.d == {}


def test_windowed_games_keeps_other_directx_options(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    reg.set(tw.DX_PATH, tw.DX_NAME, tw.REG_SZ, "VRROptimizeEnable=0;")
    t = tw.BY_ID["windowed_games"]
    t.apply(True)
    assert reg.get(tw.DX_PATH, tw.DX_NAME)[1] == "VRROptimizeEnable=0;SwapEffectUpgradeEnable=1;"
    assert t.get_state() == "On"
    t.undo()
    assert reg.get(tw.DX_PATH, tw.DX_NAME)[1] == "VRROptimizeEnable=0;"


def test_set_dx_option_replaces_existing():
    assert tw.set_dx_option("SwapEffectUpgradeEnable=0;A=1;", "SwapEffectUpgradeEnable", "1") == \
        "SwapEffectUpgradeEnable=1;A=1;"


def test_accessibility_only_flips_shortcut_bit(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    t = tw.BY_ID["sticky_keys_popup"]
    sticky = (tw.ACCESS + "\\StickyKeys", "Flags")
    reg.set(*sticky, tw.REG_SZ, "511")            # user has Sticky Keys itself turned ON
    t.apply(False)
    assert reg.get(*sticky)[1] == "507"           # 511 & ~4: feature stays on, shortcut off
    t.undo()
    assert reg.get(*sticky)[1] == "511"


def test_hibernation_undo_when_value_was_missing_turns_it_back_on(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    t = tw.BY_ID["hibernation"]
    calls = []
    monkeypatch.setattr(t, "_run", lambda on: calls.append(on))
    t.apply(False)
    t.undo()
    assert calls == [False, True]
