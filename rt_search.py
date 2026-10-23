"""Global search bar in the top bar (owner request 2026-10-22: "add a global search bar", top bar, centre).

Finds sidebar pages (by name and keywords), settings words (Settings / About), and tweaks by name or
description: the base app's 117 tweaks (Individual tweaks, CTT library, Customize) and RETWEAKS' exact-undo
tweaks. Results drop down under the box; Up/Down + Enter or a click opens one; Esc closes; Ctrl+K focuses
the box from anywhere. Opening a tweak result opens its page and puts the tweak name in that page's own
search box where the page has one. Only opens pages: it never applies or changes anything."""
import tkinter as tk

MAX_TWEAKS = 8
HINT = "Search pages, settings and tweaks   (Ctrl+K)"


def _tr(text):
    """Text in the current UI language (rt_i18n); English if translations aren't loaded."""
    try:
        import rt_i18n
        return rt_i18n.tr(text)
    except Exception:
        return text


class GlobalSearch:
    def __init__(self, hub, g):
        self.hub, self.g = hub, g
        self.query = tk.StringVar()
        self.results = []          # [(title, detail, callable)]
        self.rows = []
        self.sel = 0
        self.popup = None
        self.box = None
        self.entry = None
        self._chrome = None
        self._hint_on = False
        hub.bind_all("<Control-k>", self.focus, add="+")
        hub.bind_all("<Control-K>", self.focus, add="+")
        hub.bind("<<LanguageChanged>>", lambda e: self._relabel_hint(), add="+")

    # ------------------------------------------------------------ top bar placement
    def place(self, chrome, width):
        """Called by window_chrome.refresh() after it redraws the bar (it clears its canvas each time).
        The box is drawn on the bar itself (rounded outline) with a plain, borderless text field inside,
        so it always fits inside the 39 px bar whatever the Windows display scaling is (owner feedback
        2026-10-22: the first version was too tall)."""
        g = self.g
        if self.entry is None or self._chrome is not chrome:
            self._chrome = chrome
            self.entry = tk.Entry(chrome, textvariable=self.query, bg=g["PANEL"], fg=g["FG"], relief="flat", bd=0,
                                  highlightthickness=0, insertbackground=g["FG"], font=(g["UI"], 9))
            self.box = self.entry
            self.entry.bind("<FocusIn>", self._focus_in, add="+")
            self.entry.bind("<FocusOut>", self._focus_out, add="+")
            self.entry.bind("<Down>", lambda e: self.move(1))
            self.entry.bind("<Up>", lambda e: self.move(-1))
            self.entry.bind("<Return>", lambda e: self.open_selected())
            self.entry.bind("<Escape>", lambda e: self.clear())
            self.query.trace_add("write", lambda *a: self.update_results())
            self._show_hint()
        self.entry.configure(bg=g["PANEL"], insertbackground=g["FG"],
                             fg=g["MUTED"] if self._hint_on else g["FG"])
        left, right = 340, width - 150           # after the sidebar button, before the window buttons
        w = max(160, min(440, right - left))
        x0 = max(left, (width - w) / 2)
        top, bottom = 13, 38                     # inside the bar (7..46) with room above and below
        chrome.create_polygon(g["rr"](x0, top, x0 + w, bottom, 12), smooth=True, fill=g["PANEL"],
                              outline=g["LINE"], width=1, tags="searchbox")
        # magnifier
        cx, cy = x0 + 15, (top + bottom) / 2 - 1
        chrome.create_oval(cx - 4, cy - 4, cx + 3, cy + 3, outline=g["MUTED"], width=1.3, tags="searchbox")
        chrome.create_line(cx + 2, cy + 2, cx + 6, cy + 6, fill=g["MUTED"], width=1.3, tags="searchbox")
        chrome.tag_bind("searchbox", "<ButtonRelease-1>", lambda e: self.focus())
        chrome.create_window(x0 + 28, (top + bottom) / 2, window=self.entry, anchor="w", width=w - 40)

    # ------------------------------------------------------------ hint text
    def _show_hint(self):
        if not self.query.get():
            self._hint_on = True
            self.entry.insert(0, _tr(HINT))
            self.entry.configure(fg=self.g["MUTED"])

    def _relabel_hint(self):
        if self.entry is not None and self._hint_on:
            self.entry.delete(0, "end")
            self.entry.insert(0, _tr(HINT))

    def _focus_in(self, e=None):
        if self._hint_on:
            self._hint_on = False
            self.entry.delete(0, "end")
            self.entry.configure(fg=self.g["FG"])
        if self.text():
            self.update_results()

    def _focus_out(self, e=None):
        # Results live inside the main window (not a separate popup window), so clicking one never moves the
        # focus away first. Close only when the pointer isn't over the results.
        self.hub.after(120, self._maybe_close)

    def _pointer_over_panel(self):
        if self.popup is None:
            return False
        try:
            w = self.hub.winfo_containing(*self.hub.winfo_pointerxy())
        except (KeyError, tk.TclError):
            return False
        while w is not None:
            if w is self.popup:
                return True
            w = getattr(w, "master", None)
        return False

    def _maybe_close(self):
        try:
            f = self.hub.focus_get()
        except (KeyError, tk.TclError):
            f = None
        if f is self.entry or self._pointer_over_panel():
            return
        self.close_popup()
        if not self.query.get():
            self._show_hint()

    def text(self):
        return "" if self._hint_on else self.query.get().strip().lower()

    def focus(self, e=None):
        if self.entry is not None:
            self.entry.focus_set()
            self._focus_in()
            self.entry.select_range(0, "end")
        return "break"

    def clear(self):
        self.query.set("")
        self.close_popup()
        self.hub.focus_set()

    # ------------------------------------------------------------ results
    def search(self, q):
        """List of (title, detail, action). Pages first (sidebar order), then Settings/About, then tweaks."""
        side = getattr(self.hub, "sidebar_nav", None)
        if side is None or not q:
            return []
        import rt_sidebar as rs
        words = q.split()
        out = []

        def page_hit(name):
            return all(w in (name + " " + rs.KEYWORDS.get(name, "") + " " + _tr(name)).lower() for w in words)

        order = [n for _, items in rs.NAV for n, _ in items] + [n for n, _ in rs.BOTTOM]
        for name in order:
            if name in side.targets and page_hit(name):
                out.append((name, "Page", lambda n=name: side.open(n, side.targets[n], search="")))
        # tweaks (the base app's list)
        found = 0
        for t in self.g.get("TWEAKS") or []:
            text = t.get("name", "") + " " + t.get("desc", "")
            text = (text + " " + _tr(t.get("name", "")) + " " + _tr(t.get("desc", ""))).lower()
            if not all(w in text for w in words):
                continue
            cat = str(t.get("cat", ""))
            if cat.startswith("CTT") and "CTT library" in side.targets:
                page = "CTT library"
            elif any(c.lower() in cat.lower() for c in ("Custom", "Appearance", "Privacy", "Security")) \
                    and "Customize" in side.targets:
                page = "Customize"
            else:
                page = "Individual tweaks"
            if page not in side.targets:
                continue
            if page == "Individual tweaks":          # the "All tweaks" tab (it has no search box of its own)
                act = lambda p=page: (side.open(p, side.targets[p], search=""),
                                      callable(getattr(self.hub, "show_tweaks_tab", None))
                                      and self.hub.show_tweaks_tab("all"))
            else:
                act = lambda p=page, nm=t.get("name", ""): side.open(p, side.targets[p], search=nm.lower())
            out.append((t.get("name", ""), f"Tweak · {page}", act))
            found += 1
            if found >= MAX_TWEAKS:
                break
        # RETWEAKS exact-undo tweaks: the "Exact undo" tab of Individual tweaks (owner request 2026-10-22)
        page = getattr(self.hub, "rt_pages", {}).get("Exact-undo tweaks")
        if page is not None and "Individual tweaks" in side.targets:
            from rt_pages import open_exact_undo
            n = 0
            for r in getattr(page, "rows", []):
                if all(w in r.search_text for w in words):
                    nm = r.tweak.name
                    out.append((nm, "Tweak · Exact undo", lambda nm=nm: open_exact_undo(self.hub, nm.lower())))
                    n += 1
                    if n >= MAX_TWEAKS // 2:
                        break
        return out

    def update_results(self):
        q = self.text()
        self.results = self.search(q)
        self.sel = 0
        if not q:
            self.close_popup()
            return
        self.show_popup()

    def open_selected(self):
        if self.results:
            self.open(self.sel)
        return "break"

    def open(self, i):
        if not (0 <= i < len(self.results)):
            return
        action = self.results[i][2]
        self.query.set("")
        self.close_popup()
        self.hub.focus_set()
        action()

    # ------------------------------------------------------------ dropdown
    # Owner report 2026-10-22: "clicking a result fails". The old dropdown was its own window; on Windows the
    # first click on it activated that window, the search box lost focus and the list closed before the click
    # arrived, and hovering rebuilt the rows under the mouse. Now the list is a frame inside the main window,
    # rows are built once per search, hovering only recolours them, and a row opens on mouse press.
    def close_popup(self):
        if self.popup is not None:
            try:
                self.popup.destroy()
            except tk.TclError:
                pass
            self.popup = None
            self.rows = []

    def show_popup(self):
        g = self.g
        self.close_popup()
        p = self.popup = tk.Frame(self.hub, bg=g["PANEL"], highlightthickness=1, highlightbackground=g["LINE"],
                                  cursor="hand2")
        self.rows = []
        if not self.results:
            tk.Label(p, text="Nothing matches. Try another word.", bg=g["PANEL"], fg=g["MUTED"],
                     font=(g["UI"], 9), anchor="w").pack(fill="x", padx=14, pady=10)
        shown = self.results[:14]
        for i, (title, detail, _) in enumerate(shown):
            row = tk.Frame(p, bg=g["PANEL"])
            row.pack(fill="x")
            a = tk.Label(row, text=title, bg=g["PANEL"], fg=g["FG"], font=(g["UI"], 10), anchor="w")
            a.pack(side="left", padx=(14, 8), pady=6)
            b = tk.Label(row, text=detail, bg=g["PANEL"], fg=g["MUTED"], font=(g["UI"], 8), anchor="e")
            b.pack(side="right", padx=(8, 14))
            for w in (row, a, b):
                w.bind("<ButtonPress-1>", lambda e, k=i: self.open(k))
                w.bind("<Enter>", lambda e, k=i: self._hover(k))
            self.rows.append((row, a, b))
        if len(self.results) > len(shown):
            tk.Label(p, text=f"{len(self.results) - len(shown)} more — type more words to narrow it down.",
                     bg=g["PANEL"], fg=g["MUTED"], font=(g["UI"], 8), anchor="w").pack(fill="x", padx=14, pady=(2, 8))
        self._paint_selection()
        self.entry.update_idletasks()
        x = self.entry.winfo_rootx() - self.hub.winfo_rootx() - 28
        y = self._chrome.winfo_rooty() - self.hub.winfo_rooty() + 42
        width = max(320, self.entry.winfo_width() + 40)
        p.place(x=x, y=y, width=width)
        p.lift()

    def _paint_selection(self):
        g = self.g
        for i, (row, a, b) in enumerate(getattr(self, "rows", [])):
            bg = g["PANEL2"] if i == self.sel else g["PANEL"]
            for w in (row, a, b):
                w.configure(bg=bg)
            a.configure(font=(g["UI"], 10, "bold" if i == self.sel else "normal"))

    def move(self, step):
        if self.results:
            self.sel = (self.sel + step) % len(self.results[:14])
            self._paint_selection()
        return "break"

    def _hover(self, k):
        if k != self.sel:
            self.sel = k
            self._paint_selection()
