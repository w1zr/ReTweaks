"""RETWEAKS' own tray menu (owner feedback 2026-10-22: Windows' tray menu "does not match the theme and is
too square"). Windows draws the standard tray menu itself and it can't be themed, so a right-click on the
tray icon opens this small rounded popup instead, drawn with the current theme's colours.

Same items and actions as before (Open RETWEAKS, Quit RETWEAKS) plus Settings. Opens next to the cursor
like the Windows menu (above the taskbar), closes on a click outside it, Esc, or after an item is chosen.
Rounded corners: Windows 11 rounds the window itself (DWM corner preference); on Windows 10 the corners
are cut with a transparent colour key. Only ever touched from the Tk thread."""
import sys
import tkinter as tk

ITEM_H, PAD, WIDTH, RADIUS = 34, 6, 224, 12
KEY = "#010203"          # transparent colour key (Windows 10 corner cut-outs)


def _is_win11():
    try:
        return sys.platform == "win32" and sys.getwindowsversion().build >= 22000
    except Exception:
        return False


def _blend(a, b, k):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * k) for x, y in zip(a, b))


class TrayMenu:
    current = None

    def __init__(self, hub, x, y, items):
        """items: list of (label, callable) or None for a divider."""
        if TrayMenu.current is not None:
            TrayMenu.current.close()
        TrayMenu.current = self
        self.hub, self.items = hub, items
        g = getattr(hub, "_g", {}) or {}
        c = lambda k, d: g.get(k, d)
        self.panel, self.panel2 = c("PANEL", "#0a0a0a"), c("PANEL2", "#141414")
        self.line, self.fg, self.muted = c("LINE", "#1f1f1f"), c("FG", "#f2f2f2"), c("MUTED", "#a3a3a3")
        self.acc, self.ui = c("ACC", "#a3a3a3"), c("UI", "Segoe UI")
        self.hover = None
        self.closed = False
        rows = [i for i in items]
        h = PAD * 2 + sum(ITEM_H if r else 9 for r in rows)
        w = WIDTH
        self.win = tk.Toplevel(hub)
        self.win.withdraw()
        self.win.overrideredirect(True)
        try:
            self.win.attributes("-topmost", True)
        except tk.TclError:
            pass
        rounded_by_windows = _is_win11()
        bg = self.panel if rounded_by_windows else KEY
        if not rounded_by_windows and sys.platform == "win32":
            try:
                self.win.attributes("-transparentcolor", KEY)
            except tk.TclError:
                bg = self.panel
        self.win.configure(bg=bg)
        self.cv = tk.Canvas(self.win, width=w, height=h, bg=bg, highlightthickness=0, bd=0, cursor="hand2")
        self.cv.pack()
        self.w, self.h, self.rows = w, h, rows
        self.draw()
        # place like the Windows menu: bottom-right corner at the cursor, kept on screen
        sw, sh = hub.winfo_screenwidth(), hub.winfo_screenheight()
        px = min(max(0, x - w), sw - w)
        py = y - h if y - h >= 0 else y
        py = min(max(0, py), sh - h)
        self.win.geometry(f"{w}x{h}+{int(px)}+{int(py)}")
        self.win.deiconify()
        self.win.update_idletasks()
        if rounded_by_windows:
            self._round_native()
        self.cv.bind("<Motion>", self._motion)
        self.cv.bind("<Leave>", lambda e: self._set_hover(None))
        self.cv.bind("<ButtonRelease-1>", self._click)
        for w_ in (self.win, self.cv):
            w_.bind("<Escape>", lambda e: self.close())
            w_.bind("<Up>", lambda e: self._step(-1))
            w_.bind("<Down>", lambda e: self._step(1))
            w_.bind("<Return>", lambda e: self._choose(self.hover))
        self.win.bind("<FocusOut>", lambda e: self.win.after(80, self._focus_check))
        self._take_focus()
        self.win.after(15000, self.close)          # never left hanging around

    # ------------------------------------------------------------ drawing
    def _rr(self, x0, y0, x1, y1, r):
        return [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
                x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]

    def _row_boxes(self):
        y, out = PAD, []
        for i, r in enumerate(self.rows):
            hh = ITEM_H if r else 9
            out.append((i, y, y + hh))
            y += hh
        return out

    def draw(self):
        cv = self.cv
        cv.delete("all")
        cv.create_polygon(self._rr(0, 0, self.w - 1, self.h - 1, RADIUS), smooth=True, fill=self.panel,
                          outline=self.line, width=1)
        for i, top, bottom in self._row_boxes():
            r = self.rows[i]
            if r is None:
                cv.create_line(14, (top + bottom) / 2, self.w - 14, (top + bottom) / 2, fill=self.line)
                continue
            label = r[0]
            danger = label.lower().startswith("quit")
            if self.hover == i:
                cv.create_polygon(self._rr(PAD, top + 1, self.w - PAD, bottom - 1, 8), smooth=True,
                                  fill=self.panel2, outline="")
                cv.create_line(PAD + 3, top + 10, PAD + 3, bottom - 10, fill=self.acc, width=2)
            cv.create_text(22, (top + bottom) / 2, text=label, anchor="w",
                           fill=self.fg if (self.hover == i or not danger) else _blend(self.fg, self.muted, .35),
                           font=(self.ui, 10, "bold" if self.hover == i else "normal"))

    # ------------------------------------------------------------ input
    def _index_at(self, y):
        for i, top, bottom in self._row_boxes():
            if top <= y < bottom and self.rows[i] is not None:
                return i
        return None

    def _set_hover(self, i):
        if i != self.hover:
            self.hover = i
            self.draw()

    def _motion(self, e):
        self._set_hover(self._index_at(e.y))

    def _step(self, d):
        idx = [i for i, r in enumerate(self.rows) if r is not None]
        if not idx:
            return
        cur = idx.index(self.hover) if self.hover in idx else (-1 if d > 0 else 0)
        self._set_hover(idx[(cur + d) % len(idx)])

    def _click(self, e):
        self._choose(self._index_at(e.y))

    def _choose(self, i):
        if i is None or self.closed:
            return
        action = self.rows[i][1]
        self.close()
        try:
            action()
        except Exception:
            pass

    def _focus_check(self):
        if self.closed:
            return
        try:
            f = self.win.focus_get()
        except (KeyError, tk.TclError):
            f = None
        if f is None or not str(f).startswith(str(self.win)):
            self.close()

    def close(self):
        if self.closed:
            return
        self.closed = True
        if TrayMenu.current is self:
            TrayMenu.current = None
        try:
            self.win.destroy()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ Windows
    def _hwnd(self):
        import ctypes
        return ctypes.windll.user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()

    def _round_native(self):
        try:
            import ctypes
            hwnd = self._hwnd()
            pref = ctypes.c_int(2)                              # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), 4)
            r, g_, b = (int(self.line[i:i + 2], 16) for i in (1, 3, 5))
            color = ctypes.c_uint(r | (g_ << 8) | (b << 16))     # COLORREF for the thin border
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 34, ctypes.byref(color), 4)
        except Exception:
            pass

    def _take_focus(self):
        # A tray click lets this program take the foreground, so a click anywhere else closes the menu.
        try:
            if sys.platform == "win32":
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(self._hwnd())
        except Exception:
            pass
        try:
            self.win.focus_force()
            self.cv.focus_set()
        except tk.TclError:
            pass
