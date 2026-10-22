"""Built-in frame counter (no PresentMon): struct layouts and frame math, testable on any OS."""
import ctypes

import pytest

from core import etw_frames as E


@pytest.mark.parametrize("struct,size", [
    (E.WNODE_HEADER, 48), (E.EVENT_TRACE_PROPERTIES, 120), (E.EVENT_HEADER, 80), (E.EVENT_RECORD, 112),
    (E.EVENT_TRACE_LOGFILEW, 448), (E.EVENT_DESCRIPTOR, 16), (E.EVENT_FILTER_DESCRIPTOR, 16),
    (E.ENABLE_TRACE_PARAMETERS, 48), (E.GUID, 16)], ids=lambda v: getattr(v, "__name__", str(v)))
def test_struct_sizes_match_64bit_windows(struct, size):
    assert ctypes.sizeof(struct) == size


def test_field_offsets_used_by_windows():
    assert E.EVENT_HEADER.ProcessId.offset == 12
    assert E.EVENT_HEADER.TimeStamp.offset == 16
    assert E.EVENT_HEADER.ProviderId.offset == 24
    assert E.EVENT_HEADER.EventDescriptor.offset == 40
    assert E.EVENT_TRACE_LOGFILEW.ProcessTraceMode.offset == 28
    assert E.EVENT_TRACE_LOGFILEW.EventRecordCallback.offset == 424
    assert E.EVENT_TRACE_PROPERTIES.LoggerNameOffset.offset == 116


def test_guid_parse_and_classify():
    g = E.GUID.parse(E.DXGI)
    assert hex(g.Data1) == "0xca11c036" and g.Data4[7] == 0xC9
    assert E.classify(g.key(), 42) == "api"
    assert E.classify(g.key(), 43) is None                      # Present_Stop isn't a new frame
    assert E.classify(E.GUID.parse(E.D3D9).key(), 1) == "api"
    assert E.classify(E.GUID.parse(E.DXGKRNL).key(), 184) == "kernel"


def test_event_id_filter_blob():
    b = E._event_id_filter((42, 55)).raw
    assert b == bytes([1, 0, 2, 0, 42, 0, 55, 0])


def _feed(agg, pid, src, fps, seconds, start=0):
    step = int(1e7 / fps)          # 100 ns units
    for i in range(int(fps * seconds) + 1):
        agg.feed(pid, src, start + i * step)
    return start + int(fps * seconds) * step


def test_aggregator_measures_fps_from_timestamps():
    agg = E.FrameAggregator()
    _feed(agg, 100, "api", 144, 3)
    snap, src = agg.snapshot({100})
    assert src == "api"
    assert abs(snap["fps"] - 144) <= 1
    assert abs(snap["frame_ms"] - 1000 / 144) < 0.05
    assert abs(snap["low1"] - 144) <= 1


def test_aggregator_ignores_kernel_events_when_dxgi_reports():
    agg = E.FrameAggregator()
    end = _feed(agg, 7, "api", 60, 2)
    _feed(agg, 7, "kernel", 500, 0.5, start=end)          # same process: must not double count
    snap, src = agg.snapshot({7})
    assert src == "api" and abs(snap["fps"] - 60) <= 1


def test_aggregator_uses_kernel_for_opengl_games_and_skips_pauses():
    agg = E.FrameAggregator()
    end = _feed(agg, 9, "kernel", 120, 2)
    agg.feed(9, "kernel", end + int(5 * 1e7))             # 5 s loading pause: not a 5000 ms frame
    snap, src = agg.snapshot({9})
    assert src == "kernel" and snap["frame_ms"] < 20


def test_aggregator_picks_busiest_process_and_other_pids_ignored():
    agg = E.FrameAggregator()
    _feed(agg, 1, "api", 30, 2)
    _feed(agg, 2, "api", 240, 2)
    _feed(agg, 3, "api", 500, 2)              # not the game
    snap, _ = agg.snapshot({1, 2})
    assert abs(snap["fps"] - 240) <= 1
    assert agg.snapshot({42}) == (None, None)


class FakeSession:
    def __init__(self, on_event):
        self.on_event, self.started, self.stopped, self.error = on_event, False, 0, ""

    def start(self):
        self.started = True

    def stop(self):
        self.stopped += 1


def test_builtin_stream_lifecycle():
    s = E.BuiltinOverlayStream("game.exe", alive_check=lambda n: True, session_factory=FakeSession,
                               pid_lookup=lambda n: {55})
    s.start()
    assert s.state == "running" and s.session.started
    snap, state = s.snapshot()
    assert snap["fps"] is None and state == "running"           # no frames yet -> Unavailable
    _feed(s.agg, 55, "api", 90, 2)
    snap, _ = s.snapshot()
    assert abs(snap["fps"] - 90) <= 1 and s.has_frames() and s.source == "api"
    s.stop()
    s.stop()
    assert s.state == "idle" and s.session.stopped >= 1
    with pytest.raises(ValueError):
        E.BuiltinOverlayStream("", session_factory=FakeSession).start()


def test_session_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(E.sys, "platform", "linux")
    with pytest.raises(OSError):
        E.EtwSession(lambda *a: None).start()
