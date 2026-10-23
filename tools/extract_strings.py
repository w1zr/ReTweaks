"""Collects the user-facing English strings of the RETWEAKS app into i18n/strings_en.json.

AST pass over every runtime module (not checks/tests/tools/legacy Qt UI): plain string constants that look
like UI text, plus f-strings turned into templates with numbered placeholders ({0}, {1}, ...). Heuristics
skip identifiers, paths, registry keys, URLs, commands and format codes. Extra strings can be listed in
i18n/extra_en.json. Run: python tools/extract_strings.py   (then python tools/i18n_coverage.py)."""
import ast
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP_FILES = {"build.py", "create_logo.py", "main.py", "fetch_app_logos.py", "rt_splash_qt.py",
              "renderbench.py", "build_branding.py"}
SKIP_DIRS = {"checks", "tests", "tools", "ui", "build", "dist", "__pycache__", ".git", "i18n", "ai", "assets",
             "release-notes", "docs", "crosshairs"}


HEADINGS = {"MONITOR", "OPTIMIZE", "TOOLS", "APP", "COOLING", "LIGHTING", "RETWEAKS", "ACTIVITY", "PRESET",
            "CUSTOM", "CLEAN", "APPLY", "TUNE", "HELP", "TIPS", "SYSTEM", "GAMES", "AUDIO", "STORAGE", "DRIVERS",
            "BENCHMARK", "PRESETS", "LOG", "UNDO", "STATUS", "NETWORK", "DISPLAY", "BROWSER", "FANS", "WARNING"}


NOT_UI = {"KEYWORDS", "ICON_ALIASES", "PAGE_SEARCH", "APP_ID", "_REDRAW"}
NOT_UI_CALLS = {"run", "Popen", "check_output", "call", "compile", "match", "search", "fullmatch", "sub",
                "findall", "split", "OpenKey", "CreateKey", "QueryValueEx", "SetValueEx", "DeleteValue",
                "getenv", "startswith", "endswith", "join", "replace", "strip", "encode",
                "decode", "ps", "_ps", "powershell", "run_ps", "reg", "_reg", "netsh", "Path", "open", "exists",
                "bind", "bind_all", "after", "attributes", "event_generate", "tag_bind", "itemcget", "cget",
                "WinDLL", "CDLL", "LoadLibrary", "getattr", "hasattr", "isinstance", "format_exc", "lower",
                "upper", "index", "find", "count", "pop", "dumps", "loads", "urlopen", "Request", "quote",
                "write_json", "read_json", "log_write", "print", "debug", "write"}


def runtime_files():
    out = []
    for name in sorted(os.listdir(ROOT)):
        p = os.path.join(ROOT, name)
        if name.endswith(".py") and not name.startswith("check_") and name not in SKIP_FILES:
            out.append(p)
    for sub in ("rt_pages", "core"):
        d = os.path.join(ROOT, sub)
        for name in sorted(os.listdir(d)):
            if name.endswith(".py"):
                out.append(os.path.join(d, name))
    return out


BAD = re.compile(r"(\\\\|\\[A-Za-z]|://|^[-/$.%#@<]|\.(exe|dll|json|ini|png|ico|svg|html|txt|log|cs|py|bat|ps1|reg)\b"
                 r"|^HK(LM|CU)|^[A-Za-z_][A-Za-z0-9_]*$|^[A-Za-z0-9_.:-]+$|^\s*$|^#[0-9a-fA-F]{3,8}$"
                 r"|\bGet-|\bSet-|Select-Object|Format-|-NoProfile|\$_|\breg add\b|\bpowershell\b|\bschtasks\b"
                 r"|^[a-z_]+(\.[a-z_]+)+$|^<<|^\{|%[sd]|^[A-Za-z]:\\)", re.I)


CODEY = re.compile(r"\(\?i\)|\$[A-Za-z]|\| Out-|Out-Null|-NoRestart|\[A-Za-z0-9|AIza|\{\d*,?\d*\}|::|=>|\)\s*\{")


def ui_like(s):
    if len(s) < 2 or len(s) > 1500 or not re.search(r"[A-Za-z]{2}", s):
        return False
    if CODEY.search(s):
        return False
    if " " not in s.strip():
        # one token: keep plain words ("Apply", "Processor") and ALL-CAPS headings ("MONITOR"), not identifiers
        # ("AdapterLuid", "DeviceString") or codes ("BGRA")
        t = s.strip()
        if re.fullmatch(r"[A-Z][a-z]+[.:…]?|[a-z]+…", t):
            return True
        if re.fullmatch(r"[A-Z]{4,}", t) and t in HEADINGS:
            return True
        return False
    if BAD.search(s):
        # single capitalised words / ALL CAPS headings are fine ("Apply", "MONITOR"); identifiers aren't
        if re.fullmatch(r"[A-Z][a-z]+|[A-Z][A-Z &]+[A-Z]|[A-Z][a-z]+[A-Z]?[a-z]*", s) and "_" not in s:
            return True
        return False
    return True


def template_of(node):
    parts, n = [], 0
    for v in node.values:
        if isinstance(v, ast.Constant):
            parts.append(str(v.value).replace("{", "{{").replace("}", "}}"))
        else:
            parts.append("{%d}" % n)
            n += 1
    t = "".join(parts)
    lit = re.sub(r"\{\d+\}", "", t)
    if n == 0 or not re.search(r"[A-Za-z]{3}", lit) or BAD.search(lit.replace("{{", "").replace("}}", "")):
        return None
    if re.fullmatch(r"[\s\W\d{}]*", lit):
        return None
    return t


def main():
    strings, templates = {}, {}
    for path in runtime_files():
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except (SyntaxError, UnicodeDecodeError):
            continue
        rel = os.path.relpath(path, ROOT)
        doc_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    doc_nodes.add(id(first.value))
        skip_nodes = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id in NOT_UI for t in node.targets):
                for sub in ast.walk(node.value):
                    skip_nodes.add(id(sub))
            # arguments to commands / patterns are never shown as text
            if isinstance(node, ast.Call):
                fn = node.func
                name = fn.attr if isinstance(fn, ast.Attribute) else (fn.id if isinstance(fn, ast.Name) else "")
                if name in NOT_UI_CALLS:
                    for sub in ast.walk(node):
                        if sub is not node.func:
                            skip_nodes.add(id(sub))
        fstring_parts = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for v in node.values:
                    fstring_parts.add(id(v))
                t = template_of(node)
                if t:
                    templates.setdefault(t, rel)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in doc_nodes \
                    and id(node) not in fstring_parts and id(node) not in skip_nodes:
                s = node.value
                if ui_like(s):
                    strings.setdefault(s, rel)
    extra = os.path.join(ROOT, "i18n", "extra_en.json")
    if os.path.exists(extra):
        for s in json.load(open(extra, encoding="utf-8")):
            strings.setdefault(s, "extra")
    out = {"strings": sorted(strings), "templates": sorted(templates)}
    json.dump(out, open(os.path.join(ROOT, "i18n", "strings_en.json"), "w", encoding="utf-8"), indent=1,
              ensure_ascii=False)
    print(len(out["strings"]), "strings,", len(out["templates"]), "templates")


if __name__ == "__main__":
    main()
