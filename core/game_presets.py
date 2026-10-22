# core/game_presets.py
"""Game settings presets: edit a game's own settings file safely.

Safety rules (CLAUDE.md section 9):
- Only settings files, never game executables or anti-cheat files.
- Only keys that ALREADY EXIST in the user's file are changed. Nothing is added, so a key
  name that's wrong for some game version is simply skipped (and shown as skipped).
- The game must be closed (games rewrite these files when they exit).
- The file is backed up before every change; any backup can be restored.
- Everything else in the file (other keys, comments, spacing, encoding, line endings) is kept.

Preset tiers:
  Low               - lowest settings for weaker PCs
  High              - balanced quality and FPS
  Ultra             - best visual quality
  Ultra Performance - competitive: low effects but full resolution and clear visibility
FPS caps are never changed by presets; set them yourself with Custom.

Key names and file locations come from PCGamingWiki and the Minecraft Wiki. Keys that
couldn't be confirmed for a game are not used (CS2 has no built-in preset for that reason).
"""

import glob
import json
import os
import re
import shutil
import stat
import time
from pathlib import Path

import psutil

TIERS = ["Low", "High", "Ultra", "Ultra Performance"]
MAX_BACKUPS = 10


# ================================================================ file formats
# Each format: parse(text) -> {key: value}; write(text, changes) -> (new_text, applied, skipped)

def _style_value(old, new):
    """Write the new value in the same style as the old one (True vs true, 60.000000 vs 60,
    and "quoted" if the old value was quoted, as in newer Minecraft options.txt files)."""
    new = str(new)
    if len(old) >= 2 and old[0] == old[-1] == '"':
        return '"' + _style_value(old[1:-1], new.strip('"')) + '"'
    if not old:
        return new
    if old.lower() in ("true", "false") and new.lower() in ("true", "false"):
        if old.isupper():
            return new.upper()
        if old[0].isupper():
            return new.capitalize()
        return new.lower()
    m = re.fullmatch(r"-?\d+\.(\d+)", old)
    if m and re.fullmatch(r"-?\d+(\.\d+)?", new):
        return f"{float(new):.{len(m.group(1))}f}"
    return new


class _LineFormat:
    """Shared logic: line-by-line regex editing that keeps everything else untouched."""
    line_re = None   # must have groups: prefix, key, sep, value, suffix

    def parse(self, text):
        out = {}
        for line in text.splitlines():
            m = self.line_re.match(line)
            if m and m.group("key") not in out:
                out[m.group("key")] = m.group("value")
        return out

    def write(self, text, changes):
        lines = text.splitlines(keepends=True)
        applied, done = {}, set()
        for i, line in enumerate(lines):
            body = line.rstrip("\r\n")
            ending = line[len(body):]
            m = self.line_re.match(body)
            if not m:
                continue
            key = m.group("key")
            if key in changes and key not in done:
                new_val = _style_value(m.group("value"), changes[key])
                lines[i] = (m.group("prefix") + key + m.group("sep") + self.quote(m, new_val)
                            + m.group("suffix") + ending)
                applied[key] = (m.group("value"), new_val)
                done.add(key)
        skipped = [k for k in changes if k not in done]
        return "".join(lines), applied, skipped

    def quote(self, m, value):
        return value


class IniFormat(_LineFormat):
    name = "ini"
    line_re = re.compile(r"^(?P<prefix>\s*)(?P<key>[^;#\[\s=][^=]*?)(?P<sep>\s*=\s*)(?P<value>[^\r\n]*?)(?P<suffix>\s*)$")


class ColonFormat(_LineFormat):
    """Minecraft options.txt: key:value"""
    name = "colon"
    line_re = re.compile(r"^(?P<prefix>)(?P<key>[A-Za-z0-9_.\-]+)(?P<sep>:)(?P<value>[^\r\n]*?)(?P<suffix>)$")


class KeyValuesFormat(_LineFormat):
    """Valve KeyValues: "key"<tabs>"value" """
    name = "kv"
    line_re = re.compile(r'^(?P<prefix>\s*)"(?P<key>[^"]+)"(?P<sep>\s+)"(?P<value>[^"]*)"(?P<suffix>\s*)$')

    def quote(self, m, value):
        return f'"{value}"'

    def write(self, text, changes):
        # keys are matched without their quotes, so rebuild with the key quoted
        lines = text.splitlines(keepends=True)
        applied, done = {}, set()
        for i, line in enumerate(lines):
            body = line.rstrip("\r\n")
            ending = line[len(body):]
            m = self.line_re.match(body)
            if m and m.group("key") in changes and m.group("key") not in done:
                key = m.group("key")
                new_val = _style_value(m.group("value"), changes[key])
                lines[i] = f'{m.group("prefix")}"{key}"{m.group("sep")}"{new_val}"{m.group("suffix")}{ending}'
                applied[key] = (m.group("value"), new_val)
                done.add(key)
        return "".join(lines), applied, [k for k in changes if k not in done]


FORMATS = {f.name: f for f in (IniFormat(), ColonFormat(), KeyValuesFormat())}


def detect_format(text):
    """Guess the format of a file the user picked."""
    counts = {name: len(fmt.parse(text)) for name, fmt in FORMATS.items()}
    if counts["kv"] >= 2:
        return "kv"
    return max(("ini", "colon"), key=lambda n: counts[n])


# ================================================================ reading/writing files safely

def read_text(path):
    """Returns (text, encoding). Handles UTF-16 (common for Unreal .ini files) and UTF-8 BOM."""
    raw = Path(path).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16"), "utf-16"
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw.decode("utf-8-sig"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("cp1252"), "cp1252"


def write_text(path, text, encoding):
    tmp = str(path) + ".rytweaks.tmp"
    with open(tmp, "w", encoding=encoding, newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def is_read_only(path):
    try:
        return not (os.stat(path).st_mode & stat.S_IWRITE)
    except OSError:
        return False


def set_read_only(path, locked):
    mode = os.stat(path).st_mode
    os.chmod(path, (mode & ~stat.S_IWRITE) if locked else (mode | stat.S_IWRITE))


# ================================================================ backups

def backup_dir(game_id):
    base = Path(os.getenv("APPDATA") or Path.home()) / "RYTWEAKS" / "game_backups" / game_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def make_backup(game_id, path):
    # The very first backup of each file is the user's original: kept forever, never pruned
    original = backup_dir(game_id) / f"ORIGINAL__{Path(path).name}"
    if not original.exists():
        shutil.copyfile(path, original)
        original.with_suffix(original.suffix + ".json").write_text(
            json.dumps({"original": str(path)}), encoding="utf-8")
    stamp = time.strftime('%Y-%m-%d_%H-%M-%S')
    dest = backup_dir(game_id) / f"{stamp}__{Path(path).name}"
    n = 2
    while dest.exists():  # two backups in the same second must not overwrite each other
        dest = backup_dir(game_id) / f"{stamp}-{n}__{Path(path).name}"
        n += 1
    shutil.copyfile(path, dest)  # copyfile: the backup gets its own timestamp (used for sorting)
    meta = dest.with_suffix(dest.suffix + ".json")
    meta.write_text(json.dumps({"original": str(path)}), encoding="utf-8")
    backups = list_backups(game_id)
    for old in [b for b in backups if not b["pinned"]][MAX_BACKUPS:]:  # keep the newest 10 (+ the original)
        for p in (old["file"], old["file"].with_suffix(old["file"].suffix + ".json")):
            try:
                p.unlink()
            except OSError:
                pass
    return dest


def list_backups(game_id):
    out = []
    files = [f for f in backup_dir(game_id).glob("*__*") if f.suffix != ".json"]
    for f in sorted(files, key=lambda f: f.stat().st_mtime_ns, reverse=True):
        meta = f.with_suffix(f.suffix + ".json")
        try:
            original = json.loads(meta.read_text(encoding="utf-8"))["original"]
        except Exception:
            continue
        pinned = f.name.startswith("ORIGINAL__")
        when = "Original (before RYTWEAKS)" if pinned else f.name.split("__")[0].replace("_", " ")
        out.append({"file": f, "original": original, "when": when, "pinned": pinned})
    return out


def restore_backup(game_id, backup):
    """Put a backup back (making a backup of the current file first)."""
    target = backup["original"]
    if game_running(game_id):
        return False, "Close the game first."
    try:
        was_locked = os.path.exists(target) and is_read_only(target)
        if was_locked:
            set_read_only(target, False)
        data = Path(backup["file"]).read_bytes()  # read it before making a new backup
        if os.path.exists(target):
            make_backup(game_id, target)
        tmp = str(target) + ".rytweaks.tmp"
        Path(tmp).write_bytes(data)
        os.replace(tmp, target)
        if was_locked:
            set_read_only(target, True)
        return True, f"Restored the settings file from {backup['when']}."
    except Exception as e:
        return False, str(e)


# ================================================================ games

def documents_folder():
    """The real Documents folder, even when it's moved to OneDrive or another drive."""
    if os.name == "nt":
        try:
            import ctypes
            import uuid
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                            ("d", ctypes.c_ubyte * 8)]
            fid = GUID.from_buffer_copy(uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7").bytes_le)
            ptr = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(ptr)) == 0:
                path = ptr.value
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                return path
        except Exception:
            pass
    return os.path.join(os.path.expanduser("~"), "Documents")


def _env(path):
    return os.path.expandvars(path.replace("%DOCUMENTS%", documents_folder()))


class Game:
    def __init__(self, gid, name, fmt, candidates, processes, presets, note="", lockable=False):
        self.id, self.name, self.fmt = gid, name, fmt
        self.candidates = candidates       # path patterns, %VARS% and * allowed
        self.processes = processes         # lowercase exe names
        self.presets = presets             # {tier: {key: value}}
        self.note = note
        self.lockable = lockable           # game overwrites the file unless it's read-only

    def find_files(self):
        found = []
        for pattern in self.candidates:
            for p in glob.glob(_env(pattern)):
                if os.path.isfile(p) and p not in found:
                    found.append(p)
        # newest first: the one the game used most recently
        return sorted(found, key=lambda p: os.path.getmtime(p), reverse=True)


FALSE, TRUE = "False", "True"

GAMES = [
    Game("fortnite", "Fortnite", "ini",
         [r"%LOCALAPPDATA%\FortniteGame\Saved\Config\WindowsClient\GameUserSettings.ini"],
         ["fortniteclient-win64-shipping.exe", "fortnitelauncher.exe"],
         {
             "Low": {"sg.ResolutionQuality": 75, "sg.ViewDistanceQuality": 0, "sg.ShadowQuality": 0,
                     "sg.AntiAliasingQuality": 0, "sg.TextureQuality": 0, "sg.EffectsQuality": 0,
                     "sg.PostProcessQuality": 0, "sg.FoliageQuality": 0, "bUseVSync": FALSE, "bMotionBlur": FALSE},
             "High": {"sg.ResolutionQuality": 100, "sg.ViewDistanceQuality": 2, "sg.ShadowQuality": 2,
                      "sg.AntiAliasingQuality": 2, "sg.TextureQuality": 2, "sg.EffectsQuality": 2,
                      "sg.PostProcessQuality": 2, "sg.FoliageQuality": 2, "bUseVSync": FALSE, "bMotionBlur": FALSE},
             "Ultra": {"sg.ResolutionQuality": 100, "sg.ViewDistanceQuality": 3, "sg.ShadowQuality": 3,
                       "sg.AntiAliasingQuality": 3, "sg.TextureQuality": 3, "sg.EffectsQuality": 3,
                       "sg.PostProcessQuality": 3, "sg.FoliageQuality": 3, "bUseVSync": FALSE, "bMotionBlur": FALSE},
             "Ultra Performance": {"sg.ResolutionQuality": 100, "sg.ViewDistanceQuality": 1, "sg.ShadowQuality": 0,
                                   "sg.AntiAliasingQuality": 0, "sg.TextureQuality": 1, "sg.EffectsQuality": 0,
                                   "sg.PostProcessQuality": 0, "sg.FoliageQuality": 0, "bUseVSync": FALSE,
                                   "bMotionBlur": FALSE},
         },
         note="Rendering mode (Performance / DirectX 11 / DirectX 12) is set in-game: Settings → Video → "
              "Rendering Mode, then restart Fortnite. Fortnite may also restore settings from your Epic "
              "account; if a preset doesn't stick, apply it again after the game has started once.",
         lockable=True),
    Game("minecraft_java", "Minecraft: Java Edition", "colon",
         [r"%APPDATA%\.minecraft\options.txt"],
         [],  # runs inside javaw.exe; checked by window title below
         {
             "Low": {"renderDistance": 6, "simulationDistance": 5, "enableVsync": "false", "entityShadows": "false",
                     "particles": 2, "biomeBlendRadius": 0, "mipmapLevels": 0, "ao": "false",
                     "renderClouds": "false", "graphicsPreset": "fast", "graphicsMode": 0, "fancyGraphics": "false"},
             "High": {"renderDistance": 12, "simulationDistance": 8, "enableVsync": "false", "entityShadows": "true",
                      "particles": 1, "biomeBlendRadius": 2, "mipmapLevels": 4, "ao": "true",
                      "renderClouds": "fast", "graphicsPreset": "fancy", "graphicsMode": 1, "fancyGraphics": "true"},
             "Ultra": {"renderDistance": 24, "simulationDistance": 12, "enableVsync": "false", "entityShadows": "true",
                       "particles": 0, "biomeBlendRadius": 5, "mipmapLevels": 4, "ao": "true",
                       "renderClouds": "true", "graphicsPreset": "fancy", "graphicsMode": 1, "fancyGraphics": "true"},
             "Ultra Performance": {"renderDistance": 10, "simulationDistance": 6, "enableVsync": "false",
                                   "entityShadows": "false", "particles": 2, "biomeBlendRadius": 0,
                                   "mipmapLevels": 4, "ao": "false", "renderClouds": "false",
                                   "graphicsPreset": "fast", "graphicsMode": 0, "fancyGraphics": "false"},
         },
         note="Uses the default .minecraft folder. Using CurseForge, Prism or another launcher? Use "
              "“Choose your own file” and pick that instance's options.txt. Mods like Sodium have their own settings."),
    Game("minecraft_bedrock", "Minecraft: Bedrock Edition", "colon",
         [r"%APPDATA%\Minecraft Bedrock\users\*\games\com.mojang\minecraftpe\options.txt",
          r"%APPDATA%\Minecraft Bedrock Preview\users\*\games\com.mojang\minecraftpe\options.txt",
          r"%LOCALAPPDATA%\Packages\Microsoft.MinecraftUWP_8wekyb3d8bbwe\LocalState\games\com.mojang\minecraftpe\options.txt"],
         ["minecraft.windows.exe"],
         {
             "Low": {"gfx_viewdistance": 96, "gfx_vsync": 0, "gfx_msaa": 1, "gfx_smoothlighting": 0,
                     "gfx_fancyskies": 0, "gfx_transparentleaves": 0},
             "High": {"gfx_viewdistance": 160, "gfx_vsync": 0, "gfx_msaa": 2, "gfx_smoothlighting": 1,
                      "gfx_fancyskies": 1, "gfx_transparentleaves": 1},
             "Ultra": {"gfx_viewdistance": 320, "gfx_vsync": 0, "gfx_msaa": 4, "gfx_smoothlighting": 1,
                       "gfx_fancyskies": 1, "gfx_transparentleaves": 1},
             "Ultra Performance": {"gfx_viewdistance": 128, "gfx_vsync": 0, "gfx_msaa": 1, "gfx_smoothlighting": 0,
                                   "gfx_fancyskies": 0, "gfx_transparentleaves": 0},
         },
         note="View distance is stored in blocks (16 blocks = 1 chunk). Vibrant Visuals and ray tracing are "
              "set in-game."),
    Game("apex", "Apex Legends", "kv",
         [r"%USERPROFILE%\Saved Games\Respawn\Apex\local\videoconfig.txt"],
         ["r5apex.exe", "r5apex_dx12.exe"],
         {
             "Low": {"setting.mat_vsync_mode": 0, "setting.csm_enabled": 0, "setting.volumetric_lighting": 0,
                     "setting.ssao_enabled": 0, "setting.dvs_enable": 0, "setting.r_lod_switch_scale": 0.6,
                     "setting.mat_picmip": 2},
             "High": {"setting.mat_vsync_mode": 0, "setting.csm_enabled": 1, "setting.volumetric_lighting": 1,
                      "setting.ssao_enabled": 1, "setting.dvs_enable": 0, "setting.r_lod_switch_scale": 0.8,
                      "setting.mat_picmip": 1},
             "Ultra": {"setting.mat_vsync_mode": 0, "setting.csm_enabled": 1, "setting.volumetric_lighting": 1,
                       "setting.ssao_enabled": 1, "setting.dvs_enable": 0, "setting.r_lod_switch_scale": 1.0,
                       "setting.mat_picmip": 0},
             "Ultra Performance": {"setting.mat_vsync_mode": 0, "setting.csm_enabled": 0,
                                   "setting.volumetric_lighting": 0, "setting.ssao_enabled": 0,
                                   "setting.dvs_enable": 0, "setting.r_lod_switch_scale": 0.8,
                                   "setting.mat_picmip": 1},
         },
         note="Apex rewrites this file when it starts unless the file is locked (read-only). "
              "While locked, changes you make in Apex's video menu won't save. The FPS cap is a launch "
              "option (+fps_max), not in this file.",
         lockable=True),
    Game("rocket_league", "Rocket League", "ini",
         [r"%DOCUMENTS%\My Games\Rocket League\TAGame\Config\TASystemSettings.ini",
          r"%USERPROFILE%\Documents\My Games\Rocket League\TAGame\Config\TASystemSettings.ini"],
         ["rocketleague.exe"],
         {
             "Low": {"MaxAnisotropy": 0, "DynamicShadows": FALSE, "AmbientOcclusion": FALSE, "Bloom": FALSE,
                     "DepthOfField": FALSE, "MotionBlur": FALSE, "LensFlares": FALSE},
             "High": {"MaxAnisotropy": 8, "DynamicShadows": TRUE, "AmbientOcclusion": TRUE, "Bloom": TRUE,
                      "DepthOfField": FALSE, "MotionBlur": FALSE, "LensFlares": FALSE},
             "Ultra": {"MaxAnisotropy": 16, "DynamicShadows": TRUE, "AmbientOcclusion": TRUE, "Bloom": TRUE,
                       "DepthOfField": TRUE, "MotionBlur": FALSE, "LensFlares": TRUE},
             "Ultra Performance": {"MaxAnisotropy": 4, "DynamicShadows": FALSE, "AmbientOcclusion": FALSE,
                                   "Bloom": FALSE, "DepthOfField": FALSE, "MotionBlur": FALSE, "LensFlares": FALSE},
         },
         note="Set resolution and window mode in-game first. Rocket League rewrites this file unless it's "
              "locked (read-only); while locked, in-game video changes won't save. "
              "Unlocking above 250 FPS (AllowPerFrameSleep=False) is available in Custom.",
         lockable=True),
]

BY_ID = {g.id: g for g in GAMES}


# ================================================================ Fortnite stretched resolution (v1.5)
# Keys from Fortnite's GameUserSettings.ini as used by common stretched-resolution guides (verified
# against multiple guides 2026-10-22). Only keys that already exist in the user's file are changed.
STRETCH_SIZES = [(1720, 1080), (1680, 1080), (1650, 1080), (1600, 1080), (1440, 1080)]
STRETCH_WIDTH_KEYS = ["ResolutionSizeX", "LastUserConfirmedResolutionSizeX", "DesiredScreenWidth",
                      "LastUserConfirmedDesiredScreenWidth"]
STRETCH_HEIGHT_KEYS = ["ResolutionSizeY", "LastUserConfirmedResolutionSizeY", "DesiredScreenHeight",
                       "LastUserConfirmedDesiredScreenHeight"]
# Unreal Engine window modes: 0 = Fullscreen, 1 = Windowed Fullscreen, 2 = Windowed. Stretching needs
# real (exclusive) fullscreen; borderless always uses the desktop resolution.
FULLSCREEN_KEYS = ["FullscreenMode", "LastConfirmedFullscreenMode", "PreferredFullscreenMode"]


def resolution_changes(width, height, fullscreen=True):
    """Settings for a screen resolution in Fortnite's file (stretched or back to native)."""
    w, h = int(width), int(height)
    if not (640 <= w <= 7680 and 480 <= h <= 4320):
        raise ValueError("That resolution is out of range.")
    out = {k: w for k in STRETCH_WIDTH_KEYS}
    out.update({k: h for k in STRETCH_HEIGHT_KEYS})
    if fullscreen:
        out.update({k: 0 for k in FULLSCREEN_KEYS})
    return out


def current_resolution(path, fmt="ini"):
    """(width, height) Fortnite will use, read from the file, or None."""
    try:
        s = read_settings(path, fmt)
        return int(float(s["ResolutionSizeX"])), int(float(s["ResolutionSizeY"]))
    except Exception:
        return None


def game_running(game_id):
    """True if the game is running (it would overwrite the file when it closes)."""
    g = BY_ID.get(game_id)
    if not g:
        return False
    try:
        for p in psutil.process_iter(["name", "cmdline"]):
            name = (p.info.get("name") or "").lower()
            if name in g.processes:
                return True
            if game_id == "minecraft_java" and name in ("javaw.exe", "java.exe"):
                cmd = " ".join(p.info.get("cmdline") or []).lower()
                if "minecraft" in cmd:
                    return True
    except Exception:
        return False
    return False


# ================================================================ preview / apply

def read_settings(path, fmt):
    text, _ = read_text(path)
    return FORMATS[fmt].parse(text)


def preview(path, fmt, changes):
    """[(key, current, new)] for keys present in the file, and a list of keys not in the file."""
    current = read_settings(path, fmt)
    rows, missing = [], []
    for k, v in changes.items():
        if k in current:
            rows.append((k, current[k], _style_value(current[k], v)))
        else:
            missing.append(k)
    return rows, missing


def apply_changes(game_id, path, fmt, changes):
    """Back up, then write only existing keys. Returns (ok, message, applied, skipped)."""
    if game_running(game_id):
        return False, "Close the game first: it rewrites this file when it exits.", {}, []
    try:
        text, enc = read_text(path)
        new_text, applied, skipped = FORMATS[fmt].write(text, changes)
        if not applied:
            return False, "None of these settings exist in your file, so nothing was changed.", {}, skipped
        locked = is_read_only(path)
        make_backup(game_id, path)
        if locked:
            set_read_only(path, False)
        write_text(path, new_text, enc)
        if locked:
            set_read_only(path, True)  # keep the user's lock
        changed = sum(1 for old, new in applied.values() if old != new)
        return True, f"Changed {changed} setting(s). A backup was saved first.", applied, skipped
    except PermissionError:
        return False, "Windows blocked writing the file (is it open in another program?).", {}, []
    except Exception as e:
        return False, str(e), {}, []


# ================================================================ user's own files and presets

def _user_store():
    return Path(os.getenv("APPDATA") or Path.home()) / "RYTWEAKS" / "custom_presets.json"


def load_custom():
    """{"files": [{"id", "name", "path", "fmt"}], "presets": {file_or_game_id: {preset_name: {key: value}}}}"""
    try:
        data = json.loads(_user_store().read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("files", [])
            data.setdefault("presets", {})
            return data
    except Exception:
        pass
    return {"files": [], "presets": {}}


def save_custom(data):
    path = _user_store()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def add_custom_file(path, name=None):
    text, _ = read_text(path)
    fmt = detect_format(text)
    if not FORMATS[fmt].parse(text):
        return None, "RYTWEAKS couldn't find any settings in that file (it supports key=value, key:value and \"key\" \"value\" files)."
    data = load_custom()
    fid = "custom_" + re.sub(r"[^a-z0-9]+", "_", (name or Path(path).stem).lower()).strip("_")
    base, n = fid, 2
    while any(f["id"] == fid for f in data["files"]):
        fid, n = f"{base}_{n}", n + 1
    entry = {"id": fid, "name": name or Path(path).name, "path": str(path), "fmt": fmt}
    data["files"].append(entry)
    save_custom(data)
    return entry, f"Added {entry['name']} ({fmt} format, {len(FORMATS[fmt].parse(text))} settings)."


# ================================================================ v1.4: manage user presets
# User presets live in custom_presets.json under "presets"[game_or_file_id][name] = {key: value}.
# That format is unchanged, so presets saved by earlier versions keep loading.

PRESET_FORMAT = "rytweaks-preset"
PRESET_VERSION = 1
MAX_IMPORT_BYTES = 256 * 1024
MAX_PRESET_KEYS = 500
MAX_NAME_LEN = 60
MAX_KEY_LEN = 200
MAX_VALUE_LEN = 500


def clean_name(name):
    """(ok, name_or_message) for a preset name."""
    if not isinstance(name, str):
        return False, "The preset name must be text."
    name = name.strip()
    if not name:
        return False, "Give the preset a name."
    if len(name) > MAX_NAME_LEN:
        return False, f"The preset name can be at most {MAX_NAME_LEN} characters."
    if any(ord(c) < 32 for c in name):
        return False, "The preset name can't contain control characters."
    return True, name


def known_keys(entry_id, file_keys=None):
    """Keys the engine knows for this entry: every key in the built-in tiers of a game.
    For a user's own file there are no built-in tiers, so it is the keys found in that file."""
    game = BY_ID.get(entry_id)
    if game:
        keys = []
        for tier in game.presets.values():
            for k in tier:
                if k not in keys:
                    keys.append(k)
        return keys
    return list(file_keys or [])


def validate_settings(settings, allowed_keys=None):
    """(ok, message). Types: text, int, float or bool values only. If allowed_keys is given,
    every key must be in it."""
    if not isinstance(settings, dict) or not settings:
        return False, "The preset has no settings."
    if len(settings) > MAX_PRESET_KEYS:
        return False, f"The preset has too many settings (limit {MAX_PRESET_KEYS})."
    for k, v in settings.items():
        if not isinstance(k, str) or not k.strip() or len(k) > MAX_KEY_LEN \
                or any(ord(c) < 32 for c in k):
            return False, "The preset contains an invalid setting name."
        if allowed_keys is not None and k not in allowed_keys:
            return False, f"“{k}” is not a setting RYTWEAKS knows for this game."
        if isinstance(v, bool):
            continue
        if isinstance(v, (int, float)):
            if isinstance(v, float) and (v != v or v in (float("inf"), float("-inf"))):
                return False, f"“{k}” has an invalid number."
            continue
        if isinstance(v, str):
            if len(v) > MAX_VALUE_LEN or "\n" in v or "\r" in v:
                return False, f"The value of “{k}” is too long or has line breaks."
            continue
        return False, f"The value of “{k}” has an unsupported type."
    return True, ""


def user_presets(entry_id, data=None):
    return (data or load_custom())["presets"].get(entry_id, {})


def save_user_preset(entry_id, name, settings, replace=False):
    """Create (or, with replace=True, overwrite) a user preset. Returns (status, message):
    status is "ok", "clash" (name already used, nothing written) or "error"."""
    ok, name = clean_name(name)
    if not ok:
        return "error", name
    ok, msg = validate_settings(settings)
    if not ok:
        return "error", msg
    data = load_custom()
    store = data["presets"].setdefault(entry_id, {})
    if name in store and not replace:
        return "clash", f"You already have a preset called “{name}”."
    store[name] = dict(settings)
    save_custom(data)
    return "ok", f"Saved preset “{name}”."


def rename_user_preset(entry_id, old, new, replace=False):
    ok, new = clean_name(new)
    if not ok:
        return "error", new
    data = load_custom()
    store = data["presets"].get(entry_id, {})
    if old not in store:
        return "error", "That preset no longer exists."
    if new == old:
        return "ok", "The name is unchanged."
    if new in store and not replace:
        return "clash", f"You already have a preset called “{new}”."
    store[new] = store.pop(old)
    save_custom(data)
    return "ok", f"Renamed “{old}” to “{new}”."


def duplicate_preset(entry_id, source, new_name, replace=False):
    """Copy a user preset, or a built-in tier (source "Low", "High", ... of a built-in game),
    into a new user preset. Built-in presets themselves are never changed."""
    data = load_custom()
    store = data["presets"].get(entry_id, {})
    game = BY_ID.get(entry_id)
    if source in store:
        settings = store[source]
    elif game and source in game.presets:
        settings = game.presets[source]
    else:
        return "error", "That preset no longer exists."
    return save_user_preset(entry_id, new_name, dict(settings), replace)


def delete_user_preset(entry_id, name):
    data = load_custom()
    if data["presets"].get(entry_id, {}).pop(name, None) is None:
        return False
    save_custom(data)
    return True


def update_user_preset(entry_id, name, settings, file_keys=None):
    """Replace the settings of an existing user preset. Keys the preset already had are kept
    allowed; NEW keys must be ones the engine knows for this game (or exist in the user's file)."""
    data = load_custom()
    store = data["presets"].get(entry_id, {})
    if name not in store:
        return False, "That preset no longer exists."
    allowed = set(known_keys(entry_id, file_keys)) | set(store[name])
    ok, msg = validate_settings(settings, allowed)
    if not ok:
        return False, msg
    store[name] = dict(settings)
    save_custom(data)
    return True, f"Saved the changes to “{name}”."


# ---- export / import

def export_preset_text(entry_id, name):
    """JSON text for a user preset, or None if it doesn't exist."""
    preset = user_presets(entry_id).get(name)
    if preset is None:
        return None
    return json.dumps({"format": PRESET_FORMAT, "version": PRESET_VERSION, "game": entry_id,
                       "name": name, "settings": preset}, indent=2, ensure_ascii=False)


def export_preset(entry_id, name, path):
    text = export_preset_text(entry_id, name)
    if text is None:
        return False, "That preset no longer exists."
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as e:
        return False, f"Couldn't write the file: {e}"
    return True, f"Exported “{name}” to {path}."


def parse_preset_file(raw, entry_id):
    """Validate an exported preset (bytes or str). Returns (ok, message, name, settings)."""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    if len(raw) > MAX_IMPORT_BYTES:
        return False, f"That file is too big to be a preset (limit {MAX_IMPORT_BYTES // 1024} KB).", None, None
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, ValueError):
        return False, "That file isn't a valid RYTWEAKS preset (it isn't readable JSON).", None, None
    if not isinstance(data, dict) or data.get("format") != PRESET_FORMAT:
        return False, "That file isn't a RYTWEAKS preset export.", None, None
    version = data.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        return False, "The preset file has no valid version.", None, None
    if version > PRESET_VERSION:
        return False, "That preset was made by a newer RYTWEAKS. Update RYTWEAKS to import it.", None, None
    if data.get("game") != entry_id:
        return False, (f"That preset is for “{data.get('game')}”, not for the game you have selected."), None, None
    ok, name = clean_name(data.get("name"))
    if not ok:
        return False, name, None, None
    ok, msg = validate_settings(data.get("settings"))
    if not ok:
        return False, msg, None, None
    return True, "", name, dict(data["settings"])


def import_preset(entry_id, path, new_name=None, replace=False):
    """Read, validate and save an exported preset. Returns (status, message, name); status is
    "ok", "clash" (a preset with that name exists; nothing written, ask the user to rename or
    replace) or "error"."""
    try:
        if os.path.getsize(path) > MAX_IMPORT_BYTES:
            return "error", f"That file is too big to be a preset (limit {MAX_IMPORT_BYTES // 1024} KB).", None
        raw = Path(path).read_bytes()
    except OSError as e:
        return "error", f"Couldn't read the file: {e}", None
    ok, msg, name, settings = parse_preset_file(raw, entry_id)
    if not ok:
        return "error", msg, None
    if new_name is not None:
        name = new_name
    status, msg = save_user_preset(entry_id, name, settings, replace)
    return status, msg.replace("Saved preset", "Imported preset") if status == "ok" else msg, name
