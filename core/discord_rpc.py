# core/discord_rpc.py
"""Discord status ("Rich Presence") through Discord's local IPC.

RETWEAKS only talks to the Discord app on this PC (a named pipe on Windows).
Nothing is sent over the network by RETWEAKS itself. No extra dependency.

Wire format (Discord RPC): every frame is  <opcode: uint32 LE><length: uint32 LE><JSON, UTF-8>.
Opcodes: 0 HANDSHAKE, 1 FRAME, 2 CLOSE, 3 PING, 4 PONG.
"""

import json
import os
import re
import socket
import struct
import sys
import threading
import time
import uuid

# Public Discord Application ID (not a secret). The owner supplies it.
# While it is empty the feature reports "Not set up yet" and never connects.
DISCORD_APP_ID = "1562695957651521627"   # public Discord Application ID for RETWEAKS (not a secret)

OP_HANDSHAKE, OP_FRAME, OP_CLOSE, OP_PING, OP_PONG = 0, 1, 2, 3, 4
RETRY_SECONDS = 15.0          # reconnect interval when Discord isn't running
UPDATE_SECONDS = 15.0         # minimum gap between SET_ACTIVITY calls (Discord rate limit)
MAX_FRAME = 1 << 20           # refuse absurd frames from a broken peer
RELEASES_URL = "https://github.com/w1zr/retweaks/releases/latest"

STATUS_TEXT = {
    "off": "Off",
    "not_set_up": "Not set up yet",
    "waiting": "Waiting for Discord (it doesn't seem to be running)",
    "connected": "Connected to Discord",
}


def status_text(status):
    if status.startswith("error:"):
        return "Discord problem: " + status[6:].strip()
    return STATUS_TEXT.get(status, status)


# ---------------------------------------------------------------- frames

def pack_frame(opcode, payload):
    data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return struct.pack("<II", opcode, len(data)) + data


def unpack_header(header):
    if len(header) != 8:
        raise ValueError("short frame header")
    opcode, length = struct.unpack("<II", header)
    if length > MAX_FRAME:
        raise ValueError("frame too large")
    return opcode, length


def unpack_frame(raw):
    """Parse one complete frame from bytes -> (opcode, payload dict)."""
    opcode, length = unpack_header(raw[:8])
    body = raw[8:8 + length]
    if len(body) != length:
        raise ValueError("truncated frame")
    return opcode, (json.loads(body.decode("utf-8")) if body else {})


# ---------------------------------------------------------------- activity text

def _clip(text, limit=128):
    """Discord wants 2-128 characters for details/state."""
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[:limit - 1].rstrip() + "…"
    return text.ljust(2) if len(text) < 2 else text


_KNOWN = [
    ("fortniteclient", "Fortnite"), ("fortnite", "Fortnite"),
    ("javaw", "Minecraft"), ("minecraft", "Minecraft"),
    ("r5apex", "Apex Legends"), ("rocketleague", "Rocket League"),
    ("cs2", "Counter-Strike 2"),
]


def friendly_game_name(exe):
    """'...\\FortniteClient-Win64-Shipping.exe' or 'FortniteClient-Win64-Shipping' -> 'Fortnite'."""
    if not exe:
        return None
    base = re.split(r"[\\/]", str(exe).strip())[-1]
    stem = re.sub(r"\.exe$", "", base, flags=re.I)
    low = stem.lower()
    for key, name in _KNOWN:
        if low.startswith(key):
            return name
    stem = re.sub(r"[-_ ]?(win(32|64)?|x64|x86|shipping|client)\b", "", stem, flags=re.I)
    stem = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", stem.replace("_", " ").replace("-", " ")).strip()
    return stem or None


def parse_game_event(event):
    """AutoGameWorker event text -> ('started'|'closed', rule name) or None.
    Only the exact '<name> started.' / '<name> closed.' lines count."""
    m = re.match(r"^(.+) (started|closed)\.$", str(event).strip())
    if not m or m.group(1).startswith("Background calming"):
        return None
    return m.group(2), m.group(1)


def build_activity(state, show_game, start_ts):
    game = (state or {}).get("game")
    if game and show_game:
        details = "Gaming: " + game
    elif game:
        details = "Gaming"
    else:
        details = "Optimizing with RETWEAKS"
    sub = "Boosted by RETWEAKS" if game else "Windows PC tweaks"
    return {
        "details": _clip(details),
        "state": _clip(sub),
        "timestamps": {"start": int(start_ts)},
        "assets": {"large_image": "rytweaks", "large_text": "RETWEAKS"},
        "buttons": [{"label": "Get RETWEAKS", "url": RELEASES_URL}],
    }


# ---------------------------------------------------------------- transports

class _FileTransport:
    def __init__(self, f):
        self.f = f

    def write(self, data):
        self.f.write(data)

    def read(self, n):
        return self.f.read(n)

    def close(self):
        try:
            self.f.close()
        except Exception:
            pass


class _SocketTransport:
    def __init__(self, s):
        self.s = s

    def write(self, data):
        self.s.sendall(data)

    def read(self, n):
        return self.s.recv(n)

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def open_discord_ipc():
    """Try discord-ipc-0..9. Returns a transport or raises OSError if Discord isn't running."""
    last = None
    for i in range(10):
        try:
            if sys.platform == "win32":
                return _FileTransport(open(r"\\?\pipe\discord-ipc-%d" % i, "r+b", buffering=0))
            base = (os.environ.get("XDG_RUNTIME_DIR") or os.environ.get("TMPDIR")
                    or os.environ.get("TMP") or "/tmp")
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                s.connect(os.path.join(base, "discord-ipc-%d" % i))
            except OSError:
                s.close()
                raise
            return _SocketTransport(s)
        except OSError as e:
            last = e
    raise last or OSError("Discord IPC not found")


def _read_exact(tr, n):
    buf = b""
    while len(buf) < n:
        chunk = tr.read(n - len(buf))
        if not chunk:
            raise OSError("Discord closed the connection")
        buf += chunk
    return buf


def read_frame(tr):
    opcode, length = unpack_header(_read_exact(tr, 8))
    body = _read_exact(tr, length) if length else b""
    return opcode, (json.loads(body.decode("utf-8")) if body else {})


class DiscordError(Exception):
    """Discord answered, but with an error (shown to the user as 'error: ...')."""


# ---------------------------------------------------------------- presence

class DiscordPresence:
    """Background presence worker. All methods are cheap and never block the UI thread.

    opener/clock/app_id are injectable for tests. step() is one loop iteration.
    """

    def __init__(self, app_id=None, opener=None, clock=None, pid=None):
        self._app_id = DISCORD_APP_ID if app_id is None else app_id
        self._open = opener or open_discord_ipc
        self._clock = clock or time.time
        self._pid = pid or os.getpid()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread = None
        self._stop = False
        self._enabled = False
        self._show_game = True
        self._game = None
        self._app_start = int(self._clock())
        self._game_start = None
        self._conn = None
        self._status = "off"
        self._next_connect = 0.0
        self._next_send = 0.0
        self._sent = None            # last activity dict sent (None = nothing / cleared)
        self._want_clear = False

    # ---- public API
    @property
    def status(self):
        with self._lock:
            return self._status

    def configure(self, enabled, show_game=True):
        with self._lock:
            was = self._enabled
            self._enabled = bool(enabled)
            self._show_game = bool(show_game)
            if self._enabled and not was:
                self._next_connect = 0.0
            if not self._enabled and was:
                self._want_clear = True
            self._status = self._idle_status()
        self._wake.set()

    def set_game(self, name):
        name = name or None
        with self._lock:
            if name != self._game:
                self._game = name
                self._game_start = int(self._clock()) if name else None
        self._wake.set()

    def start(self):
        """Idempotent."""
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop = False
            self._thread = threading.Thread(target=self._run, name="DiscordPresence", daemon=True)
            self._thread.start()

    def stop(self, timeout=2.0):
        """Idempotent. Clears the status and closes the connection."""
        with self._lock:
            t = self._thread
            self._stop = True
            self._thread = None
        self._wake.set()
        if t and t.is_alive() and t is not threading.current_thread():
            t.join(timeout)
        self._shutdown(self._clock())

    # ---- internals
    def _idle_status(self):
        if not self._app_id:
            return "not_set_up"
        if not self._enabled:
            return "off"
        return self._status if self._status in ("connected", "waiting") or \
            self._status.startswith("error:") else "waiting"

    def _wanted_activity(self):
        with self._lock:
            start = self._game_start if self._game else self._app_start
            return build_activity({"game": self._game}, self._show_game, start or self._app_start)

    def _set_status(self, s):
        with self._lock:
            self._status = s

    def _send_activity(self, activity):
        payload = {"cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
                   "args": {"pid": self._pid, "activity": activity}}
        self._conn.write(pack_frame(OP_FRAME, payload))
        _, reply = read_frame(self._conn)
        if reply.get("evt") == "ERROR":
            raise DiscordError((reply.get("data") or {}).get("message", "Discord refused the status"))

    def _connect(self):
        conn = self._open()
        try:
            conn.write(pack_frame(OP_HANDSHAKE, {"v": 1, "client_id": str(self._app_id)}))
            op, reply = read_frame(conn)
            if op == OP_CLOSE:
                raise DiscordError(reply.get("message") or "Discord closed the connection")
            if reply.get("evt") != "READY":
                raise DiscordError("unexpected reply from Discord")
        except Exception:
            conn.close()
            raise
        self._conn = conn

    def _drop(self):
        c, self._conn = self._conn, None
        if c:
            c.close()
        self._sent = None

    def _shutdown(self, now):
        """Clear the status (if connected) and close. Safe to call repeatedly."""
        c = self._conn
        if c:
            try:
                self._send_activity(None)
                c.write(pack_frame(OP_CLOSE, {}))
            except Exception:
                pass
        self._drop()
        with self._lock:
            self._status = "off" if self._app_id else "not_set_up"

    def step(self):
        """One iteration of the worker loop. Returns nothing; updates status."""
        now = self._clock()
        with self._lock:
            enabled, want_clear = self._enabled, self._want_clear
            self._want_clear = False
        if not self._app_id:
            self._set_status("not_set_up")
            return                                    # never connects
        if not enabled:
            if self._conn:
                self._shutdown(now)
            self._set_status("off")
            return
        if self._conn is None:
            if now < self._next_connect:
                return
            try:
                self._connect()
            except DiscordError as e:
                self._next_connect = now + RETRY_SECONDS
                self._set_status("error: " + str(e))
                return
            except Exception:                         # Discord not running: stay quiet
                self._next_connect = now + RETRY_SECONDS
                self._set_status("waiting")
                return
            self._next_send = 0.0
            self._set_status("connected")
        activity = self._wanted_activity()
        if activity != self._sent and now >= self._next_send:
            try:
                self._send_activity(activity)
                self._sent = activity
                self._next_send = now + UPDATE_SECONDS
                self._set_status("connected")
            except DiscordError as e:
                self._next_send = now + UPDATE_SECONDS
                self._set_status("error: " + str(e))
            except Exception:                         # pipe broke (Discord quit)
                self._drop()
                self._next_connect = now + RETRY_SECONDS
                self._set_status("waiting")

    def _run(self):
        while True:
            with self._lock:
                if self._stop:
                    return
            try:
                self.step()
            except Exception as e:                    # never let the thread die noisily
                self._set_status("error: " + str(e))
            self._wake.wait(1.0)
            self._wake.clear()
