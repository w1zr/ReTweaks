"""RETWEAKS settings (the same %APPDATA%\\RETWEAKS\\config.json the original RETWEAKS app used, so every
existing key and value carries over). Unknown keys are kept as they are; writes are atomic."""
import json
import os
import threading
from pathlib import Path

_LOCK = threading.Lock()


def config_path():
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "RETWEAKS" / "config.json"


# Defaults only fill keys that are missing; existing values are never reset (CLAUDE.md section 15).
DEFAULTS = {
    "tray_on_close": True,
    "start_minimized": True,
    "check_updates": True,
    "discord_status": True,
    "discord_show_game": True,
    "temp_unit": "C",
    "interval": 1.0,          # seconds, as the original RETWEAKS stored it
}


def load():
    p = config_path()
    data = {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}
    for k, v in DEFAULTS.items():
        data.setdefault(k, v)
    # Page renamed "FPS test" -> "FPS overlay" (2026-10-22): keep "Open on" pointing at the same page. Repeat-safe.
    if data.get("startup_page") == "FPS test":
        data["startup_page"] = "FPS overlay"
    if data.get("startup_page") == "Notifications":       # page removed in v2.0.1 (owner request)
        data["startup_page"] = "Dashboard"
    return data


def save(settings):
    p = config_path()
    with _LOCK:
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(settings, indent=2), encoding="utf-8")
            os.replace(tmp, p)
            return True
        except OSError:
            return False


def temp_unit(hub):
    """'C' or 'F' — the one temperature-unit setting every page uses (config key temp_unit)."""
    u = (getattr(hub, "settings", {}) or {}).get("temp_unit", "C")
    return "F" if str(u).upper().startswith("F") else "C"


def format_temp(celsius, hub, digits=0):
    """Celsius reading -> text in the user's unit, or 'Unavailable'."""
    try:
        c = float(celsius)
    except (TypeError, ValueError):
        return "Unavailable"
    if temp_unit(hub) == "F":
        return f"{c * 9 / 5 + 32:.{digits}f} °F"
    return f"{c:.{digits}f} °C"


def set_temp_unit(hub, unit):
    """Change °C/°F from anywhere (Settings, the Temperatures page...): saves config.json, then tells every
    page that has on_temp_unit(unit) and every registered selector, so the whole app switches at once."""
    unit = "F" if str(unit).upper().startswith("F") else "C"
    hub.settings["temp_unit"] = unit
    save(hub.settings)
    for page in list((getattr(hub, "rt_pages", {}) or {}).values()):
        fn = getattr(page, "on_temp_unit", None)
        if callable(fn):
            try:
                fn(unit)
            except Exception:
                pass
    for cb in list(getattr(hub, "_temp_unit_listeners", [])):
        try:
            cb(unit)
        except Exception:
            pass
    return unit


def on_temp_unit(hub, callback):
    """Register callback(unit) for widgets that aren't rt pages (the base app panels, selectors)."""
    if not hasattr(hub, "_temp_unit_listeners"):
        hub._temp_unit_listeners = []
    hub._temp_unit_listeners.append(callback)
