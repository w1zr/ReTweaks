import csv

from core import sensorlog

SAMPLE = {
    "time": 1.0,
    "cpu": {"load": 12.5, "per_core": [10.0, 15.0], "mhz": 4000, "mhz_source": "x", "temp_c": None},
    "ram": {"percent": 40.0, "used_gb": 12.8, "total_gb": 32.0},
    "gpus": [{"luid": "abc", "name": "RTX", "load": 55.0, "vram_used_gb": 3.1, "temp_c": 60.0,
              "core_mhz": None}],
    "io": {"disk_read_bps": 100.0, "net_down_bps": None},
    "sensors": {"source": "LHM", "fans": [{"name": "CPU Fan #1", "rpm": 900.0}],
                "storage_temps": {"Samsung": 35.0}, "cpu_temp": 50.0},
}


def test_flatten():
    f = sensorlog.flatten_sample(SAMPLE)
    assert f["cpu_load"] == 12.5 and f["cpu_per_core_2"] == 15.0
    assert f["cpu_temp_c"] is None
    assert f["gpus_1_load"] == 55.0 and f["gpus_1_core_mhz"] is None
    assert f["io_net_down_bps"] is None
    assert f["sensors_fans_cpu_fan_1"] == 900.0
    assert f["sensors_storage_temps_samsung"] == 35.0
    assert "cpu_mhz_source" not in f and "time" not in f and "gpus_1_name" not in f
    assert "gpus_1_luid" not in f


def test_logger(tmp_path):
    p = tmp_path / "sub" / "log.csv"
    lg = sensorlog.SensorLogger(p)
    lg.start()
    lg.write(SAMPLE)
    s2 = {**SAMPLE, "cpu": {**SAMPLE["cpu"], "new_key": 5.0, "load": None}}
    lg.write(s2)
    lg.stop()
    rows = list(csv.reader(open(p, encoding="utf-8-sig")))
    assert rows[0][0] == "timestamp" and "cpu_new_key" not in rows[0]
    assert len(rows) == 3 and lg.rows == 2
    assert "cpu_new_key" in lg.dropped_keys
    col = rows[0].index("cpu_load")
    assert rows[1][col] == "12.5" and rows[2][col] == ""
    assert rows[1][rows[0].index("cpu_temp_c")] == ""
    assert lg.write(SAMPLE) is False
