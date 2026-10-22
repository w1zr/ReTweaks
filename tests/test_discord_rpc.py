import json
import struct

import pytest

from core import discord_rpc as d


class FakePipe:
    def __init__(self, replies=None, fail_write=False):
        self.written = []
        self.buf = b""
        self.closed = False
        self.fail_write = fail_write
        for r in replies or [(d.OP_FRAME, {"cmd": "DISPATCH", "evt": "READY"})]:
            self.buf += d.pack_frame(*r)

    def write(self, data):
        if self.fail_write:
            raise OSError("broken pipe")
        self.written.append(data)
        # auto-reply to every SET_ACTIVITY
        op, p = d.unpack_frame(data)
        if op == d.OP_FRAME:
            self.buf += d.pack_frame(d.OP_FRAME, {"cmd": "SET_ACTIVITY", "evt": None})

    def read(self, n):
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def close(self):
        self.closed = True

    def frames(self):
        return [d.unpack_frame(w) for w in self.written]


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


def make(opener, app_id="123", clock=None):
    return d.DiscordPresence(app_id=app_id, opener=opener, clock=clock or Clock(), pid=42)


def test_frame_roundtrip():
    raw = d.pack_frame(1, {"a": 1})
    assert raw[:8] == struct.pack("<II", 1, len(raw) - 8)
    assert d.unpack_frame(raw) == (1, {"a": 1})
    with pytest.raises(ValueError):
        d.unpack_frame(raw[:-1])
    with pytest.raises(ValueError):
        d.unpack_header(struct.pack("<II", 1, 1 << 30))


def test_build_activity_variants_and_limits():
    idle = d.build_activity({"game": None}, True, 100)
    assert idle["details"] == "Optimizing with RYTWEAKS" and idle["state"] == "Windows PC tweaks"
    g = d.build_activity({"game": "Fortnite"}, True, 100)
    assert g["details"] == "Gaming: Fortnite" and g["state"] == "Boosted by RYTWEAKS"
    hidden = d.build_activity({"game": "Fortnite"}, False, 100)
    assert hidden["details"] == "Gaming" and "Fortnite" not in json.dumps(hidden)
    assert idle["timestamps"]["start"] == 100
    assert idle["assets"] == {"large_image": "rytweaks", "large_text": "RYTWEAKS"}
    assert idle["buttons"][0]["url"].startswith("https://github.com/w1zr/rytweaks")
    long = d.build_activity({"game": "X" * 500}, True, 1)
    for a in (idle, g, hidden, long):
        for k in ("details", "state"):
            assert 2 <= len(a[k]) <= 128


def test_friendly_game_name():
    f = d.friendly_game_name
    assert f("FortniteClient-Win64-Shipping.exe") == "Fortnite"
    assert f(r"C:\Games\Fortnite\FortniteClient-Win64-Shipping.exe") == "Fortnite"
    assert f("FortniteClient-Win64-Shipping") == "Fortnite"
    assert f("javaw.exe") == "Minecraft" and f("Minecraft.Windows.exe") == "Minecraft"
    assert f("r5apex.exe") == "Apex Legends"
    assert f("RocketLeague.exe") == "Rocket League"
    assert f("SomeCoolGame.exe") == "Some Cool Game"
    assert f("") is None and f(None) is None


def test_parse_game_event():
    assert d.parse_game_event("FortniteClient-Win64-Shipping started.") == ("started", "FortniteClient-Win64-Shipping")
    assert d.parse_game_event("r5apex closed.") == ("closed", "r5apex")
    assert d.parse_game_event("Switched to the Ultimate Performance power plan for this game.") is None
    assert d.parse_game_event("Background calming: foo closed.") is None
    assert d.parse_game_event("r5apex: CPU priority set to High.") is None


def test_no_connect_without_app_id_or_when_off():
    calls = []

    def opener():
        calls.append(1)
        return FakePipe()

    p = make(opener, app_id="")
    p.configure(True)
    p.step()
    assert p.status == "not_set_up" and not calls
    p2 = make(opener)
    p2.step()                      # never enabled
    assert p2.status == "off" and not calls


def test_connect_handshake_and_send_then_rate_limit():
    pipe, clock = FakePipe(), Clock()
    p = make(lambda: pipe, clock=clock)
    p.configure(True, True)
    p.step()
    assert p.status == "connected"
    fr = pipe.frames()
    assert fr[0] == (d.OP_HANDSHAKE, {"v": 1, "client_id": "123"})
    assert fr[1][0] == d.OP_FRAME and fr[1][1]["cmd"] == "SET_ACTIVITY"
    assert fr[1][1]["args"]["pid"] == 42 and fr[1][1]["nonce"]
    p.set_game("Fortnite")
    clock.t += 5
    p.step()
    assert len(pipe.written) == 2                 # rate limited
    clock.t += 15
    p.step()
    assert pipe.frames()[-1][1]["args"]["activity"]["details"] == "Gaming: Fortnite"
    clock.t += 30
    p.step()
    assert len(pipe.written) == 3                 # unchanged -> no resend


def test_backoff_when_discord_not_running_then_connects():
    clock, state = Clock(), {"n": 0, "up": False}

    def opener():
        state["n"] += 1
        if not state["up"]:
            raise FileNotFoundError("no pipe")
        return FakePipe()

    p = make(opener, clock=clock)
    p.configure(True)
    p.step()
    assert p.status == "waiting" and state["n"] == 1
    clock.t += 5
    p.step()
    assert state["n"] == 1                         # still backing off
    clock.t += 11
    state["up"] = True
    p.step()
    assert state["n"] == 2 and p.status == "connected"


def test_broken_pipe_reconnects_later():
    clock = Clock()
    pipes = [FakePipe(), FakePipe()]
    p = make(lambda: pipes.pop(0), clock=clock)
    p.configure(True)
    p.step()
    pipes_first = p._conn
    pipes_first.fail_write = True
    p.set_game("Minecraft")
    clock.t += 20
    p.step()
    assert p.status == "waiting" and p._conn is None
    clock.t += 16
    p.step()
    assert p.status == "connected"


def test_handshake_error_reports_error():
    bad = FakePipe(replies=[(d.OP_CLOSE, {"code": 4000, "message": "Invalid Client ID"})])
    p = make(lambda: bad)
    p.configure(True)
    p.step()
    assert p.status == "error: Invalid Client ID" and bad.closed


def test_disable_and_stop_clear_and_close():
    pipe = FakePipe()
    p = make(lambda: pipe)
    p.configure(True)
    p.step()
    p.configure(False)
    p.step()
    assert p.status == "off" and pipe.closed
    ops = [o for o, _ in pipe.frames()]
    assert ops[-2:] == [d.OP_FRAME, d.OP_CLOSE]
    assert pipe.frames()[-2][1]["args"]["activity"] is None
    p.stop()
    p.stop()                                       # idempotent


def test_thread_start_stop_idempotent():
    pipe = FakePipe()
    p = d.DiscordPresence(app_id="1", opener=lambda: pipe, pid=1)
    p.configure(True)
    p.start()
    p.start()
    import time
    for _ in range(100):
        if p.status == "connected":
            break
        time.sleep(0.02)
    assert p.status == "connected"
    p.stop()
    p.stop()
    assert pipe.closed
