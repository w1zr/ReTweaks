"""Banner colour (v2.0.6): Settings -> Banner colour changes the Dashboard galaxy colours right away and persists.
Saves screenshots of Original, Black & white (Super Black theme) and a custom colour when RT_SHOTS is set."""
import json, os, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_bcol_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
pump = lambda s=0.3: [hub.update() or time.sleep(0.01) for _ in range(int(s / 0.01))]
hub.geometry("1400x900+0+0"); pump(0.5)
dash = hub.rt_pages["Dashboard"]; page = hub.rt_pages["Settings"]
cfg = lambda: json.loads(open(os.path.join(TMP, "RETWEAKS", "config.json"), encoding="utf-8").read())
page.set_banner("Galaxy")
hub.show_tab(hub.rt_tabs["Dashboard"]); dash.on_shown(); pump(1.0)
shots = os.environ.get("RT_SHOTS")


def shot(name):
    if not shots:
        return
    from PIL import ImageGrab
    pump(0.6)
    c = dash.banner.canvas
    x, y = c.winfo_rootx(), c.winfo_rooty()
    ImageGrab.grab((x, y, x + c.winfo_width(), y + c.winfo_height())).save(os.path.join(shots, name))


assert dash.banner.palette()["mode"] == "original" and dash.banner.palette()["space"] == "#0c0a1d"
shot("banner_original.png")
page.set_banner_color("Black & white")
assert cfg()["banner_color"] == "mono" and dash.banner.palette()["nebula"] == ("#9a9a9a", "#d6d6d6")
assert dash.banner._gal_key[-1] == ("#9a9a9a", "#d6d6d6"), "galaxy glow wasn't re-rendered"
shot("banner_mono.png")
page.banner_hex.set("zz"); page.apply_banner_hex()
assert "6 hex digits" in page.banner_hex_msg.cget("text") and cfg()["banner_color"] == "mono"
page.banner_hex.set("10b981"); page.apply_banner_hex()
assert cfg()["banner_color"] == "custom" and cfg()["banner_custom_color"] == "#10b981"
assert page.banner_color.get() == "Custom (HEX)" and dash.banner.palette()["accent"] == "#10b981"
shot("banner_custom.png")
page.set_banner("CPU cores (live)"); pump(0.5)
assert dash.banner.col("accent") == "#10b981"
print("PASS: banner colour (Original / Black & white / custom HEX) applies live and persists.")
hub.destroy()
