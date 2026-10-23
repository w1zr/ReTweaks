"""Shared helpers for the RETWEAKS pages added to the Tk-based Tk app.

Pages are classes `XPage(hub, tab, g)`: `tab` is an empty tk.Frame, `g` is retweaks.py's globals
(widgets Card/RButton/RCheck/RSelect/Segmented/REntry/Bar/pill/page_header, colours BG/PANEL/SIDE/FG/
MUTED/ACC/GREEN/LINE/RISKCOL, font UI). Rules: real results only, "Unavailable" for anything that
can't be read, all slow work off the Tk thread (run_bg), Tk is touched only from the Tk thread."""
import queue
import threading
import tkinter as tk

NA = "Unavailable"


def run_bg(hub, fn, done=None, *args):
    """Runs fn(*args) on a worker thread, then done(result) on the Tk thread. Exceptions are passed to
    done as an Exception instance. Returns the thread."""
    q = queue.Queue()

    def work():
        try:
            q.put(fn(*args))
        except Exception as e:      # reported to the page, never swallowed silently
            q.put(e)

    def check():
        try:
            res = q.get_nowait()
        except queue.Empty:
            try:
                hub.after(60, check)
            except tk.TclError:
                pass
            return
        if done:
            try:
                done(res)
            except tk.TclError:
                pass

    t = threading.Thread(target=work, daemon=True)
    t.start()
    hub.after(60, check)
    return t


def label(parent, text, g, size=10, color=None, bold=False, wrap=760, **pack):
    w = tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or g["FG"],
                 font=(g["UI"], size, "bold" if bold else "normal"), justify="left", anchor="w", wraplength=wrap)
    w.pack(fill="x", **({"padx": 16, "pady": 3} | pack))
    return w


def card(parent, g, title=None, sub=None):
    """A rounded card (the base app style) with an optional title; returns the card's body frame."""
    c = g["Card"](parent)
    c.pack(fill="x", pady=6, padx=(0, 12))
    if title:
        label(c.body, title, g, 14, bold=True, pady=(12, 2))
    if sub:
        label(c.body, sub, g, 9, g["MUTED"])
    return c.body


def button_row(parent, g):
    row = tk.Frame(parent, bg=parent.cget("bg"))
    row.pack(fill="x", padx=16, pady=(6, 12))
    return row


def kv_rows(parent, g, rows):
    """Two-column key/value grid. rows: [(key, value)]; returns {key: value_label}."""
    f = tk.Frame(parent, bg=parent.cget("bg"))
    f.pack(fill="x", padx=16, pady=4)
    out = {}
    for i, (k, v) in enumerate(rows):
        tk.Label(f, text=k, bg=f.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9), anchor="w").grid(
            row=i, column=0, sticky="w", padx=(0, 18), pady=1)
        lv = tk.Label(f, text=v if v not in (None, "") else NA, bg=f.cget("bg"), fg=g["FG"], font=(g["UI"], 10),
                      anchor="w", justify="left", wraplength=620)
        lv.grid(row=i, column=1, sticky="w", pady=1)
        out[k] = lv
    return out


def confirm(parent, title, text):
    from tkinter import messagebox
    return messagebox.askyesno(title, text, parent=parent)


def info(parent, title, text, error=False):
    from tkinter import messagebox
    (messagebox.showerror if error else messagebox.showinfo)(title, text, parent=parent)
