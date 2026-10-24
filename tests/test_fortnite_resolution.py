import json
import stat
from pathlib import Path
import pytest
from core import fortnite_resolution as fr
from core import game_presets as gp


CONFIG = ('; personal settings\r\n[/Script/FortniteGame.FortGameUserSettings]\r\n'
          'ResolutionSizeX=1920\r\nResolutionSizeY=1080\r\nFullscreenMode=1\r\n'
          'LastUserConfirmedResolutionSizeX=1920\r\nLastUserConfirmedResolutionSizeY=1080\r\n'
          'LastConfirmedFullscreenMode=1\r\nbUseDesktopResolutionForFullscreen=True\r\n'
          'FrameRateLimit=165.000000\r\nbUseVSync=False\r\n'
          '[Other]\r\nResolutionSizeX=800\r\nFullscreenMode=2\r\n')


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv('APPDATA', str(tmp_path / 'appdata'))
    monkeypatch.setattr(gp, 'game_running', lambda _: False)
    path = tmp_path / 'GameUserSettings.ini'
    path.write_bytes(CONFIG.encode('utf-8'))
    return path


def test_only_fortnite_display_keys_change_and_no_windows_mode_call(config, monkeypatch):
    from core import display
    monkeypatch.setattr(display, 'set_resolution', lambda *a, **k: pytest.fail('Desktop mode must not change'))
    fr.apply(config, '1440', '1080')
    text = config.read_bytes().decode()
    assert 'ResolutionSizeX=1440\r\n' in text and 'FullscreenMode=0\r\n' in text
    assert '[Other]\r\nResolutionSizeX=800\r\nFullscreenMode=2\r\n' in text
    assert 'FrameRateLimit=165.000000\r\n' in text and 'bUseVSync=False\r\n' in text
    assert 'PreferredFullscreenMode' not in text  # missing optional keys aren't invented
    backups = gp.list_backups('fortnite')
    assert backups and any(item['file'].read_bytes() == CONFIG.encode() for item in backups)


def test_restore_survives_repeated_applies_and_preserves_later_graphics_changes(config):
    fr.apply(config, 1440, 1080)
    fr.apply(config, 1280, 960)
    config.write_bytes(config.read_bytes().replace(b'FrameRateLimit=165.000000', b'FrameRateLimit=240.000000'))
    fr.restore(config)
    text = config.read_bytes().decode()
    assert 'ResolutionSizeX=1920\r\nResolutionSizeY=1080\r\nFullscreenMode=1' in text
    assert 'FrameRateLimit=240.000000' in text
    assert not fr._state_file(config).exists()


def test_running_game_is_not_modified(config, monkeypatch):
    monkeypatch.setattr(gp, 'game_running', lambda _: True)
    with pytest.raises(ValueError, match='Close Fortnite'):
        fr.apply(config, 1440, 1080)
    assert config.read_bytes() == CONFIG.encode()


@pytest.mark.parametrize('width,height', [('zero', '1080'), (100, 1080), (1440, 0), (True, 1080), (1440.5, 1080)])
def test_invalid_dimensions_do_not_modify_settings(config, width, height):
    with pytest.raises(ValueError):
        fr.apply(config, width, height)
    assert config.read_bytes() == CONFIG.encode()


def test_missing_required_key_is_not_a_partial_success(config):
    config.write_bytes(CONFIG.replace('FullscreenMode=1\r\n', '', 1).encode())
    before = config.read_bytes()
    with pytest.raises(ValueError, match='required video settings'):
        fr.apply(config, 1440, 1080)
    assert config.read_bytes() == before


def test_read_only_attribute_is_preserved(config):
    config.chmod(stat.S_IREAD)
    try:
        fr.apply(config, 1440, 1080)
        assert gp.is_read_only(config)
    finally:
        config.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_backup_failure_does_not_change_game_file(config, monkeypatch):
    def fail(*args):
        raise OSError('Backup unavailable')
    monkeypatch.setattr(gp, 'make_backup', fail)
    with pytest.raises(OSError, match='Backup unavailable'):
        fr.apply(config, 1440, 1080)
    assert config.read_bytes() == CONFIG.encode()
    assert not fr._state_file(config).exists()


def test_utf8_bom_and_line_endings_are_kept(config):
    config.write_bytes(b'\xef\xbb\xbf' + CONFIG.encode())
    fr.apply(config, 1440, 1080)
    data = config.read_bytes()
    assert data.startswith(b'\xef\xbb\xbf') and data.count(b'\r\n') == CONFIG.encode().count(b'\r\n')


def test_apply_locks_file_and_restore_unlocks(config):
    """v2.0.7: Fortnite rewrites the file on start, so apply makes it read-only; restore returns the old state."""
    try:
        fr.apply(config, 1440, 1080)
        assert gp.is_read_only(config)
        fr.restore(config)
        assert not gp.is_read_only(config)
        assert 'ResolutionSizeX=1920' in config.read_bytes().decode()
    finally:
        config.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_lock_off_leaves_file_writable(config):
    fr.apply(config, 1440, 1080, lock=False)
    assert not gp.is_read_only(config)


def test_desired_screen_keys_change_only_when_present(config):
    config.write_bytes(CONFIG.replace('FrameRateLimit', 'DesiredScreenWidth=1920\r\nDesiredScreenHeight=1080\r\n'
                                      'LastUserConfirmedDesiredScreenWidth=1920\r\n'
                                      'LastUserConfirmedDesiredScreenHeight=1080\r\nFrameRateLimit', 1).encode())
    try:
        fr.apply(config, 1440, 1080)
        text = config.read_bytes().decode()
        assert 'DesiredScreenWidth=1440\r\n' in text and 'LastUserConfirmedDesiredScreenHeight=1080\r\n' in text
        fr.restore(config)
        assert 'DesiredScreenWidth=1920\r\n' in config.read_bytes().decode()
    finally:
        config.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_mode_check_reads_card_modes(monkeypatch):
    from core import display
    monkeypatch.setattr(display, 'list_displays', lambda: [
        {'primary': True, 'modes': [(1920, 1080, 32, 165), (1440, 1080, 32, 165)]}])
    assert fr.mode_check(1440, 1080)[0] is True
    assert fr.mode_check(1720, 1080)[0] is False
    monkeypatch.setattr(display, 'list_displays', lambda: [])
    assert fr.mode_check(1440, 1080)[0] is None


def test_find_files_checks_every_user_profile(tmp_path, monkeypatch):
    """v2.0.7: RETWEAKS runs as admin; the player's file can be in another profile than %LOCALAPPDATA%."""
    import os
    users = tmp_path / 'Users'
    admin, player = users / 'Admin', users / 'Ryder'
    for p in (admin, player):
        p.mkdir(parents=True)
    target = player / fr.RELATIVE
    target.parent.mkdir(parents=True)
    target.write_text('[/Script/FortniteGame.FortGameUserSettings]\n', encoding='utf-8')
    monkeypatch.setenv('USERPROFILE', str(admin))
    monkeypatch.setenv('LOCALAPPDATA', str(admin / 'AppData' / 'Local'))
    monkeypatch.delenv('PUBLIC', raising=False)
    monkeypatch.delenv('SystemDrive', raising=False)
    monkeypatch.setattr(gp, 'load_custom', lambda: {})
    assert fr.find_files() == [os.path.normcase(os.path.abspath(target))]
    assert fr.find_file() == os.path.normcase(os.path.abspath(target))
    own = admin / fr.RELATIVE
    own.parent.mkdir(parents=True)
    own.write_text('x', encoding='utf-8')
    os.utime(own, (1, 1))
    assert len(fr.find_files()) == 2 and fr.find_files()[0].endswith(os.path.normcase(str(fr.RELATIVE)))
