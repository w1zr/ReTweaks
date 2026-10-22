# core/sensorlog.py
"""Log live telemetry samples to a CSV file (one row per sample).

The header is fixed from the first sample. Keys that first appear later are left out
(and counted in `dropped_keys`). Missing values are written as an empty cell, never 0.
"""

import csv
import os
import re
import threading
from datetime import datetime
from pathlib import Path


def default_log_path(now=None):
    now = now or datetime.now()
    docs = Path.home() / "Documents" / "RETWEAKS logs"
    return docs / f"sensors_{now.strftime('%Y-%m-%d_%H%M')}.csv"


def _clean(name):
    name = re.sub(r"[^0-9A-Za-z]+", "_", str(name)).strip("_").lower()
    return name or "item"


def _is_number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def flatten_sample(sample):
    """Flatten a telemetry sample dict into {column: number or None}.

    Only numeric readings are kept (strings such as source names are skipped).
    A reading that exists but has no value is kept as None so its column exists.
    Lists of dicts are numbered (gpus -> gpus_1_load); the fans list is keyed by name.
    """
    out = {}

    def walk(prefix, value):
        if isinstance(value, dict):
            for k, v in value.items():
                walk(f"{prefix}_{_clean(k)}" if prefix else _clean(k), v)
        elif isinstance(value, (list, tuple)):
            for i, v in enumerate(value, 1):
                if isinstance(v, dict) and "rpm" in v and "name" in v:
                    walk(f"{prefix}_{_clean(v['name'])}", v["rpm"])
                elif isinstance(v, dict) and "celsius" in v and "name" in v:
                    walk(f"{prefix}_{_clean(v['name'])}", v["celsius"])
                else:
                    walk(f"{prefix}_{i}", v)
        elif _is_number(value):
            out[prefix] = value
        elif value is None:
            out[prefix] = None
        # strings and bools are not readings: skipped

    for key, value in (sample or {}).items():
        if key in ("time", "luid"):
            continue
        walk(_clean(key), value)
    # identifiers that slipped in as numbers are not readings
    for k in [k for k in out if k.endswith("_luid")]:
        del out[k]
    return out


class SensorLogger:
    """Thread-safe CSV writer. write(sample) returns True when a row was written."""

    def __init__(self, path):
        self.path = Path(path)
        self._fh = None
        self._writer = None
        self._columns = None
        self._lock = threading.Lock()
        self.rows = 0
        self.dropped_keys = set()

    @property
    def active(self):
        return self._fh is not None

    def start(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # utf-8-sig so Excel opens it cleanly
        self._fh = open(self.path, "w", newline="", encoding="utf-8-sig")
        self._writer = csv.writer(self._fh)
        self._columns = None
        self.rows = 0
        self.dropped_keys = set()

    def write(self, sample, when=None):
        with self._lock:
            if self._fh is None:
                return False
            flat = flatten_sample(sample)
            if self._columns is None:
                self._columns = list(flat.keys())
                self._writer.writerow(["timestamp"] + self._columns)
            else:
                self.dropped_keys.update(k for k in flat if k not in self._columns)
            ts = (when or datetime.now()).isoformat(timespec="seconds")
            self._writer.writerow([ts] + [("" if flat.get(c) is None else flat[c])
                                          for c in self._columns])
            self._fh.flush()
            self.rows += 1
            return True

    def stop(self):
        with self._lock:
            if self._fh is not None:
                try:
                    self._fh.flush()
                    os.fsync(self._fh.fileno())
                except OSError:
                    pass
                self._fh.close()
            self._fh = None
            self._writer = None
