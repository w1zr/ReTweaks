"""Fortnite video settings only. Never changes a Windows display mode.

v2.0.7 (owner request: make it work): Fortnite rewrites GameUserSettings.ini when it starts, so the saved size
was reset (the game is `lockable` in core/game_presets for this reason). apply() now also sets the file read-only
by default (lock=True) and writes the DesiredScreen* keys Fortnite keeps beside ResolutionSize*. restore() puts the
file's previous read-only state back. mode_check() only READS the graphics card's mode list: Fullscreen at a size
the card doesn't offer can't stretch, so the UI says so before saving."""
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
                   'bUseDesktopResolutionForFullscreen', 'DesiredScreenWidth', 'DesiredScreenHeight',
                   'LastUserConfirmedDesiredScreenWidth', 'LastUserConfirmedDesiredScreenHeight')


RELATIVE = Path('AppData', 'Local', 'FortniteGame', 'Saved', 'Config', 'WindowsClient', 'GameUserSettings.ini')


def _users_dirs():
    """Folders that hold Windows user profiles (normally C:\\Users)."""
    dirs = []
    for base in (os.getenv('USERPROFILE'), os.getenv('PUBLIC')):
        if base:
            dirs.append(Path(base).parent)
    drive = os.getenv('SystemDrive')
    if drive:
        dirs.append(Path(drive + os.sep, 'Users'))
    out = []
    for d in dirs:
        if d.is_dir() and d not in out:
            out.append(d)
    return out


def find_files():
    """Every Fortnite GameUserSettings.ini on this PC, newest first (v2.0.7, owner request: find it automatically).
    Checks this account's %LOCALAPPDATA% first, then every user profile, because RETWEAKS runs as administrator and
    an administrator account's %LOCALAPPDATA% isn't the player's when they differ."""
    found = []
    for p in gp.BY_ID['fortnite'].find_files():
        found.append(os.path.normcase(os.path.abspath(p)))
    for users in _users_dirs():
        try:
            profiles = list(users.iterdir())
        except OSError:
            continue
        for profile in profiles:
            candidate = profile / RELATIVE
            try:
                if candidate.is_file():
                    key = os.path.normcase(os.path.abspath(candidate))
                    if key not in found:
                        found.append(key)
            except OSError:
                continue

    def mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return 0
    return sorted(found, key=mtime, reverse=True)


def find_file():
    saved = gp.load_custom().get('paths', {}).get('fortnite')
    if saved and Path(saved).is_file():
        return str(saved)
    files = find_files()
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
            'bUseDesktopResolutionForFullscreen': 'False',
            'DesiredScreenWidth': str(w), 'DesiredScreenHeight': str(h),
            'LastUserConfirmedDesiredScreenWidth': str(w), 'LastUserConfirmedDesiredScreenHeight': str(h)}


def mode_check(width, height):
    """Read-only check of the primary display. Returns (offered, display) where offered is True/False when the
    graphics card's mode list is known, or None when it can't be read (not Windows, no display data)."""
    wanted = settings(width, height)
    w, h = int(wanted['ResolutionSizeX']), int(wanted['ResolutionSizeY'])
    try:
        from core import display
        shown = display.list_displays()
    except Exception:
        return None, None
    main = next((d for d in shown if d.get('primary')), shown[0] if shown else None)
    if not main or not main.get('modes'):
        return None, main
    return any(m[0] == w and m[1] == h for m in main['modes']), main


def preview(path, width, height):
    _, _, _, body, _, values = _read(path)
    _, applied, _ = gp.FORMATS['ini'].write(body, settings(width, height))
    return [(key, old, new) for key, (old, new) in applied.items() if old != new]


def _state_file(path):
    identity = os.path.normcase(str(Path(path).resolve()))
    return gp.backup_dir('fortnite') / ('resolution-' + hashlib.sha256(identity.encode()).hexdigest()[:16] + '.json')


def _write(path, text, encoding, state=None, original=None, lock=None):
    if gp.game_running('fortnite'):
        raise ValueError('Close Fortnite before changing its settings.')
    backup = gp.make_backup('fortnite', path)
    created_state = False
    if state is not None and not state.exists():
        tmp = state.with_suffix('.tmp')
        tmp.write_text(json.dumps({'original': original, 'read_only': gp.is_read_only(path)}), encoding='utf-8')
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
        final = locked if lock is None else bool(lock)
        if final or locked:
            gp.set_read_only(path, final)
    return backup


def apply(path, width, height, lock=True):
    if gp.game_running('fortnite'):
        raise ValueError('Close Fortnite before changing its settings.')
    _, encoding, before, body, after, values = _read(path)
    new_body, applied, _ = gp.FORMATS['ini'].write(body, settings(width, height))
    size = f'{int(str(width).strip())} × {int(str(height).strip())}'
    if not any(old != new for old, new in applied.values()):
        if lock and not gp.is_read_only(path):
            gp.set_read_only(path, True)
            return (f'Fortnite already had {size} and Fullscreen. The file is now read-only so Fortnite can\'t '
                    'reset it.')
        return 'Fortnite already has these video settings. Windows desktop resolution is unchanged.'
    state = _state_file(path)
    original = {key: value for key, value in values.items() if key in KEYS}
    _write(path, before + new_body + after, encoding, state, original, lock=lock)
    kept = (' The file is read-only so Fortnite can\'t reset it when it starts; Restore unlocks it.' if lock else
            ' The file is not locked, so Fortnite may reset the resolution when it starts.')
    return (f'Saved {size} and Fullscreen in Fortnite\'s settings. A backup was saved.{kept} Windows desktop '
            'resolution is unchanged. Start Fortnite and check its Video settings.')


def restore(path):
    if gp.game_running('fortnite'):
        raise ValueError('Close Fortnite before restoring its settings.')
    state = _state_file(path)
    if not state.is_file():
        raise ValueError('No saved Fortnite-only resolution to restore for this file.')
    saved = json.loads(state.read_text(encoding='utf-8'))
    original = saved.get('original', {})
    was_read_only = saved.get('read_only') if isinstance(saved.get('read_only'), bool) else None
    if not isinstance(original, dict) or not all(key in original for key in REQUIRED) or any(key not in KEYS for key in original):
        raise ValueError('The saved resolution profile is invalid. Use Game config files → Backups to restore a full backup.')
    _, encoding, before, body, after, _ = _read(path)
    new_body, _, _ = gp.FORMATS['ini'].write(body, original)
    _write(path, before + new_body + after, encoding, lock=bool(was_read_only))
    state.unlink()
    return 'Restored the previous Fortnite video settings. Other game settings and Windows desktop resolution are unchanged.'
