"""Checks for the Dashboard (rt_pages.monitor) and Hardware (rt_pages.hardware) Tk pages.
Run on Linux:  xvfb-run -a python3.12 tools/linux_shim.py checks/check_rt_monitor.py
Builds both pages on a small fake hub (real Tk + real RETWEAKS widgets), feeds a fake telemetry sample
and a fake hardware scan, and checks what the pages show. No Windows calls, no network."""
import tkinter as tk
from unittest import mock

import retweaks as app
from rt_pages import monitor as M, hardware as H

g = vars(app)


class Hub(tk.Tk):
    def __init__(self):
        super().__init__()
        self.settings = {"banner_style": "cores", "temp_unit": "F", "interval": 1000}
        self.logged = []

    _scroll_area = app.Hub._scroll_area
    _wheel = app.Hub._wheel

    def log_action(self, *a):
        self.logged.append(a)


# pure logic
assert M.interval_seconds(1000) == 1.0 and M.interval_seconds(2.0) == 2.0 and M.interval_seconds("x") == 1.0
assert M.interval_seconds(0.1) == 0.5 and M.interval_seconds(99999) == 10.0
assert M.normalize_style("WAVE") == "wave" and M.normalize_style(None) == "cores"
assert M.tile_grid(28) == (2, 14) and M.tile_grid(40) == (3, 14) and M.tile_grid(0) == (0, 0)
assert M.fmt_rate(None) == "Unavailable" and M.fmt_rate(2048) == "2.0 KB/s"
assert M.temp_text(50, "F") == "122 °F" and M.temp_text(None) is None

STATIC = {"os": {"name": "Windows 11 Home", "build": "26100", "arch": "64-bit"},
          "computer": {"manufacturer": "iBUYPOWER", "model": "TMI7N4601"},
          "cpu": {"name": "Intel Core i7-14700F", "cores": 20, "threads": 28, "base_mhz": 2100},
          "ram": {"installed_gb": 32, "total_gb": 31.8, "type": "DDR5", "running_mts": 5600, "sticks": []},
          "gpus": [{"name": "NVIDIA GeForce RTX 4060", "vram_gb": 8.0, "integrated": False,
                    "driver_version": "32.0.15.6094", "driver_date": "2026-09-01"}],
          "disks": [{"name": "NVMe SSD", "size_gb": 2000, "media": "SSD", "bus": "NVMe", "letters": ["C:"],
                     "health": "Healthy"}],
          "display_modes": [{"name": "ED320Q X2", "device": r"\\.\DISPLAY1", "width": 1920, "height": 1080,
                             "hz": 240, "primary": True}],
          "monitors": [], "audio": [], "network": [], "motherboard": {}, "is_admin": True}
SAMPLE = {"time": 0, "cpu": {"load": 37.5, "per_core": [10.0, 90.0] * 14, "mhz": 4800, "mhz_source": "x",
                             "temp_c": 50.0},
          "ram": {"percent": 40.0, "used_gb": 12.7, "total_gb": 31.8},
          "gpus": [{"luid": "1", "name": "NVIDIA GeForce RTX 4060", "vendor": "NVIDIA", "vram_total_gb": 8.0,
                    "load": 55.0, "load_source": "Windows GPU counters", "engine": "3D", "vram_used_gb": 2.5,
                    "temp_c": 60.0, "temp_source": "NVIDIA driver", "hotspot_c": None, "core_mhz": 2500,
                    "mem_mhz": None, "power_w": 90, "fan_pct": 40}],
          "io": {"disk_read_bps": 1024 * 1024, "disk_write_bps": 0, "net_down_bps": 2048, "net_up_bps": 512},
          "sensors": {"source": "LibreHardwareMonitor web server", "cpu_temp": 50.0, "gpu_temps": [],
                      "fans": [{"name": "CPU fan", "rpm": 1200.0}]}}

hub = Hub()
hub.geometry("1400x900")
with mock.patch.object(M, "request_static", lambda hub, force=False: None), \
        mock.patch.object(H, "request_static", lambda hub, force=False: None):
    dash_tab, hw_tab = tk.Frame(hub, bg=g["BG"]), tk.Frame(hub, bg=g["BG"])
    dash = M.MonitorPage(hub, dash_tab, g)
    hw = H.HardwarePage(hub, hw_tab, g)
dash_tab.pack(fill="both", expand=True)
hub.update()

# the telemetry thread only runs while a page holds it
svc = hub.rt_telemetry
with mock.patch("core.telemetry.Telemetry", side_effect=RuntimeError("no counters")):
    dash.on_shown()
    assert dash.svc.holders == {dash}
    dash.on_hidden()
    assert not svc.holders and svc.stop_flag.is_set()
    assert dash.banner.job is None          # banner animation stops when hidden

hub.rt_static = STATIC
for fn in hub.rt_static_listeners:
    fn(STATIC)
assert "Intel Core i7-14700F" in dash.summary.cget("text") and "iBUYPOWER" in dash.summary.cget("text")
for fn in svc.listeners:
    fn(SAMPLE)
hub.update()
assert dash.cpu.value.cget("text") == "38%" or dash.cpu.value.cget("text") == "37%"
assert "4.80 GHz" in dash.cpu.side.cget("text") and "122 °F" in dash.cpu.side.cget("text")   # temp_unit F
assert len(dash.gpu_cards) == 1 and dash.gpu_cards[0].value.cget("text") == "55%"
assert "2.5 / 8.0 GB" in dash.gpu_cards[0].lines.cget("text")
assert dash.disk.value.cget("text") == "1.0 MB/s" and "Upload 512 B/s" in dash.net.lines.cget("text")
assert dash.fans_shown and "CPU fan: 1200 RPM" in dash.fans_label.cget("text")
assert not dash.notice_shown                  # LHM present -> no notice
no_lhm = dict(SAMPLE, sensors=None, gpus=[])
for fn in svc.listeners:
    fn(no_lhm)
hub.update()
assert dash.notice_shown and not dash.fans_shown and dash.gpu_cards == []
assert dash.banner.thread_count == 28
dash.on_banner_changed("off")
assert not dash.banner.canvas.winfo_ismapped()
dash.on_banner_changed("wave")
for style in ("cores", "circuit", "galaxy", "wave"):
    dash.banner.set_style(style)
    dash.banner.draw()              # every style paints without errors

# Hardware page
rows = H.rows_from_static(STATIC)
assert ("Model", "Intel Core i7-14700F") in rows["cpu"]
assert ("VRAM", "8.0 GB") in rows["gpu"]
assert ("ED320Q X2", "1920 × 1080 @ 240 Hz (primary)") in rows["displays"]
assert hw.cards["cpu"].rows and ("Model", "Intel Core i7-14700F") in hw.cards["cpu"].rows
assert ("Socket", "Unavailable") in hw.cards["cpu"].rows                    # missing -> Unavailable, never fake
hw.query.set("RTX 4060")
hub.update()
assert hw.cards["gpu"].filter("RTX 4060") >= 1 and hw.cards["audio"].filter("RTX 4060") == 0
src = {"windows_counters": True, "gpu_counters": True, "nvml_gpus": 1, "lhm": None}
hw.on_sources(src)
assert ("NVIDIA extras", "NVIDIA driver (1 GPU)") in hw.cards["sources"].rows
hub.rt_last_sample, hub.rt_sources = SAMPLE, src
import tempfile, os, json
with tempfile.TemporaryDirectory() as d:
    for ext in ("json", "txt", "csv"):
        p = os.path.join(d, "r." + ext)
        with mock.patch("tkinter.filedialog.asksaveasfilename", return_value=p):
            hw.export(ext)
        assert os.path.getsize(p) > 50, ext
    assert "Intel Core i7-14700F" in open(os.path.join(d, "r.json"), encoding="utf-8").read()
    assert "Component,Field,Value" in open(os.path.join(d, "r.csv"), encoding="utf-8-sig").read()
hw.copy_report()
assert "Intel Core i7-14700F" in hub.clipboard_get()
hub.destroy()
print("PASS: Dashboard and Hardware pages show real values, Unavailable for missing data, export works, "
      "telemetry and banner stop when hidden.")
