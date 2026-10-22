import pytest

from core import fps

V2 = ("Application,ProcessID,SwapChainAddress,PresentRuntime,SyncInterval,PresentFlags,AllowsTearing,"
      "PresentMode,CPUStartTime,MsBetweenPresents,MsBetweenDisplayChange\n"
      "game.exe,1,0x1,DXGI,0,0,1,Hardware: Independent Flip,0.0,16.0,16.0\n"
      "game.exe,1,0x1,DXGI,0,0,1,Hardware: Independent Flip,0.016,20.0,20.0\n"
      "game.exe,1,0x1,DXGI,0,0,1,Hardware: Independent Flip,0.036,bad,0\n"
      "game.exe,1,0x1,DXGI,0,0,1,Hardware: Independent Flip,0.036,0,0\n")

V1 = ("Application,ProcessID,SwapChainAddress,Runtime,SyncInterval,PresentFlags,AllowsTearing,PresentMode,"
      "Dropped,TimeInSeconds,msBetweenPresents,msBetweenDisplayChange,msInPresentAPI\n"
      "g.exe,1,0x1,DXGI,0,0,1,x,0,0.1,10.0,10.0,1\n"
      "g.exe,1,0x1,DXGI,0,0,1,x,0,0.2,30.0,30.0,1\n")

FT = "Application,FrameTime\ng.exe,25\ng.exe,25\n"


def test_parse_v2():
    frames, info = fps.parse_frame_times(V2)
    assert frames == [16.0, 20.0]
    assert info["column"] == "MsBetweenPresents"
    assert info["rows"] == 4 and info["skipped"] == 2


def test_parse_v1_lowercase_header():
    frames, info = fps.parse_frame_times("﻿" + V1)
    assert frames == [10.0, 30.0]


def test_parse_frametime_fallback():
    assert fps.parse_frame_times(FT)[0] == [25.0, 25.0]


def test_parse_errors():
    with pytest.raises(ValueError):
        fps.parse_frame_times("")
    with pytest.raises(ValueError):
        fps.parse_frame_times("A,B\n1,2\n")


def test_average():
    m = fps.compute_metrics([10.0, 30.0])
    assert m["avg_fps"] == pytest.approx(1000 / 20)   # 1000 / mean frame time = 50
    assert m["frames"] == 2 and m["duration_s"] == pytest.approx(0.04)
    assert m["min_frame_ms"] == 10.0 and m["max_frame_ms"] == 30.0
    assert m["low1_fps"] is None and m["low01_fps"] is None


def test_lows_hand_computed():
    # 200 frames: 198 at 10 ms and 2 at 50 ms.
    frames = [10.0] * 198 + [50.0, 50.0]
    m = fps.compute_metrics(frames)
    # slowest 1% of 200 = 2 frames, both 50 ms -> 20 FPS
    assert m["low1_fps"] == pytest.approx(20.0)
    # 99th percentile nearest rank: rank ceil(.99*200)=198 -> 10 ms -> 100 FPS
    assert m["p99_fps"] == pytest.approx(100.0)
    assert m["low01_fps"] is None and m["p999_fps"] is None
    assert fps.format_metric("low01_fps", None) == "Unavailable (needs 1000+ frames)"
    assert m["avg_fps"] == pytest.approx(1000 / ((198 * 10 + 100) / 200))


def test_low01_with_1000_frames():
    frames = [10.0] * 998 + [100.0, 200.0]
    m = fps.compute_metrics(frames)
    # slowest 0.1% = 1 frame = 200 ms -> 5 FPS
    assert m["low01_fps"] == pytest.approx(5.0)
    # slowest 1% = 10 frames: 200 + 100 + 8*10 = 380 / 10 = 38 ms
    assert m["low1_fps"] == pytest.approx(1000 / 38)
    # 99.9 pct nearest rank ceil(.999*1000)=999 -> sorted asc[998]=100 ms -> 10 FPS
    assert m["p999_fps"] == pytest.approx(10.0)


def test_no_frames():
    with pytest.raises(ValueError):
        fps.compute_metrics([])


def test_compare():
    a = fps.compute_metrics([10.0] * 100)
    b = fps.compute_metrics([8.0] * 100)
    rows = {r[0]: r for r in fps.compare_runs(a, b)}
    assert rows["avg_fps"][4] == pytest.approx(25.0)
    assert rows["avg_fps"][5] == pytest.approx(25.0)
    assert rows["low01_fps"][4] is None
    w = fps.comparison_warnings({"game": "a", "seconds": 30}, {"game": "b", "seconds": 60})
    assert len(w) == 3


def test_command():
    cmd = fps.build_command("PresentMon.exe", "game.exe", 30, "out.csv")
    assert cmd[cmd.index("--process_name") + 1] == "game.exe"
    assert cmd[cmd.index("--timed") + 1] == "30"
    for f in ("--terminate_after_timed", "--no_console_stats", "--output_file"):
        assert f in cmd
    with pytest.raises(ValueError):
        fps.build_command("p.exe", "", 30, "o.csv")


def test_interpret_result():
    assert fps.interpret_result("", "", 0)[1].startswith("No frames")
    assert "administrator" in fps.interpret_result("", "Access is denied", 1)[1]
    assert "Could not read" in fps.interpret_result("A,B\n1,2\n", "", 0)[1]
    frames, err = fps.interpret_result(V2, "", 0)
    assert err is None and len(frames) == 2


def test_saved_runs(tmp_path):
    p = tmp_path / "runs.json"
    assert fps.load_runs(p) == []
    r = fps.make_run("game.exe", 30, fps.compute_metrics([10.0] * 100), notes="n")
    fps.add_run(r, p)
    assert fps.load_runs(p)[0]["notes"] == "n"
    fps.update_notes(r["id"], "new", p)
    assert fps.load_runs(p)[0]["notes"] == "new"
    assert fps.delete_run(r["id"], p) == []
    p.write_text("garbage")
    assert fps.load_runs(p) == []
