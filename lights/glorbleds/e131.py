"""Minimal sACN / E1.31 (ANSI E1.31-2016) packet sender — pure stdlib.

The whole car is one pixel space on one K128D controller, packed
170 px/universe (510 ch) from universe 1 — see tube-map.json. Sends by
multicast (default, no device IP needed) or unicast to the controller.
FPP's E1.31 bridge input maps those universes onto its 128 string outputs.
"""

import socket
import struct
import time
import uuid

E131_PORT = 5568
PX_PER_UNIVERSE = 170
UNIVERSE_BYTES = PX_PER_UNIVERSE * 3
_ACN_PID = b"ASC-E1.17\x00\x00\x00"
_VECTOR_ROOT = 0x00000004
_VECTOR_FRAMING = 0x00000002
_VECTOR_DMP = 0x02


def iface_for(host: str) -> str | None:
    """Local IP of the interface that routes to host (for multicast pinning)."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((host, E131_PORT))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        if s is not None:
            s.close()


def resolve_controller(controller: dict, timeout: float = 0.4) -> str | None:
    """Best host string for reaching the controller: prefer the mapped IP,
    fall back to mDNS on `hostname` if the IP is unreachable (lease changed,
    board moved networks, etc.). Returns None if nothing resolves."""
    ip = controller.get("ip")
    if ip and _reachable(ip, 80, timeout):
        return ip
    host = controller.get("hostname")
    if host:
        try:
            return socket.gethostbyname(host)
        except OSError:
            pass
    return ip  # last resort — may be offline, but at least routes correctly


def _reachable(host: str, port: int, timeout: float) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def multicast_addr(universe: int) -> str:
    """239.255.<hi>.<lo> per E1.31 for universes 1..63999."""
    return f"239.255.{(universe >> 8) & 0xFF}.{universe & 0xFF}"


def build_packet(universe: int, dmx: bytes, sequence: int,
                 cid: bytes, source_name: str = "glorb") -> bytes:
    """Build one E1.31 data packet. dmx is up to 512 channel bytes."""
    if not 1 <= universe <= 63999:
        raise ValueError("E1.31 universe must be in the range 1..63999")
    if len(cid) != 16:
        raise ValueError("E1.31 CID must be exactly 16 bytes")
    if len(dmx) > 512:
        raise ValueError("DMX data exceeds 512 channels")
    dmx = dmx.ljust(512, b"\x00")          # pad to a full universe
    prop_vals = b"\x00" + dmx              # DMX start code + data
    prop_count = len(prop_vals)

    total = 125 + prop_count          # 38 root + 77 framing + 10 dmp fixed
    root_len = total - 16
    framing_len = total - 38
    dmp_len = total - 115

    name = source_name.encode("utf-8")[:63].ljust(64, b"\x00")

    pkt = bytearray()
    # --- Root layer ---
    pkt += struct.pack("!HH", 0x0010, 0x0000)   # preamble / postamble
    pkt += _ACN_PID
    pkt += struct.pack("!H", 0x7000 | root_len)
    pkt += struct.pack("!I", _VECTOR_ROOT)
    pkt += cid
    # --- Framing layer ---
    pkt += struct.pack("!H", 0x7000 | framing_len)
    pkt += struct.pack("!I", _VECTOR_FRAMING)
    pkt += name
    pkt += struct.pack("!B", 100)               # priority
    pkt += struct.pack("!H", 0)                 # sync universe
    pkt += struct.pack("!B", sequence & 0xFF)
    pkt += struct.pack("!B", 0)                 # options
    pkt += struct.pack("!H", universe)
    # --- DMP layer ---
    pkt += struct.pack("!H", 0x7000 | dmp_len)
    pkt += struct.pack("!B", _VECTOR_DMP)
    pkt += struct.pack("!B", 0xA1)              # addr+data type
    pkt += struct.pack("!H", 0x0000)            # first prop addr
    pkt += struct.pack("!H", 0x0001)            # addr increment
    pkt += struct.pack("!H", prop_count)
    pkt += prop_vals
    return bytes(pkt)


class Sender:
    """UDP sender for E1.31. Multicast by default; pass host for unicast."""

    # A whole 32-universe frame is ~20 KB of packets emitted back-to-back,
    # but the default UDP send buffer is ~9 KB on macOS, so a frame reliably
    # overruns it mid-burst. Ask for room for several frames.
    SNDBUF = 512 * 1024
    # If the buffer still fills, briefly retry rather than abandoning the rest
    # of the frame: a torn frame (some universes updated, some not) looks worse
    # on the tubes than one arriving a few hundred microseconds late.
    RETRY_BUDGET_S = 0.004
    RETRY_SLEEP_S = 0.0002

    def __init__(self, host: str | None = None, iface: str | None = None,
                 source_name: str = "glorb", cid: bytes | None = None):
        self.host = host
        self.source_name = source_name
        self.cid = cid or uuid.uuid4().bytes
        self._seq: dict[int, int] = {}
        self.dropped_packets = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Never let a congested UDP socket stall animation/control threads.
        # A skipped frame is preferable to replaying stale LED data.
        self.sock.setblocking(False)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF,
                                 self.SNDBUF)
        except OSError:
            pass          # kernel cap is fine; the retry below covers it
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8)
        if iface:
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                 socket.inet_aton(iface))

    def send(self, universe: int, dmx: bytes) -> None:
        seq = (self._seq.get(universe, 0) + 1) & 0xFF
        self._seq[universe] = seq
        pkt = build_packet(universe, dmx, seq, self.cid, self.source_name)
        dest = self.host or multicast_addr(universe)
        deadline = time.monotonic() + self.RETRY_BUDGET_S
        while True:
            try:
                self.sock.sendto(pkt, (dest, E131_PORT))
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    # Give up on this packet only, so the rest of the frame
                    # still goes out. Callers can watch dropped_packets.
                    self.dropped_packets += 1
                    return
                time.sleep(self.RETRY_SLEEP_S)

    def close(self) -> None:
        self.sock.close()


def send_span(sender, start_universe: int, data: bytes) -> None:
    """Send a whole pixel space, split at 170-px (510-channel) universes."""
    for i in range(0, len(data), UNIVERSE_BYTES):
        sender.send(start_universe + i // UNIVERSE_BYTES,
                    data[i:i + UNIVERSE_BYTES])
