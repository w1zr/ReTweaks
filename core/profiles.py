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
    "Windows Default": {
        "description": "Puts these settings back: Game Mode on (the Windows default), the Balanced power "
                       "plan, and Xbox Game Bar background recording back to how it was before RYTWEAKS.",
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
