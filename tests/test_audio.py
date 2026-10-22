# tests/test_audio.py
from core import audio


def test_clamp_percent():
    assert audio.clamp_percent(-5) == 0
    assert audio.clamp_percent(150) == 100
    assert audio.clamp_percent(42.6) == 43
    assert audio.clamp_percent(None) == 0
    assert audio.clamp_percent("abc") == 0
    assert audio.clamp_percent(float("nan")) == 0
    assert audio.clamp_percent("55") == 55


def test_percent_scalar_roundtrip():
    assert audio.percent_to_scalar(0) == 0.0
    assert audio.percent_to_scalar(100) == 1.0
    assert audio.percent_to_scalar(250) == 1.0
    assert audio.percent_to_scalar(50) == 0.5
    for p in range(0, 101):
        assert audio.scalar_to_percent(audio.percent_to_scalar(p)) == p


def test_scalar_to_percent_edges():
    assert audio.scalar_to_percent(0.504) == 50
    assert audio.scalar_to_percent(-1) == 0
    assert audio.scalar_to_percent(3) == 100
    assert audio.scalar_to_percent(None) == 0


def test_session_label():
    assert audio.session_label(0, "", "") == "System sounds"
    assert audio.session_label(10, "spotify.exe", "x") == "spotify.exe"
    assert audio.session_label(10, "", "Chrome") == "Chrome"
    assert audio.session_label(10, "", "") == "Process 10"


def test_sessions_key():
    a = audio.SessionInfo(1, "a", "n", 10, False, True, None)
    b = audio.SessionInfo(2, "b", "m", 20, True, False, None)
    assert audio.sessions_key([a, b]) == ((1, "a"), (2, "b"))
    assert audio.sessions_key([]) == ()


def test_unavailable_off_windows():
    import sys
    if sys.platform != "win32":
        assert audio.AVAILABLE is False
        assert audio.UNAVAILABLE_REASON
