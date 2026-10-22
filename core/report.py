# core/report.py
"""Hardware report export.

Users attach this to a GitHub issue when RETWEAKS detects something wrong on their PC.
It deliberately contains no serial numbers, MAC addresses, IP addresses, user names or
computer names, because GitHub issues are public.
"""

import copy
import json
import platform
from datetime import datetime

from core.version import __version__, APP_NAME


def build_report(static, live, sources):
    static = copy.deepcopy(static or {})
    # Strip anything identifying, just in case it ever gets added to the scan
    for key in ("serial", "mac", "ip", "node", "user"):
        static.pop(key, None)
    return {
        "app": f"{APP_NAME} {__version__}",
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "python": platform.python_version(),
        "sources": sources or {},
        "hardware": static,
        "live_sample": _strip_live(live),
    }


def _strip_live(live):
    if not live:
        return None
    live = copy.deepcopy(live)
    live.pop("time", None)
    return live


def report_to_json(report):
    return json.dumps(report, indent=2, default=str)


def report_to_text(report):
    lines = [f"=== {report['app']} hardware report ({report['created']}) ===", ""]
    hw = report.get("hardware", {})

    def add(label, value):
        lines.append(f"{label}: {value if value not in (None, '', []) else 'Unavailable'}")

    os_ = hw.get("os", {})
    add("OS", f"{os_.get('name')} (build {os_.get('build')}, {os_.get('arch')})")
    comp = hw.get("computer", {})
    add("PC", " ".join(x for x in (comp.get("manufacturer"), comp.get("model")) if x))
    cpu = hw.get("cpu", {})
    add("CPU", f"{cpu.get('name')} | {cpu.get('cores')} cores / {cpu.get('threads')} threads | base {cpu.get('base_mhz')} MHz")
    mb = hw.get("motherboard", {})
    add("Motherboard", " ".join(x for x in (mb.get("manufacturer"), mb.get("model")) if x))
    add("BIOS", f"{mb.get('bios_version')} ({mb.get('bios_date')})")
    ram = hw.get("ram", {})
    add("RAM", f"{ram.get('total_gb')} GB {ram.get('type') or ''} @ {ram.get('running_mts')} MT/s, "
               f"{ram.get('slots_used')}/{ram.get('slots_total')} slots")
    for i, g in enumerate(hw.get("gpus", []), 1):
        add(f"GPU {i}", f"{g.get('name')} | {g.get('vram_gb')} GB VRAM | driver {g.get('driver_version')}")
    for d in hw.get("disks", []):
        add(f"Disk {' '.join(d.get('letters') or [])}".strip(),
            f"{d.get('name')} | {d.get('size_gb')} GB {d.get('media') or ''} {d.get('bus') or ''} | health: {d.get('health')}")
    for m in hw.get("monitors", []):
        add("Monitor", m.get("name"))
    lines += ["", "Sources: " + json.dumps(report.get("sources", {}))]
    lines += ["", "Full details (JSON):", report_to_json(report)]
    return "\n".join(lines)
