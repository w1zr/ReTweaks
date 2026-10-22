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
