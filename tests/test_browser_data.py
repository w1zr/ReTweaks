"""Browser (v1.5): address bar, search engines, bookmarks/history storage, download names."""
import json

import pytest

from core import browser_data as bd


@pytest.mark.parametrize("text,expected", [
    ("google.com", "https://google.com"),
    ("www.youtube.com/watch?v=x", "https://www.youtube.com/watch?v=x"),
    ("https://example.com/a b", "https://example.com/a b"),
    ("http://192.168.1.1", "http://192.168.1.1"),
    ("192.168.1.1", "http://192.168.1.1"),
    ("localhost:8085", "http://localhost:8085"),
    ("about:blank", "about:blank"),
])
def test_addresses_open_directly(text, expected):
    assert bd.to_url(text) == expected


@pytest.mark.parametrize("text", ["how to lower ping", "fortnite", "javascript:alert(1)", "file:///C:/x",
                                  "rtx 4060 driver", "c++"])
def test_everything_else_is_a_search(text):
    assert bd.to_url(text, "DuckDuckGo").startswith("https://duckduckgo.com/?q=")


def test_search_engines_and_custom():
    assert bd.search_url("a b", "Google") == "https://www.google.com/search?q=a+b"
    assert bd.search_url("a&b", "Brave Search") == "https://search.brave.com/search?q=a%26b"
    assert bd.homepage("Startpage") == "https://www.startpage.com/"
    ok, _ = bd.valid_custom_search("https://kagi.com/search?q={q}")
    assert ok and bd.search_url("x y", bd.CUSTOM, "https://kagi.com/search?q={q}") == "https://kagi.com/search?q=x+y"
    assert bd.homepage(bd.CUSTOM, "https://kagi.com/search?q=%s") == "https://kagi.com/"
    assert not bd.valid_custom_search("http://evil.com/?q={q}")[0]        # must be https
    assert not bd.valid_custom_search("https://example.com/")[0]           # no {q}
    assert bd.to_url("", "Google") is None


def test_settings_cleaned():
    c = bd.clean_settings({"browser_search_engine": "Yahoo!!", "browser_ask_download": 1})
    assert c["browser_search_engine"] == "Google" and c["browser_ask_download"] is True
    c = bd.clean_settings({"browser_search_engine": "Custom", "browser_custom_search": "nope"})
    assert c["browser_search_engine"] == "Google" and c["browser_custom_search"] == ""
    assert bd.clean_settings(None)["browser_download_dir"] == ""


def test_bookmarks_persist_and_dedupe(tmp_path):
    p = tmp_path / "browser.json"
    d = bd.BrowserData(p)
    assert d.add_bookmark("RETWEAKS", "https://github.com/w1zr/retweaks")
    assert not d.add_bookmark("again", "https://github.com/w1zr/retweaks")
    assert not d.add_bookmark("x", "javascript:alert(1)")
    assert d.rename_bookmark("https://github.com/w1zr/retweaks", "Repo")
    d2 = bd.BrowserData(p)
    assert d2.bookmarks[0]["title"] == "Repo" and d2.is_bookmarked("https://github.com/w1zr/retweaks")
    assert d2.remove_bookmark("https://github.com/w1zr/retweaks") and not bd.BrowserData(p).bookmarks


def test_history_private_never_recorded_and_clear(tmp_path):
    d = bd.BrowserData(tmp_path / "b.json")
    assert not d.add_history("secret", "https://example.com", private=True)
    assert d.add_history("", "https://example.com")
    d.add_history("Example", "https://example.com")          # same page again: one entry, title updated
    d.update_title("https://example.com", "Example Domain")
    d.add_history("Other", "https://other.org")
    assert [h["title"] for h in d.search_history("")] == ["Other", "Example Domain"]
    assert [h["url"] for h in d.search_history("domain")] == ["https://example.com"]
    assert d.clear_history() == 2 and bd.BrowserData(tmp_path / "b.json").history == []


def test_damaged_file_is_kept_not_deleted(tmp_path):
    p = tmp_path / "browser.json"
    p.write_text("{not json", encoding="utf-8")
    d = bd.BrowserData(p)
    assert d.bookmarks == [] and "damaged" in d.load_note
    assert (tmp_path / "browser.json.bad").read_text(encoding="utf-8") == "{not json"


def test_history_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(bd, "HISTORY_LIMIT", 5)
    d = bd.BrowserData(tmp_path / "b.json")
    for i in range(9):
        d.add_history(str(i), f"https://e.com/{i}")
    assert len(d.history) == 5 and d.history[0]["url"] == "https://e.com/4"
    assert len(json.loads((tmp_path / "b.json").read_text())["history"]) == 5


@pytest.mark.parametrize("name,expected", [("report.pdf", "report.pdf"), ("../../evil.exe", "evil.exe"),
                                           ('a<b>:"c".txt', "a_b___c_.txt"), ("CON.txt", "_CON.txt"), ("", "download")])
def test_safe_filename(name, expected):
    assert bd.safe_filename(name) == expected


def test_unique_path(tmp_path):
    (tmp_path / "a.zip").write_text("x")
    (tmp_path / "a (1).zip").write_text("x")
    assert bd.unique_path(tmp_path, "a.zip").endswith("a (2).zip")


def test_start_page_is_not_history_or_bookmark(tmp_path):
    d = bd.BrowserData(tmp_path / "b.json")
    assert bd.is_newtab(bd.NEWTAB_URL) and bd.is_newtab(bd.NEWTAB_PRIVATE_URL)
    assert not d.add_history("New tab", bd.NEWTAB_URL)
    assert not d.add_bookmark("New tab", bd.NEWTAB_URL)


def test_start_page_render_escapes_and_uses_engine(tmp_path):
    from core import browser_newtab as n
    from core import themes
    t = themes.get_theme("Midnight")
    page = n.render(t, "DuckDuckGo", "", [{"title": "<script>x</script>", "url": "https://e.com/?a=\"b"},
                                          {"title": "bad", "url": "javascript:alert(1)"}])
    assert "ReTweaks" in page and "<svg" in page
    assert "<script>x</script>" not in page and "&lt;script&gt;" in page
    assert "javascript:alert" not in page
    assert '"https://duckduckgo.com/?q={q}"' in page
    page = n.render(t, bd.CUSTOM, "https://kagi.com/search?q=%s")
    assert '"https://kagi.com/search?q={q}"' in page
    assert "Private tab" in n.render(t, private=True)
    folder = n.write(tmp_path / "nt", t)
    assert (tmp_path / "nt" / "index.html").exists() and (tmp_path / "nt" / "private.html").exists()
