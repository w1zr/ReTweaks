"""Checks the Tk ports of Program rules, Startup apps and Cleanup with fake Windows back ends.
Linux: xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_rules_startup_cleanup.py
Windows: py checks/check_rt_rules_startup_cleanup.py  (no real Windows settings are changed)."""
import os
import sys
import tempfile
import time
import tkinter as tk

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import retweaks as app                       # noqa: E402
from core import app_rules as R              # noqa: E402
from rt_pages import cleanup, rules, startup  # noqa: E402

g = vars(app)


class FakeHub(tk.Tk):
    _scroll_area = app.Hub._scroll_area

    def __init__(self):
        super().__init__()
        self.settings, self.saved, self.logs = {}, 0, []

    def save_settings(self):
        self.saved += 1
        return True

    def log_action(self, *a):
        self.logs.append(a)


def pump(hub, sec=0.5):
    end = time.time() + sec
    while time.time() < end:
        hub.update()
        time.sleep(0.02)


tmp = tempfile.mkdtemp()
os.environ["APPDATA"] = tmp
hub = FakeHub()
answers = []
for mod in (startup, cleanup, rules):
    mod.confirm = lambda *a: True
    mod.info = lambda *a, **k: answers.append(a)

# ---------------- Program rules
store = {"rules": [], "calm": {"enabled": False, "priority": "Below normal", "apps": []}}
R.load_rules = lambda: list(store["rules"])
R.save_rules = lambda rs: store.__setitem__("rules", list(rs))
R.load_calm_config = lambda: dict(store["calm"], apps=list(store["calm"]["apps"]))
R.save_calm_config = lambda c: store.__setitem__("calm", dict(c, apps=list(c["apps"])))
R.load_calm_records = lambda: []
gpu_state = {}
R.get_gpu = lambda r: gpu_state.get(r["exe"])
R.set_gpu = lambda r, v: (gpu_state.__setitem__(r["exe"], v), (True, f"{r['name']}: graphics set"))[1]
R.get_fso_off = lambda r: False
R.set_fso = lambda r, v: (True, "fso set")
R.remove_rule_settings = lambda r: (True, "restored")
tab = tk.Frame(hub)
tab.pack(fill="both", expand=True)
page = rules.RulesPage(hub, tab, g)
pump(hub)
page.add(r"C:\Games\Fortnite\FortniteClient-Win64-Shipping.exe")
assert len(page.cards) == 1 and store["rules"][0]["exe"].endswith("Shipping.exe")
page.add(r"C:\Games\Fortnite\FortniteClient-Win64-Shipping.exe")      # duplicate refused
assert len(page.cards) == 1 and "already" in page.msg.cget("text")
card = page.cards[0]
page.change(card, "gpu", "High performance GPU")
assert card.gpu.get() == "High performance GPU"                       # shows the real (re-read) value
page.change(card, "priority", "High")
assert store["rules"][0]["priority"] == "High"
page.change(card, "boost", True)
assert store["rules"][0]["boost"] is True
page.calm_on.set(True); page._calm_enabled()
assert hub.settings["calm_enabled"] is True and store["calm"]["enabled"] is True and hub.saved == 1
assert page.calm_add("discord") and store["calm"]["apps"] == ["discord"]
assert not page.calm_add("discord")                                   # no duplicates
assert not page.calm_add("csrss")                                     # protected name refused
page.on_auto_event("Fortnite started: Ultimate Performance on.")
assert "Fortnite started" in page.activity.get("1.0", "end")
page.remove(card, ask=False)
assert not page.cards and store["rules"] == []
tab.destroy()

# services: start, deliver an event, stop restores
events = []
class FakeMode:
    def __init__(self): self.n = 0
    def poll(self, rs):
        self.n += 1
        return ["started"] if self.n == 1 else []
    def restore(self): return ["Switched back to your previous power plan."]
R.AutoGameMode = FakeMode
rules.POLL_SECONDS = 0.05
svc = rules.start_services(hub, on_event=events.append)
pump(hub, 0.6)
rules.stop_services(hub)
pump(hub, 0.6)
assert events[0] == "started" and events[-1].startswith("Switched back"), events

# ---------------- Startup apps
entries = [
    {"id": "hkcu|Discord", "name": "Discord", "publisher": "Discord Inc.", "path": r"C:\d.exe", "source": "Registry (HKCU Run)",
     "status": "Enabled", "scope": "Current User"},
    {"id": "task|\\Steam", "name": "Steam updater", "publisher": "Valve", "path": r"C:\s.exe", "source": startup.SCHED_SOURCE,
     "status": "Disabled", "scope": "All Users", "triggers": ["At log on"]},
    {"id": "own", "name": "RETWEAKS", "publisher": "", "path": "", "source": startup.SCHED_SOURCE, "status": "Enabled",
     "scope": "Current User", "managed": True},
]
calls = {}
startup.list_startup_apps = lambda inc=False: (calls.__setitem__("inc", inc), [dict(e) for e in entries])[1]
startup.batch_disable = lambda chosen: [(e, True, "") for e in chosen]
startup.batch_enable = lambda ids: [(i, True, "") for i in ids]
tab = tk.Frame(hub)
tab.pack(fill="both", expand=True)
sp = startup.StartupPage(hub, tab, g)
sp.on_shown()
pump(hub, 0.6)
assert len(sp.table.get_children()) == 3 and calls["inc"] is False
sp.set_all(True)
assert sp.checked == {"hkcu|Discord", "task|\\Steam"}                  # managed task never selectable
sp.filter.set("Disabled"); sp.filter_table()
assert [sp.table.set(i, "name") for i in sp.table.get_children()] == ["Steam updater"]
sp.filter.set("All apps"); sp.search.set("disc")
assert [sp.table.set(i, "name") for i in sp.table.get_children()] == ["Discord"]
sp.search.set("")
sp.checked = {"hkcu|Discord"}
sp.disable_selected()
pump(hub, 0.6)
assert any(l[1] == "Disable Discord" for l in hub.logs)
sp.win_tasks.set(True); sp._win_tasks_toggled()
pump(hub, 0.6)
assert hub.settings["startup_show_windows_tasks"] is True and calls["inc"] is True
tab.destroy()

# ---------------- Cleanup
assert cleanup.cleanup_question(0, 0) is None
assert "12 item(s), about 2.0 MB" in cleanup.cleanup_question(12, 2 * 1024 ** 2)
rows = cleanup.drive_rows([{"device": "C:\\", "fstype": "NTFS", "total": "100 GB", "free": "40 GB", "percent": 60.0}],
                          {"disks": [{"name": "Samsung 990", "health": "Healthy", "letters": ["C:"]}]})
assert rows[0][1:3] == ("Samsung 990", "Healthy"), rows
assert cleanup.drive_rows([{"device": "D:\\", "fstype": "NTFS", "total": "1", "free": "1", "percent": 1.0}], None)[0][2] == "Unavailable"
root = tempfile.mkdtemp()
os.makedirs(os.path.join(root, "big", "inner"))
with open(os.path.join(root, "big", "inner", "file.bin"), "wb") as f:
    f.write(b"x" * 300000)
with open(os.path.join(root, "small.txt"), "w") as f:
    f.write("hello")
hub.rt_static = {"disks": []}
cleanup.get_disk_drives = lambda: [{"device": root, "mountpoint": root, "fstype": "ext4", "total": "1 GB",
                                    "free": "1 GB", "percent": 5.0}]
deleted = []
cleanup.preview_temp_files = lambda: (3, 5 * 1024 ** 2)
cleanup.cleanup_temp_files_safe = lambda: (deleted.append(1), "Freed 5.0 MB (3 items).")[1]
tab = tk.Frame(hub)
tab.pack(fill="both", expand=True)
cp = cleanup.CleanupPage(hub, tab, g)
cp.on_shown()
pump(hub, 0.4)
assert cp.scan_target.get() == root
cp.start_scan()
pump(hub, 1.5)
kids = [cp.tbl_children.set(i, "name") for i in cp.tbl_children.get_children()]
assert kids[0] == "big" and "small.txt" in kids, kids
assert cp.tbl_files.set(cp.tbl_files.get_children()[0], "path").endswith("file.bin")
assert "Scan finished" in cp.scan_status.cget("text")
cp.search_q.set("file"); cp.search_root.set(root); cp.start_search()
pump(hub, 1.0)
assert [cp.tbl_search.set(i, "path") for i in cp.tbl_search.get_children()] == [os.path.join("big", "inner", "file.bin")]
cp._confirm_cleanup((0, 0))
assert "already empty" in cp.clean_result.cget("text") and not deleted
cp._confirm_cleanup((3, 5 * 1024 ** 2), ask=lambda *a: False)              # user says no -> nothing deleted
assert not deleted
cp._confirm_cleanup((3, 5 * 1024 ** 2), ask=lambda *a: True)
pump(hub, 0.6)
assert deleted and "Freed" in cp.clean_result.cget("text")
cp.close()
hub.destroy()
print("PASS: Program rules (add/dup/gpu/priority/boost/remove, calming, activity, service start/stop+restore), "
      "Startup apps (filter/search/select/managed/disable/Windows tasks setting), Cleanup (drive health join, "
      "scan, search, cleanup only after preview + OK).")
