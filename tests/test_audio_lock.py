"""Volume lock (v1.5): logic tested with fake read/write functions."""
from core import audio_lock as L


def test_clean_lock():
    assert L.clean_lock(None) is None and L.clean_lock(True) is None
    assert L.clean_lock("80") == 80 and L.clean_lock(79.6) == 80
    assert L.clean_lock(-1) is None and L.clean_lock(101) is None and L.clean_lock("x") is None
    assert L.clean_lock(float("nan")) is None and L.clean_lock(0) == 0


def test_correction():
    assert L.correction(45, 80) == 80
    assert L.correction(80, 80) is None
    assert L.correction(45, None) is None
    assert L.correction(None, 80) is None


class Fake:
    def __init__(self):
        self.vol = {"output": [50, False], "input": [80, False]}
        self.locks = {"output": None, "input": 80}
        self.logs = []
        self.t = 0.0

    def read(self, k):
        return tuple(self.vol[k]) if self.vol[k] is not None else None

    def write(self, k, p):
        self.vol[k][0] = p


def make(f):
    return L.VolumeLock(f.read, f.write, lambda k: f.locks[k], log=lambda *a: f.logs.append(a), clock=lambda: f.t)


def test_mic_is_put_back_and_logging_is_throttled():
    f = Fake()
    lock = make(f)
    assert lock.active()
    assert lock.tick() == []                       # already at 80
    f.vol["input"][0] = 45                         # Discord lowered the mic
    assert lock.tick() == [("input", 45, 80)] and f.vol["input"][0] == 80
    assert len(f.logs) == 1 and "45%" in f.logs[0][1]
    f.vol["input"][0] = 30
    f.t = 10
    lock.tick()
    assert f.vol["input"][0] == 80 and len(f.logs) == 1    # fixed, but not logged again within a minute
    f.t = 70
    f.vol["input"][0] = 10
    lock.tick()
    assert len(f.logs) == 2 and lock.corrections["input"] == 3
    assert f.vol["output"][0] == 50                # speaker isn't locked: untouched


def test_mute_is_never_touched_and_no_device_is_ok():
    f = Fake()
    f.vol["input"] = [80, True]
    lock = make(f)
    lock.tick()
    assert f.vol["input"] == [80, True]
    f.vol["input"] = None                          # mic unplugged
    assert lock.tick() == []


def test_errors_are_kept_not_raised():
    f = Fake()

    def boom(k):
        raise OSError("audio service restarting")

    lock = L.VolumeLock(boom, f.write, lambda k: 80)
    assert lock.tick() == [] and "restarting" in lock.last_error["input"]


def test_lock_off_means_inactive():
    f = Fake()
    f.locks = {"output": None, "input": None}
    assert not make(f).active()
