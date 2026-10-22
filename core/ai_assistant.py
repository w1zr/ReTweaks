# core/ai_assistant.py
"""AI Assistant: advice-only chat through the Google Gemini API (bring your own free key).

- Plain HTTPS with urllib (no SDK). Endpoint and JSON shapes: ai.google.dev/gemini-api/docs
- The API key lives in Windows Credential Manager (win32cred), never in config.json or logs.
- Nothing here runs commands or changes settings; it only sends text and returns text.
- Pure logic (request body, specs summary, response/error parsing) is unit tested.
"""

import json
import re
import socket
import sys
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta"
KEY_URL = "https://aistudio.google.com/apikey"
TERMS_URL = "https://ai.google.dev/terms"

# Google's pricing page lists this stable Flash model as free of charge (checked 2026-10-21).
# The Models list button refreshes the choices from the API for the user's own key.
DEFAULT_MODEL = "gemini-3.8-flash"
FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash-lite"]

CRED_TARGET = "RYTWEAKS/GeminiAPIKey"
TIMEOUT_S = 60
MAX_HISTORY = 20  # messages (user + assistant) sent as `contents`
MAX_OUTPUT_TOKENS = 2048

PAGE_NAMES = ["Dashboard", "Hardware", "Health Check", "FPS test", "Display & drivers", "Tweaks",
              "Profiles", "Game presets", "Program rules", "Startup apps", "Network",
              "Storage & cleanup", "Audio mixer", "Auto clicker", "Snapshots", "Fun tools",
              "Settings"]

SYSTEM_INSTRUCTION = (
    "You are the RYTWEAKS PC help assistant, built into RYTWEAKS, a Windows PC diagnostics and "
    "optimization app. Help with Windows PC performance, gaming, hardware questions and the "
    "user's specific PC.\n"
    "Rules:\n"
    "- Be honest. Say so when you are unsure or when the answer depends on information you "
    "don't have. Do not invent specs, settings, menu names or numbers.\n"
    "- Never promise or claim a guaranteed FPS or ping gain. Gains vary by PC and must be "
    "measured.\n"
    "- Recommend safe, reversible steps first. Warn clearly before anything risky, such as BIOS "
    "changes, registry edits or overclocking, and explain how to undo it.\n"
    "- Prefer pointing to RYTWEAKS features when one fits. RYTWEAKS pages: "
    + ", ".join(PAGE_NAMES) + ".\n"
    "- Refuse requests for cheating or bypassing anti-cheat, and say briefly why.\n"
    "- You give advice only. You cannot run commands or change settings; the user does that, "
    "for example in RYTWEAKS.\n"
    "- Keep answers short and practical: a few bullet points or short steps. Use Markdown."
)


class AIError(Exception):
    """An error whose message is already friendly and safe to show."""


# ---------------------------------------------------------------- API key storage

try:
    if sys.platform == "win32":
        import win32cred  # from pywin32
    else:
        win32cred = None
except Exception:  # ImportError or a broken pywin32
    win32cred = None


def credentials_available():
    return win32cred is not None


def save_key(key):
    if not credentials_available():
        raise AIError("Windows Credential Manager isn't available here.")
    key = (key or "").strip()
    if not key:
        raise AIError("The key is empty.")
    win32cred.CredWrite({
        "Type": win32cred.CRED_TYPE_GENERIC,
        "TargetName": CRED_TARGET,
        "UserName": "RYTWEAKS",
        "Comment": "RYTWEAKS Gemini API key",
        "CredentialBlob": key.encode("utf-16-le"),
        "Persist": win32cred.CRED_PERSIST_LOCAL_MACHINE,
    }, 0)


def load_key():
    """The saved key, or None."""
    if not credentials_available():
        return None
    try:
        cred = win32cred.CredRead(CRED_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception:  # not found (error 1168) or unreadable
        return None
    return decode_blob(cred.get("CredentialBlob"))


def decode_blob(blob):
    """Credential blobs come back as bytes (UTF-16-LE as we wrote them) or sometimes str."""
    if blob is None:
        return None
    if isinstance(blob, str):
        return blob.strip() or None
    try:
        text = bytes(blob).decode("utf-16-le")
    except UnicodeDecodeError:
        text = bytes(blob).decode("utf-8", errors="ignore")
    return text.strip().strip("\x00") or None


def delete_key():
    """Remove the key. Returns True if it is gone (including 'was never saved')."""
    if not credentials_available():
        return False
    try:
        win32cred.CredDelete(CRED_TARGET, win32cred.CRED_TYPE_GENERIC, 0)
    except Exception:
        return load_key() is None
    return True


# ---------------------------------------------------------------- specs summary (whitelist)

_MAC_RE = re.compile(r"\b[0-9A-Fa-f]{2}(?:[:-][0-9A-Fa-f]{2}){5}\b")
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_IPV6_RE = re.compile(r"\b(?:[0-9A-Fa-f]{1,4}:){3,7}[0-9A-Fa-f]{1,4}\b")
_PATH_RE = re.compile(r"(?:[A-Za-z]:\\[^\s,;]*|\\\\[^\s,;]+|/(?:home|Users)/[^\s,;]*)")


def scrub(text, extra_terms=()):
    """Remove anything that looks like a MAC/IP address, a file path, or a given private term."""
    text = str(text)
    for term in extra_terms:
        if term and len(term) >= 3:
            text = re.sub(re.escape(term), "[removed]", text, flags=re.IGNORECASE)
    for rx in (_PATH_RE, _MAC_RE, _IPV6_RE, _IPV4_RE):
        text = rx.sub("[removed]", text)
    return text.strip()


def _num(v, digits=0):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return f"{v:.{digits}f}" if digits else f"{round(v):d}"


def private_terms():
    """Computer name and user name on this PC, so they can never slip into the summary."""
    terms = []
    try:
        import getpass
        import platform
        terms += [platform.node(), getpass.getuser()]
    except Exception:
        pass
    return [t for t in terms if t]


def build_specs_summary(static, sample=None, screens=None, extra_terms=None):
    """Compact PC summary for the model. Built ONLY from the fields listed below.

    static:  the hardware scan dict (ctx.static); sample: live telemetry (ctx.last_sample)
    screens: optional [{"width":1920,"height":1080,"hz":144.0}, ...] (from Qt)
    Anything not listed (serial numbers, computer/user name, IP/MAC, paths, product keys,
    device IDs, monitor/disk names) is never read. Unknown values are left out.
    """
    static = static or {}
    terms = private_terms() if extra_terms is None else list(extra_terms)

    def clean(v):
        return scrub(v, terms) if v not in (None, "") else None

    lines = []
    os_ = static.get("os") or {}
    if os_.get("name"):
        v = " ".join(x for x in (clean(os_.get("name")), clean(os_.get("version")),
                                 f"(build {clean(os_.get('build'))})" if os_.get("build") else None) if x)
        lines.append(f"OS: {v}")

    cpu = static.get("cpu") or {}
    if cpu.get("name"):
        bits = [clean(cpu["name"])]
        if cpu.get("cores") and cpu.get("threads"):
            bits.append(f"{cpu['cores']} cores / {cpu['threads']} threads")
        lines.append("CPU: " + ", ".join(bits))

    for i, g in enumerate(static.get("gpus") or [], 1):
        if not g.get("name"):
            continue
        bits = [clean(g["name"])]
        bits.append(f"{_num(g['vram_gb'], 0 if float(g['vram_gb']).is_integer() else 1)} GB VRAM"
                    if isinstance(g.get("vram_gb"), (int, float)) else "VRAM unavailable")
        if g.get("driver_version"):
            bits.append(f"driver {clean(g['driver_version'])}")
        if g.get("driver_date"):
            bits.append(f"driver date {clean(g['driver_date'])}")
        lines.append(f"GPU {i}: " + ", ".join(bits))

    ram = static.get("ram") or {}
    if _num(ram.get("total_gb"), 1):
        bits = [f"{_num(ram['total_gb'], 1)} GB usable"]
        if ram.get("type"):
            bits.append(clean(ram["type"]))
        if ram.get("running_mts"):
            bits.append(f"running at {_num(ram['running_mts'])} MT/s")
        lines.append("RAM: " + ", ".join(b for b in bits if b))

    for i, d in enumerate(static.get("disks") or [], 1):
        bits = []
        if _num(d.get("size_gb")):
            bits.append(f"{_num(d['size_gb'])} GB")
        for k in ("media", "bus", "health"):
            if d.get(k):
                bits.append(("health " if k == "health" else "") + clean(d[k]))
        if bits:
            lines.append(f"Disk {i}: " + ", ".join(bits))

    for i, s in enumerate(screens or [], 1):
        if _num(s.get("width")) and _num(s.get("height")):
            hz = f" at {_num(s['hz'])} Hz" if _num(s.get("hz")) else ""
            lines.append(f"Monitor {i}: {_num(s['width'])}x{_num(s['height'])}{hz}")

    live = []
    sample = sample or {}
    scpu = sample.get("cpu") or {}
    if _num(scpu.get("load")) is not None:
        t = f", {_num(scpu['temp_c'])} C" if _num(scpu.get("temp_c")) else ""
        live.append(f"CPU load {_num(scpu['load'])}%{t}")
    for i, g in enumerate(sample.get("gpus") or [], 1):
        bits = []
        if _num(g.get("load")) is not None:
            bits.append(f"load {_num(g['load'])}%")
        if _num(g.get("temp_c")):
            bits.append(f"{_num(g['temp_c'])} C")
        if _num(g.get("vram_used_gb"), 1):
            bits.append(f"VRAM in use {_num(g['vram_used_gb'], 1)} GB")
        if bits:
            live.append(f"GPU {i} " + ", ".join(bits))
    sram = sample.get("ram") or {}
    if _num(sram.get("percent")) is not None:
        live.append(f"RAM in use {_num(sram['percent'])}%")
    if live:
        lines.append("Right now: " + "; ".join(live))

    return "\n".join(lines)


# ---------------------------------------------------------------- request building

def trim_history(history, max_messages=MAX_HISTORY):
    """Keep the last max_messages messages and make sure the first one is from the user."""
    msgs = [m for m in (history or []) if m.get("text")]
    msgs = msgs[-max_messages:]
    while msgs and msgs[0].get("role") != "user":
        msgs.pop(0)
    return msgs


def build_system_text(specs_text=None):
    if specs_text:
        return (SYSTEM_INSTRUCTION + "\n\nThe user's PC (shared by the user; values may be "
                "missing):\n" + specs_text)
    return SYSTEM_INSTRUCTION


def build_request_body(history, specs_text=None):
    """JSON body for models/{model}:generateContent. history: [{"role": "user"|"model", "text": ...}]"""
    contents = [{"role": "model" if m["role"] == "model" else "user",
                 "parts": [{"text": m["text"]}]} for m in trim_history(history)]
    return {
        "systemInstruction": {"parts": [{"text": build_system_text(specs_text)}]},
        "contents": contents,
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": MAX_OUTPUT_TOKENS},
    }


# ---------------------------------------------------------------- response / error parsing

def parse_response(data):
    """Text of the first candidate. Raises AIError with a friendly message otherwise."""
    if not isinstance(data, dict):
        raise AIError("Google sent a reply RYTWEAKS couldn't read.")
    block = (data.get("promptFeedback") or {}).get("blockReason")
    cands = data.get("candidates") or []
    if not cands:
        if block:
            raise AIError(f"Google's safety filter blocked this question ({block}). "
                          "Try rephrasing it.")
        raise AIError("Google returned no answer. Try again or rephrase the question.")
    cand = cands[0] or {}
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought")).strip()
    reason = cand.get("finishReason")
    if not text:
        if reason in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "RECITATION"):
            raise AIError(f"Google withheld the answer ({reason}). Try rephrasing the question.")
        raise AIError("Google returned an empty answer. Try again.")
    if reason == "MAX_TOKENS":
        text += "\n\n*(The answer was cut off at the length limit. Ask me to continue.)*"
    return text


def _error_fields(body_text):
    try:
        err = (json.loads(body_text) or {}).get("error") or {}
    except (ValueError, AttributeError, TypeError):
        return "", ""
    return str(err.get("status") or err.get("code") or ""), str(err.get("message") or "")


def parse_error(http_status, body_text="", key=None):
    """Friendly, honest message for an HTTP error from the Gemini API."""
    status, message = _error_fields(body_text)
    low = f"{status} {message}".lower()
    if key:
        message = message.replace(key, "[key]")
    if "api key" in low and ("not valid" in low or "invalid" in low or "expired" in low) \
            or "api_key_invalid" in low or http_status == 401:
        return ("Google says the API key isn't valid. Check that you pasted the whole key, or "
                "make a new one at aistudio.google.com/apikey.")
    if "location" in low and ("not supported" in low or "region" in low):
        return ("The Gemini API isn't available in your region with this key. Google decides "
                "this, so RYTWEAKS can't work around it.")
    if http_status == 403:
        return ("Google refused the request (403). The key may not have permission for this "
                "model, or the API isn't offered in your region. Details: "
                + (message or "none given"))
    if http_status == 429 or "resource_exhausted" in low or "quota" in low:
        return ("You've hit the free-tier limit for now (requests per minute or per day). "
                "Wait a bit and try again, or pick another model in the list.")
    if http_status in (500, 502, 503, 504) or "unavailable" in low:
        return "Google's service is busy or down right now (" + str(http_status) + "). Try again in a minute."
    if http_status == 404:
        return ("Google doesn't know this model name. Press Refresh models and pick one from "
                "the list.")
    if http_status == 400:
        return "Google rejected the request (400): " + (message or "no details given")
    return f"Google returned error {http_status}: " + (message or "no details given")


def parse_models(data):
    """Chat-capable Gemini 'flash' model IDs from a GET /v1beta/models reply."""
    out = []
    for m in (data or {}).get("models") or []:
        name = str(m.get("name", ""))
        mid = name.split("/", 1)[-1]
        methods = m.get("supportedGenerationMethods") or []
        if not mid.startswith("gemini") or "flash" not in mid or "generateContent" not in methods:
            continue
        if any(x in mid for x in ("tts", "image", "live", "audio", "embedding", "robotics",
                                  "computer-use", "native")):
            continue
        out.append(mid)
    return sorted(set(out), reverse=True)


# ---------------------------------------------------------------- network

def _request(method, url, key, body=None, timeout=TIMEOUT_S):
    headers = {"x-goog-api-key": key}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        try:
            text = e.read().decode("utf-8", errors="replace")
        except Exception:
            text = ""
        raise AIError(parse_error(e.code, text, key))
    except (socket.timeout, TimeoutError):
        raise AIError("Google didn't answer within 60 seconds. Try again.")
    except urllib.error.URLError as e:
        if isinstance(e.reason, (socket.timeout, TimeoutError)):
            raise AIError("Google didn't answer within 60 seconds. Try again.")
        raise AIError("Couldn't reach Google. Check your internet connection.")
    except ValueError:
        raise AIError("Google sent a reply RYTWEAKS couldn't read.")


def generate(key, model, history, specs_text=None, timeout=TIMEOUT_S):
    """Send the conversation and return the assistant's text. Raises AIError."""
    url = f"{API_ROOT}/models/{model}:generateContent"
    return parse_response(_request("POST", url, key, build_request_body(history, specs_text), timeout))


def list_models(key, timeout=30):
    return parse_models(_request("GET", f"{API_ROOT}/models?pageSize=200", key, timeout=timeout))
