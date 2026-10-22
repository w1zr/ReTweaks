"""Browser engine loader and download naming (the Windows-only parts are checked in CI by
tools/browser_smoke.py on GitHub's Windows runner)."""
import types

import pytest

from core import browser_engine as be


def test_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(be.sys, "platform", "linux")
    monkeypatch.setattr(be, "_engine", None)
    with pytest.raises(be.EngineUnavailable):
        be.load()


def test_sdk_dir_prefers_bundle(tmp_path, monkeypatch):
    d = tmp_path / be.SDK_DIR_NAME
    d.mkdir()
    (d / be.CORE_DLL).write_bytes(b"x")
    (d / be.LOADER_DLL).write_bytes(b"x")
    monkeypatch.setattr(be.sys, "_MEIPASS", str(tmp_path), raising=False)
    assert be.sdk_dir() == d
    assert be.loader_path(d) == d / be.LOADER_DLL


def test_missing_sdk_is_a_clear_message(tmp_path, monkeypatch):
    monkeypatch.setattr(be.sys, "_MEIPASS", str(tmp_path), raising=False)
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None)
    with pytest.raises(be.EngineUnavailable, match="couldn't find"):
        be.sdk_dir()


def test_download_target_is_safe_and_unique(tmp_path):
    pytest.importorskip("PySide6")
    from ui.widgets.edge_view import download_target
    (tmp_path / "setup.exe").write_text("x")
    args = types.SimpleNamespace(ResultFilePath=r"C:\Users\x\Downloads\setup.exe")
    assert download_target(args, str(tmp_path)).endswith("setup (1).exe")
    args = types.SimpleNamespace(ResultFilePath="")
    assert download_target(args, str(tmp_path)).endswith("download")
