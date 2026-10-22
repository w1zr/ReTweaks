"""Storage Explorer / disk analyzer logic: size aggregation, breadcrumbs, long paths, sorting."""

import os
import threading

from core.storage_manager import (ScanState, human_size, long_path, scan_tree, search_files, sort_items,
                                  split_breadcrumbs, list_directory)


def _tree(tmp_path):
    (tmp_path / "a" / "b" / "c").mkdir(parents=True)
    (tmp_path / "d").mkdir()
    (tmp_path / "root.bin").write_bytes(b"x" * 100)
    (tmp_path / "a" / "f1.bin").write_bytes(b"x" * 1000)
    (tmp_path / "a" / "b" / "f2.bin").write_bytes(b"x" * 500)
    (tmp_path / "a" / "b" / "c" / "f3.bin").write_bytes(b"x" * 250)
    (tmp_path / "d" / "f4.bin").write_bytes(b"x" * 10)


def test_scan_totals_and_children(tmp_path):
    _tree(tmp_path)
    r = scan_tree(str(tmp_path), threading.Event())
    assert r["total"] == 1860 and r["files"] == 5 and r["folders"] == 4
    kids = {c["name"]: c["size"] for c in r["children"]}
    assert kids == {"a": 1750, "d": 10, "root.bin": 100}
    assert r["children"][0]["name"] == "a"                       # largest first
    top = dict(r["top_folders"])
    assert top[str(tmp_path / "a" / "b")] == 750
    assert top[str(tmp_path / "a" / "b" / "c")] == 250
    assert r["top_files"][0][0] == 1000
    assert r["skipped"] == 0 and not r["cancelled"]


def test_scan_totals_only_mode(tmp_path):
    _tree(tmp_path)
    r = scan_tree(str(tmp_path), threading.Event(), track_depth=0, top_files=0)
    assert r["total"] == 1860 and r["children"] == [] and r["top_files"] == []


def test_symlinks_are_not_followed(tmp_path):
    _tree(tmp_path)
    try:
        os.symlink(str(tmp_path / "a"), str(tmp_path / "link_to_a"))
    except (OSError, NotImplementedError):
        return
    r = scan_tree(str(tmp_path), threading.Event())
    assert r["total"] == 1860                                    # not double counted
    assert r["link_count"] == 1
    link = [c for c in r["children"] if c["name"] == "link_to_a"][0]
    assert link["is_link"] and link["size"] == 0


def test_unreadable_folder_is_counted(tmp_path):
    _tree(tmp_path)
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "secret.bin").write_bytes(b"x" * 5)
    locked.chmod(0)
    try:
        if os.access(str(locked), os.R_OK):
            return                                               # running as root: can't test denial
        r = scan_tree(str(tmp_path), threading.Event())
        assert r["skipped"] == 1 and r["total"] == 1860
    finally:
        locked.chmod(0o700)


def test_missing_root_reports_error(tmp_path):
    r = scan_tree(str(tmp_path / "nope"), threading.Event())
    assert r["error"] and r["total"] == 0


def test_cancel_stops_scan(tmp_path):
    _tree(tmp_path)
    stop = threading.Event()
    stop.set()
    r = scan_tree(str(tmp_path), stop)
    assert r["cancelled"] and r["total"] == 0


def test_search(tmp_path):
    _tree(tmp_path)
    st = ScanState()
    st.results = []
    search_files(str(tmp_path), "F2", False, threading.Event(), st)
    assert st.results == []                                      # not recursive
    search_files(str(tmp_path), "F2", True, threading.Event(), st)
    assert [r["name"] for r in st.results] == ["f2.bin"]


def test_list_directory_hidden_and_sort(tmp_path):
    (tmp_path / ".hid").write_text("x")
    (tmp_path / "b.txt").write_text("12345")
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "dir").mkdir()
    shown = list_directory(str(tmp_path), show_hidden=False)
    assert ".hid" not in [i["name"] for i in shown]
    allitems = list_directory(str(tmp_path), show_hidden=True)
    assert ".hid" in [i["name"] for i in allitems]
    by_name = [i["name"] for i in sort_items(shown, "name")]
    assert by_name == ["dir", "a.txt", "b.txt"]                  # folders first
    assert [i["name"] for i in sort_items(shown, "size", True)][0] == "b.txt"


def test_breadcrumbs_windows():
    assert split_breadcrumbs(r"C:\Users\me\Docs") == [
        ("C:\\", "C:\\"), ("Users", r"C:\Users"), ("me", r"C:\Users\me"), ("Docs", r"C:\Users\me\Docs")]
    assert split_breadcrumbs("C:\\") == [("C:\\", "C:\\")]
    assert split_breadcrumbs("D:") == [("D:\\", "D:\\")]
    assert split_breadcrumbs("c:/Games/x") == [("c:\\", "c:\\"), ("Games", r"c:\Games"), ("x", r"c:\Games\x")]


def test_breadcrumbs_unc_and_posix():
    assert split_breadcrumbs(r"\\srv\share\a") == [(r"\\srv\share", r"\\srv\share"), ("a", r"\\srv\share\a")]
    assert split_breadcrumbs("/home/me") == [("/", "/"), ("home", "/home"), ("me", "/home/me")]
    assert split_breadcrumbs("") == []


def test_long_path_prefix():
    assert long_path(r"C:\a\b", windows=True) == "\\\\?\\C:\\a\\b"
    assert long_path(r"\\srv\share\a", windows=True) == "\\\\?\\UNC\\srv\\share\\a"
    assert long_path("\\\\?\\C:\\a", windows=True) == "\\\\?\\C:\\a"
    assert long_path("/home/x", windows=False) == "/home/x"


def test_human_size():
    assert human_size(0) == "0 B" and human_size(1536) == "1.5 KB" and human_size(None) == "Unavailable"
