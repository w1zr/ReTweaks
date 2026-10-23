"""Check: Game config files page (rt_pages/game_files.py) with a real temporary settings file.
Run on Linux: xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_game_files.py"""
import os
import tempfile
import tkinter as tk
from unittest import mock

tmp = tempfile.mkdtemp(prefix="rt_gamefiles_")
os.environ["APPDATA"] = os.path.join(tmp, "appdata")
os.environ["LOCALAPPDATA"] = os.path.join(tmp, "local")
import retweaks as app                                     # noqa: E402
from core import game_presets as gp                        # noqa: E402
from rt_pages import game_files as gf                      # noqa: E402

g = vars(app)
root = tk.Tk()
root.settings, logs = {}, []
root.save_settings = lambda: True
root.log_action = lambda *a: logs.append(a)
root._scroll_area = lambda parent: tk.Frame(parent, bg=g["BG"]) if False else _area(parent)


def _area(parent):
    f = tk.Frame(parent, bg=g["BG"])
    f.pack(fill="both", expand=True)
    return f


tab = tk.Frame(root, bg=g["BG"])
tab.pack(fill="both", expand=True)
page = gf.GameFilesPage(root, tab, g)
assert page.combo.get() == gp.GAMES[0].name

# add your own key=value file
cfg = os.path.join(tmp, "MyGame", "settings.ini")
os.makedirs(os.path.dirname(cfg))
with open(cfg, "w") as f:
    f.write("[Video]\nFullscreen=1\nFrameRateLimit=60\n")
with mock.patch.object(gf.filedialog, "askopenfilename", return_value=cfg), \
        mock.patch.object(gf.simpledialog, "askstring", return_value="My Game"):
    page.add_own_file()
assert page.combo.get() == "My Game (your file)", page.combo.get()
assert page.path == cfg and page.original.get("FrameRateLimit") == "60", page.original

# edit a value in the Custom table, apply it (confirm), wait for the worker
item = [i for i in page.table.get_children() if page.table.item(i, "values")[0] == "FrameRateLimit"][0]
page.table.selection_set(item)
with mock.patch.object(gf.simpledialog, "askstring", return_value="144"):
    page._edit_cell()
assert page.edited == {"FrameRateLimit": "144"}
with mock.patch.object(gf.messagebox, "askyesno", return_value=True):
    page.apply_custom()
for _ in range(200):
    root.update()
    if "FrameRateLimit=144" in open(cfg).read():
        break
    root.after(20)
assert "FrameRateLimit=144" in open(cfg).read(), open(cfg).read()
for _ in range(100):
    root.update()
    if page._backup_list:
        break
    root.after(20)
assert page._backup_list, "a backup is made before the change"

# save the edit as a preset of yours, then restore the backup
page.edited = {"FrameRateLimit": "240"}
with mock.patch.object(gf.simpledialog, "askstring", return_value="Comp"):
    page.save_user_preset()
assert "Comp" in gp.user_presets(page.entry_id)
with mock.patch.object(gf.messagebox, "askyesno", return_value=True):
    page.restore()
assert "FrameRateLimit=60" in open(cfg).read(), open(cfg).read()
root.destroy()
print("PASS: own file added, Custom edit applied with backup, preset saved, backup restored. Log:", len(logs), "entries")
