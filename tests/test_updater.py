from core.updater import is_newer, parse_sha256_file, parse_version, _allowed


def test_versions():
    assert parse_version("v1.3") == (1, 3, 0)
    assert parse_version("1.10.2") == (1, 10, 2)
    assert parse_version("exe") is None          # the old v1.0 tag name
    assert is_newer("v1.4", "1.3") and is_newer("v1.10", "1.9")
    assert not is_newer("v1.3", "1.3") and not is_newer("exe", "1.3")


def test_sha256_file_formats():
    h = "a" * 64
    assert parse_sha256_file(f"{h}  RETWEAKS.exe\r\n") == h
    assert parse_sha256_file(h.upper()) == h
    assert parse_sha256_file("garbage") is None


def test_download_hosts_are_restricted():
    assert _allowed("https://github.com/w1zr/retweaks/releases/download/v1.3/RETWEAKS.exe")
    assert not _allowed("http://github.com/x")          # not https
    assert not _allowed("https://evil.example.com/RETWEAKS.exe")
    assert not _allowed(None)


def test_update_comes_from_github_release(monkeypatch, tmp_path):
    """v2.0.6: from source the verified release exe is started from LOCALAPPDATA, never the source folder."""
    import core.updater as u
    assert u.LATEST_URL == "https://api.github.com/repos/w1zr/ReTweaks/releases/latest"
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert u.release_install_dir() == str(tmp_path / "RETWEAKS" / "app")
    calls = []
    monkeypatch.setattr(u, "can_self_update", lambda: False)
    monkeypatch.setattr(u, "install_release_copy", lambda p: calls.append(("copy", p)) or (True, ""))
    monkeypatch.setattr(u, "install_and_restart", lambda p: calls.append(("swap", p)) or (True, ""))
    u.install_update("new.exe")
    monkeypatch.setattr(u, "can_self_update", lambda: True)
    u.install_update("new.exe")
    assert calls == [("copy", "new.exe"), ("swap", "new.exe")]


def test_release_copy_moves_exe(monkeypatch, tmp_path):
    import subprocess
    import core.updater as u
    monkeypatch.setattr(u, "IS_WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    started = []
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: started.append(a))
    new = tmp_path / "dl.exe"
    new.write_bytes(b"new")
    target = tmp_path / "local" / "RETWEAKS" / "app" / "RETWEAKS.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"old")
    ok, _ = u.install_release_copy(str(new))
    assert ok and started and target.read_bytes() == b"new"
    assert not (target.parent / "RETWEAKS.old.exe").exists() and not new.exists()   # v2.0.7: no old exe kept


def test_remove_old_exe(monkeypatch, tmp_path):
    import sys
    import core.updater as u
    monkeypatch.setattr(u, "IS_WINDOWS", True)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "RETWEAKS.exe"))
    (tmp_path / "RETWEAKS.exe").write_bytes(b"cur")
    (tmp_path / "RETWEAKS.old.exe").write_bytes(b"old")
    (tmp_path / "other.exe").write_bytes(b"x")
    assert u.remove_old_exe() == [str(tmp_path / "RETWEAKS.old.exe")]
    assert (tmp_path / "RETWEAKS.exe").exists() and (tmp_path / "other.exe").exists()
    assert not (tmp_path / "RETWEAKS.old.exe").exists()


def test_still_starting_detects_a_fresh_copy():
    """v2.0.8: a second double-click during a slow first launch isn't reported as a stuck copy."""
    import rt_shell

    class P:
        def __init__(self, t):
            self.t = t

        def create_time(self):
            return self.t
    assert rt_shell.still_starting([P(1000.0)], now=1030.0)
    assert not rt_shell.still_starting([P(1000.0)], now=1000.0 + rt_shell.STARTING_SECONDS + 1)
    assert not rt_shell.still_starting([], now=0)


def test_restart_only_for_packaged_exe():
    import rt_shell
    assert rt_shell.restart_after_exit() is False      # running from source / not Windows: never relaunches
