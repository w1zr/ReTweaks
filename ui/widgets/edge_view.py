# ui/widgets/edge_view.py
"""One browser tab: a native Qt widget that hosts an Edge (WebView2) controller (v1.5).

WebView2's async calls return .NET Tasks. They complete on the UI thread's message loop, which Qt
pumps, so they are polled with a short QTimer instead of blocking. All WebView2 events arrive on the
UI thread too. Every .NET callback is wrapped so a Python error can never propagate into WebView2.
"""

import ctypes
import os
import traceback

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QWidget

from core import browser_data as bd

VK_CONTROL, VK_SHIFT = 0x11, 0x10


def when_done(task, on_ok, on_fail, interval=20):
    """Calls on_ok(result) or on_fail(message) on the UI thread when a .NET Task finishes."""
    def poll():
        try:
            if not task.IsCompleted:
                QTimer.singleShot(interval, poll)
                return
            if task.IsFaulted or task.IsCanceled:
                ex = task.Exception
                inner = getattr(ex, "InnerException", None) if ex is not None else None
                on_fail(str(inner.Message if inner is not None else (ex.Message if ex is not None else "Cancelled")))
                return
            on_ok(task.Result if hasattr(task, "Result") else None)
        except Exception as e:
            on_fail(f"{type(e).__name__}: {e}")
    poll()


def _safe(fn):
    def wrapped(*a):
        try:
            fn(*a)
        except Exception:
            traceback.print_exc()
    return wrapped


def _key_down(vk):
    try:
        return bool(ctypes.windll.user32.GetKeyState(vk) & 0x8000)
    except Exception:
        return False


class EnvironmentHolder:
    """One shared WebView2 environment (one browser process family) for all tabs."""

    def __init__(self, engine, user_data):
        self.engine, self.user_data = engine, user_data
        self.env = None
        self.error = ""
        self._waiting = []
        self._starting = False

    def get(self, on_ok, on_fail):
        if self.env is not None:
            return on_ok(self.env)
        self._waiting.append((on_ok, on_fail))
        if self._starting:
            return
        self._starting = True
        C = self.engine.C
        try:
            task = C.CoreWebView2Environment.CreateAsync(None, self.user_data, None)
        except Exception as e:
            return self._fail(f"{type(e).__name__}: {e}")
        when_done(task, self._ok, self._fail)

    def _ok(self, env):
        self.env, self._starting = env, False
        waiting, self._waiting = self._waiting, []
        for ok, _f in waiting:
            ok(env)

    def _fail(self, msg):
        self.error, self._starting = msg, False
        waiting, self._waiting = self._waiting, []
        for _o, fail in waiting:
            fail(msg)


class EdgeView(QWidget):
    """A tab's page area. Signals carry plain Python values."""

    titleChanged = Signal(str)
    urlChanged = Signal(str)
    loadingChanged = Signal(bool)
    navStateChanged = Signal()
    failed = Signal(str)                 # engine/controller couldn't start
    loadError = Signal(str)              # a page failed to load (no internet, bad address...)
    newWindowRequested = Signal(object)  # (uri, args, deferral, private)
    downloadStarting = Signal(object)    # (args, deferral)
    shortcut = Signal(str)               # 'new_tab', 'close_tab', 'address', 'bookmark', 'private_tab', 'find'
    fullscreenChanged = Signal(bool)
    ready = Signal()

    def __init__(self, engine, env_holder, private=False, parent=None, newtab_folder=None):
        super().__init__(parent)
        self.newtab_folder = newtab_folder
        self.setAttribute(Qt.WA_NativeWindow, True)
        self.setAttribute(Qt.WA_DontCreateNativeAncestors, True)
        self.setAttribute(Qt.WA_NoSystemBackground, True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.engine, self.env_holder, self.private = engine, env_holder, private
        self.controller = None
        self.wv = None
        self.title, self.url = "New tab", ""
        self.loading = False
        self.closed = False
        self._pending_url = None
        self._adopt = None               # (args, deferral) when this tab is a page's popup
        self._handlers = []

    # ------------------------------------------------------------ start-up
    def start(self, url=None, adopt=None):
        """Creates the controller; navigates to url, or becomes the new window for `adopt`."""
        self._pending_url, self._adopt = url, adopt
        self.env_holder.get(self._create_controller, self._fail)

    def _create_controller(self, env):
        if self.closed:
            return
        try:
            hwnd = self.engine.IntPtr(int(self.winId()))
            if self.private:
                opts = env.CreateCoreWebView2ControllerOptions()
                opts.IsInPrivateModeEnabled = True
                task = env.CreateCoreWebView2ControllerAsync(hwnd, opts)
            else:
                task = env.CreateCoreWebView2ControllerAsync(hwnd)
        except Exception as e:
            return self._fail(f"{type(e).__name__}: {e}")
        when_done(task, self._on_controller, self._fail)

    def _fail(self, msg):
        if self._adopt:
            args, deferral = self._adopt
            self._adopt = None
            try:
                deferral.Complete()
            except Exception:
                pass
        self.failed.emit(msg)

    def _on_controller(self, controller):
        if self.closed:
            try:
                controller.Close()
            except Exception:
                pass
            return
        self.controller, self.wv = controller, controller.CoreWebView2
        wv = self.wv
        s = wv.Settings
        s.IsStatusBarEnabled = True
        s.AreDefaultContextMenusEnabled = True
        s.IsZoomControlEnabled = True
        if self.newtab_folder:
            try:   # RYTWEAKS start page: https://rytweaks.newtab/ -> local folder
                wv.SetVirtualHostNameToFolderMapping(bd.NEWTAB_HOST, self.newtab_folder,
                                                     self.engine.C.CoreWebView2HostResourceAccessKind.Allow)
            except Exception:
                traceback.print_exc()
        self._on(wv, "DocumentTitleChanged", lambda *_: self._title())
        self._on(wv, "SourceChanged", lambda *_: self._source())
        self._on(wv, "HistoryChanged", lambda *_: self.navStateChanged.emit())
        self._on(wv, "NavigationStarting", lambda *_: self._set_loading(True))
        self._on(wv, "NavigationCompleted", self._nav_done)
        self._on(wv, "NewWindowRequested", self._new_window)
        self._on(wv, "DownloadStarting", self._download)
        self._on(wv, "ContainsFullScreenElementChanged",
                 lambda *_: self.fullscreenChanged.emit(bool(wv.ContainsFullScreenElement)))
        self._on(controller, "AcceleratorKeyPressed", self._accelerator)
        self._sync_bounds()
        controller.IsVisible = self.isVisible()
        if self._adopt:
            args, deferral = self._adopt
            self._adopt = None
            try:
                args.NewWindow = wv          # the page's popup opens in this tab
            except Exception:
                args.Handled = True
                self.navigate(str(args.Uri))
            finally:
                deferral.Complete()
        elif self._pending_url:
            self.navigate(self._pending_url)
        self._pending_url = None
        self.ready.emit()

    def _on(self, obj, event, fn):
        handler = _safe(fn)
        getattr(obj, event).__iadd__(handler)      # obj.Event += handler
        self._handlers.append((obj, event, handler))

    # ------------------------------------------------------------ events
    def _title(self):
        self.title = bd.display_title(str(self.wv.DocumentTitle or ""), self.url)
        self.titleChanged.emit(self.title)

    def _source(self):
        self.url = str(self.wv.Source or "")
        self.urlChanged.emit(self.url)
        self.navStateChanged.emit()

    def _set_loading(self, on):
        self.loading = on
        self.loadingChanged.emit(on)

    def _nav_done(self, _sender, args):
        self._set_loading(False)
        self.navStateChanged.emit()
        try:
            if not args.IsSuccess:
                status = str(args.WebErrorStatus)
                if status not in ("OperationCanceled", "Unknown"):
                    self.loadError.emit(status)
        except Exception:
            pass

    def _new_window(self, _sender, args):
        deferral = args.GetDeferral()
        self.newWindowRequested.emit((str(args.Uri), args, deferral, self.private))

    def _download(self, _sender, args):
        deferral = args.GetDeferral()
        self.downloadStarting.emit((args, deferral))

    def _accelerator(self, _sender, args):
        C = self.engine.C
        if args.KeyEventKind != C.CoreWebView2KeyEventKind.KeyDown or not _key_down(VK_CONTROL):
            return
        vk, shift = int(args.VirtualKey), _key_down(VK_SHIFT)
        action = {(0x54, False): "new_tab", (0x57, False): "close_tab", (0x4C, False): "address",
                  (0x44, False): "bookmark", (0x4E, True): "private_tab", (0x48, False): "history",
                  (0x4A, False): "downloads"}.get((vk, shift))
        if action:
            args.Handled = True
            self.shortcut.emit(action)

    # ------------------------------------------------------------ actions
    def navigate(self, url):
        if not url:
            return
        if self.wv is None:
            self._pending_url = url
            return
        try:
            self.wv.Navigate(url)
        except Exception as e:
            self.loadError.emit(str(e))

    def back(self):
        if self.wv is not None and self.wv.CanGoBack:
            self.wv.GoBack()

    def forward(self):
        if self.wv is not None and self.wv.CanGoForward:
            self.wv.GoForward()

    def reload(self):
        if self.wv is not None:
            self.wv.Reload()

    def stop(self):
        if self.wv is not None:
            self.wv.Stop()

    def can_back(self):
        return bool(self.wv is not None and self.wv.CanGoBack)

    def can_forward(self):
        return bool(self.wv is not None and self.wv.CanGoForward)

    def focus_page(self):
        if self.controller is not None:
            try:
                self.controller.MoveFocus(self.engine.C.CoreWebView2MoveFocusReason.Programmatic)
            except Exception:
                pass

    def clear_site_data(self, on_ok, on_fail):
        """Clears cookies, cache and site storage of the normal (non-private) profile."""
        if self.wv is None:
            return on_fail("The browser isn't ready yet.")
        try:
            task = self.wv.Profile.ClearBrowsingDataAsync()
        except Exception as e:
            return on_fail(f"{type(e).__name__}: {e}")
        when_done(task, lambda _r: on_ok(), on_fail)

    def close_engine(self):
        self.closed = True
        for obj, event, handler in self._handlers:
            try:
                getattr(obj, event).__isub__(handler)
            except Exception:
                pass
        self._handlers = []
        if self.controller is not None:
            try:
                self.controller.Close()
            except Exception:
                pass
        self.controller = self.wv = None

    # ------------------------------------------------------------ Qt plumbing
    def _sync_bounds(self):
        if self.controller is None:
            return
        r = self.devicePixelRatioF()
        try:
            self.controller.Bounds = self.engine.Rectangle(0, 0, max(1, int(self.width() * r)),
                                                           max(1, int(self.height() * r)))
        except Exception:
            pass

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_bounds()

    def moveEvent(self, e):
        super().moveEvent(e)
        if self.controller is not None:
            try:
                self.controller.NotifyParentWindowPositionChanged()
            except Exception:
                pass

    def showEvent(self, e):
        super().showEvent(e)
        if self.controller is not None:
            self.controller.IsVisible = True
            self._sync_bounds()

    def hideEvent(self, e):
        super().hideEvent(e)
        if self.controller is not None:
            self.controller.IsVisible = False

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.focus_page()


def download_target(args, folder):
    """Path RYTWEAKS saves a download to: the suggested name, made safe and unique, in `folder`."""
    suggested = os.path.basename(str(args.ResultFilePath or "")) or "download"
    os.makedirs(folder, exist_ok=True)
    return bd.unique_path(folder, bd.safe_filename(suggested))
