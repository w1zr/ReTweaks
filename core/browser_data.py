# core/browser_data.py
"""Browser (v1.5): search engines, address-bar parsing, bookmarks and history.

Pure Python, testable on any OS. Bookmarks and history live in their own file,
%APPDATA%\\RYTWEAKS\\browser.json, separate from config.json (app settings) so clearing history
can never touch settings. Private tabs never write history.
"""

import json
import os
import re
import threading
import time
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

# name -> search URL ({q} is replaced by the URL-encoded query)
SEARCH_ENGINES = {
    "Google": "https://www.google.com/search?q={q}",
    "DuckDuckGo": "https://duckduckgo.com/?q={q}",
    "Brave Search": "https://search.brave.com/search?q={q}",
    "Bing": "https://www.bing.com/search?q={q}",
    "Startpage": "https://www.startpage.com/sp/search?query={q}",
}
HOMEPAGES = {
    "Google": "https://www.google.com/",
    "DuckDuckGo": "https://duckduckgo.com/",
    "Brave Search": "https://search.brave.com/",
    "Bing": "https://www.bing.com/",
    "Startpage": "https://www.startpage.com/",
}
CUSTOM = "Custom"
NEWTAB_HOST = "rytweaks.newtab"                    # RYTWEAKS start page (core/browser_newtab.py)
NEWTAB_URL = f"https://{NEWTAB_HOST}/index.html"
NEWTAB_PRIVATE_URL = f"https://{NEWTAB_HOST}/private.html"
DEFAULT_ENGINE = "Google"
HISTORY_LIMIT = 5000

SETTINGS_DEFAULTS = {
    "browser_search_engine": DEFAULT_ENGINE,
    "browser_custom_search": "",        # e.g. https://example.com/search?q={q}
    "browser_download_dir": "",         # "" = the user's Downloads folder
    "browser_ask_download": False,      # ask where to save every download
}

_DOMAIN = re.compile(r"^(localhost|(\d{1,3}\.){3}\d{1,3}|([a-z0-9-]+\.)+[a-z]{2,63})(:\d{1,5})?(/.*)?$", re.I)


def clean_settings(settings):
    """Browser settings with bad or missing values replaced by defaults."""
    s = settings or {}
    eng = s.get("browser_search_engine")
    if eng not in SEARCH_ENGINES and eng != CUSTOM:
        eng = DEFAULT_ENGINE
    custom = s.get("browser_custom_search") or ""
    if eng == CUSTOM and not valid_custom_search(custom)[0]:
        eng = DEFAULT_ENGINE
    d = s.get("browser_download_dir") or ""
    return {"browser_search_engine": eng, "browser_custom_search": custom if valid_custom_search(custom)[0] else "",
            "browser_download_dir": d if isinstance(d, str) else "",
            "browser_ask_download": bool(s.get("browser_ask_download", False))}


def valid_custom_search(url):
    """(ok, message) for a user's own search URL. Must be https and contain {q} or %s."""
    url = (url or "").strip()
    if not url:
        return False, "Enter a search URL."
    if "{q}" not in url and "%s" not in url:
        return False, "Put {q} (or %s) where the search words go, e.g. https://example.com/search?q={q}"
    parts = urlsplit(url.replace("{q}", "x").replace("%s", "x"))
    if parts.scheme != "https" or not parts.netloc:
        return False, "The search URL must start with https://"
    return True, "OK"


def search_url(query, engine=DEFAULT_ENGINE, custom=""):
    q = quote_plus(query)
    if engine == CUSTOM and valid_custom_search(custom)[0]:
        return custom.strip().replace("{q}", q).replace("%s", q)
    return SEARCH_ENGINES.get(engine, SEARCH_ENGINES[DEFAULT_ENGINE]).replace("{q}", q)


def homepage(engine=DEFAULT_ENGINE, custom=""):
    if engine == CUSTOM and valid_custom_search(custom)[0]:
        p = urlsplit(custom.replace("{q}", "x").replace("%s", "x"))
        return f"{p.scheme}://{p.netloc}/"
    return HOMEPAGES.get(engine, HOMEPAGES[DEFAULT_ENGINE])


def to_url(text, engine=DEFAULT_ENGINE, custom=""):
    """What the address bar should open for the typed text: a web address or a search.
    Only http(s) pages open directly; anything else (javascript:, file:, ...) is searched for."""
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()
    if low.startswith(("http://", "https://")):
        return t if urlsplit(t).netloc else search_url(t, engine, custom)
    if low == "about:blank":
        return "about:blank"
    if " " not in t and _DOMAIN.match(t):
        host = t.split("/")[0].split(":")[0].lower()
        scheme = "http" if host == "localhost" or re.match(r"^\d{1,3}(\.\d{1,3}){3}$", host) else "https"
        return f"{scheme}://{t}"
    return search_url(t, engine, custom)


def is_newtab(url):
    return urlsplit(url or "").netloc.lower() == NEWTAB_HOST


def display_title(title, url):
    t = (title or "").strip()
    if t:
        return t
    host = urlsplit(url or "").netloc
    return host or (url or "New tab")


def safe_filename(name):
    """A download's suggested name made safe for Windows (no folders, no reserved characters)."""
    base = os.path.basename((name or "").replace("\\", "/")) or "download"
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", base).strip(" .") or "download"
    if base.split(".")[0].upper() in {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
                                      *(f"LPT{i}" for i in range(1, 10))}:
        base = "_" + base
    return base[:180]


def unique_path(folder, name):
    """folder/name, or folder/name (1).ext etc. if that file already exists."""
    folder = Path(folder)
    p = folder / name
    stem, ext = os.path.splitext(name)
    i = 1
    while p.exists():
        p = folder / f"{stem} ({i}){ext}"
        i += 1
    return str(p)


def default_download_dir():
    home = Path(os.environ.get("USERPROFILE") or Path.home())
    d = home / "Downloads"
    return str(d if d.is_dir() else home)


def data_path():
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / "RYTWEAKS" / "browser.json"


def user_data_dir():
    """Edge engine profile folder (cookies, cache). Kept outside the .exe's folder."""
    base = os.getenv("LOCALAPPDATA") or os.getenv("APPDATA") or str(Path.home())
    return str(Path(base) / "RYTWEAKS" / "Browser")


class BrowserData:
    """Bookmarks and history, saved to browser.json on every change. Thread-safe.
    A damaged file is kept as browser.json.bad (never silently deleted) and the browser starts empty."""

    def __init__(self, path=None):
        self.path = Path(path) if path else data_path()
        self._lock = threading.Lock()
        self.bookmarks = []      # [{"title", "url", "added"}]
        self.history = []        # [{"title", "url", "time"}], newest last
        self.load_note = ""
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.bookmarks = [b for b in data.get("bookmarks", []) if _ok_entry(b)]
            self.history = [h for h in data.get("history", []) if _ok_entry(h)][-HISTORY_LIMIT:]
        except Exception:
            try:
                bad = self.path.with_suffix(".json.bad")
                self.path.replace(bad)
                self.load_note = f"Your bookmarks file was damaged; it was kept as {bad.name}."
            except OSError:
                self.load_note = "Your bookmarks file couldn't be read."

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps({"bookmarks": self.bookmarks, "history": self.history}, indent=1),
                       encoding="utf-8")
        tmp.replace(self.path)

    # ---- bookmarks
    def is_bookmarked(self, url):
        with self._lock:
            return any(b["url"] == url for b in self.bookmarks)

    def add_bookmark(self, title, url):
        if not url or not url.lower().startswith(("http://", "https://")) or is_newtab(url):
            return False
        with self._lock:
            if any(b["url"] == url for b in self.bookmarks):
                return False
            self.bookmarks.append({"title": display_title(title, url), "url": url, "added": int(time.time())})
            self._save()
        return True

    def remove_bookmark(self, url):
        with self._lock:
            n = len(self.bookmarks)
            self.bookmarks = [b for b in self.bookmarks if b["url"] != url]
            if len(self.bookmarks) != n:
                self._save()
                return True
        return False

    def rename_bookmark(self, url, title):
        with self._lock:
            for b in self.bookmarks:
                if b["url"] == url:
                    b["title"] = (title or "").strip() or b["title"]
                    self._save()
                    return True
        return False

    # ---- history
    def add_history(self, title, url, private=False):
        """Records a visit. Private tabs and non-web pages are never recorded."""
        if private or not url or not url.lower().startswith(("http://", "https://")) or is_newtab(url):
            return False
        with self._lock:
            now = int(time.time())
            if self.history and self.history[-1]["url"] == url:
                self.history[-1]["title"] = display_title(title, url)
                self.history[-1]["time"] = now
            else:
                self.history.append({"title": display_title(title, url), "url": url, "time": now})
                del self.history[:-HISTORY_LIMIT]
            self._save()
        return True

    def update_title(self, url, title, private=False):
        if private:
            return
        with self._lock:
            for h in reversed(self.history[-20:]):
                if h["url"] == url:
                    h["title"] = display_title(title, url)
                    self._save()
                    return

    def clear_history(self):
        with self._lock:
            n = len(self.history)
            self.history = []
            self._save()
        return n

    def search_history(self, text, limit=200):
        words = (text or "").lower().split()
        with self._lock:
            items = list(reversed(self.history))
        if words:
            items = [h for h in items if all(w in (h["title"] + " " + h["url"]).lower() for w in words)]
        return items[:limit]


def _ok_entry(e):
    return isinstance(e, dict) and isinstance(e.get("url"), str) and isinstance(e.get("title", ""), str)
