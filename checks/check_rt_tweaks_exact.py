"""Check: Exact-undo tweaks page lists only RETWEAKS tweaks the base app lacks, and apply/undo use core.tweaks.
Run on Linux: xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_tweaks_exact.py"""
import os
import tempfile
import tkinter as tk
from unittest import mock

tmp = tempfile.mkdtemp(prefix="rt_tweaks_")
os.environ["APPDATA"] = tmp
import retweaks as app                                     # noqa: E402
import retweaks_data as P                                  # noqa: E402
from core import tweaks as T                               # noqa: E402
from rt_pages import tweaks_exact as te                    # noqa: E402

# 1) every listed tweak exists, and none is one of the tweaks the base app has individually
covered = {"game_mode", "xbox_capture", "mouse_accel", "transparency", "sticky_keys_popup", "hags", "fast_startup",
           "hibernation", "background_apps", "animations", "ad_id", "diag_data", "activity_history",
           "web_search_start", "start_suggestions", "tips", "silent_apps", "file_ext", "hidden_files",
           "classic_menu", "taskbar_left", "task_view_btn", "widgets", "dark_mode", "end_task", "svc_diagtrack",
           "svc_sysmain", "svc_wsearch", "storage_sense", "delivery_p2p", "power_throttling", "mmcss_reserve"}
assert all(i in T.BY_ID for i in te.ONLY_HERE)
assert not covered & set(te.ONLY_HERE)
assert set(te.ONLY_HERE) | covered == set(T.BY_ID), set(T.BY_ID) - set(te.ONLY_HERE) - covered
# the tweaks that aren't in the base app at all really have no matching registry value there
blob = "\n".join(str(x) for t in P.TWEAKS for x in (t.get("apply") or []) + (t.get("undo") or [])).lower()
for tid in ("windowed_games", "update_restart", "wu_drivers", "narrator_shortcut", "game_bar_button", "clock_seconds"):
    assert all(name.lower() not in blob for _path, name in T.BY_ID[tid].keys()), tid

# 2) page builds; selection + apply go through core.profiles.apply_selection
g = vars(app)
root = tk.Tk()
root.settings, logs = {}, []
root.save_settings = lambda: True
root.log_action = lambda *a: logs.append(a)
root._scroll_area = lambda parent: (lambda f: (f.pack(fill="both", expand=True), f)[1])(tk.Frame(parent, bg=g["BG"]))
tab = tk.Frame(root)
tab.pack(fill="both", expand=True)
calls = []
states = {cls: mock.patch.object(cls, "get_state", lambda self: "Off")
          for cls in {type(T.BY_ID[i]) for i in te.ONLY_HERE}}
for p_ in states.values():
    p_.start()
if True:
    page = te.ExactTweaksPage(root, tab, g)
    import time
    for _ in range(100):
        root.update()
        if all(r.status.cget("text") != "Checking…" for r in page.rows):
            break
        time.sleep(0.02)
    assert len(page.rows) == len(te.ONLY_HERE)
    assert all(r.status.cget("text") == "Off" for r in page.rows), [r.status.cget("text") for r in page.rows]
    page.query.set("narrator")
    root.update()
    shown = [r for r in page.rows if r.winfo_manager()]
    assert [r.tweak.id for r in shown] == ["narrator_shortcut"], [r.tweak.id for r in shown]
    page.select_shown()
    page.query.set("")
    page.rows[[r.tweak.id for r in page.rows].index("narrator_shortcut")].target.set("Turn off")
    with mock.patch("core.profiles.apply_selection", lambda sel: calls.append(sel) or [("x", True, "ok")]), \
            mock.patch("core.profiles.selection_preview",
                       lambda sel: [("Narrator", "On", "Off", True) for _ in sel]), \
            mock.patch("tkinter.messagebox.askyesno", return_value=True):
        page.apply_selected()
        for _ in range(100):
            root.update()
            if calls:
                break
            root.after(20)
assert calls == [[("narrator_shortcut", False)]], calls
root.destroy()
print(f"PASS: {len(te.ONLY_HERE)} exact-undo tweaks, none duplicated from the base app; search, selection and Apply work.")
