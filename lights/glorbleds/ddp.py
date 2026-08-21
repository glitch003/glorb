"""Minimal DDP (Distributed Display Protocol) sender — pure stdlib.

This is the preferred transport to the K128D, and the fix for the flicker
that appeared with the move from WLED to FPP.

Why: FPP's bridge mode free-runs its channel outputs on a 50 ms timer
(E131BridgingInterval, i.e. 20 fps) and latches whatever is in channel
memory whenever it fires — incoming E1.31 data packets do NOT trigger an
output. A 30 fps stream beats against that 20 fps clock (frames dropped and
doubled at ~10 Hz) and the latch regularly lands mid-way through a frame's
packet burst (a torn frame). On moving patterns that reads as flicker and
judder. WLED applied packets as they arrived, which is why the Angio boards
never showed it.

A DDP packet with the PUSH flag makes fppd latch the frame IMMEDIATELY
(src/e131bridge.cpp: Bridge_StoreDDPData returns true, and the main loop
calls ForceChannelOutputNow). So each frame here ends with a pushed packet
and the sender paces the LEDs; the 50 ms free-run timer never fires as long
as frames keep arriving faster than it. Bonus over E1.31: unicast (no
multicast/IGMP in the show path) and ~12 packets per frame instead of 32.

FPP listens on UDP 4048 whenever bridging is enabled; no input config is
needed. DDP offset n lands on FPP channel n+1, which matches our flat pixel
space exactly (tube k starts at channel k*120+1 = offset k*120).
"""

import socket
import time

DDP_PORT = 4048
# Data bytes per packet: the spec ceiling is 1440 and it is already a
# multiple of 3, so packets split on whole RGB pixels (480 px).
MAX_DATA = 1440

_FLAG_VER1 = 0x40
_FLAG_PUSH = 0x01
_TYPE_RGB = 0x01
_DEST_DEFAULT = 0x01     # default output device


def build_packet(offset: int, data: bytes, sequence: int,
                 push: bool) -> bytes:
    """One DDP data packet. offset is the 0-based channel offset
    (FPP channel = offset + 1); sequence must cycle 1..15."""
    if not 0 < len(data) <= MAX_DATA:
        raise ValueError(f"DDP data length must be 1..{MAX_DATA}")
    if not 0 <= offset <= 0xFFFFFFFF:
        raise ValueError("DDP offset out of range")
    flags = _FLAG_VER1 | (_FLAG_PUSH if push else 0)
    return (bytes((flags, sequence & 0x0F, _TYPE_RGB, _DEST_DEFAULT))
            + offset.to_bytes(4, "big")
            + len(data).to_bytes(2, "big")
            + data)


class DDPSender:
    """Unicast UDP sender for DDP. One send_pixels() call per frame."""

    # Same rationale as e131.Sender: a frame's packets go out back-to-back
    # and must not stall the animation thread or silently vanish.
    SNDBUF = 512 * 1024
    RETRY_BUDGET_S = 0.004
    RETRY_SLEEP_S = 0.0002

    def __init__(self, host: str):
        if not host:
            raise ValueError("DDP is unicast: a controller host is required")
        self.host = host
        # fppd validates the 1..15 sequence per PACKET (0 disables the
        # check, but then we lose the receiver-side loss counter).
        self._seq = 0
        self.dropped_packets = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        try:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF,
                                 self.SNDBUF)
        except OSError:
            pass          # kernel cap is fine; the retry below covers it

    def send_pixels(self, start_universe: int, data: bytes) -> None:
        """One whole frame. start_universe keeps the e131.Sender signature:
        the flat pixel space starts at (start_universe-1)*510 channels in,
        i.e. offset 0 for universe 1. The LAST packet carries PUSH, so fppd
        latches the frame the instant it is complete."""
        offset = (start_universe - 1) * 510
        last = len(data) - 1
        for i in range(0, len(data), MAX_DATA):
            chunk = data[i:i + MAX_DATA]
            self._seq = self._seq % 15 + 1
            pkt = build_packet(offset + i, chunk, self._seq,
                               push=i + len(chunk) > last)
            self._transmit(pkt)

    def _transmit(self, pkt: bytes) -> None:
        deadline = time.monotonic() + self.RETRY_BUDGET_S
        while True:
            try:
                self.sock.sendto(pkt, (self.host, DDP_PORT))
                return
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    # Drop this packet only; the rest of the frame still goes
                    # out. If the PUSH packet is the casualty, fppd's 50 ms
                    # free-run timer still outputs the frame, just late.
                    self.dropped_packets += 1
                    return
                time.sleep(self.RETRY_SLEEP_S)
            except OSError:
                # "Host is down" / unreachable — the controller is off or
                # rebooting (bench reality: it shares a power strip with the
                # tubes). Count it and keep animating; frames resume flowing
                # the moment the board is back, no restart needed.
                self.dropped_packets += 1
                return

    def close(self) -> None:
        self.sock.close()
