"""Display & drivers (Tk port of the RETWEAKS Qt page): refresh-rate check with Set max Hz, stretched
resolution (global, with the NVIDIA NVAPI add flow), Back to native, and GPU driver version/age.

All logic lives in core/display.py and core/nvidia_display.py (unchanged); this file is the UI."""
import tkinter as tk
import webbrowser

from core import display as dsp
from rt_pages.common import NA, button_row, card, info, kv_rows, label, run_bg

REVERT_SECONDS = 15


def _ask(parent, title, text):
    from tkinter import messagebox
    return messagebox.askyesno(title, text, parent=parent)


class KeepSettingsDialog:
    """'Keep these settings?' with a countdown. Revert, closing the window or the timeout means revert.
    run() -> True when the user pressed Keep changes."""

    def __init__(self, parent, g, seconds=REVERT_SECONDS):
        self.parent, self.g, self.left, self.result = parent, g, seconds, False

    def run(self):
        g = self.g
        top = tk.Toplevel(self.parent)
        top.title("Keep these display settings?")
        top.configure(bg=g["PANEL"])
        top.resizable(False, False)
        try:
            top.transient(self.parent.winfo_toplevel())
            top.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.msg = tk.Label(top, bg=g["PANEL"], fg=g["FG"], font=(g["UI"], 10), justify="left", wraplength=380)
        self.msg.pack(padx=22, pady=(20, 12), anchor="w")
        row = tk.Frame(top, bg=g["PANEL"])
        row.pack(fill="x", padx=22, pady=(0, 18))
        g["RButton"](row, "Keep changes", lambda: self._close(top, True), kind="primary").pack(side="right")
        g["RButton"](row, "Revert", lambda: self._close(top, False)).pack(side="right", padx=(0, 8))
        top.protocol("WM_DELETE_WINDOW", lambda: self._close(top, False))
        self._text()
        top.after(1000, lambda: self._tick(top))
        try:
            top.grab_set()
        except tk.TclError:
            pass
        top.wait_window()
        return self.result

    def _text(self):
        self.msg.configure(text=f"Keep these settings? Reverting automatically in {self.left} s "
                                "if you do not confirm.")

    def _tick(self, top):
        if not top.winfo_exists():
            return
        self.left -= 1
        if self.left <= 0:
            self._close(top, False)
        else:
            self._text()
            top.after(1000, lambda: self._tick(top))

    def _close(self, top, keep):
        self.result = keep
        try:
            top.grab_release()
            top.destroy()
        except tk.TclError:
            pass


class DisplayPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self._loaded = False
        g["page_header"](tab, "RETWEAKS", "Display & drivers",
                         "Checks whether each monitor runs at the highest refresh rate it supports at its current "
                         "resolution, sets a stretched resolution, and shows how old your graphics driver is.")
        self.body = hub._scroll_area(tab)
        self.mon_box = tk.Frame(self.body, bg=g["BG"])
        self.mon_box.pack(fill="x")
        self.drv_box = tk.Frame(self.body, bg=g["BG"])
        self.drv_box.pack(fill="x")
        row = tk.Frame(self.body, bg=g["BG"])
        row.pack(fill="x", pady=(8, 16))
        g["RButton"](row, "Re-check", self.refresh).pack(side="left")

    # tests replace these
    def keep_dialog(self):
        return KeepSettingsDialog(self.hub, self.g).run()

    def on_shown(self):
        if not self._loaded:
            self.refresh()

    def refresh(self):
        self._loaded = True
        self._placeholder(self.mon_box, "Monitors", "Reading displays…")
        self._placeholder(self.drv_box, "Graphics driver", "Reading driver information…")
        run_bg(self.hub, dsp.list_displays, self._show_displays)
        run_bg(self.hub, dsp.list_gpu_drivers, self._show_drivers)

    def _placeholder(self, box, title, text):
        for w in box.winfo_children():
            w.destroy()
        b = card(box, self.g, title)
        label(b, text, self.g, 9, self.g["MUTED"], pady=(0, 12))

    # ------------------------------------------------------------ monitors
    def _show_displays(self, displays):
        g = self.g
        for w in self.mon_box.winfo_children():
            w.destroy()
        if not isinstance(displays, list):
            displays = []
        if not displays:
            b = card(self.mon_box, g, "Monitors")
            label(b, f"Display modes: {NA} (Windows did not list any active display).", g, 9, g["MUTED"],
                  pady=(0, 12))
            return
        for d in displays:
            self._monitor_card(d, d.get("name") or d.get("monitor") or d["device"])

    def _monitor_card(self, d, name):
        g = self.g
        b = card(self.mon_box, g, name + (" (primary)" if d.get("primary") else ""))
        cur, mx = d.get("hz"), d.get("max_hz")
        kv_rows(b, g, [
            ("Display", d["device"]),
            ("Resolution", f"{d['width']} x {d['height']}" + (" (rotated)" if d.get("rotated") else "")),
            ("Native resolution", "{} x {}".format(*d["native"]) if d.get("native") else NA),
            ("Refresh rate", f"{cur} Hz" if cur else NA),
            ("Max at this resolution", f"{mx} Hz" if mx else NA),
            ("Bit depth", f"{d['bpp']}-bit" if d.get("bpp") else NA),
        ])
        if cur and mx and cur < mx:
            label(b, f"Running below max refresh: {cur} Hz now, {mx} Hz supported.", g, 10, "#ffb020", bold=True)
            row = button_row(b, g)
            g["RButton"](row, "Open Windows display settings", self._open_settings).pack(side="left")
            g["RButton"](row, f"Set {mx} Hz", lambda dd=d: self._apply(dd), kind="primary").pack(side="left", padx=8)
            label(b, "In Windows: Display, then Advanced display, then choose the refresh rate.", g, 9, g["MUTED"])
        elif cur and mx:
            label(b, "Running at the highest refresh rate this display reports at this resolution.", g, 10,
                  g["GREEN"], bold=True)
        else:
            label(b, "Refresh rate could not be read for this display.", g, 9, g["MUTED"])
        self._stretch_section(b, d)
        tk.Frame(b, bg=b.cget("bg"), height=10).pack()

    # ------------------------------------------------------------ stretched resolution
    def _stretch_section(self, b, d):
        g = self.g
        if d.get("rotated"):
            label(b, "Stretched resolution isn't offered for a rotated (portrait) screen.", g, 9, g["MUTED"])
            return
        choices = dsp.stretch_choices(d)
        nw, nh = dsp.native_size(d)
        if not choices or not nw:
            return
        label(b, "Stretched resolution", g, 12, bold=True, pady=(10, 2))
        stretched = (d["width"], d["height"]) != (nw, nh)
        label(b, (f"Now running {d['width']}×{d['height']} on a {nw}×{nh} screen." if stretched else
                  f"Runs the whole screen at a narrower resolution stretched to fill it (native: {nw}×{nh}). "
                  "Games in Windowed Fullscreen, like Fortnite, use it automatically. Characters look wider; "
                  "you don't see more of the map. Fortnite's Arena and tournaments stay 16:9 (Epic's rule)."),
              g, 9, g["MUTED"])
        texts = [f"{w} × {h}" + (f"  ({hz} Hz)" if hz else "  (not on your graphics card yet)")
                 for w, h, hz in choices]
        by_text = dict(zip(texts, choices))
        row = button_row(b, g)
        sel = g["RSelect"](row, texts, width=290)
        sel.pack(side="left")
        g["RButton"](row, "Apply stretched", lambda: self._stretch(d, *by_text[sel.get()]),
                     kind="primary").pack(side="left", padx=8)
        back = g["RButton"](row, f"Back to native ({nw}×{nh})", lambda: self._native(d))
        back.pack(side="left")
        back.set_enabled(stretched)
        label(b, "If a resolution isn't on your graphics card yet, RETWEAKS adds it on NVIDIA cards (NVIDIA's own "
                 "NVAPI, like Control Panel → Create Custom Resolution). On AMD or Intel add it once in AMD Software "
                 "or Intel Graphics Command Center. If you see black bars instead of a stretched picture, set "
                 "scaling to Full-screen (NVIDIA Control Panel → Adjust desktop size and position) or Full panel "
                 "(AMD GPU Scaling).", g, 9, g["MUTED"])
        self._stretch_sel = sel     # the last card's selector (tests)

    def _stretch(self, d, w, h, hz):
        if not hz:
            if not self._nvidia_add(d, w, h):
                return
            d = next((x for x in dsp.list_displays() if x["device"] == d["device"]), d)
            hz = dsp.max_refresh_at(d.get("modes") or [], w, h, d.get("bpp"))
            if not hz:
                info(self.hub, "Stretched resolution", f"{w}×{h} still isn't on the graphics card's list.", True)
                self.refresh()
                return
        if not _ask(self.hub, "Stretched resolution",
                    f"Switch {d['device']} to {w}×{h} at {hz} Hz, stretched to fill the screen?\n\n"
                    f"The screen goes black for a moment. You'll have {REVERT_SECONDS} seconds to keep it, "
                    "otherwise it switches back."):
            return
        what = f"{d['device']}: stretched {w}×{h}"
        ok, msg = dsp.set_resolution(d["device"], w, h, hz, stretch=True, persist=False)
        if not ok:
            self.hub.log_action("Display", what, "Failed", msg)
            info(self.hub, "Stretched resolution", msg, True)
            self.refresh()
            return
        if self.keep_dialog():
            ok, msg = dsp.set_resolution(d["device"], w, h, hz, stretch=True, persist=True)   # save it
            self.hub.log_action("Display", what, "Success" if ok else "Failed", "" if ok else msg)
            if not ok:
                info(self.hub, "Stretched resolution", msg, True)
        else:
            ok, msg = dsp.restore_saved_mode(d["device"])
            self.hub.log_action("Display", what, "Reverted" if ok else "Revert failed", "" if ok else msg)
            if not ok:
                info(self.hub, "Stretched resolution", msg + " Use Windows display settings to fix it.", True)
        self.refresh()

    def _native(self, d):
        nw, nh = dsp.native_size(d)
        hz = dsp.max_refresh_at(d.get("modes") or [], nw, nh, d.get("bpp"))
        ok, msg = dsp.set_resolution(d["device"], nw, nh, hz, stretch=False, persist=True)
        self.hub.log_action("Display", f"{d['device']}: back to native {nw}×{nh}", "Success" if ok else "Failed",
                            "" if ok else msg)
        if not ok:
            info(self.hub, "Stretched resolution", msg, True)
        self.refresh()

    def _nvidia_add(self, d, w, h):
        """Adds w×h to the NVIDIA driver for this monitor (source w×h, native timing = GPU stretches), with
        NVIDIA's own Try → Keep/Revert. Returns True when saved."""
        from core import nvidia_display as nvd
        if not _ask(self.hub, "Add to graphics card",
                    f"{w}×{h} isn't on your graphics card's list yet. Add it now (NVIDIA cards)?\n\n"
                    "The screen switches to it for a test; press Keep within "
                    f"{REVERT_SECONDS} seconds or it switches back by itself."):
            return False
        what = f"{d['device']}: NVIDIA custom resolution {w}×{h}"
        nw, nh = dsp.native_size(d)
        try:
            nv = nvd.NvApi()
            did = nv.display_id(d["device"])
            timing = nv.timing(did, nw, nh, d.get("max_hz") or d.get("hz") or 60)
            nv.try_custom(did, nvd.build_custom(w, h, timing))
        except Exception as e:
            self.hub.log_action("Display", what, "Failed", str(e))
            info(self.hub, "Add to graphics card",
                 f"The graphics driver didn't accept it: {e}\n\nNothing was changed. Add it by hand: NVIDIA "
                 "Control Panel → Change resolution → Customize → Create Custom Resolution; AMD Software → "
                 "Display → Custom Resolutions.", True)
            return False
        keep = self.keep_dialog()
        try:
            if keep:
                nv.save_custom(did)
                dsp.restore_saved_mode(d["device"])
                self.hub.log_action("Display", what, "Saved")
                return True
            nv.revert_trial(did)
            self.hub.log_action("Display", what, "Reverted")
        except Exception as e:
            ok, msg = dsp.restore_saved_mode(d["device"])
            self.hub.log_action("Display", what, "Failed", str(e))
            info(self.hub, "Add to graphics card", f"{e}\n\n{msg}", True)
        return False

    # ------------------------------------------------------------ refresh rate
    def _open_settings(self):
        try:
            import os
            os.startfile("ms-settings:display")
        except (AttributeError, OSError):
            webbrowser.open("ms-settings:display")

    def _apply(self, d):
        mx = d["max_hz"]
        if not _ask(self.hub, "Change refresh rate",
                    f"Change {d['device']} from {d['hz']} Hz to {mx} Hz at {d['width']} x {d['height']}?\n\n"
                    f"The screen may flicker. You will have {REVERT_SECONDS} seconds to confirm, "
                    "otherwise the previous setting is restored."):
            return
        run_bg(self.hub, dsp.set_refresh_rate, lambda res, dd=d: self._after_apply(dd, res), d["device"], mx)

    def _after_apply(self, d, res):
        if isinstance(res, Exception):
            res = (False, str(res), None)
        ok, msg, previous = res
        what = f"{d['device']}: {d['hz']} Hz -> {d['max_hz']} Hz"
        if not ok:
            self.hub.log_action("Display", what, "Failed", msg)
            info(self.hub, "Refresh rate", msg, True)
            self.refresh()
            return
        if self.keep_dialog():
            self.hub.log_action("Display", what, "Success", "Kept after confirmation")
            self.refresh()
            return
        run_bg(self.hub, dsp.set_refresh_rate, lambda r2, dd=d, w=what: self._after_revert(dd, w, r2),
               d["device"], previous)

    def _after_revert(self, d, what, res):
        if isinstance(res, Exception):
            res = (False, str(res), None)
        ok, msg, _ = res
        self.hub.log_action("Display", what, "Reverted" if ok else "Revert failed",
                            "Not confirmed in time" if ok else msg)
        if not ok:
            info(self.hub, "Refresh rate", "Could not restore the previous refresh rate automatically: "
                 f"{msg}\nUse Windows display settings to fix it.", True)
        self.refresh()

    # ------------------------------------------------------------ drivers
    def _show_drivers(self, drivers):
        g = self.g
        for w in self.drv_box.winfo_children():
            w.destroy()
        if not isinstance(drivers, list):
            drivers = []
        if not drivers:
            b = card(self.drv_box, g, "Graphics driver")
            label(b, f"Driver information: {NA}", g, 9, g["MUTED"], pady=(0, 12))
            return
        for drv in drivers:
            b = card(self.drv_box, g, drv["name"])
            rows = [("Driver version", drv.get("version")),
                    ("Driver date", drv["date"].isoformat() if drv.get("date") else None),
                    ("Age", dsp.driver_age_text(drv.get("age_days")))]
            if drv.get("vendor") == "NVIDIA":
                rows.append(("NVML driver version", drv.get("nvml_version")))
            kv_rows(b, g, rows)
            if drv.get("url"):
                row = button_row(b, g)
                g["RButton"](row, f"Open {drv['vendor']} driver page",
                             lambda u=drv["url"]: webbrowser.open(u)).pack(side="left")
            else:
                tk.Frame(b, bg=b.cget("bg"), height=8).pack()
        note = card(self.drv_box, g)
        label(note, "The age is only the date stamped on the installed driver. It does not mean a newer driver "
                    "exists or is better for you.", g, 9, g["MUTED"], pady=10)
