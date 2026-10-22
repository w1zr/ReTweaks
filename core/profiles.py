# core/profiles.py
"""Performance profiles: named bundles of the real tweaks in core/optimizer.py.

Each step runs a real Windows change and reports its real result. Nothing here deletes
user files or changes game files.
"""

from core.optimizer import WindowsOptimizer as W

PROFILES = {
    "Max Performance": {
        "description": "For gaming sessions. Turns on Game Mode, switches to the Ultimate "
                       "Performance power plan and stops Xbox Game Bar recording in the background. "
                       "Laptops will use more battery and run warmer.",
        "steps": [
            ("Turn on Game Mode", lambda: W.set_game_mode(True)),
            ("Ultimate Performance power plan", W.enable_ultimate_power_plan),
            ("Stop Xbox background recording", lambda: W.set_xbox_captures(True)),
        ],
    },
    "Windows Default": {
        "description": "Puts these settings back the way Windows ships them: Game Mode on, "
                       "Balanced power plan, Xbox Game Bar background recording allowed.",
        "steps": [
            ("Turn on Game Mode", lambda: W.set_game_mode(True)),
            ("Balanced power plan", W.set_balanced_power_plan),
            ("Allow Xbox background recording", lambda: W.set_xbox_captures(False)),
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
