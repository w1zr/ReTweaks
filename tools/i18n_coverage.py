"""Translation coverage: how much of i18n/strings_en.json (from tools/extract_strings.py) each catalog covers.

    python tools/i18n_coverage.py            # summary per language
    python tools/i18n_coverage.py --missing  # also list the English text that has no translation yet

Text deliberately kept in English (product, game and hardware names, commands, file names, language names)
is listed in i18n/keep_en.json and counts as covered.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODES = ["es", "fr", "de", "pt-BR"]


def _load(name, default):
    try:
        with open(os.path.join(ROOT, "i18n", name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def report(show_missing=False):
    en = _load("strings_en.json", {"strings": [], "templates": []})
    keep = _load("keep_en.json", {"strings": [], "templates": []})
    want_s = [s for s in en.get("strings", []) if s not in set(keep.get("strings", []))]
    want_t = [t for t in en.get("templates", []) if t not in set(keep.get("templates", []))]
    result = {}
    for code in CODES:
        cat = _load(code + ".json", {})
        s, t = cat.get("strings", {}), cat.get("templates", {})
        miss_s = [x for x in want_s if x not in s]
        miss_t = [x for x in want_t if x not in t]
        total = len(want_s) + len(want_t)
        done = total - len(miss_s) - len(miss_t)
        result[code] = (done, total, miss_s, miss_t)
        print(f"{code:6} {done}/{total}  {100.0 * done / max(1, total):.1f}%   "
              f"(strings {len(want_s) - len(miss_s)}/{len(want_s)}, templates {len(want_t) - len(miss_t)}/{len(want_t)})")
        if show_missing:
            for x in miss_s + miss_t:
                print("   missing:", json.dumps(x, ensure_ascii=False)[:140])
    return result


if __name__ == "__main__":
    report("--missing" in sys.argv)
