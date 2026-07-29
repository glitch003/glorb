"""Minimal sACN / E1.31 (ANSI E1.31-2016) packet sender — pure stdlib.

Each Angio owns one pixel space packed 170 px/universe from its start
universe (WLED "Multi" mode; see tube-map.json). Sends by multicast
(default, no device IPs needed) or unicast to a specific Angio.
"""

import socket
import struct
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
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((host, E131_PORT))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def multicast_addr(universe: int) -> str:
    """239.255.<hi>.<lo> per E1.31 for universes 1..63999."""
    return f"239.255.{(universe >> 8) & 0xFF}.{universe & 0xFF}"


def build_packet(universe: int, dmx: bytes, sequence: int,
                 cid: bytes, source_name: str = "glorb") -> bytes:
    """Build one E1.31 data packet. dmx is up to 512 channel bytes."""
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

    def __init__(self, host: str | None = None, iface: str | None = None,
                 source_name: str = "glorb", cid: bytes | None = None):
        self.host = host
        self.source_name = source_name
        self.cid = cid or uuid.uuid4().bytes
        self._seq: dict[int, int] = {}
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 8)
        if iface:
            self.sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                                 socket.inet_aton(iface))

    def send(self, universe: int, dmx: bytes) -> None:
        seq = (self._seq.get(universe, 0) + 1) & 0xFF
        self._seq[universe] = seq
        pkt = build_packet(universe, dmx, seq, self.cid, self.source_name)
        dest = self.host or multicast_addr(universe)
        self.sock.sendto(pkt, (dest, E131_PORT))

    def close(self) -> None:
        self.sock.close()


def send_span(sender, start_universe: int, data: bytes) -> None:
    """Send one Angio's whole pixel space, split at 170-px universes."""
    for i in range(0, len(data), UNIVERSE_BYTES):
        sender.send(start_universe + i // UNIVERSE_BYTES,
                    data[i:i + UNIVERSE_BYTES])
