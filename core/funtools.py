# core/funtools.py
"""Pure logic for the Fun tools page (no Qt, no Windows): easy to test.

All times are seconds from time.perf_counter() and are passed in by the caller.
"""

import random
from collections import deque

# A gap longer than this between two move events means the mouse stopped, so it is not
# part of a rate measurement.
MAX_GAP_S = 0.05
WINDOW_S = 5.0


class PollingMeter:
    """Rate of distinct mouse move events over a sliding window.

    current = rate over the most recent events, average = rate over the whole window,
    max = highest 'current' seen inside the window. Gaps over MAX_GAP_S are ignored.
    """

    RECENT = 20

    def __init__(self, window_s=WINDOW_S, max_gap_s=MAX_GAP_S):
        self.window_s = window_s
        self.max_gap_s = max_gap_s
        self._last = None
        self._intervals = deque()   # (timestamp, dt) of valid intervals
        self._currents = deque()    # (timestamp, current_hz)
        self.total_events = 0

    def reset(self):
        self.__init__(self.window_s, self.max_gap_s)

    def add(self, t):
        self.total_events += 1
        if self._last is not None:
            dt = t - self._last
            if 0 < dt <= self.max_gap_s:
                self._intervals.append((t, dt))
                cur = self.current()
                if cur is not None:
                    self._currents.append((t, cur))
        self._last = t
        self._trim(t)

    def _trim(self, now):
        lo = now - self.window_s
        while self._intervals and self._intervals[0][0] < lo:
            self._intervals.popleft()
        while self._currents and self._currents[0][0] < lo:
            self._currents.popleft()

    def current(self):
        if len(self._intervals) < 2:
            return None
        recent = [dt for _, dt in list(self._intervals)[-self.RECENT:]]
        return len(recent) / sum(recent)

    def average(self):
        if len(self._intervals) < 2:
            return None
        return len(self._intervals) / sum(dt for _, dt in self._intervals)

    def maximum(self):
        return max((c for _, c in self._currents), default=None)

    def stale(self, now):
        """True when no move event arrived recently (mouse stopped)."""
        return self._last is None or now - self._last > self.max_gap_s * 4


class CpsTest:
    """Counts clicks inside a fixed duration that starts on the first click."""

    def __init__(self, duration_s):
        self.duration = float(duration_s)
        self.start = None
        self.clicks = 0

    def click(self, t):
        """Register a click. Returns True if it counted (False once time is up)."""
        if self.start is None:
            self.start = t
        if t - self.start > self.duration:
            return False
        self.clicks += 1
        return True

    def elapsed(self, now):
        return 0.0 if self.start is None else min(now - self.start, self.duration)

    def finished(self, now):
        return self.start is not None and now - self.start >= self.duration

    def cps(self, now=None):
        """Clicks per second. While running uses elapsed time; when finished, the duration."""
        if self.start is None:
            return 0.0
        if now is None or self.finished(now):
            return self.clicks / self.duration
        el = max(now - self.start, 0.001)
        return self.clicks / el


def random_delay(rng=random):
    return rng.uniform(1.5, 5.0)


class ReactionTest:
    """Reaction test state machine.

    states: idle -> waiting -> ready -> shown (result of one try) ...; too_soon on early click;
    done after `tries` valid results.
    """

    def __init__(self, tries=5):
        self.tries = tries
        self.results_ms = []
        self.state = "idle"
        self.go_at = None
        self.shown_at = None
        self.last_ms = None

    def begin_try(self, now, delay=None):
        self.state = "waiting"
        self.go_at = now + (random_delay() if delay is None else delay)
        self.last_ms = None

    def tick(self, now, shown_at=None):
        """Call often. Moves waiting -> ready when the delay is over. Returns True on change."""
        if self.state == "waiting" and now >= self.go_at:
            self.state = "ready"
            self.shown_at = now if shown_at is None else shown_at
            return True
        return False

    def click(self, now):
        """Handle a click. Returns 'too_soon', 'result', or 'done' (or None if ignored)."""
        self.tick(now, shown_at=self.go_at)   # timer hadn't fired yet: the box turned at go_at
        if self.state == "waiting":
            self.state = "too_soon"
            return "too_soon"
        if self.state == "ready":
            self.last_ms = (now - self.shown_at) * 1000.0
            self.results_ms.append(self.last_ms)
            self.state = "done" if len(self.results_ms) >= self.tries else "shown"
            return self.state
        return None

    def reset(self):
        self.__init__(self.tries)

    def average_ms(self):
        return sum(self.results_ms) / len(self.results_ms) if self.results_ms else None

    def best_ms(self):
        return min(self.results_ms) if self.results_ms else None


def is_new_best(new, old, lower_is_better=False):
    if new is None:
        return False
    if old is None:
        return True
    return new < old if lower_is_better else new > old
