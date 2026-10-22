# core/profiles.py
"""Performance profiles: named bundles of the real tweaks in core/optimizer.py.

Each step runs a real Windows change and reports its real result. Nothing here deletes
user files or changes game files.
"""

from core.optimizer import WindowsOptimizer as W
from core.tweaks import BY_ID as T

# Steps use core.tweaks so "Undo" / "Undo everything" can put the original settings back.

def _xbox_original():
    ok, msg = T["xbox_capture"].undo()
    if not ok and "Nothing to undo" in msg:
        return True, "Already at your original setting."
    return ok, msg


_EXISTING = {
    "Max Performance": {
        "description": "For gaming sessions. Turns on Game Mode, switches to the Ultimate "
                       "Performance power plan and stops Xbox Game Bar recording in the background. "
                       "Laptops will use more battery and run warmer.",
        "steps": [
            ("Turn on Game Mode", lambda: T["game_mode"].apply(True)),
            ("Ultimate Performance power plan", W.enable_ultimate_power_plan),
            ("Stop Xbox background recording", lambda: T["xbox_capture"].apply(False)),
        ],
    },
    "Windows Default": {
        "description": "Puts the main gaming settings back: Game Mode on (the Windows default), the Balanced power "
                       "plan, and Xbox Game Bar background recording back to how it was before RETWEAKS. "
                       "To undo every other change, use “Undo everything” on the Tweaks page.",
        "steps": [
            ("Turn on Game Mode", lambda: T["game_mode"].apply(True)),
            ("Balanced power plan", W.set_balanced_power_plan),
            ("Xbox background recording back to your original setting", _xbox_original),
        ],
    },
}


# ---------------------------------------------------------------- presets (v1.4.3)
# Each preset is a list of INDIVIDUAL tweaks set On or Off (plus an optional power plan). Every one of
# them is a normal tweak on the Tweaks page with its own Undo, and "Undo everything" puts all back.
# None of these presets promises an FPS gain; measure with the FPS test.

_E = {"game_mode": True, "update_restart": True,
      "xbox_capture": False, "mouse_accel": False, "sticky_keys_popup": False, "background_apps": False,
      "tips": False, "notification_banners": False, "narrator_shortcut": False, "power_throttling": False}

PRESETS = {
    "Esports": {
        "description": "For competitive games where input feel matters most: raw mouse movement, no "
                       "pop-ups or accidental shortcuts mid-match, nothing slowed down in the background, "
                       "no surprise update restarts.",
        "power": "ultimate", "tweaks": dict(_E)},
    "Max FPS": {
        "description": "Everything in Esports, plus lighter Windows visuals and less running in the "
                       "background. Windows looks plainer.",
        "power": "ultimate",
        "tweaks": {**_E, "transparency": False, "animations": False, "menu_delay": True,
                   "windowed_games": True, "edge_background": False}},
    "Balanced": {
        "description": "Good everyday setup for a PC you game and work on. Windows keeps its normal look "
                       "and the Balanced power plan.",
        "power": "balanced",
        "tweaks": {"game_mode": True, "update_restart": True, "transparency": True, "animations": True,
                   "background_apps": False, "tips": False}},
    "Low-end PC": {
        "description": "For PCs that get low FPS: turns off visual extras and things that run in the "
                       "background, so more of a weak CPU and GPU is left for the game. Laptops will use "
                       "more battery.",
        "power": "ultimate",
        "tweaks": {"game_mode": True, "windowed_games": True, "menu_delay": True, "xbox_capture": False,
                   "transparency": False, "animations": False, "background_apps": False,
                   "edge_background": False, "widgets": False, "tips": False, "start_suggestions": False,
                   "silent_apps": False, "power_throttling": False}},
    "High quality": {
        "description": "For a strong PC where you want Windows to look its best: all visual effects "
                       "on, Game Mode and windowed-game optimizations on, Balanced power plan. Set the "
                       "in-game graphics on the Game presets page.",
        "power": "balanced",
        "tweaks": {"game_mode": True, "transparency": True, "animations": True, "windowed_games": True}},
    "Ultra quality": {
        "description": "High quality plus the Ultimate Performance plan and hardware-accelerated GPU "
                       "scheduling (needed for NVIDIA DLSS Frame Generation on RTX 40 and newer). "
                       "Restart after applying.",
        "power": "ultimate",
        "tweaks": {"game_mode": True, "transparency": True, "animations": True, "windowed_games": True,
                   "hags": True, "power_throttling": False}},
    "Streamer": {
        "description": "For streaming or recording with OBS or similar: no notification pop-ups on "
                       "stream, no Xbox recording competing with your recorder, no accidental "
                       "accessibility shortcuts, no update restarts while live.",
        "power": "ultimate",
        "tweaks": {"game_mode": True, "update_restart": True, "xbox_capture": False,
                   "notification_banners": False, "tips": False, "sticky_keys_popup": False,
                   "narrator_shortcut": False, "power_throttling": False}},
    "Privacy": {
        "description": "Turns off what Windows collects for ads and suggestions. Leaves services alone "
                       "(those are on the Tweaks page).",
        "power": None,
        "tweaks": {i: False for i in ("ad_id", "tailored", "diag_data", "activity_history",
                                       "web_search_start", "online_speech", "inking_typing",
                                       "suggested_content", "start_suggestions", "tips",
                                       "lockscreen_tips", "silent_apps", "recall")}},
}

_POWER = {"ultimate": ("Ultimate Performance power plan", lambda: W.enable_ultimate_power_plan()),
          "balanced": ("Balanced power plan", lambda: W.set_balanced_power_plan())}


def _steps(preset):
    steps = []
    if preset.get("power"):
        steps.append(_POWER[preset["power"]])
    for tid, on in preset["tweaks"].items():
        steps.append((f"{T[tid].name}: {'On' if on else 'Off'}", (lambda t=T[tid], v=on: t.apply(v))))
    return steps


PROFILES = {name: {"description": p["description"], "steps": _steps(p)} for name, p in PRESETS.items()}
PROFILES.update(_EXISTING)       # Max Performance and Windows Default stay exactly as before


def preview(name):
    """What a preset would change, read from Windows: [(label, current, target, changes)]."""
    p = PRESETS.get(name)
    if p is None:
        return [(step, "", "", True) for step, _ in PROFILES[name]["steps"]]
    out = []
    if p.get("power"):
        label, _ = _POWER[p["power"]]
        cur = W.get_active_power_plan()
        want = "Ultimate Performance" if p["power"] == "ultimate" else "Balanced"
        out.append((label, cur, want, want.lower() not in str(cur).lower()))
    for tid, on in p["tweaks"].items():
        t = T[tid]
        try:
            cur = t.get_state()
        except Exception:
            cur = "Unknown"
        want = "On" if on else "Off"
        out.append((t.name, cur, want, cur != want))
    return out


# ---------------------------------------------------------------- selection (v1.4.3, Tweaks page)
# A preset only TICKS tweaks on the Tweaks page; the user can untick or add tweaks, then applies the
# selection. A selection is [(key, target)]: key is a tweak id or "power"; target is True/False for a
# tweak, "ultimate"/"balanced" for the power plan.

SELECTABLE_PRESETS = dict(PRESETS)
SELECTABLE_PRESETS["Max Performance"] = {     # same changes as the original Max Performance profile
    "description": PROFILES["Max Performance"]["description"], "power": "ultimate",
    "tweaks": {"game_mode": True, "xbox_capture": False}}


def preset_selection(name):
    p = SELECTABLE_PRESETS[name]
    sel = [("power", p["power"])] if p.get("power") else []
    return sel + list(p["tweaks"].items())


def _label(key, target):
    if key == "power":
        return _POWER[target][0]
    return f"{T[key].name}: {'On' if target else 'Off'}"


def selection_preview(selection):
    """[(label, current, target, changes)] read from Windows, like preview()."""
    out = []
    for key, target in selection:
        if key == "power":
            cur = W.get_active_power_plan()
            want = "Ultimate Performance" if target == "ultimate" else "Balanced"
            out.append((_POWER[target][0], cur, want, want.lower() not in str(cur).lower()))
            continue
        try:
            cur = T[key].get_state()
        except Exception:
            cur = "Unknown"
        want = "On" if target else "Off"
        out.append((T[key].name, cur, want, cur != want))
    return out


def apply_selection(selection):
    """Apply each selected item. Returns [(label, ok, message)]; one failure never stops the rest."""
    results = []
    for key, target in selection:
        try:
            ok, msg = _POWER[target][1]() if key == "power" else T[key].apply(bool(target))
        except Exception as e:
            ok, msg = False, str(e)
        results.append((_label(key, target), ok, msg))
    return results


def apply_profile(name):
    """Run every step. Returns a list of (step_name, ok, message)."""
    results = []
    for step_name, fn in PROFILES[name]["steps"]:
        try:
            ok, msg = fn()
        except Exception as e:  # never let one step stop the others
            ok, msg = False, str(e)
        results.append((step_name, ok, msg))
    return results
