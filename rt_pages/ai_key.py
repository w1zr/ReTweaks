"""AI assistant: "Use my own key" (owner request 2026-10-22, after the built-in Gemini key stopped working).

The key is saved where the AI helper (ai/GeminiChat.cs ReadKey) already looks for a replacement key:
%LOCALAPPDATA%\\GeminiChat\\key-v2.dat, encrypted with Windows DPAPI for the current Windows user (same as
.NET ProtectedData.Protect(..., null, CurrentUser)). It is never written to config.json or a log. The helper
uses a saved key first and the built-in key otherwise; DriverAI, ValueAI and the service check use the
same key because they ask GeminiChat for it."""
import os
import re
import tkinter as tk
import webbrowser
from pathlib import Path

AI_STUDIO_URL = "https://aistudio.google.com/apikey"
LIMITS_URL = "https://aistudio.google.com/rate-limit"   # per-model limits for your own key (Google docs)
KEY_RE = re.compile(r"^[A-Za-z0-9._\-]{20,200}$")


def key_path():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "GeminiChat" / "key-v2.dat"


def _protect(data: bytes) -> bytes:
    import win32crypt
    return win32crypt.CryptProtectData(data, None, None, None, None, 0x1)      # CRYPTPROTECT_UI_FORBIDDEN


def _unprotect(blob: bytes) -> bytes:
    import win32crypt
    return win32crypt.CryptUnprotectData(blob, None, None, None, 0x1)[1]


def valid(key):
    return bool(KEY_RE.match((key or "").strip()))


def has_own_key():
    p = key_path()
    try:
        return p.is_file() and bool(_unprotect(p.read_bytes()).decode("utf-8").strip())
    except Exception:
        return False


def save(key):
    """Returns (ok, message). The key itself is never part of the message."""
    key = (key or "").strip()
    if not valid(key):
        return False, "That doesn't look like a Gemini API key. Copy the whole key from Google AI Studio."
    try:
        p = key_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(_protect(key.encode("utf-8")))
    except Exception as e:
        return False, f"Couldn't save the key ({type(e).__name__})."
    return True, "Your key is saved (encrypted for your Windows account). The AI reloads with it now."


def remove():
    try:
        key_path().unlink()
    except FileNotFoundError:
        pass
    except Exception as e:
        return False, f"Couldn't remove the key ({type(e).__name__})."
    return True, "Your key was removed."


def is_key_error(text):
    t = (text or "").lower()
    return "api key not valid" in t or "http 401" in t or "api_key_invalid" in t or "permission_denied" in t


def build_card(hub, parent, g, on_change):
    """The card on the AI assistant page. on_change() restarts the AI so it picks up the key."""
    bg = g["BG"]
    box = tk.Frame(parent, bg=bg)
    box.pack(fill="x", pady=(2, 4))
    row = tk.Frame(box, bg=bg)
    row.pack(fill="x")
    tk.Label(row, text="Your Gemini key", bg=bg, fg=g["FG"], font=(g["UI"], 10, "bold")).pack(side="left",
                                                                                              padx=(0, 10))
    var = tk.StringVar()
    entry = g["REntry"](row, var, width_px=320)
    entry.entry.configure(show="•")
    entry.pack(side="left")
    status = tk.Label(box, text="", bg=bg, fg=g["MUTED"], font=(g["UI"], 9), anchor="w", justify="left",
                      wraplength=900)

    def refresh_status(extra=""):
        base = ("Using your own key." if has_own_key() else
                "No key of your own saved: the AI uses the key built into this version, if it has one. If the AI "
                "shows a key error, paste your own free key here.")
        status.configure(text=(extra + "  " if extra else "") + base)

    def do_save():
        ok, msg = save(var.get())
        var.set("")
        refresh_status(msg)
        if ok:
            on_change()

    def do_remove():
        ok, msg = remove()
        refresh_status(msg)
        if ok:
            on_change()

    entry.entry.bind("<Return>", lambda e: do_save())
    g["RButton"](row, "Save key", do_save, kind="primary").pack(side="left", padx=(8, 4))
    g["RButton"](row, "Remove my key", do_remove, kind="ghost").pack(side="left", padx=4)
    g["RButton"](row, "Get a free key", lambda: webbrowser.open(AI_STUDIO_URL), kind="ghost").pack(side="left",
                                                                                                  padx=4)
    status.pack(fill="x", pady=(4, 0))
    tk.Label(box, text="Keys come from Google AI Studio. Google's terms require you to be 18 or older. Your key is "
                       "stored only on this PC, encrypted for your Windows account, and is sent only to Google.",
             bg=bg, fg=g["MUTED"], font=(g["UI"], 8), anchor="w", justify="left", wraplength=900).pack(fill="x")
    refresh_status()
    box.refresh_status = refresh_status
    return box


# ------------------------------------------------------------------ model choice
# Owner request 2026-10-23: choose the Gemini model like RETWEAKS v1.4-v1.6 did. Same setting key as before
# (ai_model), so a model picked in v1.6 is kept. "" = Automatic: the helper picks the lightweight Flash-Lite model
# (fast, and the most generous free quota). The list comes from Google for the key in use (helper "Load models").
SETTING = "ai_model"
AUTO = "Automatic (newest Flash-Lite)"


def saved_model(hub):
    return str((getattr(hub, "settings", {}) or {}).get(SETTING) or "").strip()


def build_model_row(hub, parent, g, send):
    """Model dropdown for the AI assistant page. send(dict) passes a command to the AI helper."""
    bg = g["BG"]
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=(2, 4))
    tk.Label(row, text="Model", bg=bg, fg=g["FG"], font=(g["UI"], 10, "bold")).pack(side="left", padx=(0, 10))
    saved = saved_model(hub)
    select = g["RSelect"](row, [AUTO] + ([saved] if saved else []), width=300, command=lambda v: choose(v))
    select.set(saved or AUTO)
    select.pack(side="left")
    g["RButton"](row, "See my limits", lambda: webbrowser.open(LIMITS_URL), kind="ghost").pack(side="left",
                                                                                            padx=(8, 0))
    note = tk.Label(row, text="The list loads from Google when the AI starts.", bg=bg, fg=g["MUTED"],
                    font=(g["UI"], 9), anchor="w")
    note.pack(side="left", padx=(10, 0))

    def choose(value):
        name = "" if value == AUTO else str(value).strip()
        hub.settings[SETTING] = name
        from rt_pages import settings_store
        settings_store.save(hub.settings)
        send({"op": "model", "name": name})
        note.configure(text=f"Using {name}." if name else "Using the automatic choice.")

    def set_models(names, selected="", preferred="", found=True):
        names = [str(n) for n in (names or []) if str(n).strip()]
        select.values = [AUTO] + names
        current = saved_model(hub)
        if current and current in names:
            select.set(current)
            note.configure(text=f"Using {current}. {len(names)} models available for this key.")
        elif current:
            select.set(AUTO)
            note.configure(text=f"{current} isn't available for this key, so the automatic choice ({selected}) is used.")
        else:
            select.set(AUTO)
            note.configure(text=f"Automatic: {selected}. {len(names)} models available for this key."
                           if selected else f"{len(names)} models available for this key.")

    row.select, row.set_models, row.choose = select, set_models, choose
    return row
