"""AI assistant "Use my own key" card (rt_pages/ai_key.py): saves the key encrypted where the AI helper reads it
(%LOCALAPPDATA%\\GeminiChat\\key-v2.dat), rejects junk, never shows the key, removes it, restarts the AI."""
import os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_aikey_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import retweaks as app, hubplus
from rt_pages import ai_key
ai_key._protect = lambda b: b"ENC" + b[::-1]           # stand-in for Windows DPAPI on Linux
ai_key._unprotect = lambda b: b[3:][::-1]
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.geometry("1500x940+0+0"); hub.deiconify()
pump = lambda n=15: [hub.update() or time.sleep(0.01) for _ in range(n)]
pump(30)
restarts = []
hub.retry_ai = lambda: restarts.append(1)
card = hub.ai_key_card
assert "built into this version" in card.winfo_children()[1].cget("text")
KEY = "test-only_not-a-real-key_1234567890"
ok, msg = ai_key.save("not a key!")
assert not ok and not ai_key.key_path().exists()
ok, msg = ai_key.save(KEY)
assert ok and KEY not in msg and ai_key.key_path().read_bytes() != KEY.encode()
assert ai_key.key_path() == __import__("pathlib").Path(TMP) / "GeminiChat" / "key-v2.dat"
assert ai_key.has_own_key()
ok, msg = ai_key.remove(); assert ok and not ai_key.has_own_key()
# through the page: type, press Save -> saved, field cleared, AI restarted
row = card.winfo_children()[0]
entry = next(w for w in row.winfo_children() if isinstance(w, app.REntry))
assert entry.entry.cget("show") == "•"
hub.show_tab(20); pump()
entry.entry.insert(0, KEY)
save_btn = [w for w in row.winfo_children() if isinstance(w, app.RButton)][0]
save_btn.event_generate("<Enter>"); save_btn.event_generate("<ButtonPress-1>", x=5, y=5)
save_btn.event_generate("<ButtonRelease-1>", x=5, y=5); pump()
assert ai_key.has_own_key() and entry.entry.get() == "" and restarts == [1]
assert "Using your own key" in card.winfo_children()[1].cget("text")
assert ai_key.is_key_error("Google HTTP 401: API key not valid. Please pass a valid API key.")
print("PASS: AI own-key card — saves encrypted where the helper reads it, rejects junk, hides the key, "
      "removes it, restarts the AI on save; key errors are recognised.")

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
