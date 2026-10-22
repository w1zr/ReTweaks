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
    assert len(backups) == 1 and "sg.ShadowQuality=3" in backups[0]["file"].read_bytes().decode("utf-16")
    os.chmod(f, stat.S_IREAD | stat.S_IWRITE)
    ok, _ = gp.restore_backup("fortnite", backups[0])
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
