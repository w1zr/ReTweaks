"""Dashboard banner on first launch (owner report 2026-10-24): the Dashboard is shown while the main window is still
hidden behind the startup screen. The banner must start animating by itself once the window appears (no tab switch),
stop while minimized, and resume after restore."""
import os, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_banner_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.settings["banner_style"] = "wave"
pump = lambda s=0.3: [hub.update() or time.sleep(0.01) for _ in range(int(s / 0.01))]
hub.withdraw(); pump(0.2)
page = hub.rt_pages["Dashboard"]
banner = page.banner
banner.set_style("wave")
hub.show_tab(hub.rt_tabs["Dashboard"]); page.on_shown(); pump(0.3)
assert banner.visible and banner.job is None, "should wait while the window is hidden"
hub.geometry("1400x900+0+0"); hub.deiconify(); pump(1.2)
assert banner.job is not None, "banner didn't start after the window appeared"
p1 = banner.phase; pump(0.5); assert banner.phase > p1, "banner isn't advancing"
hub.withdraw(); pump(1.0); assert banner.job is None, "should pause while the window is hidden or minimized"
hub.deiconify(); pump(1.2); assert banner.job is not None, "should resume after restore"
page.on_hidden(); pump(1.0); assert banner.job is None and banner._watch_job is None, "should stop fully when hidden"
print("PASS: dashboard banner starts on its own once the window appears (first launch), pauses minimized, resumes.")
hub.destroy()
