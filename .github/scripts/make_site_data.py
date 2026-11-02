"""Writes docs/site-data.json: the website's numbers and lists, read straight from the app code.

The website (docs/index.html) loads this file and fills every count, the page list, the language list and the
preset preview from it, so the site always matches the code. Version, release notes, size and SHA-256 come from
the latest GitHub release instead (the page asks the GitHub API).

Run from the repo root:  python .github/scripts/make_site_data.py
The "Site data" workflow runs it on every push to main and every published release, and commits the file
when something changed. If any value can't be read, nothing is written and the run fails, so the site keeps the last good file.
"""
import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "site-data.json")
DEMO_PRESETS = ("balanced", "maxfps", "privacy")   # the three shown in "How a preset runs"

data, counts, problems = {}, {}, []


def grab(label, fn):
    try:
        return fn()
    except Exception as e:                               # keep going: one unreadable value must not block the rest
        problems.append(f"{label}: {type(e).__name__}: {e}")
        return None


def version():
    from core.version import __version__
    return __version__


def tweaks():
    import retweaks_data as d
    counts["tweaks"] = len(d.TWEAKS)
    counts["categories"] = len(d.CATS)
    counts["presets"] = len(d.PRESET_ORDER)
    counts["games"] = len(d.GAMES)
    by_id = {t["id"]: t for t in d.TWEAKS}
    presets, used = {}, {}
    for key in DEMO_PRESETS:
        p = d.PRESETS[key]
        presets[key] = {"name": p["name"], "ids": [i for i in p["ids"] if i in by_id]}
        for i in presets[key]["ids"]:
            t = by_id[i]
            used[i] = [t["name"], t.get("risk") or "Safe", 1 if t.get("reboot") else 0, 1 if t.get("undo") is None else 0]
    data["presets"] = presets
    data["tweaks"] = used


def exact_undo():
    from core.tweaks import TWEAKS
    counts["exact_undo"] = len(TWEAKS)


def appearance():
    import appearance as a
    counts["themes"] = len(a.THEMES)
    counts["backgrounds"] = len([x for x in a.ANIMATIONS if x not in ("Off", "Picture")])


def languages():
    from rt_i18n import LANGUAGES
    counts["languages"] = len(LANGUAGES)
    data["languages"] = list(LANGUAGES.values())


def pages():
    from rt_sidebar import NAV
    names = [name for _, items in NAV for name, _ in items]
    counts["pages"] = len(names)
    data["pages"] = names


def crosshairs():
    from core.crosshair import ALL_BUILTIN
    counts["crosshairs"] = len(ALL_BUILTIN)


for label, fn in (("version", None), ("tweaks", tweaks), ("exact undo", exact_undo), ("appearance", appearance),
                  ("languages", languages), ("pages", pages), ("crosshairs", crosshairs)):
    if fn is None:
        v = grab(label, version)
        if v:
            data["version"] = v
    else:
        grab(label, fn)

if problems:                                          # never publish a half-read file; the page keeps the last good one
    for p in problems:
        print("Not read:", p)
    sys.exit(1)
data["counts"] = counts
text = json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
old = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
if text != old:
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("Updated", os.path.relpath(OUT, ROOT))
else:
    print("No change")
