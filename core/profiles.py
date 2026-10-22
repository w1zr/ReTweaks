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


PROFILES = {
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
    "Esports": {
        "description": "For competitive games where input feel matters most. Game Mode, Ultimate "
                       "Performance, raw mouse movement (no acceleration), no Xbox background recording, no "
                       "Sticky Keys pop-ups mid-game, no Store apps in the background, no tip "
                       "notifications and no surprise update restarts while you're signed in.",
        "steps": [
            ("Turn on Game Mode", lambda: T["game_mode"].apply(True)),
            ("Ultimate Performance power plan", W.enable_ultimate_power_plan),
            ("Stop Xbox background recording", lambda: T["xbox_capture"].apply(False)),
            ("Turn off mouse acceleration", lambda: T["mouse_accel"].apply(False)),
            ("Turn off Sticky/Filter/Toggle Keys pop-ups", lambda: T["sticky_keys_popup"].apply(False)),
            ("Stop Store apps running in the background", lambda: T["background_apps"].apply(False)),
            ("Turn off tips notifications", lambda: T["tips"].apply(False)),
            ("No automatic restart while signed in", lambda: T["update_restart"].apply(True)),
        ],
    },
    "Max FPS": {
        "description": "Everything in Esports, plus lighter visuals: no transparency, no window "
                       "animations, faster menus, and Windows' optimizations for windowed and borderless "
                       "games. Windows looks plainer. Measure with the FPS test; no FPS gain is promised.",
        "steps": [
            ("Turn on Game Mode", lambda: T["game_mode"].apply(True)),
            ("Ultimate Performance power plan", W.enable_ultimate_power_plan),
            ("Stop Xbox background recording", lambda: T["xbox_capture"].apply(False)),
            ("Turn off mouse acceleration", lambda: T["mouse_accel"].apply(False)),
            ("Turn off Sticky/Filter/Toggle Keys pop-ups", lambda: T["sticky_keys_popup"].apply(False)),
            ("Stop Store apps running in the background", lambda: T["background_apps"].apply(False)),
            ("Turn off tips notifications", lambda: T["tips"].apply(False)),
            ("No automatic restart while signed in", lambda: T["update_restart"].apply(True)),
            ("Turn off transparency effects", lambda: T["transparency"].apply(False)),
            ("Turn off window animations", lambda: T["animations"].apply(False)),
            ("Faster menus", lambda: T["menu_delay"].apply(True)),
            ("Turn on optimizations for windowed games", lambda: T["windowed_games"].apply(True)),
        ],
    },
    "Balanced": {
        "description": "Good everyday setup for a PC you game and work on. Game Mode, the Balanced "
                       "power plan, no Store apps in the background, no tip notifications and no "
                       "surprise update restarts. Looks and animations stay as they are.",
        "steps": [
            ("Turn on Game Mode", lambda: T["game_mode"].apply(True)),
            ("Balanced power plan", W.set_balanced_power_plan),
            ("Stop Store apps running in the background", lambda: T["background_apps"].apply(False)),
            ("Turn off tips notifications", lambda: T["tips"].apply(False)),
            ("No automatic restart while signed in", lambda: T["update_restart"].apply(True)),
        ],
    },
    "Privacy": {
        "description": "Turns off the advertising ID, tailored experiences, optional diagnostic data, "
                       "activity history, web results in Start, online speech, inking and typing "
                       "personalization, and Windows' suggestions, tips and automatic app installs. Leaves "
                       "services alone (those are on the Tweaks page). Each can be undone there.",
        "steps": [(f"Turn off {T[i].name[0].lower() + T[i].name[1:]}", (lambda i=i: T[i].apply(False)))
                  for i in ("ad_id", "tailored", "diag_data", "activity_history", "web_search_start",
                            "online_speech", "inking_typing", "suggested_content", "start_suggestions",
                            "tips", "lockscreen_tips", "silent_apps")],
    },
    "Windows Default": {
        "description": "Puts the main gaming settings back: Game Mode on (the Windows default), the Balanced power "
                       "plan, and Xbox Game Bar background recording back to how it was before RYTWEAKS. "
                       "To undo every other change, use “Undo everything” on the Tweaks page.",
        "steps": [
            ("Turn on Game Mode", lambda: T["game_mode"].apply(True)),
            ("Balanced power plan", W.set_balanced_power_plan),
            ("Xbox background recording back to your original setting", _xbox_original),
        ],
    },
}


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
