import struct

from core import nettest as N


def test_dns_query_format():
    q = N.build_query("google.com", 0x1234)
    assert q[:4] == b"\x12\x34\x01\x00"
    assert b"\x06google\x03com\x00" in q and q.endswith(b"\x00\x01\x00\x01")


def test_dns_response_must_match_our_id():
    good = struct.pack(">HHHHHH", 7, 0x8180, 1, 1, 0, 0)
    nx = struct.pack(">HHHHHH", 7, 0x8183, 1, 0, 0, 0)
    assert N.parse_response(good, 7) == 0
    assert N.parse_response(nx, 7) == 3
    assert N.parse_response(good, 8) is None          # someone else's answer
    assert N.parse_response(b"\x00", 7) is None


def test_stats():
    s = N.summarize([10.0, None, 30.0, 20.0])
    assert s["avg"] == 20.0 and s["best"] == 10.0 and s["worst"] == 30.0 and s["failed"] == 1
    assert N.jitter([10.0, 14.0, None, 12.0]) == 3.0   # |14-10| and |12-14| -> 3.0


def test_ping_target_restricted():
    assert "error" in N.ping_test("8.8.8.8")
