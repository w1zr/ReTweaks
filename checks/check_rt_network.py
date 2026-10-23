"""Network page (Tk): adapters + current DNS, preset/custom/Automatic/restore actions with logging,
custom IP validation, DNS speed-test table, ping result and live traffic. Windows calls are faked."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tkinter as tk
from _tk_harness import FakeHub, g, pump
import rt_pages.network as nm

hub = FakeHub()
calls = []
dns = {"Ethernet": ["1.1.1.1", "1.0.0.1"]}
nm.W.get_network_adapters = staticmethod(lambda: ["Ethernet", "Wi-Fi"])
nm.W.get_dns_servers = staticmethod(lambda name: dns.get(name, []))
nm.W.apply_dns = staticmethod(lambda name, *s: (calls.append(("apply", name) + s), (True, "ok"))[1])
nm.W.restore_dhcp_dns = staticmethod(lambda name: (calls.append(("auto", name)), (True, "ok"))[1])
nm.W.restore_previous_dns = staticmethod(lambda name: (calls.append(("restore", name)), (False, "No saved DNS for this adapter."))[1])
nm.info = lambda *a, **k: calls.append(("info", a[2]))


def fake_dns_test(servers, rounds, progress):
    progress(1, 1)
    calls.append(("dnstest", tuple(ip for _, ip in servers)))
    s = {"avg": 10.0, "best": 8.0, "worst": 14.0, "failed": 0, "count": 10}
    return [{"label": lbl, "ip": ip, "popular": dict(s), "uncached": dict(s, avg=12.0 + i)}
            for i, (lbl, ip) in enumerate(servers)]


nm.nettest.dns_speed_test = fake_dns_test
nm.nettest.ping_test = lambda target, count, interval, timeout, progress: {
    "target": target, "count": count, "avg": 11.2, "best": 9.0, "worst": 20.0, "jitter": 1.5, "loss_pct": 0.0}

tab = tk.Frame(hub)
tab.pack(fill="both", expand=True)
p = nm.NetworkPage(hub, tab, g())
p.on_shown()
assert pump(hub, lambda: "1.1.1.1, 1.0.0.1" in p.current.cget("text")), p.current.cget("text")
assert "(Cloudflare)" in p.current.cget("text") and p.adapter.values == ["Ethernet", "Wi-Fi"]
assert all(b.enabled for b in p.buttons)

p.apply("Google", "8.8.8.8", "8.8.4.4")
assert pump(hub, lambda: hub.logs and hub.logs[-1][1] == "Google 8.8.8.8/8.8.4.4")
assert calls[-1] == ("apply", "Ethernet", "8.8.8.8", "8.8.4.4") and hub.logs[-1][2] == "Success"

p.custom1.set("999.1.1.1")
p.apply_custom()
assert calls[-1] == ("info", "Enter valid IP addresses. Not valid: 999.1.1.1")
p.custom1.set("9.9.9.9"); p.custom2.set("2620:fe::fe")
p.apply_custom()
assert pump(hub, lambda: hub.logs[-1][1] == "Custom 9.9.9.9 / 2620:fe::fe")
assert calls[-1] == ("apply", "Ethernet", "9.9.9.9", "2620:fe::fe")

p.reset()
assert pump(hub, lambda: hub.logs[-1][1] == "Automatic") and ("auto", "Ethernet") in calls
p.restore_previous()
assert pump(hub, lambda: hub.logs[-1][1] == "Restore previous")
assert hub.logs[-1][2] == "Failed" and calls[-1] == ("info", "No saved DNS for this adapter.")

p.run_dns_test()
assert pump(hub, lambda: p.dns_progress.cget("text") == "Done.")
tested = next(c for c in calls if c[0] == "dnstest")[1]
assert tested[:3] == ("1.1.1.1", "8.8.8.8", "9.9.9.9") and "1.0.0.1" in tested and "2620:fe::fe" in tested
texts = [w.cget("text") for w in p.dns_table.winfo_children()]
assert "Uncached (avg)" in texts and "12.0 ms" in texts and "0 of 20" in texts
assert "lookups per server" in p.dns_method.cget("text")

p.run_ping()
assert pump(hub, lambda: p.ping_result.cget("text") == "11 ms")
assert "Packet loss 0%" in p.ping_details.cget("text") and "1.1.1.1" in p.ping_details.cget("text")
assert pump(hub, lambda: p.traffic.cget("text").startswith("Download "), timeout=3)
assert nm.fmt_rate(2048) == "2.0 KB/s" and nm.fmt_rate(None) == "Unavailable"
p.on_hidden()
hub.destroy()
print("PASS: network page — DNS presets/custom/Automatic/restore with logs, validation, DNS speed test table, ping, traffic")
