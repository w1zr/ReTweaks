"""Exact-undo tweaks live inside Individual tweaks as a second tab (owner request 2026-10-22).
- "All tweaks" / "Exact undo" switch at the top swaps two frames, each with its own scroll area
- the last tab is remembered (setting tweaks_tab) across a restart
- no "Exact-undo tweaks" sidebar entry; every old route (old tab index, startup_page, sidebar search, global search)
  lands on Individual tweaks -> Exact undo, a matching search fills that tab's search box
- exact-undo actions still exist (search, Apply, Undo everything, restore point)"""
import os, sys, json, tempfile, time, subprocess
RESTART = "--restart" in sys.argv
TMP = os.environ.get("RT_TABS_TMP") if RESTART else tempfile.mkdtemp(prefix="rt_tabs_")
os.environ["APPDATA"] = TMP; os.environ["LOCALAPPDATA"] = TMP
import retweaks as app, hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))


def make():
    h = app.Hub(show_intro=False, enable_ai=False)
    h.geometry("1400x900"); h.update()
    return h


pump = lambda h, n=10: [h.update() or time.sleep(0.01) for _ in range(n)]
if RESTART:
    hub = make()
    assert hub.tweaks_tab_current == "exact"
    assert hub.cur_tab == 1, hub.cur_tab                   # opened on Individual tweaks (Exact undo)
    cfg = json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))
    assert cfg["startup_page"] == "Individual tweaks" and cfg["tweaks_tab"] == "exact"
    print("RESTART-OK")
    sys.exit(0)
hub = make()
side = hub.sidebar_nav
assert "Exact-undo tweaks" not in side.targets and "Individual tweaks" in side.targets
exact = hub.rt_pages["Exact-undo tweaks"]
assert exact is not None and exact.body.winfo_toplevel() is hub
# the page is built inside Individual tweaks' holder frame
w = exact.body
while w is not None and w is not hub.tweaks_exact_holder:
    w = w.master
assert w is hub.tweaks_exact_holder
# default tab: All tweaks
hub.show_tab(1); pump(hub)
assert hub.tweaks_tab_current == "all" and hub.tweaks_all.winfo_ismapped() and not hub.tweaks_exact_holder.winfo_ismapped()
# switch by clicking the button
b = hub.tweaks_tab_buttons["exact"]
b.event_generate("<ButtonPress-1>", x=20, y=15); b.event_generate("<ButtonRelease-1>", x=20, y=15); pump(hub)
assert hub.tweaks_tab_current == "exact" and hub.tweaks_exact_holder.winfo_ismapped() and not hub.tweaks_all.winfo_ismapped()
assert hub.settings.get("tweaks_tab") == "exact"
cfg = json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))
assert cfg.get("tweaks_tab") == "exact"
# each tab has its own scroll canvas (no nesting)
def scrollers(frame):
    out, st = [], [frame]
    while st:
        x = st.pop()
        if hasattr(x, "wheel_scroll") or getattr(x, "wheel_target", None) is x:
            out.append(x)
        st.extend(x.winfo_children())
    return out
assert scrollers(hub.tweaks_all) and scrollers(hub.tweaks_exact_holder)
# exact-undo controls still there
assert exact.b_undo_all.winfo_exists() and exact.b_restore.winfo_exists() and exact.rows
# old routes: old tab index -> Individual tweaks / Exact undo
hub.show_tweaks_tab("all"); hub.show_tab(hub.rt_tabs["Dashboard"]); pump(hub)
hub.show_tab(hub.rt_tabs["Exact-undo tweaks"]); pump(hub)
assert hub.cur_tab == 1 and hub.tweaks_tab_current == "exact"
# sidebar search: words of an exact-undo tweak find Individual tweaks and fill the Exact undo search box
nm = exact.rows[0].tweak.name
hub.show_tweaks_tab("all"); hub.show_tab(hub.rt_tabs["Dashboard"]); pump(hub)
side.query.set(nm.lower()); pump(hub)
shown = {n for n, bt in side.buttons.items() if bt.winfo_manager() and bt.master is side.holder}
assert "Individual tweaks" in shown, shown
side.open_first(); pump(hub)
assert hub.cur_tab == 1 and hub.tweaks_tab_current == "exact" and exact.query.get() == nm.lower()
side.query.set(""); exact.query.set(""); pump(hub)
# a base-list tweak result opens the All tweaks tab
gs = hub.global_search
t = app.TWEAKS[0]
res = gs.search(t["name"].lower())
r = next(r for r in res if r[0] == t["name"])
hub.show_tweaks_tab("exact"); r[2](); pump(hub)
assert hub.cur_tab == 1 and hub.tweaks_tab_current == "all"
# remembered tab survives a restart; old startup_page value is mapped once
hub.show_tweaks_tab("exact"); hub.settings["startup_page"] = "Exact-undo tweaks"; hub.save_settings()
hub.destroy()
r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "tools", "linux_shim.py"), os.path.abspath(__file__), "--restart"],
                   capture_output=True, text=True, timeout=180, env=dict(os.environ, RT_TABS_TMP=TMP))
assert "RESTART-OK" in r.stdout, r.stdout[-600:] + r.stderr[-1500:]
print("PASS: Individual tweaks tabs — switch, own scroll areas, remembered tab, no sidebar entry, old tab index, "
      "sidebar + global search routing with search filled, startup_page mapping.")
