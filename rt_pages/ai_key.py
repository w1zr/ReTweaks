"""AI assistant page: Gemini model choice.

The AI uses the built-in keys added at build time (build.py, GitHub secret GEMINI_API_KEY); ai/GeminiChat.cs switches
to the next key when Google says one no longer works. The "use my own key" box (v2.0.1 development) was removed by
owner request 2026-10-23 once the built-in keys were confirmed working; the helper no longer reads saved keys."""
import tkinter as tk
import webbrowser

LIMITS_URL = "https://aistudio.google.com/rate-limit"   # per-model limits for a key (Google docs)


def is_key_error(text):
    t = (text or "").lower()
    return "api key not valid" in t or "http 401" in t or "api_key_invalid" in t or "rejected every key" in t


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
