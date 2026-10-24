"""Global search (top bar) + sidebar filter: pages by name/keyword, settings words, tweaks by name (the base app
and exact-undo), Enter/arrows/click open, search carries into the page's own box, Ctrl+K, Esc. Also the
separate About/Settings section."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tempfile
os.environ["APPDATA"] = tempfile.mkdtemp(); os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.deiconify(); hub.update()
side, gs = hub.sidebar_nav, hub.global_search
# --- the box is in the top bar, shows a hint, and the hint isn't a query
assert gs.box is not None and gs.box.master is hub.chrome and gs.box.winfo_ismapped()
assert gs.text() == "" and "Ctrl+K" in gs.entry.get()
# --- About / Settings: own section under a divider with a heading
assert side.bottom_head.cget("text") == "APP" and side.bottom_line.winfo_ismapped()
assert side.buttons["Settings"].master is side.bottom_head.master is not side.holder
# --- Ctrl+K focuses and clears the hint
gs.focus(); hub.update()
assert hub.focus_get() is gs.entry and gs.entry.get() == ""
titles = lambda: [r[0] for r in gs.results]
gs.query.set("dns"); hub.update()
assert "Network" in titles() and gs.popup is not None and gs.popup.winfo_exists()
assert any(d.startswith("Tweak") for _, d, _ in gs.results)         # DNS tweaks too
gs.query.set("discord"); hub.update()
assert titles()[0] == "Settings", titles()
gs.open_selected(); hub.update()
assert hub.cur_tab == hub.rt_tabs["Settings"] and gs.popup is None and gs.text() == ""
# --- tweak result opens its page and fills that page's own search
ctt = next(x for x in app.TWEAKS if str(x["cat"]).startswith("CTT"))
gs.focus(); gs.query.set(ctt["name"].lower()); hub.update()
k = next(i for i, r in enumerate(gs.results) if r[0] == ctt["name"])
gs.sel = 0
for _ in range(k): gs.move(1)
assert gs.sel == k
gs.open_selected(); hub.update()
assert hub.cur_tab == side.targets["CTT library"] and hub.ctt_search.get() == ctt["name"].lower()
# --- exact-undo tweak results
page = hub.rt_pages["Exact-undo tweaks"]
nm = page.rows[0].tweak.name
gs.focus(); gs.query.set(nm.lower()); hub.update()
i = next(i for i, r in enumerate(gs.results) if r[0] == nm and "Exact undo" in r[1])
gs.open(i); hub.update()
# exact-undo tweaks are the "Exact undo" tab of Individual tweaks now
assert hub.cur_tab == side.targets["Individual tweaks"] and hub.tweaks_tab_current == "exact"
assert page.query.get() == nm.lower()
# --- real mouse click on a result (owner report: "clicking a result fails"): the list is inside the main
# window, focus stays put, and pressing on the row opens the page
gs.focus(); gs.query.set("network"); hub.update()
assert gs.popup is not None and gs.popup.master is hub          # not a separate window
row, title, _ = gs.rows[0]
assert title.cget("text") == "Network"
title.event_generate("<Enter>"); hub.update()
title.event_generate("<ButtonPress-1>", x=5, y=5); hub.update()
assert hub.cur_tab == side.targets["Network"] and gs.popup is None, hub.cur_tab
# hovering only recolours rows (rows survive, so a click can't land on a destroyed widget)
gs.focus(); gs.query.set("dns"); hub.update()
first = gs.rows[1][1]
first.event_generate("<Enter>"); hub.update()
assert gs.sel == 1 and first.winfo_exists()
gs.clear(); hub.update()
# --- nothing / Esc
gs.focus(); gs.query.set("zzzz-nothing"); hub.update()
assert gs.results == [] and gs.popup is not None
gs.clear(); hub.update()
assert gs.popup is None and gs.query.get() == ""
# A manual result opens a filtered list, and filtering never changes selection values.
manual=next(t for t in app.TWEAKS if not str(t['cat']).startswith('CTT') and not any(c in str(t['cat']).lower() for c in ('custom','appearance','privacy','security')))
gs.focus();gs.query.set(manual['name'].lower());hub.update()
i=next(i for i,r in enumerate(gs.results) if r[0]==manual['name'] and r[1]=='Tweak · Individual tweaks')
gs.open(i);hub.update()
assert hub.tweaks_tab_current=='all' and hub.tweak_search.get()==manual['name']
assert manual['id'] in hub.tweak_visible_ids and len(hub.tweak_visible_ids)<len(app.TWEAKS)
hub.vars[manual['id']].set(True)
hub.tweak_search.set('zzzz-no-matching-tweak');hub.update()
assert hub.tweak_visible_ids==[] and hub.vars[manual['id']].get()
assert abs(hub.tweak_scroll.canvasy(0))<=1
hub.tweak_search.set('');hub.update()
assert len(hub.tweak_visible_ids)==len(app.TWEAKS) and hub.vars[manual['id']].get()
hub.vars[manual['id']].set(False)
# Native pages need a separate transient popup above the embedded helper windows.
for index in [19,20,25,28,29,hub.rt_tabs['Browser']]:
    hub.show_tab(index);gs.focus();gs.query.set('network');hub.update()
    assert gs.popup_host is not None and gs.popup_host.winfo_exists()
    assert hub.focus_get() is gs.entry
    title=gs.rows[0][1];assert title.cget('text')=='Network'
    title.event_generate('<ButtonPress-1>',x=3,y=3);hub.update()
    assert hub.cur_tab==side.targets['Network'] and gs.popup is None and gs.popup_host is None
# Navigation closes results and clears stale query text.
gs.focus();gs.query.set('dns');hub.update()
hub.show_tab(hub.rt_tabs['Settings']);hub.update()
assert gs.popup is None and gs.text()==''
# Sidebar icon resolves even if the explicitly named asset is unavailable.
assert side.icon('Windows backgrounds', app.FG) is not None

# --- sidebar filter still works (internal)
side.query.set("fortnite"); hub.update()
shown = {n for n, b in side.buttons.items() if b.winfo_manager() and b.master is side.holder}
assert "Gaming tools" in shown and "Dashboard" not in shown
side.query.set(""); hub.update()
# --- theme change keeps the box and recolours the section
hub.apply_theme("Ocean"); hub.update()
assert gs.box.winfo_ismapped()
print("PASS: global search (top bar, Ctrl+K, pages, settings words, tweaks, exact-undo, arrows/Enter, carry-over, "
      "Esc) and the separate About/Settings section.")
hub.destroy()
