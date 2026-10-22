# core/nettest.py
"""DNS speed test and ping test. Real measurements only (CLAUDE.md section 8).

DNS speed test
- Sends standard DNS queries (UDP port 53) straight to each server, so Windows' own DNS
  cache is not involved.
- Two kinds of lookups:
  * "Popular sites": names a DNS server has usually cached. Shows everyday speed.
  * "Uncached": random names that can't be in any cache, so the server must look them up
    from scratch. Shows worst-case speed.
- Results are for this PC, on this network, right now.

Ping test
- ICMP echo to 1.1.1.1 (or 1.0.0.1) using Windows' IcmpSendEcho (no admin needed, and it
  doesn't depend on the language of ping.exe's output).
- Reports average, best, worst, jitter (average change between consecutive pings) and loss.
"""

import random
import socket
import string
import struct
import time

from core.winutil import IS_WINDOWS

POPULAR = ["google.com", "youtube.com", "epicgames.com", "minecraft.net", "discord.com"]
UNCACHED_PARENTS = ["google.com", "microsoft.com", "amazon.com", "cloudflare.com", "apple.com"]
PRESET_SERVERS = [("Cloudflare", "1.1.1.1"), ("Google", "8.8.8.8"), ("Quad9", "9.9.9.9")]
PING_TARGETS = ["1.1.1.1", "1.0.0.1"]


# ---------------------------------------------------------------- DNS

def build_query(name, qid):
    header = struct.pack(">HHHHHH", qid, 0x0100, 1, 0, 0, 0)  # recursion desired, 1 question
    qname = b"".join(bytes([len(p)]) + p.encode("ascii") for p in name.split(".")) + b"\x00"
    return header + qname + struct.pack(">HH", 1, 1)           # type A, class IN


def parse_response(data, qid):
    """Returns the DNS response code (0 = found, 3 = name doesn't exist) or None if invalid."""
    if len(data) < 12:
        return None
    rid, flags = struct.unpack(">HH", data[:4])
    if rid != qid or not flags & 0x8000:   # must be a response to OUR query
        return None
    return flags & 0x000F


def time_lookup(server, name, timeout=2.0):
    """One lookup. Returns milliseconds, or None if it failed or timed out."""
    family = socket.AF_INET6 if ":" in server else socket.AF_INET
    qid = random.randint(0, 0xFFFF)
    with socket.socket(family, socket.SOCK_DGRAM) as s:
        s.settimeout(timeout)
        try:
            start = time.perf_counter()
            s.sendto(build_query(name, qid), (server, 53))
            while True:
                data, _ = s.recvfrom(4096)
                rcode = parse_response(data, qid)
                if rcode is not None:
                    elapsed = (time.perf_counter() - start) * 1000
                    # 0 = found, 3 = doesn't exist (expected for random names); others = server error
                    return elapsed if rcode in (0, 3) else None
        except (socket.timeout, OSError):
            return None


def _random_name():
    label = "rytweaks-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
    return f"{label}.{random.choice(UNCACHED_PARENTS)}"


def summarize(times):
    ok = [t for t in times if t is not None]
    return {"avg": sum(ok) / len(ok) if ok else None, "best": min(ok) if ok else None,
            "worst": max(ok) if ok else None, "failed": len(times) - len(ok), "count": len(times)}


def dns_speed_test(servers, rounds=2, progress=None):
    """servers: [(label, ip)]. Returns [{label, ip, popular: summary, uncached: summary}].
    rounds x 5 popular + rounds x 5 uncached lookups per server."""
    results = []
    total = len(servers) * rounds * (len(POPULAR) + len(UNCACHED_PARENTS))
    done = 0
    for label, ip in servers:
        pop, unc = [], []
        for _ in range(rounds):
            for name in POPULAR:
                pop.append(time_lookup(ip, name))
                done += 1
                if progress:
                    progress(done, total)
            for _ in UNCACHED_PARENTS:
                unc.append(time_lookup(ip, _random_name()))
                done += 1
                if progress:
                    progress(done, total)
        results.append({"label": label, "ip": ip, "popular": summarize(pop), "uncached": summarize(unc)})
    return results


DNS_METHOD = ("Method: {n} lookups per server sent directly to it (Windows' DNS cache isn't used): "
              "half are popular sites the server has likely cached, half are random names that can't be "
              "cached, so the server has to look them up from scratch. Results are for this PC, on this "
              "network, right now.")


# ---------------------------------------------------------------- ping (ICMP)

def jitter(times):
    ok = [t for t in times if t is not None]
    if len(ok) < 2:
        return None
    return sum(abs(b - a) for a, b in zip(ok, ok[1:])) / (len(ok) - 1)


def _icmp_ping_windows(ip, count, interval, timeout_ms, progress=None):
    import ctypes
    from ctypes import wintypes

    class IP_OPTION_INFORMATION(ctypes.Structure):
        _fields_ = [("Ttl", ctypes.c_ubyte), ("Tos", ctypes.c_ubyte), ("Flags", ctypes.c_ubyte),
                    ("OptionsSize", ctypes.c_ubyte), ("OptionsData", ctypes.c_void_p)]

    class ICMP_ECHO_REPLY(ctypes.Structure):
        _fields_ = [("Address", wintypes.ULONG), ("Status", wintypes.ULONG), ("RoundTripTime", wintypes.ULONG),
                    ("DataSize", wintypes.USHORT), ("Reserved", wintypes.USHORT), ("Data", ctypes.c_void_p),
                    ("Options", IP_OPTION_INFORMATION)]

    iphlpapi = ctypes.WinDLL("iphlpapi")
    iphlpapi.IcmpCreateFile.restype = wintypes.HANDLE
    iphlpapi.IcmpSendEcho.argtypes = [wintypes.HANDLE, wintypes.ULONG, ctypes.c_void_p, wintypes.WORD,
                                      ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD]
    iphlpapi.IcmpSendEcho.restype = wintypes.DWORD
    iphlpapi.IcmpCloseHandle.argtypes = [wintypes.HANDLE]

    handle = iphlpapi.IcmpCreateFile()
    if not handle or handle == wintypes.HANDLE(-1).value:
        raise OSError("Windows couldn't open an ICMP handle.")
    dest = int.from_bytes(socket.inet_aton(ip), "little")   # IPAddr is network byte order in memory
    payload = b"RYTWEAKS ping test 32 bytes....."
    reply_size = ctypes.sizeof(ICMP_ECHO_REPLY) + len(payload) + 8
    buf = ctypes.create_string_buffer(reply_size)
    times = []
    try:
        for i in range(count):
            n = iphlpapi.IcmpSendEcho(handle, dest, payload, len(payload), None, buf, reply_size, timeout_ms)
            reply = ICMP_ECHO_REPLY.from_buffer_copy(buf.raw[:ctypes.sizeof(ICMP_ECHO_REPLY)])
            times.append(float(reply.RoundTripTime) if n and reply.Status == 0 else None)
            if progress:
                progress(i + 1, count)
            if i + 1 < count:
                time.sleep(interval)
    finally:
        iphlpapi.IcmpCloseHandle(handle)
    return times


def ping_test(target="1.1.1.1", count=20, interval=0.25, timeout_ms=1000, progress=None):
    """Returns dict with avg/best/worst/jitter/loss_pct/count, or {'error': ...}."""
    if target not in PING_TARGETS:
        return {"error": "Ping tests use 1.1.1.1 or 1.0.0.1."}
    if not IS_WINDOWS:
        return {"error": "The ping test needs Windows."}
    try:
        times = _icmp_ping_windows(target, count, interval, timeout_ms, progress)
    except Exception as e:
        return {"error": str(e)}
    s = summarize(times)
    return {"target": target, "avg": s["avg"], "best": s["best"], "worst": s["worst"],
            "jitter": jitter(times), "loss_pct": 100.0 * s["failed"] / count, "count": count}


PING_METHOD = ("Method: {count} ICMP pings to {target}, {interval:.2f} s apart, 1 s timeout. Windows reports "
               "ping times in whole milliseconds. This measures your connection to Cloudflare's network, "
               "not to a specific game server, so in-game ping can be different.")
