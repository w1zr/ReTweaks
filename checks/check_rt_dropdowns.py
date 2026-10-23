"""Dropdowns (owner report 2026-10-22: Theme, Dashboard banner, Sidebar header, Refresh and Open on did nothing
when clicked). Real mouse events on each Settings dropdown: click opens a list INSIDE the main window (no
separate window that can lose focus), losing focus doesn't close it, clicking an item applies + saves the
setting, Esc / click outside / page switch / scrolling close it, only one list open at a time."""
import json, os, sys, tempfile, time
TMP = tempfile.mkdtemp(prefix="rt_dd_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.geometry("1500x940+0+0"); hub.deiconify()
pump = lambda n=15: [hub.update() or time.sleep(0.01) for _ in range(n)]
pump(30)
hub.settings["welcome_done_version"] = "2.0"
hub.show_tab(hub.rt_tabs["Settings"]); pump()
page = hub.rt_pages["Settings"]
cfg = lambda: json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))
RSelect = app.RSelect


def pick(sel, label):
    """Click the dropdown, then click the item called `label`, like a mouse would."""
    canvas = page_scroll_to(sel)
    sel.event_generate("<Enter>"); sel.event_generate("<ButtonPress-1>", x=10, y=10)
    sel.event_generate("<ButtonRelease-1>", x=10, y=10); pump()
    pop = sel.popup
    assert pop is not None and pop.winfo_ismapped(), "list didn't open"
    assert pop.winfo_toplevel() is hub, "list must be inside the main window, not a separate window"
    assert len(pop.find_all()) > len(sel.values), "list items weren't drawn"
    assert hub.focus_get() is pop, "list should take keyboard focus"
    over = hub.winfo_containing(pop.winfo_rootx() + 30, pop.winfo_rooty() + 20)
    assert over is pop, ("list is hidden behind", over)
    # Windows moving focus away right after opening must NOT close it
    hub.focus_set(); pump()
    assert sel.popup is pop, "list closed itself when focus moved"
    i = sel.values.index(label)
    y = 6 + i * 34 + 17 - pop.canvasy(0)
    if not (0 < y < int(pop.cget("height"))):
        pop.yview_moveto(max(0, (6 + i * 34) / (len(sel.values) * 34 + 12))); pump(); y = 6 + i * 34 + 17 - pop.canvasy(0)
    pop.event_generate("<Motion>", x=40, y=int(y))
    pop.event_generate("<ButtonPress-1>", x=40, y=int(y))
    pop.event_generate("<ButtonRelease-1>", x=40, y=int(y)); pump()
    assert sel.popup is None and sel.get() == label, (sel.get(), label)


def page_scroll_to(w):
    """Scroll the page so `w` is in view, like the user would before clicking it."""
    hub.update_idletasks()
    cv = w.master
    while cv is not None and not hasattr(cv, "wheel_scroll"):     # the page's scroll area
        cv = cv.master
    if cv is None:
        return None
    wins = [i for i in cv.find_all() if cv.type(i) == "window"]
    inner = cv.nametowidget(cv.itemcget(wins[0], "window")) if wins else None
    if inner is None:
        return cv
    off = w.winfo_rooty() - inner.winfo_rooty()
    cv.yview_moveto(max(0.0, (off - 200) / max(1, inner.winfo_height())))
    pump()
    return cv


# Theme
pick(page.theme, "Ocean"); pump(); assert hub.theme_name == "Ocean", hub.theme_name
import glob
saved = [f for f in glob.glob(os.path.join(TMP, "**", "appearance.json"), recursive=True)]
assert saved and json.load(open(saved[0]))["theme"] == "Ocean", ("theme not saved", saved)
page = hub.rt_pages["Settings"]
# Sidebar header
other = next(v for v in page.header.values if v != page.header.get())
pick(page.header, other); assert cfg()["header_style"] in ("chip", "wordmark")
# Dashboard banner
target = next(v for v in page.banner.values if "wave" in v.lower())
pick(page.banner, target); assert cfg()["banner_style"] == "wave"
# Refresh
pick(page.interval, "Every 5 seconds"); assert cfg()["interval"] == 5.0
# Open on (list is filled when Settings is shown)
page.on_shown(); pump()
assert "Network" in page.start_page.values
pick(page.start_page, "Network"); assert cfg()["startup_page"] == "Network"
# Esc closes, click elsewhere closes, page switch closes, only one open at a time
page.theme.event_generate("<ButtonRelease-1>", x=10, y=10); pump(); assert page.theme.popup is not None
page.theme.popup.event_generate("<Escape>"); pump(); assert page.theme.popup is None
page.theme.event_generate("<ButtonRelease-1>", x=10, y=10); pump()
page.banner.event_generate("<ButtonRelease-1>", x=10, y=10); pump()
assert page.theme.popup is None and page.banner.popup is not None and RSelect._open_one is page.banner
hub.event_generate("<ButtonPress-1>", x=5, y=5); pump()
assert page.banner.popup is None, "click outside should close"
page.banner.event_generate("<ButtonRelease-1>", x=10, y=10); pump()
hub.show_tab(hub.rt_tabs["Dashboard"]); pump()
assert page.banner.popup is None, "switching pages should close"
print("PASS: dropdowns — Theme, Sidebar header, Dashboard banner, Refresh, Open on open inside the window, survive a "
      "focus change, apply + save on click; Esc / outside click / page switch close; one at a time.")
hub.destroy()
