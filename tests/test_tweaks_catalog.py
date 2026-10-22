"""v1.4.3 tweak catalog, presets and quick actions."""
import core.tweaks as tw
from core import profiles, quick_actions
from core.tweaks_catalog import CATEGORY_ORDER


class FakeReg:
    def __init__(self):
        self.d = {}
        self.deleted_keys = []

    def get(self, path, name):
        return self.d.get((path, name))

    def set(self, path, name, typ, data):
        self.d[(path, name)] = (typ, data)

    def delete(self, path, name):
        self.d.pop((path, name), None)

    def delete_key(self, path):
        self.deleted_keys.append(path)


def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    fake = FakeReg()
    monkeypatch.setattr(tw, "REG", fake)
    return fake


def test_catalog_ids_unique_and_documented():
    ids = [t.id for t in tw.TWEAKS]
    assert len(ids) == len(set(ids))
    assert len(ids) >= 44
    for t in tw.TWEAKS:
        assert t.category in CATEGORY_ORDER, t.id
        assert len(t.description) > 20 and len(t.tradeoff) > 10, t.id
    for cat in CATEGORY_ORDER:
        assert any(t.category == cat for t in tw.TWEAKS), cat


def test_service_tweaks_need_admin_restart_and_undo_exactly(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    for t in [t for t in tw.TWEAKS if t.category == "Services"]:
        assert t.admin and t.restart == "restart" and t.level == tw.ADVANCED
        key = list(t.values_off)[0]
        reg.set(*key, tw.REG_DWORD, 3)               # some original start type
        assert t.apply(False)[0]
        assert reg.get(*key) == (tw.REG_DWORD, 4)    # Disabled
        assert t.undo()[0]
        assert reg.get(*key) == (tw.REG_DWORD, 3)    # exact original back


def test_classic_menu_on_off_undo(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    t = tw.BY_ID["classic_menu"]
    assert t.get_state() == "Off"
    assert t.apply(True)[0] and t.get_state() == "On"
    assert t.undo()[0] and t.get_state() == "Off"
    assert reg.deleted_keys                          # the empty handler key was removed again


def test_privacy_tweak_roundtrip(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    t = tw.BY_ID["ad_id"]
    assert t.apply(False)[0] and t.get_state() == "Off"
    assert t.undo()[0]
    assert reg.d == {}                               # value didn't exist before, so it's removed


def test_presets_exist_and_run_every_step(monkeypatch):
    for name in ("Esports", "Max FPS", "Balanced", "Privacy", "Max Performance", "Windows Default"):
        assert name in profiles.PROFILES
    calls = []
    monkeypatch.setitem(profiles.PROFILES, "Test", {"description": "x", "steps": [
        ("a", lambda: calls.append("a") or (True, "ok")),
        ("b", lambda: 1 / 0),
        ("c", lambda: calls.append("c") or (True, "ok"))]})
    res = profiles.apply_profile("Test")
    assert calls == ["a", "c"] and res[1][1] is False   # one failure doesn't stop the rest


def test_privacy_preset_turns_settings_off(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    res = profiles.apply_profile("Privacy")
    assert all(ok for _, ok, _ in res)
    assert tw.BY_ID["ad_id"].get_state() == "Off"
    assert tw.BY_ID["diag_data"].get_state() == "Off"
    assert reg.d


def test_wu_cache_preview_counts_files(tmp_path, monkeypatch):
    d = tmp_path / "SoftwareDistribution" / "Download" / "sub"
    d.mkdir(parents=True)
    (d / "a.cab").write_bytes(b"x" * 2048)
    (d.parent / "b.cab").write_bytes(b"x" * 1024)
    monkeypatch.setenv("SystemRoot", str(tmp_path))
    ok, size, count, msg = quick_actions.wu_cache_preview()
    assert ok and size == 3072 and count == 2 and "2 files" in msg


def test_wu_cache_preview_missing_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemRoot", str(tmp_path / "nope"))
    ok, size, count, _ = quick_actions.wu_cache_preview()
    assert ok and size == 0 and count == 0


def test_sfc_parsing_handles_utf16_spacing(monkeypatch):
    class R:
        returncode = 0
        stderr = ""
        stdout = "W\x00i\x00n\x00d\x00o\x00w\x00s\x00 Resource Protection did not\n find any integrity violations."
    monkeypatch.setattr(quick_actions, "IS_WINDOWS", True)
    monkeypatch.setattr(quick_actions, "run", lambda *a, **k: R())
    ok, msg = quick_actions.sfc_scan()
    assert ok and "No problems" in msg
    R.stdout = "Windows Resource Protection found corrupt files but was unable to fix some of them."
    ok, msg = quick_actions.sfc_scan()
    assert not ok and "DISM" in msg


def test_every_preset_uses_real_individual_tweaks():
    for name, p in profiles.PRESETS.items():
        assert p["tweaks"], name
        for tid, on in p["tweaks"].items():
            assert tid in tw.BY_ID and isinstance(on, bool), (name, tid)
        assert p.get("power") in (None, "ultimate", "balanced")
    for name in ("Esports", "Max FPS", "Balanced", "Low-end PC", "High quality", "Ultra quality",
                 "Streamer", "Privacy", "Max Performance", "Windows Default"):
        assert name in profiles.PROFILES


def test_preview_reports_only_real_changes(tmp_path, monkeypatch):
    setup(tmp_path, monkeypatch)
    monkeypatch.setattr(profiles.W, "get_active_power_plan", staticmethod(lambda: "Balanced"))
    items = profiles.preview("Streamer")
    by = {lbl: (cur, want, ch) for lbl, cur, want, ch in items}
    assert by["Ultimate Performance power plan"] == ("Balanced", "Ultimate Performance", True)
    assert by["Notification banners"][1] == "Off" and by["Notification banners"][2]
    tw.BY_ID["notification_banners"].apply(False)
    by = {lbl: (cur, want, ch) for lbl, cur, want, ch in profiles.preview("Streamer")}
    assert by["Notification banners"] == ("Off", "Off", False)


def test_applying_a_preset_then_undo_everything_restores(tmp_path, monkeypatch):
    reg = setup(tmp_path, monkeypatch)
    monkeypatch.setattr(profiles.W, "enable_ultimate_power_plan", staticmethod(lambda: (True, "ok")))
    res = profiles.apply_profile("Max FPS")
    assert all(ok for _, ok, _ in res), res
    assert tw.BY_ID["transparency"].get_state() == "Off"
    for t in tw.changed_tweaks():
        assert t.undo()[0]
    assert reg.d == {}                      # nothing existed before, so everything is removed again


def test_new_tweaks_and_search_keywords():
    for tid in ("power_throttling", "mmcss_reserve", "notification_banners", "narrator_shortcut",
                "edge_background", "key_repeat_fast", "game_bar_button", "recall", "clock_seconds"):
        assert tid in tw.BY_ID
    mm = tw.BY_ID["mmcss_reserve"]
    assert list(mm.values_off.values())[0][1] == 10      # Microsoft's minimum (below 10 is clamped to 20)
    for tid in tw.KEYWORDS:
        assert tid in tw.BY_ID
    assert "sticky" in tw.KEYWORDS["sticky_keys_popup"]
