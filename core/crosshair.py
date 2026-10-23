# core/crosshair.py
"""Crosshair overlay data: designs, validation, drawing, share codes, files, saved list and gallery.

Owner request 2026-10-22: a custom crosshair like Crosshair X — make your own, use built-in ones and
get other people's (share codes, .rtxhair files and an online gallery).

Nothing here touches a game: the overlay (rt_pages/crosshair.py) is an ordinary click-through window
drawn above the desktop. This module is pure Python + Pillow, so it is tested on any OS.

Design fields (every one is validated; numbers are clamped to their range, wrong types are rejected):
  name, style, color, opacity, size, thickness, gap, outline, outline_color, outline_thickness,
  center_dot, dot_size, dot_color ("" = same as color), dot_outline, rotation,
  image (base64 PNG, only for style "image")
dot_color, dot_outline and the styles "split_circle" / "wedge" were added later (2026-10-22); codes made
before that simply lack them and get the defaults. (Also 2026-10-22: even-thickness arms are mirrored so a
plus is exactly symmetric, and chevrons are one clean shape — older designs can differ by a pixel.)
"""

import base64
import binascii
import io
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

STYLES = {
    "cross": "Cross",
    "cross_dot": "Cross + dot",
    "t": "T shape",
    "dot": "Dot",
    "circle": "Circle",
    "circle_dot": "Circle + dot",
    "circle_cross": "Circle + cross",
    "square": "Square",
    "chevron": "Chevron",
    "split_circle": "Bracket ring",
    "wedge": "Wedge cross",
    "image": "Image (PNG)",
}
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
# name: (min, max, default) for numbers; integers everywhere
RANGES = {
    "opacity": (10, 100, 100),
    "size": (1, 60, 8),
    "thickness": (1, 12, 2),
    "gap": (0, 30, 4),
    "outline_thickness": (1, 4, 1),
    "dot_size": (1, 12, 2),
    "rotation": (0, 359, 0),
}
DEFAULT = {
    "name": "My crosshair", "style": "cross", "color": "#00ff66", "opacity": 100, "size": 8, "thickness": 2,
    "gap": 4, "outline": True, "outline_color": "#000000", "outline_thickness": 1, "center_dot": False,
    "dot_size": 2, "dot_color": "", "dot_outline": True, "rotation": 0, "image": "",
}
NAME_MAX = 40
IMAGE_MAX_BYTES = 48 * 1024          # PNG bytes before base64
IMAGE_MAX_SIDE = 128
CODE_PREFIX = "RTX1-"
CODE_MAX_CHARS = 90000
FILE_FORMAT = "retweaks-crosshair"
GALLERY_FORMAT = "retweaks-crosshair-gallery"
GALLERY_URL = "https://raw.githubusercontent.com/w1zr/ReTweaks/main/crosshairs/gallery.json"
GALLERY_MAX = 500
KEY = (1, 2, 3)                       # overlay transparent colour key (#010203)


class CrosshairError(ValueError):
    """Bad crosshair data (message is shown to the user as is)."""


# ---------------------------------------------------------------- validation
def _num(d, key):
    lo, hi, default = RANGES[key]
    v = d.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise CrosshairError(f"'{key}' must be a number.")
    if v != v:                                            # NaN
        raise CrosshairError(f"'{key}' must be a number.")
    return int(max(lo, min(hi, round(v))))


def _color(d, key):
    v = d.get(key, DEFAULT[key])
    if not isinstance(v, str) or not HEX_RE.match(v.strip()):
        raise CrosshairError(f"'{key}' must be a colour like #00FF66.")
    return v.strip().lower()


def _bool(d, key):
    v = d.get(key, DEFAULT[key])
    if not isinstance(v, bool):
        raise CrosshairError(f"'{key}' must be true or false.")
    return v


def _image(v):
    """Checks a base64 PNG: real PNG, small enough. Returns the cleaned base64 text."""
    if not isinstance(v, str):
        raise CrosshairError("'image' must be a base64 PNG.")
    try:
        raw = base64.b64decode(v.strip(), validate=True)
    except (binascii.Error, ValueError):
        raise CrosshairError("The crosshair image isn't valid base64.")
    if len(raw) > IMAGE_MAX_BYTES:
        raise CrosshairError(f"The crosshair image is too big (max {IMAGE_MAX_BYTES // 1024} KB).")
    if not raw.startswith(b"\x89PNG\r\n\x1a\n"):
        raise CrosshairError("The crosshair image must be a PNG.")
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        raise CrosshairError("The crosshair image couldn't be read.")
    if max(im.size) > IMAGE_MAX_SIDE:
        raise CrosshairError(f"The crosshair image must be at most {IMAGE_MAX_SIDE} x {IMAGE_MAX_SIDE} pixels.")
    return base64.b64encode(raw).decode("ascii")


def validate(d):
    """Returns a clean copy of a crosshair dict, or raises CrosshairError. Unknown keys are dropped;
    missing keys get defaults; numbers are clamped to their ranges."""
    if not isinstance(d, dict):
        raise CrosshairError("A crosshair must be a set of named values.")
    out = {}
    name = d.get("name", DEFAULT["name"])
    if not isinstance(name, str):
        raise CrosshairError("'name' must be text.")
    name = " ".join(name.split())[:NAME_MAX] or DEFAULT["name"]
    out["name"] = name
    style = d.get("style", DEFAULT["style"])
    if style not in STYLES:
        raise CrosshairError(f"Unknown crosshair style: {style!r}.")
    out["style"] = style
    out["color"] = _color(d, "color")
    out["outline_color"] = _color(d, "outline_color")
    for k in RANGES:
        out[k] = _num(d, k)
    out["outline"] = _bool(d, "outline")
    out["center_dot"] = _bool(d, "center_dot")
    out["dot_outline"] = _bool(d, "dot_outline")
    dc = d.get("dot_color", "")
    out["dot_color"] = "" if dc == "" else _color(d, "dot_color")
    img = d.get("image", "")
    if style == "image":
        if not img:
            raise CrosshairError("An image crosshair needs a PNG image.")
        out["image"] = _image(img)
    else:
        out["image"] = ""
    return out


def new(**kw):
    d = dict(DEFAULT)
    d.update(kw)
    return validate(d)


def image_from_png_file(path):
    """Reads a PNG for an image crosshair; shrinks it to fit 128 x 128. Returns base64 text."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            im.load()
            im = im.convert("RGBA")
    except Exception:
        raise CrosshairError("That file couldn't be opened as an image.")
    if max(im.size) > IMAGE_MAX_SIDE:
        im.thumbnail((IMAGE_MAX_SIDE, IMAGE_MAX_SIDE), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=True)
    if buf.tell() > IMAGE_MAX_BYTES:
        raise CrosshairError(f"The image is still over {IMAGE_MAX_BYTES // 1024} KB after shrinking it.")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ---------------------------------------------------------------- drawing
def _rgb(hexcolor):
    return tuple(int(hexcolor[i:i + 2], 16) for i in (1, 3, 5))


def extent(c):
    """Half-width in pixels the design can reach from the centre (before rotation)."""
    ol = c["outline_thickness"] if c["outline"] else 0
    reach = c["gap"] + c["size"] + c["thickness"] + ol
    if c["style"] in ("circle", "circle_dot", "circle_cross", "square", "split_circle"):
        reach = max(reach, c["gap"] + c["size"] + c["thickness"] + ol)
    if c["style"] == "image" and c.get("image"):
        reach = IMAGE_MAX_SIDE // 2 + 2
    reach = max(reach, c["dot_size"] + ol + 2)
    return int(reach * 1.5) + 4          # room for rotation


def render(c, background=None):
    """Draws the design. Returns an RGBA PIL image with the crosshair centred on the middle pixel
    (odd size). Opacity is applied to the alpha channel. background=(r,g,b) composites it."""
    from PIL import Image, ImageDraw
    c = validate(c)
    half = extent(c)
    S = half * 2 + 1
    cx = cy = half
    col = _rgb(c["color"]) + (255,)
    dotc = _rgb(c["dot_color"] or c["color"]) + (255,)
    olc = _rgb(c["outline_color"]) + (255,)
    ol = c["outline_thickness"] if c["outline"] else 0
    t, gap, size = c["thickness"], c["gap"], c["size"]
    a0 = -(t // 2)                       # thickness band around the centre line: a0 .. a0 + t - 1

    if c["style"] == "image":
        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        src = Image.open(io.BytesIO(base64.b64decode(c["image"]))).convert("RGBA")
        im.paste(src, (cx - src.width // 2, cy - src.height // 2), src)
    else:
        def shapes(draw, color, grow):
            """Draws every part; grow > 0 draws the outline (each part expanded by `grow` px)."""
            def bar(x0, y0, x1, y1):                        # inclusive pixel rectangle
                draw.rectangle([x0 - grow, y0 - grow, x1 + grow, y1 + grow], fill=color)

            def arms(top=True):
                lo, hi = gap, gap + size - 1
                # even thickness: the band is centred half a pixel up-left, so the left/top arms are
                # mirrored about that point (otherwise the plus is lopsided by 1 px)
                m = 1 if t % 2 == 0 else 0
                bar(cx + lo, cy + a0, cx + hi, cy + a0 + t - 1)               # right
                bar(cx - hi - m, cy + a0, cx - lo - m, cy + a0 + t - 1)       # left
                bar(cx + a0, cy + lo, cx + a0 + t - 1, cy + hi)               # bottom
                if top:
                    bar(cx + a0, cy - hi - m, cx + a0 + t - 1, cy - lo - m)   # top

            def ring():
                r = gap + size
                draw.ellipse([cx - r - grow, cy - r - grow, cx + r + grow, cy + r + grow], outline=color,
                             width=t + 2 * grow)

            def dot():
                if grow and not c["dot_outline"]:
                    return
                d = c["dot_size"]
                o = -(d // 2)
                draw.rectangle([cx + o - grow, cy + o - grow, cx + o + d - 1 + grow, cy + o + d - 1 + grow],
                               fill=color if grow else dotc)

            def wedges():
                """Four tapered arms: about 40 % of `thickness` wide at the gap, full width at the end.
                One arm is drawn, then copied by exact 90-degree turns so all four are identical."""
                from PIL import Image as _I, ImageDraw as _D
                lo, hi = gap, gap + size - 1
                win = ((max(1, t // 2 - 1) | 1) - 1) / 2         # odd inner width, about 40 % of thickness
                wout = (t - 1) / 2
                layer = _I.new("RGBA", im.size, (0, 0, 0, 0))
                ld = _D.Draw(layer)
                for x in range(lo - grow, hi + grow + 1):          # one pixel column at a time: symmetric
                    k = min(1.0, max(0.0, (x - lo) / max(1, hi - lo)))
                    half = int(round(win + (wout - win) * k)) + grow
                    ld.rectangle([cx + x, cy - half, cx + x, cy + half], fill=color)
                for k in range(4):
                    im.alpha_composite(layer)
                    layer = layer.transpose(_I.ROTATE_90)

            def split_ring():
                """A ring broken into four arcs centred on the diagonals (corner brackets)."""
                r = gap + size
                for mid in (45, 135, 225, 315):
                    ext = 2 if grow else 0
                    draw.arc([cx - r - grow, cy - r - grow, cx + r + grow, cy + r + grow], mid - 26 - ext,
                             mid + 26 + ext, fill=color, width=t + 2 * grow)

            s = c["style"]
            if s in ("cross", "cross_dot"):
                arms()
            elif s == "t":
                arms(top=False)
            elif s in ("circle", "circle_dot"):
                ring()
            elif s == "circle_cross":
                ring()
                arms()
            elif s == "square":
                r = gap + size
                draw.rectangle([cx - r - grow, cy - r - grow, cx + r + grow, cy + r + grow], outline=color,
                               width=t + 2 * grow)
            elif s == "wedge":
                wedges()
            elif s == "split_circle":
                split_ring()
            elif s == "chevron":
                L = gap + size + grow
                h = t * 0.71 + grow                    # half the thickness measured vertically
                draw.polygon([(cx, cy - h), (cx + L, cy + L - h), (cx + L, cy + L + h), (cx, cy + h),
                              (cx - L, cy + L + h), (cx - L, cy + L - h)], fill=color)
            if s in ("dot", "cross_dot", "circle_dot") or c["center_dot"]:
                dot()

        im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        if ol:
            shapes(ImageDraw.Draw(im), olc, ol)
        shapes(ImageDraw.Draw(im), col, 0)

    if c["rotation"]:
        exact = c["rotation"] % 90 == 0
        im = im.rotate(-c["rotation"], resample=Image.NEAREST if exact else Image.BICUBIC, center=(cx, cy))
    if c["opacity"] < 100:
        a = im.getchannel("A").point(lambda v: v * c["opacity"] // 100)
        im.putalpha(a)
    if background is not None:
        bg = Image.new("RGBA", im.size, tuple(background) + (255,))
        bg.alpha_composite(im)
        return bg
    return im


def render_keyed(c):
    """For the overlay window: RGB image where 'see-through' pixels are exactly the key colour
    (Windows -transparentcolor only hides exact matches). Opacity is left to the window alpha, so
    pixels here are either the crosshair colour or the key."""
    from PIL import Image
    c = dict(validate(c), opacity=100)
    im = render(c)
    a = im.getchannel("A")
    solid = Image.new("RGB", im.size, KEY)
    mask = a.point(lambda v: 255 if v >= 110 else 0)
    solid.paste(im.convert("RGB"), (0, 0), mask)
    return solid


def bounds(c):
    """Bounding box of the drawn pixels relative to the centre: (left, top, right, bottom)."""
    im = render(c)
    box = im.getchannel("A").getbbox()
    if not box:
        return (0, 0, 0, 0)
    h = im.width // 2
    return (box[0] - h, box[1] - h, box[2] - 1 - h, box[3] - 1 - h)


# ---------------------------------------------------------------- share codes
def to_code(c):
    c = validate(c)
    raw = json.dumps(c, separators=(",", ":"), sort_keys=True).encode("utf-8")
    code = CODE_PREFIX + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii").rstrip("=")
    if len(code) > CODE_MAX_CHARS:
        raise CrosshairError("This crosshair is too big for a share code (use Export file instead).")
    return code


def from_code(code):
    if not isinstance(code, str):
        raise CrosshairError("Paste a crosshair code that starts with RTX1-.")
    code = "".join(code.split())
    if not code.startswith(CODE_PREFIX):
        raise CrosshairError("That isn't a RETWEAKS crosshair code (it should start with RTX1-).")
    if len(code) > CODE_MAX_CHARS:
        raise CrosshairError("That code is too long.")
    body = code[len(CODE_PREFIX):]
    try:
        packed = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        z = zlib.decompressobj()
        raw = z.decompress(packed, 400_000)
        if z.unconsumed_tail:
            raise CrosshairError("That code is too large.")
        data = json.loads(raw.decode("utf-8"))
    except CrosshairError:
        raise
    except Exception:
        raise CrosshairError("That code is damaged or incomplete. Copy the whole code and try again.")
    return validate(data)


# ---------------------------------------------------------------- files
def export_file(c, path):
    c = validate(c)
    data = {"format": FILE_FORMAT, "version": 1, "crosshair": c}
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return Path(path)


def import_file(path):
    """Reads a .rtxhair file (or any text file holding a share code)."""
    try:
        p = Path(path)
        if p.stat().st_size > 1_000_000:
            raise CrosshairError("That file is too big to be a crosshair.")
        text = p.read_text(encoding="utf-8-sig")
    except CrosshairError:
        raise
    except (OSError, UnicodeDecodeError):
        raise CrosshairError("That file couldn't be read.")
    s = text.strip()
    if s.startswith(CODE_PREFIX):
        return from_code(s)
    try:
        data = json.loads(s)
    except ValueError:
        raise CrosshairError("That file isn't a RETWEAKS crosshair.")
    if isinstance(data, dict) and data.get("format") == FILE_FORMAT:
        if data.get("version") != 1:
            raise CrosshairError("That crosshair file was made by a newer RETWEAKS.")
        return validate(data.get("crosshair"))
    raise CrosshairError("That file isn't a RETWEAKS crosshair.")


# ---------------------------------------------------------------- built-in designs
BUILTIN = [
    new(name="Classic green", style="cross", color="#00ff66", size=7, thickness=2, gap=4),
    new(name="Tiny dot", style="dot", color="#00ffff", dot_size=3, outline=True),
    new(name="Cross + dot", style="cross_dot", color="#ffffff", size=6, thickness=2, gap=5, dot_size=2),
    new(name="T shape", style="t", color="#ff3b3b", size=8, thickness=2, gap=3),
    new(name="Ring", style="circle", color="#ffffff", size=6, thickness=2, gap=4, outline=True),
    new(name="Ring + dot", style="circle_dot", color="#ffd400", size=7, thickness=1, gap=5, dot_size=2),
    new(name="Scope", style="circle_cross", color="#ff2fd6", size=9, thickness=1, gap=6, outline=True),
    new(name="Box", style="square", color="#7cff00", size=4, thickness=1, gap=3),
    new(name="Chevron", style="chevron", color="#ff8a00", size=8, thickness=2, gap=0),
    new(name="Thick plus", style="cross", color="#ffffff", size=10, thickness=4, gap=0, outline=True,
        outline_thickness=2),
    new(name="Diagonal X", style="cross", color="#00e5ff", size=7, thickness=2, gap=3, rotation=45),
    new(name="Soft cross", style="cross", color="#ffffff", size=6, thickness=2, gap=4, opacity=60, outline=False),
]


# Pack 2 (owner request 2026-10-22: "add all of these crosshairs"): 21 designs recreated from a screenshot of
# another crosshair app's library. They are approximations drawn from small thumbnails (about 12-30 px), so
# shapes, colours and proportions are as close as those thumbnails allow, not exact copies. Names describe
# the design.
# Names (owner request 2026-10-22, "do the streamer names"): designs that carried a creator's name in the
# owner's screenshot keep that name; a short description in brackets tells apart several by the same name.
# They're recreations, not files from those creators. Unnamed ones ("New", "Untitled") keep a description.
PACK2 = [
    new(name="Green plus", style="cross", color="#00ff00", size=6, thickness=2, gap=0, outline=False),
    new(name="MrSavage", style="cross", color="#ffffff", size=5, thickness=2, gap=0, outline=True,
        outline_color="#e00000", center_dot=True, dot_size=2, dot_color="#ff0000", dot_outline=False),
    new(name="Small white plus", style="cross", color="#ffffff", size=3, thickness=2, gap=0, outline=False),
    new(name="EXD Pollo", style="cross_dot", color="#f2f2f2", size=5, thickness=2, gap=3, outline=True,
        outline_color="#000000", dot_size=2),
    new(name="Magenta ring", style="circle_dot", color="#d000d0", size=3, thickness=2, gap=1, outline=False,
        dot_size=2, dot_color="#b0406e"),
    new(name="MrLust (green gap cross)", style="cross", color="#00ff00", size=3, thickness=2, gap=2, outline=False),
    new(name="MrSavage (bracket scope)", style="split_circle", color="#ff0000", size=11, thickness=3, gap=1,
        outline=False, center_dot=True, dot_size=2, dot_color="#00c800"),
    new(name="Red-rimmed ring", style="circle_dot", color="#ffffff", size=2, thickness=1, gap=1, outline=True,
        outline_color="#e01818", dot_size=1, dot_color="#e8d878", dot_outline=False),
    new(name="MrSavage AR", style="cross", color="#00e000", size=4, thickness=2, gap=2, outline=True,
        outline_color="#0b5a0b"),
    new(name="Pink soft plus", style="cross", color="#ff9cf0", size=4, thickness=2, gap=1, outline=True,
        outline_color="#6a2a6a"),
    new(name="Lolli", style="wedge", color="#ffffff", size=9, thickness=7, gap=3, outline=True,
        outline_color="#ff2a00", outline_thickness=1),
    new(name="Mongraal", style="circle_dot", color="#ffffff", size=2, thickness=1, gap=1, outline=True,
        outline_color="#101010", dot_size=1, dot_color="#e8d878", dot_outline=False),
    new(name="White plus", style="cross", color="#ffffff", size=5, thickness=2, gap=0, outline=True,
        outline_color="#5a5a5a"),
    new(name="P2X Scope", style="chevron", color="#ff0000", size=5, thickness=2, gap=0, outline=False),
    new(name="Yellow ring", style="circle_dot", color="#ffe000", size=4, thickness=1, gap=1, outline=True,
        outline_color="#000000", dot_size=1, dot_color="#a8a8a8", dot_outline=False),
    new(name="MrLust (magenta gap cross)", style="cross", color="#ff00ff", size=4, thickness=2, gap=3, outline=True,
        outline_color="#5a1a5a"),
    new(name="MrLust (white gap cross)", style="cross", color="#ffffff", size=3, thickness=2, gap=2, outline=True,
        outline_color="#2a2a2a"),
    new(name="Magenta plus", style="cross", color="#ff00ff", size=4, thickness=2, gap=0, outline=False),
    new(name="Grey ghost cross", style="cross", color="#c8c8c8", size=3, thickness=2, gap=3, outline=True,
        outline_color="#1a1a1a", center_dot=True, dot_size=4, dot_color="#3a1a3a", dot_outline=False,
        opacity=85),
    new(name="MrLust (magenta outlined plus)", style="cross", color="#ffffff", size=6, thickness=2, gap=0, outline=True,
        outline_color="#ff00ff", center_dot=True, dot_size=2, dot_color="#ff00ff", dot_outline=False),
    new(name="MrSavage (magenta plus)", style="cross", color="#ffffff", size=5, thickness=2, gap=0,
        outline=True, outline_color="#ff00ff", center_dot=True, dot_size=2, dot_color="#ff00ff",
        dot_outline=False),
]
ALL_BUILTIN = BUILTIN + PACK2


# ---------------------------------------------------------------- saved crosshairs
def data_dir():
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "RETWEAKS"


def store_path():
    return data_dir() / "crosshairs.json"


class Store:
    """The user's saved crosshairs (%APPDATA%\\RETWEAKS\\crosshairs.json, kept apart from config.json).
    A damaged file is never overwritten: it is copied to crosshairs.json.bad-<time> first, and entries
    that fail validation are kept in that copy."""

    def __init__(self, path=None):
        self.path = Path(path) if path else store_path()
        self.items = []
        self.note = ""
        self._lock = threading.Lock()
        self.load()

    def load(self):
        self.items, self.note = [], ""
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError as e:
            self.note = f"Couldn't read your saved crosshairs ({e.strerror or e})."
            return
        try:
            data = json.loads(text)
            raw = data.get("saved") if isinstance(data, dict) else None
            if not isinstance(raw, list):
                raise ValueError
        except ValueError:
            self._backup(text)
            self.note = "Your saved crosshairs file was damaged; a copy was kept next to it."
            return
        bad = 0
        for d in raw:
            try:
                self.items.append(validate(d))
            except CrosshairError:
                bad += 1
        if bad:
            self._backup(text)
            self.note = f"{bad} saved crosshair(s) couldn't be read; a copy of the file was kept."

    def _backup(self, text):
        try:
            self.path.with_name(self.path.name + f".bad-{time.strftime('%Y%m%d-%H%M%S')}").write_text(
                text, encoding="utf-8")
        except OSError:
            pass

    def save(self):
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.path.with_suffix(".tmp")
                tmp.write_text(json.dumps({"version": 1, "saved": self.items}, indent=2), encoding="utf-8")
                os.replace(tmp, self.path)
                return True
            except OSError:
                return False

    def unique_name(self, name, skip=None):
        names = {x["name"].lower() for i, x in enumerate(self.items) if i != skip}
        base, n = name[:NAME_MAX], 2
        while name.lower() in names:
            suffix = f" ({n})"
            name = base[:NAME_MAX - len(suffix)] + suffix
            n += 1
        return name

    def add(self, c):
        c = validate(c)
        c["name"] = self.unique_name(c["name"])
        self.items.append(c)
        self.save()
        return c

    def rename(self, i, name):
        name = " ".join(str(name).split())[:NAME_MAX]
        if not name:
            raise CrosshairError("Give the crosshair a name.")
        self.items[i]["name"] = self.unique_name(name, skip=i)
        self.save()
        return self.items[i]

    def duplicate(self, i):
        c = dict(self.items[i])
        c["name"] = c["name"] + " copy"
        return self.add(c)

    def delete(self, i):
        del self.items[i]
        self.save()


# ---------------------------------------------------------------- online gallery
def gallery_cache_path():
    return data_dir() / "crosshair_gallery_cache.json"


def parse_gallery(data):
    """Validates a gallery JSON document. Returns (entries, skipped). Each entry:
    {"name", "author", "crosshair"}. Raises CrosshairError if the document itself is wrong."""
    if not isinstance(data, dict) or data.get("format") != GALLERY_FORMAT or not isinstance(
            data.get("crosshairs"), list):
        raise CrosshairError("The gallery list isn't in the expected format.")
    out, skipped = [], 0
    for e in data["crosshairs"][:GALLERY_MAX]:
        try:
            if not isinstance(e, dict):
                raise CrosshairError("bad entry")
            c = from_code(e.get("code", ""))
            name = e.get("name") if isinstance(e.get("name"), str) and e.get("name").strip() else c["name"]
            c["name"] = " ".join(name.split())[:NAME_MAX]
            author = e.get("author") if isinstance(e.get("author"), str) else ""
            out.append({"name": c["name"], "author": " ".join(author.split())[:40], "crosshair": c})
        except CrosshairError:
            skipped += 1
    return out, skipped


def fetch_gallery(url=GALLERY_URL, timeout=8, opener=None):
    """Downloads and checks the gallery. Returns a dict:
      {"status": "ok"|"not_available"|"offline"|"invalid", "entries": [...], "skipped": n,
       "cached_at": text or None, "message": text}
    On any failure the last good copy (if there is one) is returned with its date, never fake data."""
    opener = opener or urllib.request.urlopen
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RETWEAKS crosshair gallery"})
        with opener(req, timeout=timeout) as r:
            body = r.read(2_000_001)
        if len(body) > 2_000_000:
            raise CrosshairError("The gallery list is too large.")
        entries, skipped = parse_gallery(json.loads(body.decode("utf-8")))
        _write_cache(body)
        msg = f"{len(entries)} crosshair(s) from the RETWEAKS gallery."
        if skipped:
            msg += f" {skipped} broken entr{'y' if skipped == 1 else 'ies'} skipped."
        return {"status": "ok", "entries": entries, "skipped": skipped, "cached_at": None, "message": msg}
    except urllib.error.HTTPError as e:
        status = "not_available" if e.code == 404 else "offline"
        msg = ("Gallery isn't available yet." if e.code == 404
               else f"The gallery couldn't be loaded (the server answered {e.code}).")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        status, msg = "offline", "The gallery couldn't be loaded. Check your internet connection."
    except (CrosshairError, ValueError, UnicodeDecodeError) as e:
        status, msg = "invalid", f"The gallery list couldn't be read: {e}"
    cached = _read_cache()
    if cached:
        entries, skipped, when = cached
        return {"status": status, "entries": entries, "skipped": skipped, "cached_at": when,
                "message": msg + f" Showing the copy saved {when}."}
    return {"status": status, "entries": [], "skipped": 0, "cached_at": None, "message": msg}


def _write_cache(body):
    try:
        p = gallery_cache_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"saved_at": time.strftime("%Y-%m-%d %H:%M"),
                                   "gallery": json.loads(body.decode("utf-8"))}), encoding="utf-8")
        os.replace(tmp, p)
    except (OSError, ValueError):
        pass


def _read_cache():
    try:
        data = json.loads(gallery_cache_path().read_text(encoding="utf-8"))
        entries, skipped = parse_gallery(data["gallery"])
        return entries, skipped, str(data.get("saved_at", "earlier"))
    except Exception:
        return None


def gallery_document(items):
    """Builds a gallery JSON document from crosshairs (used for crosshairs/gallery.json in the repo)."""
    return {"format": GALLERY_FORMAT, "version": 1,
            "crosshairs": [{"name": c["name"], "author": "RETWEAKS", "code": to_code(c)} for c in items]}


# ---------------------------------------------------------------- hotkey
def hotkey_names():
    from core.autoclicker import HOTKEY_VKS
    return list(HOTKEY_VKS)


DEFAULT_HOTKEY = "F9"


class HotkeyPoller:
    """Watches one key with GetAsyncKeyState on its own thread (works while a game has focus) and
    calls on_press() once per physical press. on_press runs on this thread, so callers only queue
    work there (Tk is touched only from the Tk thread)."""

    def __init__(self, key_name, on_press, get_state=None, interval=0.03):
        from core.autoclicker import HOTKEY_VKS
        if key_name not in HOTKEY_VKS:
            raise CrosshairError("Choose a hotkey from the list.")
        self.vk = HOTKEY_VKS[key_name]
        self.on_press = on_press
        self.interval = interval
        self._get = get_state or self._win
        self._quit = threading.Event()
        self._thread = None

    @staticmethod
    def _win(vk):
        import sys
        if sys.platform != "win32":
            return False
        import ctypes
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._quit.clear()
        self._thread = threading.Thread(target=self._loop, name="RetweaksCrosshairKey", daemon=True)
        self._thread.start()

    def stop(self, timeout=0.5):
        self._quit.set()
        if self._thread:
            self._thread.join(timeout)
            self._thread = None

    def poll_once(self, prev):
        down = self._get(self.vk)
        if down and not prev:
            self.on_press()
        return down

    def _loop(self):
        prev = self._get(self.vk)            # a key already held when starting doesn't count
        while not self._quit.wait(self.interval):
            try:
                prev = self.poll_once(prev)
            except Exception:
                pass
