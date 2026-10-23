"""Merge translation batches into the language catalogs.

Batches are JSON files {"<queue index>": [es, fr, de, pt-BR] | "="} that refer to rows of a queue
file [[index, "s"|"t", english, source file], ...] ("t" = template with {0} placeholders, "=" = keep English).
Existing catalog entries are kept unless a batch gives a new translation for the same English text.

    python tools/i18n_merge.py QUEUE.json BATCH_DIR

Checks every translation keeps only placeholders the English has (a plural helper such as "{1}" for "s"
may be dropped), and the same number of line breaks.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODES = ["es", "fr", "de", "pt-BR"]


def load_cat(code):
    p = os.path.join(ROOT, "i18n", code + ".json")
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        return {"strings": dict(d.get("strings", {})), "templates": dict(d.get("templates", {}))}
    except (OSError, ValueError):
        return {"strings": {}, "templates": {}}


def main(queue_path, batch_dir):
    with open(queue_path, encoding="utf-8") as f:
        queue = {str(i): (k, en) for i, k, en, _src in json.load(f)}
    batch = {}
    for p in sorted(glob.glob(os.path.join(batch_dir, "*.json"))):
        with open(p, encoding="utf-8") as f:
            batch.update(json.load(f))
    cats = {c: load_cat(c) for c in CODES}
    problems = 0
    for idx, val in batch.items():
        if idx not in queue or val == "=":
            continue
        kind, en = queue[idx]
        if not (isinstance(val, list) and len(val) == 4):
            print("bad entry", idx, val)
            problems += 1
            continue
        ph = set(re.findall(r"\{\d+\}", en))
        for code, t in zip(CODES, val):
            if set(re.findall(r"\{\d+\}", t)) - ph:
                print("placeholder", code, idx, repr(en), repr(t))
                problems += 1
                continue
            if t.count("\n") != en.count("\n"):
                print("newlines", code, idx, repr(en)[:60])
            cats[code]["templates" if kind == "t" else "strings"][en] = t
    for code in CODES:
        c = cats[code]
        out = {"language": code,
               "note": "Machine-made translations of RETWEAKS' English text; corrections welcome.",
               "strings": dict(sorted(c["strings"].items())),
               "templates": dict(sorted(c["templates"].items()))}
        with open(os.path.join(ROOT, "i18n", code + ".json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=0, sort_keys=False)
            f.write("\n")
        print(code, len(c["strings"]), "strings,", len(c["templates"]), "templates")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
