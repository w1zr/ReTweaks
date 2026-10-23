"""Crosshair: model validation/clamping, drawing, share codes (round trip + bad codes rejected), .rtxhair files,
built-in designs, saved list (damaged file kept), gallery (404 / offline / invalid / valid, cache), hotkey
edge detection, and the page: editor, use/save/rename/copy/delete, share, overlay show/hide/close, settings."""
import base64
import io
import json
import os
import sys
import tempfile
import urllib.error
import zlib

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = tempfile.mkdtemp()
os.environ["APPDATA"] = TMP
os.environ["LOCALAPPDATA"] = tempfile.mkdtemp()

from core import crosshair as xh
from PIL import Image

E = xh.CrosshairError


def raises(fn, *a):
    try:
        fn(*a)
    except E as e:
        return str(e)
    raise AssertionError(f"{fn.__name__}{a!r} should have failed")


# ---------------- validation
d = xh.validate({"style": "cross", "size": 999, "gap": -5, "opacity": 3, "rotation": 400.4, "thickness": 2.6,
                 "color": "#ABCDEF", "extra": "dropped", "name": "  a   b  "})
assert d["size"] == 60 and d["gap"] == 0 and d["opacity"] == 10 and d["rotation"] == 359 and d["thickness"] == 3
assert d["color"] == "#abcdef" and "extra" not in d and d["name"] == "a b"
raises(xh.validate, {"style": "laser"})
raises(xh.validate, {"color": "red"})
raises(xh.validate, {"size": "10"})
raises(xh.validate, {"size": True})
raises(xh.validate, {"size": float("nan")})
raises(xh.validate, {"outline": "yes"})
raises(xh.validate, {"style": "image"})                      # needs a PNG
raises(xh.validate, {"style": "image", "image": base64.b64encode(b"GIF89a....").decode()})
raises(xh.validate, "not a dict")
assert xh.validate({"name": "x" * 99})["name"] == "x" * xh.NAME_MAX

# ---------------- drawing: centred on the middle pixel, styles differ, opacity, rotation
for c in xh.BUILTIN:
    im = xh.render(c)
    assert im.width == im.height and im.width % 2 == 1 and im.getchannel("A").getbbox()
names = [c["name"] for c in xh.BUILTIN]
assert len(names) >= 10 and len(set(names)) == len(names)
assert len({xh.render(c).tobytes() for c in xh.BUILTIN}) == len(xh.BUILTIN)      # all distinct designs
cross = xh.new(style="cross", size=5, gap=2, thickness=1, outline=False)
l, t, r, b = xh.bounds(cross)
assert (l, t, r, b) == (-6, -6, 6, 6), (l, t, r, b)                                 # gap 2 + length 5 → ±6
im = xh.render(cross)
mid = im.width // 2
assert im.getpixel((mid, mid))[3] == 0 and im.getpixel((mid + 3, mid))[3] == 255    # gap empty, arm drawn
half = xh.render(xh.new(style="dot", dot_size=4, opacity=50, outline=False))
assert half.getchannel("A").getextrema()[1] == 127
# Pack 2 (21 designs from the owner's screenshot): each draws, is distinct, and survives a share code
assert len(xh.PACK2) == 21 and len(xh.ALL_BUILTIN) == len(xh.BUILTIN) + 21
p2names = [c["name"] for c in xh.ALL_BUILTIN]
assert len(set(p2names)) == len(p2names)
for c in xh.PACK2:
    assert xh.render(c).getchannel("A").getbbox(), c["name"]
    assert xh.from_code(xh.to_code(c)) == c, c["name"]
assert len({xh.render(c).tobytes() for c in xh.PACK2}) == 21
for style in ("wedge", "split_circle"):
    assert any(c["style"] == style for c in xh.PACK2)
# even-thickness plus is exactly symmetric about its centre point
l2, t2, r2, b2_ = xh.bounds(xh.new(style="cross", size=4, gap=0, thickness=2, outline=False))
assert -l2 - 1 == r2 and -t2 - 1 == b2_, (l2, t2, r2, b2_)
# the 4 wedge arms are identical (90-degree copies)
from PIL import Image as _Img
w_im = xh.render(dict(xh.PACK2[10], outline=True))
assert w_im.tobytes() == w_im.transpose(_Img.ROTATE_90).tobytes()
# new fields: dot colour and dot outline; old codes (made before these fields) still decode the same way
dc = xh.new(style="cross_dot", color="#ffffff", dot_color="#ff0000", dot_size=3, outline=False)
dim = xh.render(dc)
assert dim.getpixel((dim.width // 2, dim.width // 2))[:3] == (255, 0, 0)
raises(xh.validate, {"dot_color": "blue"})
raises(xh.validate, {"dot_outline": 1})
old_style = {"name": "Old", "style": "cross", "color": "#00ff66", "opacity": 100, "size": 8, "thickness": 2,
             "gap": 4, "outline": True, "outline_color": "#000000", "outline_thickness": 1, "center_dot": False,
             "dot_size": 2, "rotation": 0, "image": ""}
old_code = "RTX1-" + base64.urlsafe_b64encode(zlib.compress(json.dumps(old_style).encode())).decode().rstrip("=")
oc = xh.from_code(old_code)
assert oc["dot_color"] == "" and oc["dot_outline"] is True and oc["size"] == 8
tshape = xh.bounds(xh.new(style="t", size=5, gap=2, thickness=1, outline=False))
assert tshape[1] == 0                                                                 # no top arm
rot = xh.render_keyed(xh.new(style="cross", rotation=45))
assert rot.mode == "RGB" and xh.KEY in {c for _, c in rot.getcolors(1 << 20)}
# image crosshair
png = io.BytesIO()
Image.new("RGBA", (300, 200), (255, 0, 0, 255)).save(png, "PNG")
pp = os.path.join(TMP, "big.png")
open(pp, "wb").write(png.getvalue())
img_b64 = xh.image_from_png_file(pp)                                                  # shrunk to 128 max
imgc = xh.new(style="image", image=img_b64, name="Pic")
assert max(Image.open(io.BytesIO(base64.b64decode(imgc["image"]))).size) <= 128
assert xh.render(imgc).getchannel("A").getbbox()
raises(xh.image_from_png_file, os.path.join(TMP, "missing.png"))

# ---------------- share codes
for c in xh.BUILTIN + [imgc]:
    code = xh.to_code(c)
    assert code.startswith("RTX1-") and xh.from_code(code) == c
assert xh.from_code("  " + xh.to_code(cross)[:20] + "\n" + xh.to_code(cross)[20:] + " ") == cross   # whitespace ok
raises(xh.from_code, "hello")
raises(xh.from_code, "RTX1-!!!!")
raises(xh.from_code, xh.to_code(cross)[:-6])                                           # truncated
raises(xh.from_code, None)
bad = "RTX1-" + base64.urlsafe_b64encode(zlib.compress(b'{"style":"laser"}')).decode().rstrip("=")
assert "Unknown crosshair style" in raises(xh.from_code, bad)
bomb = "RTX1-" + base64.urlsafe_b64encode(zlib.compress(b" " * 2_000_000)).decode().rstrip("=")
assert "too large" in raises(xh.from_code, bomb)

# ---------------- files
fp = os.path.join(TMP, "mine.rtxhair")
xh.export_file(xh.BUILTIN[2], fp)
assert xh.import_file(fp) == xh.BUILTIN[2]
open(fp, "w").write(xh.to_code(xh.BUILTIN[3]))                                       # a code saved as text
assert xh.import_file(fp) == xh.BUILTIN[3]
open(fp, "w").write('{"format": "something-else"}')
raises(xh.import_file, fp)
open(fp, "w").write('{"format": "retweaks-crosshair", "version": 2, "crosshair": {}}')
assert "newer" in raises(xh.import_file, fp)
open(fp, "w").write("not json")
raises(xh.import_file, fp)

# ---------------- saved list: survives restart, damaged data is kept, never wiped
st = xh.Store()
assert st.items == [] and st.note == ""
a = st.add(dict(xh.BUILTIN[0], name="Mine"))
b2 = st.add(dict(xh.BUILTIN[0], name="Mine"))
assert a["name"] == "Mine" and b2["name"] == "Mine (2)"
st.rename(1, "Second")
st.duplicate(1)
assert [x["name"] for x in xh.Store().items] == ["Mine", "Second", "Second copy"]
raises(st.rename, 0, "   ")
st.delete(2)
assert len(xh.Store().items) == 2
path = xh.store_path()
data = json.loads(path.read_text())
data["saved"].append({"style": "laser"})
path.write_text(json.dumps(data))
st2 = xh.Store()
assert len(st2.items) == 2 and "couldn't be read" in st2.note
assert any(p.name.startswith("crosshairs.json.bad-") for p in path.parent.iterdir())
path.write_text("{ broken")
st3 = xh.Store()
assert st3.items == [] and "damaged" in st3.note and path.read_text() == "{ broken"   # not overwritten on load

# ---------------- gallery
class Resp:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self, n=-1): return self.body


def http(code):
    def f(req, timeout):
        raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
    return f


def offline(req, timeout):
    raise urllib.error.URLError("no network")


r = xh.fetch_gallery(opener=http(404))
assert r["status"] == "not_available" and r["entries"] == [] and r["message"] == "Gallery isn't available yet."
r = xh.fetch_gallery(opener=offline)
assert r["status"] == "offline" and r["entries"] == []
r = xh.fetch_gallery(opener=lambda req, timeout: Resp(b"<html>nope</html>"))
assert r["status"] == "invalid" and r["entries"] == []
doc = xh.gallery_document(xh.BUILTIN[:3])
doc["crosshairs"].append({"name": "broken", "code": "RTX1-zzz"})
doc["crosshairs"].append("junk")
doc["crosshairs"].append({"name": "Friend", "author": "Sam", "code": xh.to_code(cross)})
r = xh.fetch_gallery(opener=lambda req, timeout: Resp(json.dumps(doc).encode()))
assert r["status"] == "ok" and len(r["entries"]) == 4 and r["skipped"] == 2
assert r["entries"][-1]["author"] == "Sam" and r["entries"][-1]["crosshair"]["style"] == "cross"
r = xh.fetch_gallery(opener=offline)                                                   # last good copy, labelled
assert r["status"] == "offline" and len(r["entries"]) == 4 and r["cached_at"] and "saved" in r["message"]
repo_doc = json.load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                       "crosshairs", "gallery.json")))
entries, skipped = xh.parse_gallery(repo_doc)
assert len(entries) == len(xh.ALL_BUILTIN) and skipped == 0

# ---------------- hotkey edge detection
hits = []
state = {"down": False}
hp = xh.HotkeyPoller("F9", lambda: hits.append(1), get_state=lambda vk: state["down"])
prev = hp.poll_once(False)
state["down"] = True
prev = hp.poll_once(prev)
prev = hp.poll_once(prev)                 # held: counts once
state["down"] = False
prev = hp.poll_once(prev)
state["down"] = True
hp.poll_once(prev)
assert len(hits) == 2
raises(xh.HotkeyPoller, "Q", lambda: None)

# ---------------- the page
import tkinter as tk
from unittest.mock import patch
import retweaks as app
import hubplus
app.Hub._load_info = lambda self: None
hubplus.install(vars(app))
hub = app.Hub(show_intro=False, enable_ai=False)
hub.update()
page = hub.rt_pages["Crosshair"]
assert page is not None, "Crosshair page failed to load"
assert hub.sidebar_nav.targets["Crosshair"] == hub.rt_tabs["Crosshair"]
assert not page.visible() and hub.settings.get("crosshair_enabled") in (None, False)   # never shown on its own
hub.show_tab(hub.rt_tabs["Crosshair"])
hub.update()

def cfg():
    return json.load(open(os.path.join(TMP, "RETWEAKS", "config.json")))

# editor
page.sliders["size"].set(20, user=True)
assert page.design["size"] == 20 and cfg()["crosshair_active"]["size"] == 20
page.hex_var.set("ff0000"); assert page.apply_hex() and page.design["color"] == "#ff0000"
page.hex_var.set("nope"); assert page.apply_hex() is False and page.design["color"] == "#ff0000"
page._style_picked("Circle + dot"); assert page.design["style"] == "circle_dot"
page.dot_var.set(True); page.change("center_dot", True)
page.name_var.set("Red ring"); page.save_current()
assert page.store.items[-1]["name"] == "Red ring" and xh.Store().items[-1]["style"] == "circle_dot"
# built-in → editor
page.use(xh.BUILTIN[8])
assert page.design == xh.BUILTIN[8] and page.style_sel.value == xh.STYLES["chevron"]
# my crosshairs: rename (needs a name), copy, delete with confirmation
n = len(page.store.items)
page.rename_var.set(""); page.rename(n - 1); assert "Type the new name" in page.mine_msg.cget("text")
page.rename_var.set("Renamed"); page.rename(n - 1); assert page.store.items[n - 1]["name"] == "Renamed"
page.duplicate(n - 1); assert len(page.store.items) == n + 1
with patch("rt_pages.crosshair.messagebox.askyesno", return_value=False):
    page.delete(n); assert len(page.store.items) == n + 1
with patch("rt_pages.crosshair.messagebox.askyesno", return_value=True):
    page.delete(n); assert len(page.store.items) == n
# share code: copy + paste back; bad code refused
page.use(xh.BUILTIN[5])
page.copy_code(); hub.update()
assert hub.clipboard_get() == xh.to_code(xh.BUILTIN[5])
page.paste_var.set("RTX1-garbage"); assert page.load_code() is False and "damaged" in page.share_msg.cget("text")
page.paste_var.set(xh.to_code(xh.BUILTIN[1])); assert page.load_code() and page.design == xh.BUILTIN[1]
# files through the dialogs
fp2 = os.path.join(TMP, "exp.rtxhair")
with patch("rt_pages.crosshair.filedialog.asksaveasfilename", return_value=fp2):
    page.export_file()
assert xh.import_file(fp2) == xh.BUILTIN[1]
page.use(xh.BUILTIN[0])
with patch("rt_pages.crosshair.filedialog.askopenfilename", return_value=fp2):
    page.import_file()
assert page.design == xh.BUILTIN[1]
# gallery tab: 404 → plain message, no entries
with patch.object(xh, "fetch_gallery", lambda *a, **k: {"status": "not_available", "entries": [], "skipped": 0,
                                                         "cached_at": None, "message": "Gallery isn't available yet."}):
    page.tab_var.set("Gallery"); page._switch()
    for _ in range(40):
        hub.update(); hub.after(20)
        if page.gallery is not None:
            break
assert page.gallery["status"] == "not_available" and page.gal_msg.cget("text") == "Gallery isn't available yet."
assert not page.gal_box.winfo_children()
# overlay: show / move / monitor / hotkey toggle / hide
page.show(); hub.update()
assert page.visible() and page.overlay.win.winfo_viewable() and page.overlay.win.attributes("-topmost")
w, h, x, y = page.overlay.geometry
rect = page.monitor_list[page.monitor][1]
assert x + w // 2 == rect[0] + rect[2] // 2 and y + h // 2 == rect[1] + rect[3] // 2       # centred
page.nudge(1, 0); page.nudge(0, -1)
assert page.overlay.geometry[2] == x + 1 and page.overlay.geometry[3] == y - 1 and cfg()["crosshair_offset"] == [1, -1]
page.nudge(None, None); assert cfg()["crosshair_offset"] == [0, 0]
page.sliders["size"].set(30, user=True); hub.update()
assert page.overlay.geometry[0] > w                                                   # live update while showing
page.set_hotkey("F10"); assert cfg()["crosshair_hotkey"] == "F10"
page.events.put("toggle")
for _ in range(20):
    hub.update(); hub.after(15)
assert not page.visible()                                                             # hotkey hid it
page.toggle(); hub.update(); assert page.visible()
page.start_var.set(True); page.set_start(); assert cfg()["crosshair_enabled"] is True
page.close()
assert page.overlay is None and page.closed
print("PASS: crosshair — validation/clamping, drawing (12 built-ins + 21 Pack 2, distinct, symmetric, wedge/bracket "
      "styles, dot colour/outline, old codes still decode), share codes (round trip, bad/"
      "truncated/zip-bomb rejected), .rtxhair files, saved list (damaged data kept), gallery (404/offline/invalid/"
      "valid/cache, repo gallery.json valid), hotkey edges, page editor/use/save/rename/copy/delete/share/files/"
      "gallery, overlay centred/move/live update/hotkey/close, settings persisted.")
hub.destroy()
