# ui/pages/network.py
"""DNS switcher with the adapter's real current DNS, plus live network speed."""

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLineEdit, QMessageBox, QPushButton,
                               QTableWidget, QTableWidgetItem)

from core import nettest

from core.optimizer import WindowsOptimizer as W, valid_ip
from ui.widgets.common import Card, Page, fmt_rate, label, set_role

DNS_PROVIDERS = [
    ("Cloudflare", "1.1.1.1", "1.0.0.1"),
    ("Google", "8.8.8.8", "8.8.4.4"),
    ("Quad9", "9.9.9.9", "149.112.112.112"),
]


class NetworkPage(Page):
    title = "Network"
    subtitle = ("Change which DNS servers your PC uses to look up websites and game servers. "
                "A different DNS doesn't raise your in-game ping, but it can make lookups faster or more reliable.")

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._loaded = False

        card = Card("DNS")
        row = QHBoxLayout()
        row.addWidget(label("Adapter:", "muted"))
        self.adapter = QComboBox()
        self.adapter.setMinimumWidth(240)
        self.adapter.currentTextChanged.connect(self.refresh_dns)
        row.addWidget(self.adapter)
        b_reload = QPushButton("Reload adapters")
        b_reload.clicked.connect(self.load_adapters)
        row.addWidget(b_reload)
        row.addStretch()
        card.body.addLayout(row)

        self.current = label("Current DNS: checking…", "cardLine")
        card.body.addWidget(self.current)

        btns = QHBoxLayout()
        self.buttons = []
        for name, a, b in DNS_PROVIDERS:
            btn = QPushButton(f"{name} ({a})")
            btn.clicked.connect(lambda _=False, n=name, x=a, y=b: self.apply(n, x, y))
            btns.addWidget(btn)
            self.buttons.append(btn)
        auto = QPushButton("Automatic (from router)")
        auto.clicked.connect(self.reset)
        btns.addWidget(auto)
        self.buttons.append(auto)
        self.btn_restore = QPushButton("Restore previous")
        self.btn_restore.setToolTip("Puts back the DNS this adapter had before RYTWEAKS first changed it.")
        self.btn_restore.clicked.connect(self.restore_previous)
        btns.addWidget(self.btn_restore)
        self.buttons.append(self.btn_restore)
        btns.addStretch()
        card.body.addLayout(btns)

        custom = QHBoxLayout()
        custom.addWidget(label("Custom:", "muted"))
        self.custom1 = QLineEdit()
        self.custom1.setPlaceholderText("Primary (IPv4 or IPv6)")
        self.custom2 = QLineEdit()
        self.custom2.setPlaceholderText("Secondary (optional)")
        b_custom = QPushButton("Apply custom")
        b_custom.clicked.connect(self.apply_custom)
        self.buttons.append(b_custom)
        for w in (self.custom1, self.custom2):
            w.setMaximumWidth(220)
            custom.addWidget(w)
        custom.addWidget(b_custom)
        custom.addStretch()
        card.body.addLayout(custom)
        card.body.addWidget(label("Changing DNS needs administrator rights. RYTWEAKS saves your previous DNS "
                                  "the first time it changes an adapter.", "muted", wrap=True))
        self.content.addWidget(card)

        # ---- DNS speed test
        speed = Card("DNS speed test")
        speed.body.addWidget(label("Tests Cloudflare, Google, Quad9, your current DNS and any custom servers "
                                   "typed above. RYTWEAKS never changes your DNS from these results: you pick "
                                   "and apply.", "muted", wrap=True))
        row = QHBoxLayout()
        self.b_dns_test = set_role(QPushButton("Run DNS speed test"), "primary")
        self.b_dns_test.clicked.connect(self.run_dns_test)
        row.addWidget(self.b_dns_test)
        self.dns_progress = label("", "muted")
        row.addWidget(self.dns_progress)
        row.addStretch()
        speed.body.addLayout(row)
        self.dns_table = QTableWidget(0, 6)
        self.dns_table.setHorizontalHeaderLabels(["Server", "Popular sites (avg)", "Uncached (avg)",
                                                  "Best", "Worst", "Failed"])
        self.dns_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.dns_table.verticalHeader().setVisible(False)
        self.dns_table.setMinimumHeight(180)
        self.dns_table.hide()
        speed.body.addWidget(self.dns_table)
        self.dns_method = label("", "muted", wrap=True)
        speed.body.addWidget(self.dns_method)
        self.content.addWidget(speed)

        # ---- ping test
        ping = Card("Ping test")
        row = QHBoxLayout()
        self.ping_target = QComboBox()
        self.ping_target.addItems(nettest.PING_TARGETS)
        self.b_ping = set_role(QPushButton("Run ping test"), "primary")
        self.b_ping.clicked.connect(self.run_ping)
        row.addWidget(label("Target:", "cardLine"))
        row.addWidget(self.ping_target)
        row.addWidget(self.b_ping)
        self.ping_progress = label("", "muted")
        row.addWidget(self.ping_progress)
        row.addStretch()
        ping.body.addLayout(row)
        self.ping_result = label("", "bigValue")
        self.ping_result.hide()
        ping.body.addWidget(self.ping_result)
        self.ping_details = label("", "cardLine", wrap=True)
        ping.body.addWidget(self.ping_details)
        self.content.addWidget(ping)

        live = Card("Live traffic")
        self.traffic = label("Measuring…", "cardLine")
        live.body.addWidget(self.traffic)
        self.content.addWidget(live)
        self.finish()

    def _run(self, fn, *args, on_done=None):
        self.run_task(fn, *args, on_done=on_done)

    def on_shown(self):
        if not self._loaded:
            self._loaded = True
            self.load_adapters()

    def load_adapters(self):
        self.current.setText("Current DNS: loading adapters…")

        def done(names):
            self.adapter.blockSignals(True)
            self.adapter.clear()
            self.adapter.addItems(names if isinstance(names, list) else [])
            self.adapter.blockSignals(False)
            if self.adapter.count():
                self.refresh_dns()
            else:
                self.current.setText("No connected network adapters found.")
            for b in self.buttons:
                b.setEnabled(self.adapter.count() > 0)

        self._run(W.get_network_adapters, on_done=done)

    def refresh_dns(self):
        name = self.adapter.currentText()
        if not name:
            return
        self.current.setText("Current DNS: checking…")

        def done(servers):
            servers = servers if isinstance(servers, list) else []
            self.current.setProperty("servers", servers)
            known = next((n for n, a, b in DNS_PROVIDERS if servers[:1] == [a]), None)
            if servers:
                self.current.setText(f"Current DNS: {', '.join(servers)}" + (f"  ({known})" if known else ""))
            else:
                self.current.setText("Current DNS: automatic (from your router / ISP)")

        self._run(W.get_dns_servers, name, on_done=done)

    def _after_change(self, action):
        def done(result):
            ok, msg = result
            for b in self.buttons:
                b.setEnabled(True)
            self.ctx.log_action(f"DNS ({self.adapter.currentText()})", action, "Success" if ok else "Failed",
                                "" if ok else msg)
            if not ok:
                QMessageBox.warning(self, "DNS", msg)
            self.refresh_dns()
        return done

    def apply(self, provider, a, b):
        for btn in self.buttons:
            btn.setEnabled(False)
        self._run(W.apply_dns, self.adapter.currentText(), a, b, on_done=self._after_change(f"{provider} {a}/{b}"))

    def apply_custom(self):
        servers = [w.text().strip() for w in (self.custom1, self.custom2) if w.text().strip()]
        bad = [s for s in servers if not valid_ip(s)]
        if not servers or bad:
            QMessageBox.warning(self, "DNS", f"Enter valid IP addresses. Not valid: {', '.join(bad) or '(empty)'}")
            return
        for btn in self.buttons:
            btn.setEnabled(False)
        self._run(W.apply_dns, self.adapter.currentText(), *servers,
                  on_done=self._after_change(f"Custom {' / '.join(servers)}"))

    def restore_previous(self):
        for btn in self.buttons:
            btn.setEnabled(False)
        self._run(W.restore_previous_dns, self.adapter.currentText(), on_done=self._after_change("Restore previous"))

    def reset(self):
        for btn in self.buttons:
            btn.setEnabled(False)
        self._run(W.restore_dhcp_dns, self.adapter.currentText(), on_done=self._after_change("Automatic"))

    # ------------------------------------------------------------ speed tests
    def _poll(self, attr, lbl):
        """Show progress written by a worker thread (only plain numbers cross threads)."""
        done, total = getattr(self, attr, (0, 0))
        if total:
            lbl.setText(f"{done} / {total}")
        if getattr(self, attr + "_running", False):
            QTimer.singleShot(250, lambda: self._poll(attr, lbl))

    def run_dns_test(self):
        servers = list(nettest.PRESET_SERVERS)
        current = self.current.property("servers") or []
        for ip in current:
            if ip not in [s[1] for s in servers]:
                servers.append(("Your current DNS", ip))
        for w in (self.custom1, self.custom2):
            ip = w.text().strip()
            if ip and valid_ip(ip) and ip not in [s[1] for s in servers]:
                servers.append(("Custom", ip))
        self.b_dns_test.setEnabled(False)
        self._dns_prog, self._dns_prog_running = (0, 0), True
        self._poll("_dns_prog", self.dns_progress)
        rounds = 2
        self.run_task(nettest.dns_speed_test, servers, rounds,
                      lambda d, t: setattr(self, "_dns_prog", (d, t)),
                      on_done=lambda r: self._dns_done(r, rounds))

    def _dns_done(self, results, rounds):
        self._dns_prog_running = False
        self.b_dns_test.setEnabled(True)
        if not isinstance(results, list):
            self.dns_progress.setText(f"Test failed: {results[1] if isinstance(results, tuple) else results}")
            return
        self.dns_progress.setText("Done.")

        def ms(v):
            return "—" if v is None else f"{v:.1f} ms"

        # fastest first by uncached average (servers that failed everything go last)
        results.sort(key=lambda r: (r["uncached"]["avg"] is None, r["uncached"]["avg"] or 0))
        self.dns_table.setRowCount(0)
        for r in results:
            row = self.dns_table.rowCount()
            self.dns_table.insertRow(row)
            p, u = r["popular"], r["uncached"]
            best = min([x for x in (p["best"], u["best"]) if x is not None], default=None)
            worst = max([x for x in (p["worst"], u["worst"]) if x is not None], default=None)
            vals = [f"{r['label']} ({r['ip']})", ms(p["avg"]), ms(u["avg"]), ms(best), ms(worst),
                    f"{p['failed'] + u['failed']} of {p['count'] + u['count']}"]
            for c, v in enumerate(vals):
                self.dns_table.setItem(row, c, QTableWidgetItem(v))
        self.dns_table.show()
        self.dns_method.setText(nettest.DNS_METHOD.format(n=rounds * (len(nettest.POPULAR) +
                                                                      len(nettest.UNCACHED_PARENTS)))
                                + " Some routers or internet providers redirect all DNS traffic to their own "
                                "server, which can make every result look similar.")
        self.ctx.log_action("DNS speed test", f"{len(results)} servers", "Success")

    def run_ping(self):
        target = self.ping_target.currentText()
        self.b_ping.setEnabled(False)
        self._ping_prog, self._ping_prog_running = (0, 0), True
        self._poll("_ping_prog", self.ping_progress)
        self.run_task(nettest.ping_test, target, 20, 0.25, 1000,
                      lambda d, t: setattr(self, "_ping_prog", (d, t)), on_done=self._ping_done)

    def _ping_done(self, r):
        self._ping_prog_running = False
        self.b_ping.setEnabled(True)
        if not isinstance(r, dict) or "error" in r:
            self.ping_progress.setText(r.get("error", "Ping test failed.") if isinstance(r, dict) else "Ping test failed.")
            return
        self.ping_progress.setText("Done.")
        if r["avg"] is None:
            self.ping_result.setText("No replies")
        else:
            self.ping_result.setText(f"{r['avg']:.0f} ms")
        self.ping_result.show()

        def ms(v):
            return "—" if v is None else f"{v:.0f} ms"

        self.ping_details.setText(
            f"Best {ms(r['best'])}   Worst {ms(r['worst'])}   Jitter {ms(r['jitter'])}   "
            f"Packet loss {r['loss_pct']:.0f}%\n"
            + nettest.PING_METHOD.format(count=r["count"], target=r["target"], interval=0.25))
        self.ctx.log_action("Ping test", r["target"], "Success")

    def on_telemetry(self, s):
        io = s["io"]
        self.traffic.setText(f"Download {fmt_rate(io['net_down_bps'])}     Upload {fmt_rate(io['net_up_bps'])}")
