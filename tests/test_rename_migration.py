"""The one-time moves from earlier versions (previous name, base app): data is copied, never lost, repeat-safe."""
import json
import types

from core import rename_migration as rm
from core import themes, game_presets as gp


def test_folders_copied_once_and_old_kept(tmp_path):
    old = tmp_path / rm.OLD
    (old / "game_backups" / "fortnite").mkdir(parents=True)
    (old / "config.json").write_text(json.dumps({"theme": "Galaxy", "tray_on_close": False}))
    (old / "game_backups" / "fortnite" / "b.ini").write_text("x=1")
    res = rm.migrate_folders([tmp_path])
    assert res and res[0][2] is True
    new = tmp_path / "RETWEAKS"
    assert json.loads((new / "config.json").read_text())["theme"] == "Galaxy"     # settings kept as they were
    assert (new / "game_backups" / "fortnite" / "b.ini").read_text() == "x=1"
    assert (old / "config.json").exists()                                        # old folder kept as a backup
    assert (new / rm.MARKER).exists()
    # repeat-safe: a second run never overwrites the new folder (settings changed after the move stay)
    (new / "config.json").write_text(json.dumps({"theme": "Ocean"}))
    assert rm.migrate_folders([tmp_path]) == []
    assert json.loads((new / "config.json").read_text())["theme"] == "Ocean"


def test_no_old_folder_does_nothing(tmp_path):
    assert rm.migrate_folders([tmp_path]) == []
    assert not (tmp_path / "RETWEAKS").exists()


def test_interrupted_copy_is_redone(tmp_path):
    (tmp_path / rm.OLD).mkdir()
    (tmp_path / rm.OLD / "config.json").write_text("{}")
    (tmp_path / "RETWEAKS.migrating").mkdir()                                     # left over from a crash
    (tmp_path / "RETWEAKS.migrating" / "half").write_text("?")
    assert rm.migrate_folders([tmp_path])[0][2] is True
    assert not (tmp_path / "RETWEAKS" / "half").exists() and not (tmp_path / "RETWEAKS.migrating").exists()


def test_credential_copied_only_when_missing():
    store = {rm.OLD + "/GeminiAPIKey": b"key"}
    read = store.get
    write = store.__setitem__
    assert rm.migrate_credential(read, write) is True and store["RETWEAKS/GeminiAPIKey"] == b"key"
    store["RETWEAKS/GeminiAPIKey"] = b"newer"
    assert rm.migrate_credential(read, write) is False and store["RETWEAKS/GeminiAPIKey"] == b"newer"
    assert rm.migrate_credential({}.get, write) is False


def test_autostart_moves_task_keeping_minimized(monkeypatch):
    from core import autostart
    monkeypatch.setattr(autostart, "available", lambda: True)
    calls = []

    def run(cmd, timeout=0):
        calls.append(cmd)
        if cmd[1] == "/Query":
            return types.SimpleNamespace(returncode=0, stdout="<Arguments>--minimized</Arguments>")
        return types.SimpleNamespace(returncode=0, stdout="")
    made = []
    ok, msg = rm.migrate_autostart(run, lambda enable, minimized: (made.append(minimized), (True, "ok"))[1])
    assert ok and made == [True] and ["schtasks", "/Delete", "/TN", rm.OLD, "/F"] in calls

    # new task failed -> the old one is NOT deleted
    calls.clear()
    ok, msg = rm.migrate_autostart(run, lambda enable, minimized: (False, "denied"))
    assert not ok and not any(c[1] == "/Delete" for c in calls)


def test_old_share_codes_and_preset_files_still_import():
    code = themes.export_code("Mine", themes.editable_colors("Midnight"))
    if code:
        assert code.startswith("RET1-")
        assert themes.parse_code("RYT1-" + code[len("RET1-"):])[0] is True
    assert rm.OLD.lower() + "-preset" in gp.OLD_PRESET_FORMATS


def test_merges_into_new_folder_created_early(tmp_path):
    old = tmp_path / rm.OLD
    old.mkdir()
    (old / "config.json").write_text('{"theme": "Forest"}')
    (old / "galaxy_backdrop_v1.png").write_text("old")
    new = tmp_path / "RETWEAKS"
    new.mkdir()
    (new / "galaxy_backdrop_v1.png").write_text("new")              # made by the new version first
    assert rm.migrate_folders([tmp_path])[0][2] is True
    assert (new / "config.json").read_text() == '{"theme": "Forest"}'
    assert (new / "galaxy_backdrop_v1.png").read_text() == "new"     # never overwritten
    (new / "config.json").write_text('{"theme": "Ocean"}')
    assert rm.migrate_folders([tmp_path]) == []                        # marker: only once
    assert (new / "config.json").read_text() == '{"theme": "Ocean"}'


def test_base_app_data_copied_without_collisions(tmp_path):
    ph = tmp_path / rm.BASE_APP
    ph.mkdir()
    (ph / "appearance.json").write_text('{"theme": "Graphite"}')
    (ph / "custom_presets.json").write_text('{"maxfps": ["temp"]}')       # base-app tweak presets
    new = tmp_path / "RETWEAKS"
    new.mkdir()
    (new / "custom_presets.json").write_text('{"fortnite": []}')         # RETWEAKS game presets
    assert rm.migrate_base_app([tmp_path])[0][2] is True
    assert (new / "appearance.json").read_text() == '{"theme": "Graphite"}'
    assert (new / "tweak_custom_presets.json").read_text() == '{"maxfps": ["temp"]}'
    assert (new / "custom_presets.json").read_text() == '{"fortnite": []}'  # never overwritten
    assert (ph / "appearance.json").exists()                               # old folder kept
    assert rm.migrate_base_app([tmp_path]) == []                             # one time only
