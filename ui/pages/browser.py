# ui/pages/browser.py
"""Browser (v1.5): RYTWEAKS's own browser frame around Microsoft's Edge engine (WebView2).

Tabs, private tabs, address bar that also searches (Google, DuckDuckGo, Brave Search, Bing,
Startpage or your own), bookmarks, history and downloads. The engine starts the first time this page
is opened, never at app start. Bookmarks/history: %APPDATA%\\RYTWEAKS\\browser.json. Cookies/cache:
%LOCALAPPDATA%\\RYTWEAKS\\Browser. Private tabs keep nothing after they close.
"""

import os
import subprocess
import sys
import time

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QInputDialog, QLineEdit, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QPushButton, QScrollArea,
                               QStackedWidget, QTabBar, QToolButton, QVBoxLayout, QWidget)

from core import browser_data as bd
from ui.widgets.common import Page, label, set_role

LOAD_ERRORS = {
    "HostNameNotResolved": "Couldn't find that site. Check the address and your internet connection.",
    "ConnectionAborted": "The connection was interrupted.",
    "ConnectionReset": "The connection was reset.",
    "Disconnected": "You're offline. Check your internet connection.",
    "CannotConnect": "Couldn't connect to the site.",
    "Timeout": "The site took too long to answer.",
    "CertificateCommonNameIsIncorrect": "The site's security certificate doesn't match its address.",
    "CertificateExpired": "The site's security certificate has expired.",
    "CertificateIsInvalid": "The site's security certificate isn't valid.",
    "ServerUnreachable": "The site's server can't be reached.",
}


def human_size(n):
    if n is None:
        return "?"
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class DownloadItem:
    """One download, updated from its WebView2 DownloadOperation."""

    def __init__(self, op, path, on_change):
        self.op, self.path, self.name = op, path, os.path.basename(path)
        self.state = "Downloading"
        self.received, self.total = 0, None
        self.started = time.time()
        self._on_change = on_change
        self._handlers = []
        if op is not None:
            for ev in ("BytesReceivedChanged", "StateChanged"):
                h = self._wrap(self._update)
                getattr(op, ev).__iadd__(h)
                self._handlers.append((ev, h))
            self._update()

    @staticmethod
    def _wrap(fn):
        def w(*_a):
            try:
                fn()
            except Exception:
                pass
        return w

    def _update(self):
        op = self.op
        try:
            self.received = int(op.BytesReceived)
            t = op.TotalBytesToReceive
            self.total = int(t) if t is not None and int(t) > 0 else None
            st = str(op.State)
            if st == "Completed":
                self.state = "Done"
            elif st == "Interrupted":
                reason = str(op.InterruptReason)
                self.state = "Cancelled" if reason == "UserCanceled" else f"Failed ({reason})"
            else:
                self.state = "Downloading"
        except Exception:
            pass
        self._on_change(self)

    def active(self):
        return self.state == "Downloading"

    def text(self):
        if self.state == "Downloading":
            size = f"{human_size(self.received)} of {human_size(self.total)}" if self.total else human_size(self.received)
            pct = f" · {self.received * 100 // self.total}%" if self.total else ""
            return f"{self.name}\nDownloading · {size}{pct}"
        if self.state == "Done":
            return f"{self.name}\nDone · {human_size(self.received)}"
        return f"{self.name}\n{self.state}"

    def cancel(self):
        try:
            if self.active():
                self.op.Cancel()
        except Exception:
            pass


class BrowserPage(Page):
    title = ""
    subtitle = ""
    no_fade = True                       # opacity effects don't work on native child windows

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(0)
        scroll = self.findChild(QScrollArea)
        if scroll:
            scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cfg = bd.clean_settings(getattr(ctx, "settings", {}))
        self.data = bd.BrowserData()
        self.engine = None
        self.env_holder = None
        self.views = []                  # EdgeView per tab, in tab order
        self.downloads = []
        self.panel_mode = None
        self._started = False

        root = QWidget()
        root.setObjectName("browserRoot")
        lay = QVBoxLayout(root)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ---- tab strip
        strip = QWidget()
        strip.setObjectName("browserStrip")
        sl = QHBoxLayout(strip)
        sl.setContentsMargins(10, 8, 10, 0)
        sl.setSpacing(6)
        self.tabbar = QTabBar()
        self.tabbar.setObjectName("browserTabs")
        self.tabbar.setTabsClosable(False)      # own themed close buttons (see _add_close)
        self.tabbar.setDrawBase(False)
        self.tabbar.setMovable(True)
        self.tabbar.setExpanding(False)
        self.tabbar.setElideMode(Qt.ElideRight)
        self.tabbar.setDocumentMode(True)
        self.tabbar.setUsesScrollButtons(True)
        self.tabbar.currentChanged.connect(self._tab_changed)
        self.tabbar.tabMoved.connect(self._tab_moved)
        sl.addWidget(self.tabbar, 1)
        self.b_new = self._tool("+", "New tab (Ctrl+T)", lambda: self.new_tab())
        self.b_private = self._tool("Private", "New private tab (Ctrl+Shift+N): nothing is saved after it closes",
                                    lambda: self.new_tab(private=True))
        sl.addWidget(self.b_new)
        sl.addWidget(self.b_private)
        lay.addWidget(strip)

        # ---- navigation row
        nav = QWidget()
        nav.setObjectName("browserNav")
        nl = QHBoxLayout(nav)
        nl.setContentsMargins(10, 8, 10, 8)
        nl.setSpacing(6)
        self.b_back = self._tool("←", "Back", lambda: self._cur("back"))
        self.b_fwd = self._tool("→", "Forward", lambda: self._cur("forward"))
        self.b_reload = self._tool("⟳", "Reload (F5)", self._reload_or_stop)
        self.b_home = self._tool("⌂", "Home: your search engine's start page", self.go_home)
        for b in (self.b_back, self.b_fwd, self.b_reload, self.b_home):
            nl.addWidget(b)
        self.address = QLineEdit()
        self.address.setObjectName("browserAddress")
        self.address.setClearButtonEnabled(True)
        self.address.returnPressed.connect(self._go_address)
        nl.addWidget(self.address, 1)
        self.b_star = self._tool("☆", "Bookmark this page (Ctrl+D)", self.toggle_bookmark)
        self.b_bookmarks = self._tool("Bookmarks", "Bookmarks", lambda: self.show_panel("bookmarks"))
        self.b_history = self._tool("History", "History (Ctrl+H)", lambda: self.show_panel("history"))
        self.b_downloads = self._tool("Downloads", "Downloads (Ctrl+J)", lambda: self.show_panel("downloads"))
        self.b_menu = self._tool("•••", "More", None)
        self.b_menu.setPopupMode(QToolButton.InstantPopup)
        self.b_menu.setMenu(self._build_menu())
        for b in (self.b_star, self.b_bookmarks, self.b_history, self.b_downloads, self.b_menu):
            nl.addWidget(b)
        lay.addWidget(nav)

        # ---- message bar (page load errors, engine notes)
        self.msg = label("", "browserMsg", wrap=True)
        self.msg.setVisible(False)
        self.msg.setContentsMargins(14, 6, 14, 6)
        lay.addWidget(self.msg)

        # ---- pages + side panel
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        self.stack = QStackedWidget()
        self.unavailable = self._build_unavailable()
        self.stack.addWidget(self.unavailable)
        body.addWidget(self.stack, 1)
        self.panel = self._build_panel()
        self.panel.setVisible(False)
        body.addWidget(self.panel)
        lay.addLayout(body, 1)

        self.content.addWidget(root, 1)
        self._chrome = (strip, nav)
        self._shortcuts()
        self._update_placeholder()
        self._update_nav()
        if self.data.load_note:
            self._show_msg(self.data.load_note)

    # ------------------------------------------------------------ building blocks
    def _tool(self, text, tip, fn):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setObjectName("browserTool")
        b.setCursor(Qt.PointingHandCursor)
        if fn:
            b.clicked.connect(fn)
        return b

    def _build_unavailable(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(40, 40, 40, 40)
        v.addStretch(1)
        self.un_title = label("Starting the browser…", "pageTitle")
        self.un_text = label("RYTWEAKS uses Microsoft's Edge engine, which is part of Windows 11.", "muted", wrap=True)
        self.un_retry = set_role(QPushButton("Try again"), "primary")
        self.un_retry.clicked.connect(self._retry)
        self.un_retry.setVisible(False)
        for x in (self.un_title, self.un_text):
            x.setAlignment(Qt.AlignCenter)
            v.addWidget(x)
        v.addWidget(self.un_retry, 0, Qt.AlignCenter)
        v.addStretch(2)
        return w

    def _build_panel(self):
        p = QFrame()
        p.setObjectName("browserPanel")
        p.setFixedWidth(320)
        v = QVBoxLayout(p)
        v.setContentsMargins(14, 12, 14, 12)
        v.setSpacing(8)
        head = QHBoxLayout()
        self.panel_title = label("", "sectionTitle")
        close = self._tool("✕", "Close", self.hide_panel)
        head.addWidget(self.panel_title, 1)
        head.addWidget(close)
        v.addLayout(head)
        self.panel_search = QLineEdit()
        self.panel_search.setClearButtonEnabled(True)
        self.panel_search.textChanged.connect(lambda _t: self._fill_panel())
        v.addWidget(self.panel_search)
        self.panel_list = QListWidget()
        self.panel_list.setObjectName("browserList")
        self.panel_list.setWordWrap(True)
        self.panel_list.itemDoubleClicked.connect(lambda _i: self._panel_open(False))
        v.addWidget(self.panel_list, 1)
        self.panel_note = label("", "muted", wrap=True)
        v.addWidget(self.panel_note)
        self.panel_btns = QHBoxLayout()
        self.panel_btns.setSpacing(6)
        v.addLayout(self.panel_btns)
        self.panel_btns2 = QHBoxLayout()
        self.panel_btns2.setSpacing(6)
        v.addLayout(self.panel_btns2)
        return p

    def _build_menu(self):
        m = QMenu(self)
        m.addAction("New tab\tCtrl+T", lambda: self.new_tab())
        m.addAction("New private tab\tCtrl+Shift+N", lambda: self.new_tab(private=True))
        m.addSeparator()
        m.addAction("Bookmarks", lambda: self.show_panel("bookmarks"))
        m.addAction("History\tCtrl+H", lambda: self.show_panel("history"))
        m.addAction("Downloads\tCtrl+J", lambda: self.show_panel("downloads"))
        m.addSeparator()
        se = m.addMenu("Search engine")
        self.engine_group = QActionGroup(self)
        self.engine_group.setExclusive(True)
        for name in list(bd.SEARCH_ENGINES) + [bd.CUSTOM]:
            a = QAction(name if name != bd.CUSTOM else "Custom…", self, checkable=True)
            a.setData(name)
            a.setChecked(name == self.cfg["browser_search_engine"])
            a.triggered.connect(lambda _c=False, n=name: self.set_search_engine(n))
            self.engine_group.addAction(a)
            se.addAction(a)
        m.addAction("Download folder…", self.choose_download_dir)
        self.ask_action = QAction("Ask where to save each download", self, checkable=True)
        self.ask_action.setChecked(self.cfg["browser_ask_download"])
        self.ask_action.toggled.connect(lambda on: self._set("browser_ask_download", bool(on)))
        m.addAction(self.ask_action)
        m.addSeparator()
        m.addAction("Clear history…", self.clear_history)
        m.addAction("Clear cookies and site data…", self.clear_site_data)
        m.addSeparator()
        m.addAction("About the browser engine", self.about_engine)
        return m

    def _shortcuts(self):
        for keys, fn in (("Ctrl+T", lambda: self.new_tab()), ("Ctrl+W", lambda: self.close_tab(self.tabbar.currentIndex())),
                         ("Ctrl+L", self.focus_address), ("Ctrl+D", self.toggle_bookmark),
                         ("Ctrl+Shift+N", lambda: self.new_tab(private=True)), ("Ctrl+H", lambda: self.show_panel("history")),
                         ("Ctrl+J", lambda: self.show_panel("downloads")), ("F5", self._reload_or_stop)):
            s = QShortcut(QKeySequence(keys), self)
            s.setContext(Qt.WidgetWithChildrenShortcut)
            s.activated.connect(fn)

    # ------------------------------------------------------------ engine start
    def on_shown(self):
        if not self._started:
            self._started = True
            QTimer.singleShot(0, self._start_engine)
        elif self.current():
            self.current().focus_page()

    def _start_engine(self):
        from core import browser_engine as be
        try:
            self.engine = be.load()
            from ui.widgets.edge_view import EnvironmentHolder
            self.env_holder = EnvironmentHolder(self.engine, be.user_data_dir())
        except be.EngineUnavailable as e:
            return self._engine_failed(str(e))
        except Exception as e:
            return self._engine_failed(f"{type(e).__name__}: {e}")
        self.new_tab()

    def _engine_failed(self, msg):
        self.un_title.setText("The browser can't start")
        self.un_text.setText(msg)
        self.un_retry.setVisible(True)
        self.stack.setCurrentWidget(self.unavailable)
        try:
            self.ctx.log_action("Browser", "Start the Edge engine", "Failed", msg)
        except Exception:
            pass

    def _retry(self):
        from core import browser_engine as be
        be._engine = None
        self.un_title.setText("Starting the browser…")
        self.un_retry.setVisible(False)
        self._start_engine()

    # ------------------------------------------------------------ tabs
    def current(self):
        i = self.tabbar.currentIndex()
        return self.views[i] if 0 <= i < len(self.views) else None

    def new_tab(self, url=None, private=False, adopt=None, activate=True):
        if self.engine is None:
            return None
        from ui.widgets.edge_view import EdgeView
        v = EdgeView(self.engine, self.env_holder, private=private)
        self.stack.addWidget(v)
        self.views.append(v)
        i = self.tabbar.addTab("Private · New tab" if private else "New tab")
        self._add_close(i, v)
        self.tabbar.setTabToolTip(i, "Private tab: no history, cookies or cache are kept" if private else "")
        v.titleChanged.connect(lambda t, v=v: self._view_title(v, t))
        v.urlChanged.connect(lambda u, v=v: self._view_url(v, u))
        v.loadingChanged.connect(lambda _l, v=v: self._update_nav() if v is self.current() else None)
        v.navStateChanged.connect(lambda v=v: self._update_nav() if v is self.current() else None)
        v.loadError.connect(lambda s, v=v: self._load_error(v, s))
        v.failed.connect(lambda m, v=v: self._view_failed(v, m))
        v.newWindowRequested.connect(self._new_window)
        v.downloadStarting.connect(lambda p, v=v: QTimer.singleShot(0, lambda: self._download(v, p)))
        v.shortcut.connect(self._shortcut)
        v.fullscreenChanged.connect(self._fullscreen)
        if activate:
            self.tabbar.setCurrentIndex(i)
            self.stack.setCurrentWidget(v)
        v.start(url=None if adopt else (url or self.home_url()), adopt=adopt)
        if activate and not url and not adopt:
            QTimer.singleShot(50, self.focus_address)
        return v

    def _add_close(self, i, v):
        b = QToolButton()
        b.setObjectName("browserTabClose")
        b.setText("✕")
        b.setToolTip("Close tab (Ctrl+W)")
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedSize(18, 18)
        b.clicked.connect(lambda _c=False, v=v: self.close_tab(self._index(v)))
        self.tabbar.setTabButton(i, QTabBar.RightSide, b)

    def close_tab(self, i):
        if not (0 <= i < len(self.views)):
            return
        v = self.views.pop(i)
        self.tabbar.removeTab(i)
        v.close_engine()
        self.stack.removeWidget(v)
        v.deleteLater()
        if not self.views and self.engine is not None:
            self.new_tab()
        else:
            self._tab_changed(self.tabbar.currentIndex())

    def _tab_moved(self, frm, to):
        self.views.insert(to, self.views.pop(frm))

    def _tab_changed(self, i):
        v = self.views[i] if 0 <= i < len(self.views) else None
        if v is None:
            return
        self.stack.setCurrentWidget(v)
        self._set_address(v.url)
        self._update_nav()
        self.msg.setVisible(False)
        self._update_placeholder()
        v.focus_page()

    def _view_title(self, v, title):
        i = self._index(v)
        if i < 0:
            return
        text = ("Private · " if v.private else "") + title
        self.tabbar.setTabText(i, text if len(text) <= 28 else text[:27] + "…")
        self.tabbar.setTabToolTip(i, title + ("\nPrivate tab: nothing is kept after it closes" if v.private else ""))
        self.data.update_title(v.url, title, private=v.private)

    def _view_url(self, v, url):
        self.data.add_history(v.title if v.title != "New tab" else "", url, private=v.private)
        if v is self.current():
            self._set_address(url)
            self._update_nav()
            self.msg.setVisible(False)

    def _view_failed(self, v, msg):
        if len(self.views) <= 1:
            self._engine_failed(f"The Edge engine couldn't open a page: {msg}")
        else:
            self._show_msg(f"Couldn't open that tab: {msg}")
            self.close_tab(self._index(v))

    def _index(self, v):
        try:
            return self.views.index(v)
        except ValueError:
            return -1

    def _new_window(self, payload):
        uri, args, deferral, private = payload
        if uri.lower().startswith(("http://", "https://", "about:blank")) or not uri:
            self.new_tab(private=private, adopt=(args, deferral))
        else:
            args.Handled = True          # don't let pages open other kinds of windows
            deferral.Complete()

    def _shortcut(self, action):
        {"new_tab": lambda: self.new_tab(), "close_tab": lambda: self.close_tab(self.tabbar.currentIndex()),
         "address": self.focus_address, "bookmark": self.toggle_bookmark,
         "private_tab": lambda: self.new_tab(private=True), "history": lambda: self.show_panel("history"),
         "downloads": lambda: self.show_panel("downloads")}.get(action, lambda: None)()

    def _fullscreen(self, on):
        for w in self._chrome:
            w.setVisible(not on)
        if on:
            self.panel.setVisible(False)

    # ------------------------------------------------------------ navigation
    def _cur(self, method):
        v = self.current()
        if v:
            getattr(v, method)()

    def _reload_or_stop(self):
        v = self.current()
        if v:
            (v.stop if v.loading else v.reload)()

    def home_url(self):
        return bd.homepage(self.cfg["browser_search_engine"], self.cfg["browser_custom_search"])

    def go_home(self):
        v = self.current()
        if v:
            v.navigate(self.home_url())

    def _go_address(self):
        url = bd.to_url(self.address.text(), self.cfg["browser_search_engine"], self.cfg["browser_custom_search"])
        v = self.current()
        if url and v:
            v.navigate(url)
            v.focus_page()

    def focus_address(self):
        self.address.setFocus()
        self.address.selectAll()

    def _set_address(self, url):
        if not self.address.hasFocus():
            self.address.setText(url or "")
            self.address.setCursorPosition(0)
        self._update_star()

    def _update_placeholder(self):
        eng = self.cfg["browser_search_engine"]
        name = "your search engine" if eng == bd.CUSTOM else eng
        v = self.current()
        self.address.setPlaceholderText(("Private · " if v and v.private else "") +
                                        f"Search with {name} or type an address")

    def _update_nav(self):
        v = self.current()
        self.b_back.setEnabled(bool(v and v.can_back()))
        self.b_fwd.setEnabled(bool(v and v.can_forward()))
        loading = bool(v and v.loading)
        self.b_reload.setText("✕" if loading else "⟳")
        self.b_reload.setToolTip("Stop" if loading else "Reload (F5)")
        for b in (self.b_reload, self.b_home, self.b_star):
            b.setEnabled(v is not None)
        self._update_star()

    def _load_error(self, v, status):
        if v is self.current():
            self._show_msg(LOAD_ERRORS.get(status, f"The page didn't load ({status})."))

    def _show_msg(self, text):
        self.msg.setText(text)
        self.msg.setVisible(bool(text))

    # ------------------------------------------------------------ bookmarks
    def _update_star(self):
        v = self.current()
        on = bool(v and v.url and self.data.is_bookmarked(v.url))
        self.b_star.setText("★" if on else "☆")
        self.b_star.setToolTip("Remove bookmark (Ctrl+D)" if on else "Bookmark this page (Ctrl+D)")

    def toggle_bookmark(self):
        v = self.current()
        if not v or not v.url:
            return
        if self.data.is_bookmarked(v.url):
            self.data.remove_bookmark(v.url)
        elif not self.data.add_bookmark(v.title, v.url):
            self._show_msg("Only web pages (http/https) can be bookmarked.")
        self._update_star()
        if self.panel_mode == "bookmarks":
            self._fill_panel()

    # ------------------------------------------------------------ side panel
    def show_panel(self, mode):
        if self.panel.isVisible() and self.panel_mode == mode:
            return self.hide_panel()
        self.panel_mode = mode
        self.panel_title.setText({"bookmarks": "Bookmarks", "history": "History", "downloads": "Downloads"}[mode])
        self.panel_search.setVisible(mode != "downloads")
        self.panel_search.setPlaceholderText(f"Search {mode}")
        self.panel_search.blockSignals(True)
        self.panel_search.clear()
        self.panel_search.blockSignals(False)
        for lay in (self.panel_btns, self.panel_btns2):
            while lay.count():
                w = lay.takeAt(0).widget()
                if w:
                    w.deleteLater()

        def btn(lay, text, fn):
            b = QPushButton(text)
            b.clicked.connect(fn)
            lay.addWidget(b)

        if mode == "bookmarks":
            btn(self.panel_btns, "Open", lambda: self._panel_open(False))
            btn(self.panel_btns, "New tab", lambda: self._panel_open(True))
            btn(self.panel_btns2, "Rename", self._rename_bookmark)
            btn(self.panel_btns2, "Delete", self._delete_bookmark)
        elif mode == "history":
            btn(self.panel_btns, "Open", lambda: self._panel_open(False))
            btn(self.panel_btns, "New tab", lambda: self._panel_open(True))
            btn(self.panel_btns2, "Clear history…", self.clear_history)
        else:
            btn(self.panel_btns, "Open file", self._open_download)
            btn(self.panel_btns, "Show in folder", self._show_download)
            btn(self.panel_btns2, "Cancel", self._cancel_download)
            btn(self.panel_btns2, "Clear finished", self._clear_downloads)
        self._fill_panel()
        self.panel.setVisible(True)

    def hide_panel(self):
        self.panel.setVisible(False)
        self.panel_mode = None
        v = self.current()
        if v:
            v.focus_page()

    def _fill_panel(self):
        mode = self.panel_mode
        lst = self.panel_list
        lst.clear()
        q = self.panel_search.text().lower().split()
        if mode == "bookmarks":
            rows = [b for b in reversed(self.data.bookmarks)
                    if all(w in (b["title"] + " " + b["url"]).lower() for w in q)]
            for b in rows:
                it = QListWidgetItem(f"{b['title']}\n{b['url']}")
                it.setData(Qt.UserRole, b["url"])
                it.setToolTip(b["url"])
                lst.addItem(it)
            self.panel_note.setText("" if rows else ("No matches." if q else "No bookmarks yet. Press ☆ to save a page."))
        elif mode == "history":
            rows = self.data.search_history(" ".join(q))
            for h in rows:
                when = time.strftime("%b %d, %H:%M", time.localtime(h.get("time", 0)))
                it = QListWidgetItem(f"{h['title']}\n{when} · {h['url']}")
                it.setData(Qt.UserRole, h["url"])
                it.setToolTip(h["url"])
                lst.addItem(it)
            self.panel_note.setText("Private tabs aren't recorded." if rows else
                                    ("No matches." if q else "No history yet. Private tabs are never recorded."))
        elif mode == "downloads":
            for d in reversed(self.downloads):
                it = QListWidgetItem(d.text())
                it.setData(Qt.UserRole, d)
                it.setToolTip(d.path)
                lst.addItem(it)
            folder = self.cfg["browser_download_dir"] or bd.default_download_dir()
            self.panel_note.setText(("" if self.downloads else "No downloads yet. ") + f"Saving to: {folder}")

    def _selected(self):
        it = self.panel_list.currentItem()
        return it.data(Qt.UserRole) if it else None

    def _panel_open(self, new_tab):
        if self.panel_mode == "downloads":
            return self._open_download()
        url = self._selected()
        if not url:
            return
        if new_tab or not self.current():
            self.new_tab(url)
        else:
            self.current().navigate(url)

    def _rename_bookmark(self):
        url = self._selected()
        if not url:
            return
        old = next((b["title"] for b in self.data.bookmarks if b["url"] == url), "")
        title, ok = QInputDialog.getText(self, "Rename bookmark", "Name:", text=old)
        if ok:
            self.data.rename_bookmark(url, title)
            self._fill_panel()

    def _delete_bookmark(self):
        url = self._selected()
        if url and self.data.remove_bookmark(url):
            self._fill_panel()
            self._update_star()

    # ------------------------------------------------------------ downloads
    def _download(self, v, payload):
        args, deferral = payload
        try:
            folder = self.cfg["browser_download_dir"] or bd.default_download_dir()
            from ui.widgets.edge_view import download_target
            path = download_target(args, folder)
            if self.cfg["browser_ask_download"]:
                path, _f = QFileDialog.getSaveFileName(self, "Save download", path)
                if not path:
                    args.Cancel = True
                    return
            args.ResultFilePath = path
            args.Handled = True          # RYTWEAKS shows the download, not Edge's own pop-up
            item = DownloadItem(args.DownloadOperation, path, self._download_changed)
            self.downloads.append(item)
            self._download_changed(item)
            self._show_msg(f"Downloading {item.name} to {os.path.dirname(path)}")
        except Exception as e:
            self._show_msg(f"Couldn't start the download: {e}")
        finally:
            try:
                deferral.Complete()
            except Exception:
                pass

    def _download_changed(self, item):
        active = sum(1 for d in self.downloads if d.active())
        self.b_downloads.setText(f"Downloads ({active})" if active else "Downloads")
        if item.state == "Done" and not getattr(item, "_logged", False):
            item._logged = True
            self._show_msg(f"✔ Downloaded {item.name}")
            self.ctx.log_action("Browser", f"Download {item.name}", "Done")
        elif item.state.startswith("Failed") and not getattr(item, "_logged", False):
            item._logged = True
            self._show_msg(f"✖ {item.name}: {item.state}")
            self.ctx.log_action("Browser", f"Download {item.name}", "Failed", item.state)
        if self.panel_mode == "downloads" and self.panel.isVisible():
            # refresh texts in place (don't rebuild the list, so the selection stays)
            for i in range(self.panel_list.count()):
                it = self.panel_list.item(i)
                if it.data(Qt.UserRole) is item:
                    it.setText(item.text())
                    return
            self._fill_panel()

    def _selected_download(self):
        d = self._selected()
        return d if isinstance(d, DownloadItem) else None

    def _open_download(self):
        d = self._selected_download()
        if d and d.state == "Done" and os.path.exists(d.path):
            os.startfile(d.path)                            # opens with the normal Windows app
        elif d:
            self.panel_note.setText("The file isn't finished (or was moved).")

    def _show_download(self):
        d = self._selected_download()
        if d and os.path.exists(d.path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(d.path)])
        elif d:
            self.panel_note.setText("The file isn't there anymore.")

    def _cancel_download(self):
        d = self._selected_download()
        if d:
            d.cancel()

    def _clear_downloads(self):
        self.downloads = [d for d in self.downloads if d.active()]
        self._fill_panel()

    def choose_download_dir(self):
        start = self.cfg["browser_download_dir"] or bd.default_download_dir()
        d = QFileDialog.getExistingDirectory(self, "Download folder", start)
        if d:
            self._set("browser_download_dir", d)
            self._show_msg(f"Downloads will be saved to {d}")

    # ------------------------------------------------------------ settings and clearing
    def _set(self, key, value):
        self.cfg[key] = value
        try:
            self.ctx.set_setting(key, value)
        except Exception:
            pass

    def set_search_engine(self, name):
        if name == bd.CUSTOM:
            url, ok = QInputDialog.getText(self, "Custom search engine",
                                           "Search URL with {q} where the search words go:",
                                           text=self.cfg["browser_custom_search"] or "https://")
            good, msg = bd.valid_custom_search(url) if ok else (False, "")
            if not good:
                if ok:
                    QMessageBox.warning(self, "Custom search engine", msg)
                for a in self.engine_group.actions():
                    a.setChecked(a.data() == self.cfg["browser_search_engine"])
                return
            self._set("browser_custom_search", url.strip())
        self._set("browser_search_engine", name)
        self._update_placeholder()
        self._show_msg(f"Search engine: {'your custom search' if name == bd.CUSTOM else name}")

    def clear_history(self):
        if QMessageBox.question(self, "Clear history",
                                "Delete your whole browsing history? Bookmarks are kept.") != QMessageBox.Yes:
            return
        n = self.data.clear_history()
        self._show_msg(f"✔ History cleared ({n} entries).")
        self.ctx.log_action("Browser", "Clear history", "Done")
        if self.panel_mode == "history":
            self._fill_panel()

    def clear_site_data(self):
        v = next((x for x in self.views if not x.private and x.wv is not None), None)
        if v is None:
            return self._show_msg("Open a normal (not private) tab first.")
        if QMessageBox.question(self, "Clear cookies and site data",
                                "Sign out of websites and delete cookies, cached files and site data? "
                                "Bookmarks and history are kept.") != QMessageBox.Yes:
            return

        def ok():
            self._show_msg("✔ Cookies, cache and site data cleared.")
            self.ctx.log_action("Browser", "Clear cookies and site data", "Done")

        def fail(m):
            self._show_msg(f"✖ Couldn't clear site data: {m}")
            self.ctx.log_action("Browser", "Clear cookies and site data", "Failed", m)

        v.clear_site_data(ok, fail)

    def about_engine(self):
        ver = getattr(self.engine, "version", "") or "not started"
        QMessageBox.information(
            self, "Browser engine",
            f"Microsoft Edge WebView2 runtime: {ver}\n\nRYTWEAKS draws the tabs, address bar, bookmarks "
            "and history; Microsoft's Edge engine (part of Windows) shows the web pages and keeps itself "
            "updated with Windows.\n\nBookmarks and history: " + str(self.data.path) +
            "\nCookies and cache: " + bd.user_data_dir())

    # ------------------------------------------------------------ theme and shutdown
    def on_theme(self, t):
        self.setStyleSheet(f"""
            QWidget#browserStrip, QWidget#browserNav {{ background-color: {t['sidebar']}; }}
            QWidget#browserNav {{ border-bottom: 1px solid {t['border']}; }}
            QTabBar#browserTabs {{ background: transparent; }}
            QTabBar#browserTabs::tab {{ background: transparent; color: {t['subtext']}; padding: 7px 12px;
                min-width: 90px; max-width: 220px; border-top-left-radius: 8px; border-top-right-radius: 8px;
                margin-right: 2px; }}
            QTabBar#browserTabs::tab:selected {{ background: {t['bg']}; color: {t['text']}; }}
            QTabBar#browserTabs::tab:hover:!selected {{ background: {t['card_hover']}; color: {t['text']}; }}
            QToolButton#browserTabClose {{ background: transparent; color: {t['subtext']}; border: none;
                border-radius: 9px; font-size: 10px; }}
            QToolButton#browserTabClose:hover {{ background: {t['card_hover']}; color: {t['text']}; }}
            QToolButton#browserTool {{ background: transparent; color: {t['text']}; border: none;
                border-radius: 8px; padding: 5px 9px; }}
            QToolButton#browserTool:hover {{ background: {t['card_hover']}; }}
            QToolButton#browserTool:disabled {{ color: {t['muted']}; }}
            QToolButton#browserTool::menu-indicator {{ image: none; }}
            QLineEdit#browserAddress {{ background: {t['input']}; border: 1px solid {t['border']};
                border-radius: 16px; padding: 6px 14px; }}
            QLineEdit#browserAddress:focus {{ border: 1px solid {t['accent']}; }}
            QFrame#browserPanel {{ background: {t['card']}; border-left: 1px solid {t['border']}; }}
            QListWidget#browserList {{ background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 8px; }}
            QListWidget#browserList::item {{ padding: 6px; border-bottom: 1px solid {t['border']}; }}
            QListWidget#browserList::item:selected {{ background: {t['card_hover']}; color: {t['text']}; }}
            QLabel#browserMsg {{ background: {t['card']}; color: {t['subtext']}; border-bottom: 1px solid {t['border']}; }}
        """)

    def shutdown(self):
        for d in self.downloads:
            if d.active():
                d.cancel()
        for v in self.views:
            v.close_engine()
