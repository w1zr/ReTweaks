"""Network (Tk port of the RETWEAKS Qt page): DNS per adapter (presets, custom, Automatic, restore
previous), DNS speed test, ping test to 1.1.1.1 / 1.0.0.1 and live traffic.

All logic lives in core/nettest.py and core/optimizer.py (unchanged); this file is the UI."""
import time
import tkinter as tk

from core import nettest
from core.optimizer import WindowsOptimizer as W, valid_ip
from rt_pages.common import button_row, card, info, label, run_bg

DNS_PROVIDERS = [
    ("Cloudflare", "1.1.1.1", "1.0.0.1"),
    ("Google", "8.8.8.8", "8.8.4.4"),
    ("Quad9", "9.9.9.9", "149.112.112.112"),
]
NO_ADAPTER = "(no connected adapter)"


def fmt_rate(bps):
    if bps is None:
        return "Unavailable"
    for unit in ("B/s", "KB/s", "MB/s", "GB/s"):
        if bps < 1024 or unit == "GB/s":
            return f"{bps:,.1f} {unit}" if unit != "B/s" else f"{bps:,.0f} {unit}"
        bps /= 1024


class NetworkPage:
    def __init__(self, hub, tab, g):
        self.hub, self.g = hub, g
        self._loaded = False
        self._shown = False
        self._current_servers = []
        self._net_prev = None
        g["page_header"](tab, "RETWEAKS", "Network",
                         "Change which DNS servers your PC uses to look up websites and game servers. A different DNS "
                         "doesn't raise your in-game ping, but it can make lookups faster or more reliable.")
        body = hub._scroll_area(tab)

        # ---- DNS
        b = card(body, g, "DNS")
        row = button_row(b, g)
        tk.Label(row, text="Adapter:", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left",
                                                                                                 padx=(0, 8))
        self.adapter = g["RSelect"](row, [NO_ADAPTER], width=280, command=lambda v: self.refresh_dns())
        self.adapter.pack(side="left")
        g["RButton"](row, "Reload adapters", self.load_adapters).pack(side="left", padx=8)
        self.current = label(b, "Current DNS: checking…", g, 10)
        row = button_row(b, g)
        self.buttons = []
        for name, a, s in DNS_PROVIDERS:
            btn = g["RButton"](row, f"{name} ({a})", lambda n=name, x=a, y=s: self.apply(n, x, y))
            btn.pack(side="left", padx=(0, 6))
            self.buttons.append(btn)
        auto = g["RButton"](row, "Automatic (from router)", self.reset)
        auto.pack(side="left", padx=(0, 6))
        self.buttons.append(auto)
        self.btn_restore = g["RButton"](row, "Restore previous", self.restore_previous)
        self.btn_restore.pack(side="left")
        self.buttons.append(self.btn_restore)
        label(b, "Restore previous puts back the DNS this adapter had before RETWEAKS first changed it.", g, 9,
              g["MUTED"])
        row = button_row(b, g)
        tk.Label(row, text="Custom:", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9)).pack(side="left",
                                                                                                padx=(0, 8))
        self.custom1, self.custom2 = tk.StringVar(), tk.StringVar()
        e1 = g["REntry"](row, self.custom1, width_px=220)
        e1.pack(side="left")
        e2 = g["REntry"](row, self.custom2, width_px=220)
        e2.pack(side="left", padx=6)
        self._placeholder(e1.entry, self.custom1, "Primary (IPv4 or IPv6)")
        self._placeholder(e2.entry, self.custom2, "Secondary (optional)")
        b_custom = g["RButton"](row, "Apply custom", self.apply_custom)
        b_custom.pack(side="left")
        self.buttons.append(b_custom)
        label(b, "Changing DNS needs administrator rights. RETWEAKS saves your previous DNS the first time it "
                 "changes an adapter.", g, 9, g["MUTED"], pady=(0, 12))
        self._set_buttons(False)

        # ---- DNS speed test
        b = card(body, g, "DNS speed test")
        label(b, "Tests Cloudflare, Google, Quad9, your current DNS and any custom servers typed above. RETWEAKS "
                 "never changes your DNS from these results: you pick and apply.", g, 9, g["MUTED"])
        row = button_row(b, g)
        self.b_dns_test = g["RButton"](row, "Run DNS speed test", self.run_dns_test, kind="primary")
        self.b_dns_test.pack(side="left")
        self.dns_progress = tk.Label(row, text="", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9))
        self.dns_progress.pack(side="left", padx=10)
        self.dns_table = tk.Frame(b, bg=b.cget("bg"))
        self.dns_table.pack(fill="x", padx=16)
        self.dns_method = label(b, "", g, 9, g["MUTED"], pady=(4, 12))

        # ---- ping test
        b = card(body, g, "Ping test")
        row = button_row(b, g)
        tk.Label(row, text="Target:", bg=row.cget("bg"), fg=g["FG"], font=(g["UI"], 10)).pack(side="left",
                                                                                              padx=(0, 8))
        self.ping_target = g["RSelect"](row, list(nettest.PING_TARGETS), width=140)
        self.ping_target.pack(side="left")
        self.b_ping = g["RButton"](row, "Run ping test", self.run_ping, kind="primary")
        self.b_ping.pack(side="left", padx=8)
        self.ping_progress = tk.Label(row, text="", bg=row.cget("bg"), fg=g["MUTED"], font=(g["UI"], 9))
        self.ping_progress.pack(side="left", padx=4)
        self.ping_result = label(b, "", g, 22, bold=True)
        self.ping_details = label(b, "", g, 10, pady=(0, 12))

        # ---- live traffic
        b = card(body, g, "Live traffic")
        self.traffic = label(b, "Measuring…", g, 10, pady=(0, 12))

    @staticmethod
    def _placeholder(entry, var, text):
        """Grey hint text inside an empty entry (not part of the value)."""
        hint = tk.Label(entry.master, text=text, bg=entry.cget("bg"), fg="#6c6d74", font=entry.cget("font"))

        def update(*_):
            if var.get() or entry.focus_get() is entry:
                hint.place_forget()
            else:
                hint.place(in_=entry, x=1, rely=0.5, anchor="w")
        var.trace_add("write", update)
        entry.bind("<FocusIn>", update, add="+")
        entry.bind("<FocusOut>", update, add="+")
        hint.bind("<Button-1>", lambda e: entry.focus_set())
        entry.after_idle(update)

    def _set_buttons(self, flag):
        for btn in self.buttons:
            btn.set_enabled(flag)

    def _adapter_name(self):
        v = self.adapter.get()
        return "" if v == NO_ADAPTER else v

    # ------------------------------------------------------------ show / hide
    def on_shown(self):
        self._shown = True
        if not self._loaded:
            self._loaded = True
            self.load_adapters()
        self._net_prev = None
        self._tick_traffic()

    def on_hidden(self):
        self._shown = False

    def _tick_traffic(self):
        if not self._shown:
            return
        try:
            import psutil
            c = psutil.net_io_counters()
            now = (time.monotonic(), c.bytes_recv, c.bytes_sent)
        except Exception:
            self.traffic.configure(text="Download Unavailable     Upload Unavailable")
            return
        if self._net_prev:
            dt = max(1e-6, now[0] - self._net_prev[0])
            down = max(0, now[1] - self._net_prev[1]) / dt
            up = max(0, now[2] - self._net_prev[2]) / dt
            self.traffic.configure(text=f"Download {fmt_rate(down)}     Upload {fmt_rate(up)}")
        self._net_prev = now
        self.hub.after(1000, self._tick_traffic)

    # ------------------------------------------------------------ DNS
    def load_adapters(self):
        self.current.configure(text="Current DNS: loading adapters…")

        def done(names):
            names = names if isinstance(names, list) else []
            self.adapter.values = names or [NO_ADAPTER]
            self.adapter.set(self.adapter.values[0])
            self._set_buttons(bool(names))
            if names:
                self.refresh_dns()
            else:
                self.current.configure(text="No connected network adapters found.")

        run_bg(self.hub, W.get_network_adapters, done)

    def refresh_dns(self):
        name = self._adapter_name()
        if not name:
            return
        self.current.configure(text="Current DNS: checking…")

        def done(servers):
            servers = servers if isinstance(servers, list) else []
            self._current_servers = servers
            known = next((n for n, a, b in DNS_PROVIDERS if servers[:1] == [a]), None)
            if servers:
                self.current.configure(text=f"Current DNS: {', '.join(servers)}" + (f"  ({known})" if known else ""))
            else:
                self.current.configure(text="Current DNS: automatic (from your router / ISP)")

        run_bg(self.hub, W.get_dns_servers, done, name)

    def _after_change(self, action):
        adapter = self._adapter_name()

        def done(result):
            if isinstance(result, Exception):
                result = (False, str(result))
            ok, msg = result
            self._set_buttons(True)
            self.hub.log_action(f"DNS ({adapter})", action, "Success" if ok else "Failed", "" if ok else msg)
            if not ok:
                info(self.hub, "DNS", msg, True)
            self.refresh_dns()
        return done

    def apply(self, provider, a, b):
        self._set_buttons(False)
        run_bg(self.hub, W.apply_dns, self._after_change(f"{provider} {a}/{b}"), self._adapter_name(), a, b)

    def _custom_servers(self):
        return [v.get().strip() for v in (self.custom1, self.custom2) if v.get().strip()]

    def apply_custom(self):
        servers = self._custom_servers()
        bad = [s for s in servers if not valid_ip(s)]
        if not servers or bad:
            info(self.hub, "DNS", f"Enter valid IP addresses. Not valid: {', '.join(bad) or '(empty)'}", True)
            return
        self._set_buttons(False)
        run_bg(self.hub, W.apply_dns, self._after_change(f"Custom {' / '.join(servers)}"), self._adapter_name(),
               *servers)

    def restore_previous(self):
        self._set_buttons(False)
        run_bg(self.hub, W.restore_previous_dns, self._after_change("Restore previous"), self._adapter_name())

    def reset(self):
        self._set_buttons(False)
        run_bg(self.hub, W.restore_dhcp_dns, self._after_change("Automatic"), self._adapter_name())

    # ------------------------------------------------------------ speed tests
    def _poll(self, attr, lbl):
        """Shows progress written by a worker thread (only plain numbers cross threads)."""
        d, t = getattr(self, attr, (0, 0))
        if t:
            lbl.configure(text=f"{d} / {t}")
        if getattr(self, attr + "_running", False):
            self.hub.after(250, lambda: self._poll(attr, lbl))

    def run_dns_test(self):
        servers = list(nettest.PRESET_SERVERS)
        for ip in self._current_servers:
            if ip not in [s[1] for s in servers]:
                servers.append(("Your current DNS", ip))
        for ip in self._custom_servers():
            if valid_ip(ip) and ip not in [s[1] for s in servers]:
                servers.append(("Custom", ip))
        self.b_dns_test.set_enabled(False)
        self._dns_prog, self._dns_prog_running = (0, 0), True
        self._poll("_dns_prog", self.dns_progress)
        rounds = 2
        run_bg(self.hub, nettest.dns_speed_test, lambda r: self._dns_done(r, rounds), servers, rounds,
               lambda d, t: setattr(self, "_dns_prog", (d, t)))

    def _dns_done(self, results, rounds):
        g = self.g
        self._dns_prog_running = False
        self.b_dns_test.set_enabled(True)
        if not isinstance(results, list):
            self.dns_progress.configure(text=f"Test failed: {results}")
            return
        self.dns_progress.configure(text="Done.")

        def ms(v):
            return "—" if v is None else f"{v:.1f} ms"

        results.sort(key=lambda r: (r["uncached"]["avg"] is None, r["uncached"]["avg"] or 0))
        for w in self.dns_table.winfo_children():
            w.destroy()
        heads = ["Server", "Popular sites (avg)", "Uncached (avg)", "Best", "Worst", "Failed"]
        bg = self.dns_table.cget("bg")
        for c, h in enumerate(heads):
            tk.Label(self.dns_table, text=h, bg=bg, fg=g["MUTED"], font=(g["UI"], 9, "bold"), anchor="w").grid(
                row=0, column=c, sticky="w", padx=(0, 18), pady=(4, 2))
        for i, r in enumerate(results, start=1):
            p, u = r["popular"], r["uncached"]
            best = min([x for x in (p["best"], u["best"]) if x is not None], default=None)
            worst = max([x for x in (p["worst"], u["worst"]) if x is not None], default=None)
            vals = [f"{r['label']} ({r['ip']})", ms(p["avg"]), ms(u["avg"]), ms(best), ms(worst),
                    f"{p['failed'] + u['failed']} of {p['count'] + u['count']}"]
            for c, v in enumerate(vals):
                tk.Label(self.dns_table, text=v, bg=bg, fg=g["FG"], font=(g["UI"], 10), anchor="w").grid(
                    row=i, column=c, sticky="w", padx=(0, 18), pady=1)
        self.dns_method.configure(
            text=nettest.DNS_METHOD.format(n=rounds * (len(nettest.POPULAR) + len(nettest.UNCACHED_PARENTS)))
            + " Some routers or internet providers redirect all DNS traffic to their own server, which can make "
              "every result look similar.")
        self.hub.log_action("DNS speed test", f"{len(results)} servers", "Success")

    def run_ping(self):
        target = self.ping_target.get()
        self.b_ping.set_enabled(False)
        self._ping_prog, self._ping_prog_running = (0, 0), True
        self._poll("_ping_prog", self.ping_progress)
        run_bg(self.hub, nettest.ping_test, self._ping_done, target, 20, 0.25, 1000,
               lambda d, t: setattr(self, "_ping_prog", (d, t)))

    def _ping_done(self, r):
        self._ping_prog_running = False
        self.b_ping.set_enabled(True)
        if not isinstance(r, dict) or "error" in r:
            self.ping_progress.configure(
                text=r.get("error", "Ping test failed.") if isinstance(r, dict) else f"Ping test failed: {r}")
            return
        self.ping_progress.configure(text="Done.")
        self.ping_result.configure(text="No replies" if r["avg"] is None else f"{r['avg']:.0f} ms")

        def ms(v):
            return "—" if v is None else f"{v:.0f} ms"

        self.ping_details.configure(
            text=f"Best {ms(r['best'])}   Worst {ms(r['worst'])}   Jitter {ms(r['jitter'])}   "
                 f"Packet loss {r['loss_pct']:.0f}%\n"
                 + nettest.PING_METHOD.format(count=r["count"], target=r["target"], interval=0.25))
        self.hub.log_action("Ping test", r["target"], "Success")
