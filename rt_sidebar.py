"""The RETWEAKS sidebar for the combined app (owner request 2026-10-22: keep the RETWEAKS sidebar and its
thin-line icons instead of the base app's diamond markers).

Header: chip logo + ReTweaks wordmark + version (Settings -> Sidebar header can switch to wordmark only,
setting `header_style` = chip / wordmark). Sections MONITOR / OPTIMIZE / TOOLS scroll; About and Settings
stay at the bottom with the administrator footer. The selected page gets an accent bar that slides there
in 150 ms. Icons are white PNGs (assets/nav, from tools/make_branding.py) tinted to the theme."""
import ctypes
import sys
import tkinter as tk
from pathlib import Path

from PIL import Image, ImageTk

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "assets"

# (section, [(sidebar name, target)]) - target is the base app tab index (int) or a RETWEAKS page key (str).
NAV = [
    # Every original page has an entry (owner request 2026-10-22: "add all of the pages").
    # the base app's About (tab 14) only repeated the app name, so RETWEAKS' About covers it; its Appearance page
    # (tab 18) moved into Settings -> Appearance.
    ("MONITOR", [("Dashboard", "Dashboard"), ("Hardware", "Hardware"), ("PC specs", 4),
                 ("Temperatures", "Temperatures"), ("Health Check", "Health Check"), ("FPS overlay", "FPS overlay"), ("Benchmark", 8),
                 ("Display", "Display")]),
    # Exact-undo tweaks are a tab inside Individual tweaks (owner request 2026-10-22), not a sidebar entry.
    ("OPTIMIZE", [("Quick start", 0), ("Presets", 15), ("Individual tweaks", 1), ("CTT library", 2),
                  ("Windows tweaks", 17), ("Windows Activation", 28), ("Transparent TB (taskbar)", "Transparent TB (taskbar)"), ("Customize", 10),
                  ("Game profiles", 3), ("Game config files", "Game config files"),
                  ("Program rules", "Program rules"), ("Startup apps", "Startup apps"), ("Network", "Network"),
                  ("Drivers", 22)]),
    ("TOOLS", [("Browser", "Browser"), ("Windhawk", 29), ("File Transfers", "File Transfers"), ("Backgrounds", "Backgrounds"), ("Storage", 9), ("Cleanup", "Cleanup"), ("Audio Mixer", 27),
               ("Fan control", "Fan control"), ("RGB lighting", "RGB lighting"), ("Run", "Run"),
               ("Auto clicker", 21), ("AI assistant", 20), ("Daily Tools", 26), ("App Starter", 23),
               ("PC Value Checker", 24), ("3D PC Builder", 25), ("Bottleneck", 19), ("Snapshots", "Snapshots"),
               ("Fun tools", "Fun tools"), ("Crosshair", "Crosshair"), ("Tools", 16), ("Advanced tools", 12), ("Backups & fixes", 11),
               ("Tips", 5), ("Help", 6), ("Activity", 7)]),   # Notifications removed (owner request 2026-10-23)
]
LEGACY_NAV = NAV
from rt_navigation import GROUPS, NAV, GROUP_ALIASES, preferred_section, group_for_index, group_for_name, target_index
BOTTOM = [("About", "About"), ("Settings", "Settings")]

# Sidebar search (owner request 2026-10-22: "search for any setting"). Words that find a page besides its name.
KEYWORDS = {
    "Dashboard": "live cpu gpu load clock vram temperature temps fans usage monitor",
    "Hardware": "cpu gpu ram memory motherboard bios disk drive monitor audio specs report export",
    "PC specs": "specs cpu gpu ram copy rescan device",
    "Health Check": "scan check fix problems health",
    "FPS overlay": "fps test frames 1% lows presentmon overlay benchmark counter frame time",
    "Benchmark": "benchmark score speed test",
    "Display": "refresh rate hz resolution stretched stretch nvidia driver monitor",
    "Quick start": "home recommended preset start",
    "Presets": "preset profile max fps esports balanced streamer low-end laptop privacy",
    "Individual tweaks": "tweak registry undo exact-undo exact original restore point",
    "CTT library": "ctt chris titus winutil",
    "Windows tweaks": "windows tweak",
    "Windows Activation": "windows activation massgrave license office",
    "Transparent TB (taskbar)": "translucenttb transparent translucent taskbar blur acrylic download install",
    "Customize": "appearance privacy security windows look",
    "Game profiles": "game fortnite valorant cs2 apex warzone minecraft gta roblox league rocket overwatch",
    "Game config files": "game config ini settings file backup lock fortnite minecraft",
    "Program rules": "priority gpu preference fullscreen optimizations game mode calming background",
    "Startup apps": "startup sign in boot autorun scheduled tasks",
    "Network": "dns ping latency internet wifi ethernet adapter speed test",
    "Drivers": "driver nvidia amd intel update",
    "Browser": "browser web internet tabs bookmarks history downloads search engine",
    "Windhawk": "windhawk mods windows customization extensions",
    "File Transfers": "send receive share code upload download files folders internet transfer litterbox",
    "Backgrounds": "wallpaper background picture image video gif lively animated animation desktop preview favorites",
    "Storage": "storage explorer files folders disk",
    "Cleanup": "cleanup clean temp junk space analyzer delete",
    "Audio Mixer": "audio sound volume mixer microphone mic speakers lock",
    "Auto clicker": "auto clicker click cps hotkey",
    "AI assistant": "ai gemini chat assistant help",
    "Daily Tools": "daily tools",
    "App Starter": "app starter launch programs",
    "PC Value Checker": "value price worth",
    "3D PC Builder": "build builder parts 3d",
    "Bottleneck": "bottleneck calculator cpu gpu",
    "Snapshots": "snapshot compare before after",
    "Fun tools": "polling rate cps test reaction mouse",
    "Crosshair": "crosshair reticle aim overlay crosshair x dot custom share code gallery",
    "Temperatures": "temperature temps heat thermal cpu gpu hot spot sensor celsius fahrenheit pawnio "
                    "librehardwaremonitor",
    "Fan control": "fan fans rpm speed cooling cooler duty curve curves silent balanced performance quiet loud bios "
                   "pawnio",
    "RGB lighting": "rgb lighting light lights led argb ram color colour rainbow breathing cycle brightness profile "
                    "openrgb fan lights off",
    "Run": "run open launch command task manager services event viewer regedit msinfo calculator",
    "Tools": "tools",
    "Advanced tools": "services scheduled tasks network report task scheduler",
    "Backups & fixes": "backup restore point repair sfc dism fix",
    "Tips": "tips advice",
    "Help": "help guide how",
    "Activity": "activity log history results",
    "About": "about version credits license",
    "Settings": "settings theme appearance accent color colour super black background animation theme maker "
                "share code sidebar header banner discord tray close minimized start with windows updates "
                "refresh interval temperature celsius fahrenheit open on lhm librehardwaremonitor report problem "
                "language idioma langue sprache lingua língua english español français deutsch português",
}
KEYWORDS['Windows backgrounds']=KEYWORDS['Backgrounds']


def _tr(text):
    """Page name in the current UI language (rt_i18n), so searching works in the language shown."""
    try:
        import rt_i18n
        return rt_i18n.tr(text)
    except Exception:
        return ""


# Pages with their own search box: a sidebar search carries over to it when the page is opened.
PAGE_SEARCH = {"CTT library": "ctt_search", "Customize": "customize_search"}
BADGES = {"PC Value Checker": "Beta"}


def slug(name):
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _tint(path, color, size=18):
    im = Image.open(path).convert("RGBA")
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    solid = Image.new("RGBA", im.size, (r, g, b, 255))
    solid.putalpha(im.getchannel("A"))
    return solid


def HEAD_FONT(g):
    """Section headers (MONITOR, OPTIMIZE, TOOLS, APP): bold and full-brightness so they read as headings,
    not as pages, tweaks or settings (owner request 2026-10-22)."""
    return (g["UI"], 9, "bold")


class NavButton(tk.Canvas):
    """One sidebar row: icon + label; hover and selected states (RETWEAKS 'nav' button look)."""

    H = 34

    def __init__(self, parent, side, name, command):
        super().__init__(parent, height=self.H, bg=side.c("SIDE"), highlightthickness=0, bd=0, cursor="hand2",
                         takefocus=1)
        self.side, self.name, self.command = side, name, command
        self.active = self.hover = False
        self.bind("<Enter>", lambda e: self._set(hover=True))
        self.bind("<Leave>", lambda e: self._set(hover=False))
        self.bind("<ButtonRelease-1>", lambda e: self.command())
        self.bind("<Return>", lambda e: self.command())
        self.bind("<space>", lambda e: self.command())
        self.bind("<FocusIn>", lambda e: self.draw())
        self.bind("<FocusOut>", lambda e: self.draw())
        self.bind("<Configure>", lambda e: self.draw())
        self.draw()

    def _set(self, hover=None, active=None):
        if hover is not None:
            self.hover = hover
        if active is not None:
            self.active = active
        self.draw()

    def draw(self):
        s = self.side
        self.delete("all")
        w = max(self.winfo_width(), 180)
        bg = s.c("NAV_ACTIVE") if self.active else (s.c("NAV_HOVER") if self.hover else s.c("SIDE"))
        self.configure(bg=s.c("SIDE"))
        r = 8
        x1, y1, x2, y2 = 2, 2, w - 2, self.H - 2
        if bg != s.c("SIDE"):
            pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2,
                   x1, y2 - r, x1, y1 + r, x1, y1]
            self.create_polygon(pts, smooth=True, fill=bg, outline="")
        if self.focus_get() is self:
            self.create_rectangle(x1 + 1, y1 + 1, x2 - 1, y2 - 1, outline=s.c("ACC"))
        fg = s.c("FG") if (self.active or self.hover) else s.c("MUTED")
        icon = s.icon(self.name, fg)
        if icon is not None:
            self.create_image(16, self.H // 2, image=icon)
        self.create_text(36, self.H // 2, text=self.name, anchor="w", fill=fg,
                         font=(s.g["UI"], 10, "bold" if self.active else "normal"))
        badge = BADGES.get(self.name)
        if badge:
            self.create_text(w - 12, self.H // 2, text=badge, anchor="e", fill=s.c("MUTED"), font=(s.g["UI"], 7, "bold"))


class Sidebar:
    def __init__(self, hub, side, g):
        self.hub, self.side, self.g = hub, side, g
        self._icons = {}
        self.buttons = {}            # name -> NavButton
        self.targets = {}            # name -> tab index
        self.current = None
        self._anim = None
        for w in list(side.winfo_children()):
            w.destroy()
        side.configure(bg=self.c("SIDE"))
        self._build()
        self.primary_names=list(self.buttons)
        for _section,items in LEGACY_NAV:
            for name,target in items:
                index=target_index(hub,target)
                if index is not None:self.targets.setdefault(name,index)
        for old,new in GROUP_ALIASES.items():self.targets.setdefault(old,self.targets[new])

    # colours always read live from retweaks.py globals (they change with the theme)
    def c(self, key):
        return self.g.get(key) or {"NAV_ACTIVE": self.g["PANEL"], "NAV_HOVER": self.g["PANEL"]}.get(key, "#000000")

    def icon(self, name, color):
        key = (name, color)
        if key not in self._icons:
            p = ASSETS / "nav" / f"{slug(name)}.png"
            if not p.is_file() and name == 'Windows backgrounds':
                p = ASSETS / 'nav' / 'backgrounds.png'
            if not p.is_file():
                self._icons[key] = None
            else:
                self._icons[key] = ImageTk.PhotoImage(_tint(p, color), master=self.side)
        return self._icons[key]

    def _target(self, t):
        if isinstance(t, int):
            return t
        if t in GROUPS:return target_index(self.hub,GROUPS[t][0][2])
        return self.hub.rt_tabs.get(t)

    def _build(self):
        hub, side, g = self.hub, self.side, self.g
        from core.version import BRAND, __version__
        head = tk.Frame(side, bg=self.c("SIDE"))
        head.pack(fill="x", padx=14, pady=(20, 2))
        chip = Image.open(ASSETS / "chip-32.png").convert("RGBA").resize((26, 26), Image.LANCZOS)
        self._chip = ImageTk.PhotoImage(chip, master=side)
        self.header_chip = tk.Label(head, image=self._chip, bg=self.c("SIDE"))
        self.header_chip.pack(side="left", padx=(0, 9))
        tk.Label(head, text=BRAND, bg=self.c("SIDE"), fg=self.c("FG"), font=(g["UI"], 15, "bold")).pack(side="left")
        tk.Label(side, text=f"Version {__version__}", bg=self.c("SIDE"), fg=self.c("MUTED"),
                 font=(g["UI"], 8)).pack(anchor="w", padx=(49, 0), pady=(0, 10))
        self.apply_header_style(hub.settings.get("header_style", "chip"))

        # Search lives in the top bar now (rt_search.GlobalSearch, owner request 2026-10-22). The sidebar keeps
        # an internal query so filter() can still narrow the list (used by checks and the global search).
        self.query = tk.StringVar()
        self.search_entry = None
        self._hint_text = ""
        self.query.trace_add("write", lambda *a: self.filter())

        # bottom part first so the scrolling list takes the remaining height
        bottom = tk.Frame(side, bg=self.c("SIDE"))
        bottom.pack(side="bottom", fill="x", padx=10, pady=(4, 12))
        # About and Settings get their own section, apart from the tool pages (owner request 2026-10-22)
        self.bottom_line = tk.Frame(bottom, bg=self.c("LINE"), height=1)
        self.bottom_line.pack(fill="x", padx=12, pady=(6, 8))
        self.bottom_head = tk.Label(bottom, text="APP", bg=self.c("SIDE"), fg=self.c("FG"),
                                    font=HEAD_FONT(g), anchor="w")
        self.bottom_head.pack(fill="x", padx=12, pady=(0, 3))
        for name, t in BOTTOM:
            self._add(bottom, name, t)
        foot = "Running as administrator" if is_admin() else "Not running as administrator"
        tk.Label(bottom, text=foot, bg=self.c("SIDE"), fg=self.c("MUTED"), font=(g["UI"], 8),
                 anchor="w").pack(fill="x", padx=12, pady=(8, 0))
        # the base app's status line (set_status) lives here now
        hub.status = tk.Label(bottom, text="", bg=self.c("SIDE"), fg=self.c("GREEN"), font=(g["UI"], 8, "bold"),
                              anchor="w")
        hub.status.pack(fill="x", padx=12)

        wrap = tk.Frame(side, bg=self.c("SIDE"))
        wrap.pack(fill="both", expand=True)
        cv = tk.Canvas(wrap, bg=self.c("SIDE"), highlightthickness=0, bd=0, width=220)
        cv.pack(side="left", fill="both", expand=True)
        holder = tk.Frame(cv, bg=self.c("SIDE"))
        win = cv.create_window((0, 0), window=holder, anchor="nw")
        holder.bind("<Configure>", lambda e:self._fit_scroll_region())
        cv.bind("<Configure>", lambda e:(cv.itemconfigure(win,width=e.width),self._fit_scroll_region()))
        cv.wheel_target = cv
        import rt_perf
        rt_perf.smooth_scroll(cv)
        self.canvas, self.holder = cv, holder
        self.sections = []
        for section, items in NAV:
            head_lbl = tk.Label(holder, text=section, bg=self.c("SIDE"), fg=self.c("FG"),
                                font=HEAD_FONT(g), anchor="w")
            head_lbl.pack(fill="x", padx=22, pady=(10, 3))
            for name, t in items:
                self._add(holder, name, t)
            self.sections.append((head_lbl, [n for n, _ in items if n in self.buttons]))
        self.no_match = tk.Label(holder, text="Nothing matches. Try another word.", bg=self.c("SIDE"),
                                 fg=self.c("MUTED"), font=(g["UI"], 9), anchor="w", wraplength=190, justify="left")
        # sliding accent bar
        self.indicator = tk.Frame(side, bg=self.c("ACC"), width=3, height=20)
        # apply_theme() in hubplus calls hub.sidebar_nav.refresh() after a theme change

    def _fit_scroll_region(self):
        """A short menu fills its viewport, preventing Tk from centering/overscrolling it."""
        if not hasattr(self,'canvas'):return
        cv=self.canvas
        height=max(self.holder.winfo_height(),cv.winfo_height())
        cv.configure(scrollregion=(0,0,max(1,cv.winfo_width()),height),confine=True)
        if self.holder.winfo_height()<=cv.winfo_height():cv.yview_moveto(0)
        if hasattr(self,'indicator'):self._place_indicator(animate=False)

    def _add(self, parent, name, target):
        idx = self._target(target)
        if idx is None:
            return
        b = NavButton(parent, self, name, lambda i=idx, n=name: self.open(n, i))
        b.pack(fill="x", padx=10, pady=1)
        self.buttons[name] = b
        self.targets[name] = idx

    # ------------------------------------------------------------ search
    def search_text(self):
        return self.query.get().strip().lower()

    def matches(self, q):
        """Names of sidebar entries that match q (every word must match the page name, its keywords, or,
        for tweak pages, the name/description of one of their tweaks)."""
        words = q.split()
        if not words:
            return set(self.targets)
        hits = set()
        for name in self.targets:
            text = (name + " " + KEYWORDS.get(name, "") + " " + _tr(name)).lower()
            if all(w in text for w in words):
                hits.add(name)
        tweaks = self.g.get("TWEAKS") or []
        found = [t for t in tweaks if all(w in (t.get("name", "") + " " + t.get("desc", "")).lower() for w in words)]
        if found:
            hits.add("Individual tweaks")
            if any(str(t.get("cat", "")).startswith("CTT") for t in found):
                hits.add("CTT library")
            if any(any(c.lower() in str(t.get("cat", "")).lower() for c in ("Custom", "Appearance", "Privacy",
                                                                             "Security")) for t in found):
                hits.add("Customize")
        page = getattr(self.hub, "rt_pages", {}).get("Exact-undo tweaks")
        if page is not None and any(all(w in r.search_text for w in words) for r in getattr(page, "rows", [])):
            hits.add("Individual tweaks")          # exact-undo tweaks are a tab of Individual tweaks
        hits.update(group_for_name(h) for h in list(hits))
        return {h for h in hits if h in self.targets}

    def exact_match(self, q):
        """True when q matches a tweak on the Exact undo tab of Individual tweaks."""
        words = (q or "").lower().split()
        page = getattr(self.hub, "rt_pages", {}).get("Exact-undo tweaks")
        return bool(words) and page is not None and any(all(w in r.search_text for w in words)
                                                        for r in getattr(page, "rows", []))

    def filter(self):
        q = self.search_text()
        hits = self.matches(q)
        for w in self.holder.winfo_children():
            w.pack_forget()
        shown = 0
        for head_lbl, names in self.sections:
            rows = [n for n in names if n in hits]
            if not rows:
                continue
            head_lbl.pack(fill="x", padx=22, pady=(10, 3))
            for n in rows:
                self.buttons[n].pack(fill="x", padx=10, pady=1)
            shown += len(rows)
        if not shown:
            below = [n for n, _ in BOTTOM if q and all(w in (n + " " + KEYWORDS.get(n, "")).lower() for w in q.split())]
            self.no_match.configure(text=(f"Found in {' and '.join(below)} (below). Press Enter to open."
                                          if below else "Nothing matches. Try another word."))
            self.no_match.pack(fill="x", padx=22, pady=10)
        self.canvas.yview_moveto(0)
        self.side.after_idle(lambda: self._place_indicator(animate=False))
        self.visible = [n for _, names in self.sections for n in names if n in hits] + \
                       [n for n, _ in BOTTOM if n in self.targets]
        return shown

    def open_first(self):
        q = self.search_text()
        hits=self.matches(q)
        first=next((n for n in self.targets if n not in self.primary_names and n in hits),None) if q else None
        if first is None:first = next((n for _, names in self.sections for n in names if n in hits), None)
        if first is None and q:
            first = next((n for n, _ in BOTTOM if n in self.targets and
                          all(w in (n + " " + KEYWORDS.get(n, "")).lower() for w in q.split())), None)
        if first:
            self.open(first, self.targets[first])

    def open(self, name, index, search=None):
        """Open a page; search (or the sidebar query) is put into that page's own search box if it has one."""
        q = self.search_text() if search is None else search
        if name in GROUPS:
            saved=preferred_section(self.hub.settings,name)
            saved_target=next((target for _,alias,target in GROUPS[name] if alias==saved),None)
            if saved_target is not None:index=target_index(self.hub,saved_target)
            if q:
                words=q.lower().split()
                match=next(((alias,target) for _,alias,target in GROUPS[name]
                            if all(w in (alias+' '+KEYWORDS.get(alias,'')).lower() for w in words)),None)
                if match is None:
                    hits=self.matches(q)
                    match=next(((alias,target) for _,alias,target in GROUPS[name] if alias in hits),None)
                if match:name,index=match[0],target_index(self.hub,match[1])
        self.hub.show_tab(index)
        if not q:
            return
        var = None
        if name in PAGE_SEARCH:
            var = getattr(self.hub, PAGE_SEARCH[name], None)
        elif name in ("Exact-undo tweaks", "Individual tweaks"):
            # the Exact undo tab of Individual tweaks has the search box; open that tab when the words match there
            if name == "Exact-undo tweaks" or self.exact_match(q):
                from rt_pages import open_exact_undo
                open_exact_undo(self.hub, q)
            elif callable(getattr(self.hub, "show_tweaks_tab", None)):
                self.hub.show_tweaks_tab("all")
            return
        if var is not None:
            try:
                var.set(q)
            except tk.TclError:
                pass

    def apply_header_style(self, style):
        if style == "wordmark":
            self.header_chip.pack_forget()
        elif not self.header_chip.winfo_ismapped():
            self.header_chip.pack(side="left", padx=(0, 9), before=self.header_chip.master.winfo_children()[-1])

    def select(self, index):
        """Called by hub.show_tab: highlight the matching row and slide the accent bar to it."""
        name = group_for_index(self.hub,index) or next((n for n, i in self.targets.items() if i == index), None)
        for n, b in self.buttons.items():
            if b.active != (n == name):
                b._set(active=(n == name))
        self.current = name
        if name and name in self.buttons and self.buttons[name].master is self.holder:
            self._scroll_into_view(self.buttons[name])
        self._place_indicator(animate=True)

    def _scroll_into_view(self, b):
        self.side.update_idletasks()
        top, h = b.winfo_y(), self.holder.winfo_height()
        view_h = self.canvas.winfo_height()
        if h <= view_h or h <= 0:
            return
        y0 = self.canvas.canvasy(0)
        if top < y0 or top + b.winfo_height() > y0 + view_h:
            self.canvas.yview_moveto(max(0, top - 40) / h)

    def _place_indicator(self, animate=True):
        b = self.buttons.get(self.current)
        if b is None or not b.winfo_ismapped():
            self.indicator.place_forget()
            return
        self.side.update_idletasks()
        y = b.winfo_rooty() - self.side.winfo_rooty() + 8
        x = b.winfo_rootx() - self.side.winfo_rootx()
        h = b.winfo_height() - 16
        # hide it while the row is scrolled out of the list area
        top = self.canvas.winfo_rooty() - self.side.winfo_rooty()
        if b.master is self.holder and not (top <= y <= top + self.canvas.winfo_height() - h):
            self.indicator.place_forget()
            return
        if self._anim:
            self.side.after_cancel(self._anim)
            self._anim = None
        info = self.indicator.place_info()
        start = int(float(info["y"])) if animate and info else y
        steps = 6 if animate and info else 1

        def step(k=1):
            cur = start + (y - start) * (1 - (1 - k / steps) ** 3)    # ease-out, 150 ms total
            self.indicator.place(x=x, y=int(cur), width=3, height=h)
            self.indicator.lift()
            if k < steps:
                self._anim = self.side.after(25, step, k + 1)
            else:
                self._anim = None
        step()

    def relabel(self):
        """Language changed (rt_i18n.set_language): redraw the rows' text only. The icons stay as they are; clearing
        and re-tinting them (refresh) left the sidebar without icons while a slow switch was still running on
        Windows (owner report v2.0.8)."""
        for b in self.buttons.values():
            try:
                b.draw()
            except tk.TclError:
                pass

    def refresh(self):
        """Theme changed: redraw rows (icons are re-tinted) and recolour the accent bar."""
        self._icons.clear()
        self.indicator.configure(bg=self.c("ACC"))
        self.bottom_line.configure(bg=self.c("LINE"))
        self.bottom_head.configure(bg=self.c("SIDE"), fg=self.c("FG"))
        for head_lbl, _names in getattr(self, "sections", []):
            try:
                head_lbl.configure(bg=self.c("SIDE"), fg=self.c("FG"))
            except tk.TclError:
                pass
        for b in self.buttons.values():
            b.draw()
