# ui/pages/network.py
"""DNS switcher with the adapter's real current DNS, plus live network speed."""

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLineEdit, QMessageBox, QPushButton

from core.optimizer import WindowsOptimizer as W, valid_ip
from ui.widgets.common import Card, Page, fmt_rate, label

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

    def on_telemetry(self, s):
        io = s["io"]
        self.traffic.setText(f"Download {fmt_rate(io['net_down_bps'])}     Upload {fmt_rate(io['net_up_bps'])}")
