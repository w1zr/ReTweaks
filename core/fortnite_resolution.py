"""Fortnite video settings only. Never calls a Windows display-mode API."""
import hashlib
import json
import os
from pathlib import Path
import re
from core import game_presets as gp

SECTION = '/script/fortnitegame.fortgameusersettings'
REQUIRED = ('ResolutionSizeX', 'ResolutionSizeY', 'FullscreenMode')
KEYS = REQUIRED + ('LastUserConfirmedResolutionSizeX', 'LastUserConfirmedResolutionSizeY',
                   'LastConfirmedFullscreenMode', 'PreferredFullscreenMode',
                   'bUseDesktopResolutionForFullscreen')


def find_file():
    saved = gp.load_custom().get('paths', {}).get('fortnite')
    if saved and Path(saved).is_file():
        return str(saved)
    files = gp.BY_ID['fortnite'].find_files()
    return files[0] if files else None


def _section(text):
    lines = text.splitlines(keepends=True)
    headers = [(i, re.fullmatch(r'\s*\[([^\]]+)\]\s*', line.strip())) for i, line in enumerate(lines)]
    headers = [(i, match.group(1).casefold()) for i, match in headers if match]
    matches = [i for i, name in headers if name == SECTION]
    if len(matches) != 1:
        raise ValueError('This file does not contain one recognizable Fortnite video-settings section.')
    start = matches[0] + 1
    end = next((i for i, _ in headers if i >= start), len(lines))
    return ''.join(lines[:start]), ''.join(lines[start:end]), ''.join(lines[end:])


def _read(path):
    if not path or not Path(path).is_file():
        raise ValueError('Fortnite settings were not found. Start Fortnite once, close it, then choose GameUserSettings.ini.')
    if Path(path).name.casefold() != 'gameusersettings.ini':
        raise ValueError('Choose Fortnite\'s GameUserSettings.ini file.')
    text, encoding = gp.read_text(path)
    before, body, after = _section(text)
    values = gp.FORMATS['ini'].parse(body)
    missing = [key for key in REQUIRED if key not in values]
    if missing:
        raise ValueError('Fortnite has not saved the required video settings: ' + ', '.join(missing) +
                         '. Set a display mode in Fortnite, close the game, and retry.')
    return text, encoding, before, body, after, values


def settings(width, height):
    try:
        w, h = int(str(width).strip()), int(str(height).strip())
    except (TypeError, ValueError):
        raise ValueError('Width and height must be whole numbers.') from None
    if not (640 <= w <= 16384 and 480 <= h <= 16384):
        raise ValueError('Use a width of 640–16384 and a height of 480–16384 pixels.')
    return {'ResolutionSizeX': str(w), 'ResolutionSizeY': str(h), 'FullscreenMode': '0',
            'LastUserConfirmedResolutionSizeX': str(w), 'LastUserConfirmedResolutionSizeY': str(h),
            'LastConfirmedFullscreenMode': '0', 'PreferredFullscreenMode': '0',
            'bUseDesktopResolutionForFullscreen': 'False'}


def preview(path, width, height):
    _, _, _, body, _, values = _read(path)
    _, applied, _ = gp.FORMATS['ini'].write(body, settings(width, height))
    return [(key, old, new) for key, (old, new) in applied.items() if old != new]


def _state_file(path):
    identity = os.path.normcase(str(Path(path).resolve()))
    return gp.backup_dir('fortnite') / ('resolution-' + hashlib.sha256(identity.encode()).hexdigest()[:16] + '.json')


def _write(path, text, encoding, state=None, original=None):
    if gp.game_running('fortnite'):
        raise ValueError('Close Fortnite before changing its settings.')
    backup = gp.make_backup('fortnite', path)
    created_state = False
    if state is not None and not state.exists():
        tmp = state.with_suffix('.tmp')
        tmp.write_text(json.dumps({'original': original}), encoding='utf-8')
        os.replace(tmp, state)
        created_state = True
    locked = gp.is_read_only(path)
    try:
        if locked:
            gp.set_read_only(path, False)
        gp.write_text(path, text, encoding)
    except Exception:
        if created_state:
            state.unlink(missing_ok=True)
        raise
    finally:
        if locked:
            gp.set_read_only(path, True)
    return backup


def apply(path, width, height):
    if gp.game_running('fortnite'):
        raise ValueError('Close Fortnite before changing its settings.')
    _, encoding, before, body, after, values = _read(path)
    new_body, applied, _ = gp.FORMATS['ini'].write(body, settings(width, height))
    if not any(old != new for old, new in applied.values()):
        return 'Fortnite already has these video settings. Windows desktop resolution is unchanged.'
    state = _state_file(path)
    original = {key: value for key, value in values.items() if key in KEYS}
    _write(path, before + new_body + after, encoding, state, original)
    return (f'Saved {int(str(width).strip())} × {int(str(height).strip())} and Fullscreen in Fortnite\'s settings. '
            'A backup was saved. Windows desktop resolution is unchanged. Start Fortnite and check its Video settings; '
            'the game or graphics driver may override the requested mode.')


def restore(path):
    if gp.game_running('fortnite'):
        raise ValueError('Close Fortnite before restoring its settings.')
    state = _state_file(path)
    if not state.is_file():
        raise ValueError('No saved Fortnite-only resolution to restore for this file.')
    original = json.loads(state.read_text(encoding='utf-8')).get('original', {})
    if not isinstance(original, dict) or not all(key in original for key in REQUIRED) or any(key not in KEYS for key in original):
        raise ValueError('The saved resolution profile is invalid. Use Game config files → Backups to restore a full backup.')
    _, encoding, before, body, after, _ = _read(path)
    new_body, _, _ = gp.FORMATS['ini'].write(body, original)
    _write(path, before + new_body + after, encoding)
    state.unlink()
    return 'Restored the previous Fortnite video settings. Other game settings and Windows desktop resolution are unchanged.'
