from core import overlay_fps as of


def only(*keys, **extra):
    return {**of.DEFAULTS, **{'overlay_show_' + key: key in keys for key, _, _ in of.METRIC_OPTIONS}, **extra}


def test_selected_metrics_show_without_forcing_other_rows():
    lines = of.format_lines({'fps': 144, 'low1': 99}, settings=only('low1', 'ram'), hardware={'ram': 45})
    assert lines == ['1% low 99', 'RAM 45%']
    assert of.format_lines({}, settings=only()) == ['No metrics selected']


def test_separate_cpu_and_gpu_toggles_and_master_switch():
    assert of.format_lines({}, settings=only('cpu'), hardware={'cpu': 20, 'gpu': 80}) == ['CPU 20%']
    assert of.format_lines({}, settings=only('gpu'), hardware={'cpu': 20, 'gpu': 80}) == ['GPU 80%']
    assert of.format_lines({}, settings=only('fps', 'cpu', 'ram', overlay_show_load=False)) == ['FPS –']


def test_point_one_percent_requires_enough_frames_and_tracks_slowest_frames():
    metrics = of.RollingMetrics(window_s=60)
    for i in range(999):
        metrics.add(10)
    assert metrics.snapshot()['low01'] is None
    metrics.add(100)
    snap = metrics.snapshot()
    assert snap['frames'] == 1000
    assert snap['low01'] == 10 and snap['min'] == 10 and snap['max'] == 100
    assert snap['low1'] > snap['low01']
    assert abs(snap['avg'] - 1000000 / 10090) < 0.001


def test_hardware_uses_one_consistent_gpu_and_rejects_stale_sample():
    sample = {'time': 100, 'cpu': {'load': 20, 'temp_c': 60},
              'ram': {'percent': 42, 'used_gb': 13.4, 'total_gb': 32},
              'gpus': [{'name': 'Idle GPU', 'load': 2, 'vram_used_gb': 1},
                       {'name': 'Busy GPU', 'load': 90, 'vram_used_gb': 5, 'vram_total_gb': 8}]}
    hardware = of.hardware_from_sample(sample, now=101)
    assert hardware['gpu'] == 90 and hardware['gpu_name'] == 'Busy GPU'
    assert hardware['vram_used'] == 5 and hardware['ram'] == 42
    assert of.hardware_from_sample(sample, now=106) == {}
    assert of.hardware_from_sample(None) == {}


def test_missing_sensors_never_become_zero_and_temperature_follows_unit():
    assert of.format_lines({}, settings=only('gpu_temp', 'vram')) == ['VRAM – / – GB', 'GPU temp – °C']
    assert of.format_lines({}, settings=only('cpu_temp'),
                           hardware={'cpu_temp': 50, 'temperature_unit': 'F'}) == ['CPU temp 122 °F']


def test_compact_layout_precision_and_invalid_settings():
    assert of.format_lines({'fps': 143.65, 'low1': 90.25},
        settings=only('fps', 'low1', overlay_layout='compact', overlay_decimals=1)) == ['FPS 143.7  |  1% low 90.2']
    cfg = of.clean_settings({'overlay_show_ram': 'false', 'overlay_refresh_ms': -1, 'overlay_margin': 'bad'})
    assert cfg['overlay_show_ram'] is False and cfg['overlay_refresh_ms'] == 400 and cfg['overlay_margin'] == 16


def test_live_timing_change_prunes_statistics_window_consistently():
    metrics = of.RollingMetrics(window_s=5)
    for _ in range(100):
        metrics.add(100)
    for _ in range(1000):
        metrics.add(2)
    assert metrics.snapshot()['min'] == 10
    for _ in range(2000):
        metrics.add(2)
    snap = metrics.snapshot()
    assert snap['min'] == 500 and snap['max'] == 500 and snap['low01'] == 500


def test_telemetry_restarts_if_overlay_acquires_while_previous_holder_is_stopping(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from rt_pages.monitor import TelemetryService
    threads = []
    def thread(**kwargs):
        worker = Mock()
        worker.is_alive.return_value = True
        threads.append(worker)
        return worker
    monkeypatch.setattr('rt_pages.monitor.threading.Thread', thread)
    service = TelemetryService(SimpleNamespace(after=lambda *a: None))
    service.acquire('dashboard')
    old_flag = service.stop_flag
    service.release('dashboard')
    service.acquire('overlay')
    assert len(threads) == 2 and old_flag.is_set() and not service.stop_flag.is_set()
    assert service.holders == {'overlay'}
