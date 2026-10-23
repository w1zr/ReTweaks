"""AI assistant page (rt_pages/ai_key.py): the own-key box is gone (owner request 2026-10-23); model picker
(setting ai_model, same key as RETWEAKS v1.6) and key-error detection."""
import os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_aikey_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import retweaks as app, hubplus
from rt_pages import ai_key
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.geometry("1500x940+0+0"); hub.deiconify()
pump = lambda n=15: [hub.update() or time.sleep(0.01) for _ in range(n)]
pump(30)
assert not hasattr(hub, "ai_key_card"), "own-key box should be gone"
assert not hasattr(ai_key, "build_card") and not hasattr(ai_key, "save")
assert ai_key.is_key_error("Google HTTP 401: API key not valid. Please pass a valid API key.")
assert ai_key.is_key_error("Google rejected every key (2). Google HTTP 400: API key expired.")
assert not ai_key.is_key_error("Google's usage limit was reached. Try again later.")
# ---- model picker (setting ai_model, same key as RETWEAKS v1.6)
import json
sent = []
hub.ai_bridge = type("B", (), {"send": lambda self, m: sent.append(m), "close": lambda self, **k: None})()
row = hub.ai_model_row
assert row.select.get() == ai_key.AUTO
names = ["gemini-2.5-flash-lite", "gemini-3.5-flash", "gemini-3.5-flash-lite"]
row.set_models(names, "gemini-3.5-flash-lite", "", False)
assert row.select.values == [ai_key.AUTO] + names and "Automatic: gemini-3.5-flash-lite" in row.winfo_children()[-1].cget("text")
hub.show_tab(20); pump()
sel = row.select
sel.event_generate("<ButtonRelease-1>", x=10, y=10); pump()
pop = sel.popup; i = sel.values.index("gemini-3.5-flash"); y = 6 + i * 34 + 17
pop.event_generate("<Motion>", x=40, y=y); pop.event_generate("<ButtonRelease-1>", x=40, y=y); pump()
cfg = json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))
assert cfg["ai_model"] == "gemini-3.5-flash" and sent[-1] == {"op": "model", "name": "gemini-3.5-flash"}, (cfg.get("ai_model"), sent)
# a saved model the key doesn't offer falls back to automatic, and says so
hub.settings["ai_model"] = "gemini-3.8-flash"
row.set_models(names, "gemini-3.5-flash-lite", "gemini-3.8-flash", False)
assert row.select.get() == ai_key.AUTO and "isn't available" in row.winfo_children()[-1].cget("text")
row.choose(ai_key.AUTO); assert hub.settings["ai_model"] == "" and sent[-1] == {"op": "model", "name": ""}
print("PASS: AI model picker — lists the key's models, saves ai_model on click and tells the helper, "
      "falls back to automatic when a saved model isn't offered.")
hub.destroy()
