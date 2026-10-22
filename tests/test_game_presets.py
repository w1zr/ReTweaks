import os
import stat

import core.game_presets as gp

FORTNITE = (
    "[/Script/FortniteGame.FortGameUserSettings]\r\n"
    "bUseVSync=True\r\n"
    "FrameRateLimit=60.000000\r\n"
    "[ScalabilityGroups]\r\n"
    "sg.ResolutionQuality=50.773800\r\n"
    "sg.ShadowQuality=3\r\n"
)
MC = "version:3955\nrenderDistance:12\ngraphicsMode:1\nkey_key.attack:key.mouse.left\n"
APEX = '"VideoConfig"\n{\n\t"setting.csm_enabled"\t\t"1"\n\t"setting.r_lod_switch_scale"\t"1.000000"\n}\n'


def test_ini_keeps_style_line_endings_and_other_lines():
    new, applied, skipped = gp.FORMATS["ini"].write(
        FORTNITE, {"bUseVSync": "False", "sg.ResolutionQuality": 100, "sg.ShadowQuality": 0, "NotThere": 1})
    assert "bUseVSync=False\r\n" in new
    assert "sg.ResolutionQuality=100.000000\r\n" in new          # same decimals as before
    assert "FrameRateLimit=60.000000\r\n" in new                 # untouched
    assert new.count("\r\n") == FORTNITE.count("\r\n")
    assert skipped == ["NotThere"] and applied["sg.ShadowQuality"] == ("3", "0")


def test_colon_format_minecraft():
    fmt = gp.FORMATS["colon"]
    assert fmt.parse(MC)["renderDistance"] == "12"
    new, applied, skipped = fmt.write(MC, {"renderDistance": 6, "graphicsPreset": "fast"})
    assert "renderDistance:6\n" in new and "key_key.attack:key.mouse.left" in new
    assert skipped == ["graphicsPreset"]                        # never added if missing


def test_keyvalues_format_apex():
    fmt = gp.FORMATS["kv"]
    assert fmt.parse(APEX)["setting.csm_enabled"] == "1"
    new, applied, _ = fmt.write(APEX, {"setting.csm_enabled": 0, "setting.r_lod_switch_scale": 0.8})
    assert '\t"setting.csm_enabled"\t\t"0"\n' in new
    assert '"setting.r_lod_switch_scale"\t"0.800000"' in new


def test_detect_format():
    assert gp.detect_format(APEX) == "kv"
    assert gp.detect_format(MC) == "colon"
    assert gp.detect_format(FORTNITE) == "ini"


def test_apply_backs_up_and_keeps_utf16_and_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(gp, "game_running", lambda gid: False)
    f = tmp_path / "GameUserSettings.ini"
    f.write_bytes(FORTNITE.encode("utf-16"))
    os.chmod(f, stat.S_IREAD)                                    # user locked it
    ok, msg, applied, skipped = gp.apply_changes("fortnite", str(f), "ini", {"sg.ShadowQuality": 0})
    assert ok, msg
    assert f.read_bytes().startswith(b"\xff\xfe")                 # still UTF-16
    assert "sg.ShadowQuality=0" in f.read_bytes().decode("utf-16")
    assert gp.is_read_only(str(f))                               # lock kept
    backups = gp.list_backups("fortnite")
    assert len(backups) == 2                                     # the pinned original + this change
    assert all("sg.ShadowQuality=3" in b["file"].read_bytes().decode("utf-16") for b in backups)
    original = next(b for b in backups if b["pinned"])
    os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    ok, _ = gp.restore_backup("fortnite", original)
    assert ok and "sg.ShadowQuality=3" in f.read_bytes().decode("utf-16")


def test_refuses_while_game_running(tmp_path, monkeypatch):
    monkeypatch.setattr(gp, "game_running", lambda gid: True)
    f = tmp_path / "options.txt"
    f.write_text(MC)
    ok, msg, _, _ = gp.apply_changes("minecraft_java", str(f), "colon", {"renderDistance": 6})
    assert not ok and "Close the game" in msg and "renderDistance:12" in f.read_text()


def test_every_builtin_tier_is_complete():
    for g in gp.GAMES:
        assert set(g.presets) == set(gp.TIERS), g.id


def test_original_backup_is_never_pruned(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    monkeypatch.setattr(gp, "game_running", lambda gid: False)
    f = tmp_path / "options.txt"
    f.write_text("renderDistance:12\n")
    for i in range(15):
        gp.apply_changes("minecraft_java", str(f), "colon", {"renderDistance": 2 + i})
    backups = gp.list_backups("minecraft_java")
    assert len(backups) == gp.MAX_BACKUPS + 1
    original = next(b for b in backups if b["pinned"])
    assert original["file"].read_text() == "renderDistance:12\n"


def test_quoted_values_stay_quoted():
    new, applied, _ = gp.FORMATS["colon"].write('renderClouds:"true"\nmaxFps:120\n',
                                                {"renderClouds": "false", "maxFps": 260})
    assert 'renderClouds:"false"' in new and "maxFps:260" in new


# ---------------------------------------------------------------- v1.4 preset management
import json as _json

import pytest as _pytest


@_pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


def test_old_presets_still_load(store):
    (store / "RYTWEAKS").mkdir()
    (store / "RYTWEAKS" / "custom_presets.json").write_text(
        _json.dumps({"files": [], "presets": {"fortnite": {"Mine": {"bUseVSync": "False"}}}}))
    assert gp.user_presets("fortnite") == {"Mine": {"bUseVSync": "False"}}


def test_rename_duplicate_delete_and_clash(store):
    assert gp.save_user_preset("fortnite", "A", {"bUseVSync": "False"})[0] == "ok"
    assert gp.save_user_preset("fortnite", "A", {"bUseVSync": "True"})[0] == "clash"
    assert gp.user_presets("fortnite")["A"] == {"bUseVSync": "False"}      # not overwritten
    assert gp.duplicate_preset("fortnite", "A", "B")[0] == "ok"
    assert gp.rename_user_preset("fortnite", "B", "A")[0] == "clash"
    assert gp.rename_user_preset("fortnite", "B", "C")[0] == "ok"
    assert set(gp.user_presets("fortnite")) == {"A", "C"}
    assert gp.save_user_preset("fortnite", "A", {"bUseVSync": "True"}, replace=True)[0] == "ok"
    assert gp.delete_user_preset("fortnite", "C") and not gp.delete_user_preset("fortnite", "C")


def test_duplicate_builtin_is_a_copy(store):
    assert gp.duplicate_preset("fortnite", "Ultra", "My ultra")[0] == "ok"
    copy = gp.user_presets("fortnite")["My ultra"]
    assert copy == gp.BY_ID["fortnite"].presets["Ultra"]
    copy["sg.ShadowQuality"] = 0
    assert gp.BY_ID["fortnite"].presets["Ultra"]["sg.ShadowQuality"] == 3  # built-in untouched


def test_edit_limited_to_known_keys(store):
    gp.save_user_preset("fortnite", "A", {"bUseVSync": "False"})
    assert gp.update_user_preset("fortnite", "A", {"bUseVSync": "True", "sg.ShadowQuality": "1"})[0]
    ok, msg = gp.update_user_preset("fortnite", "A", {"bUseVSync": "True", "Evil.Key": "1"})
    assert not ok and "Evil.Key" in msg
    assert gp.user_presets("fortnite")["A"]["sg.ShadowQuality"] == "1"
    assert "sg.ShadowQuality" in gp.known_keys("fortnite")


def test_export_import_roundtrip_and_clash(store, tmp_path):
    gp.save_user_preset("fortnite", "A", {"bUseVSync": "False", "sg.ShadowQuality": 2})
    f = tmp_path / "a.json"
    assert gp.export_preset("fortnite", "A", f)[0]
    data = _json.loads(f.read_text())
    assert data["format"] == gp.PRESET_FORMAT and data["version"] == 1 and data["game"] == "fortnite"
    assert gp.import_preset("fortnite", f)[0] == "clash"                   # never silently overwrites
    assert gp.import_preset("fortnite", f, "A2")[0] == "ok"
    assert gp.user_presets("fortnite")["A2"] == {"bUseVSync": "False", "sg.ShadowQuality": 2}
    assert gp.import_preset("fortnite", f, "A", replace=True)[0] == "ok"


def _good(**over):
    d = {"format": gp.PRESET_FORMAT, "version": 1, "game": "fortnite", "name": "X", "settings": {"k": "v"}}
    d.update(over)
    return d


@_pytest.mark.parametrize("raw,part", [
    ("not json", "valid"),
    (_json.dumps([1]), "isn't a RYTWEAKS"),
    (_json.dumps(_good(format="other")), "isn't a RYTWEAKS"),
    (_json.dumps(_good(game="apex")), "apex"),
    (_json.dumps(_good(version=99)), "newer"),
    (_json.dumps(_good(version="1")), "version"),
    (_json.dumps(_good(name="")), "name"),
    (_json.dumps(_good(settings={})), "no settings"),
    (_json.dumps(_good(settings={"k": [1]})), "unsupported"),
    (_json.dumps(_good(settings={"k": None})), "unsupported"),
    (_json.dumps(_good(settings={"k": "x" * 600})), "too long"),
    (_json.dumps(_good(settings={f"k{i}": 1 for i in range(600)})), "too many"),
    ("x" * (gp.MAX_IMPORT_BYTES + 1), "too big"),
])
def test_import_validation_rejects(raw, part):
    ok, msg, name, settings = gp.parse_preset_file(raw, "fortnite")
    assert not ok and part in msg and name is None


def test_import_validation_accepts_and_writes_nothing_on_reject(store, tmp_path):
    ok, _, name, settings = gp.parse_preset_file(_json.dumps(_good(settings={"a": 1, "b": 1.5, "c": True, "d": "x"})), "fortnite")
    assert ok and name == "X" and settings["c"] is True
    bad = tmp_path / "bad.json"
    bad.write_text(_json.dumps(_good(game="apex")))
    assert gp.import_preset("fortnite", bad)[0] == "error"
    assert gp.user_presets("fortnite") == {}
