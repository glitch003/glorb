"""Maps tube-map.json onto the controller and renders test patterns.

Works with any sender exposing send_pixels(start_universe, data):
ddp.DDPSender (preferred) or e131.Sender (multicast fallback).
"""

import json
import time
from pathlib import Path

from .e131 import Sender

DEFAULT_MAP = Path(__file__).resolve().parent.parent / "tube-map.json"

# Per-tube distinct colors for the "tubes" test (one per receiver output).
TUBE_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
COLORCHECK = [("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
              ("BLUE", (0, 0, 255)), ("WHITE", (255, 255, 255))]


def load_map(path=DEFAULT_MAP) -> dict:
    return json.loads(Path(path).read_text())


def normalize_receiver(token) -> int:
    """'R7' / 'r7' / '7' / 7 -> 7."""
    return int(str(token).upper().lstrip("R"))


class Show:
    """Install-time test patterns, addressed by receiver (4 tubes)."""

    def __init__(self, sender: Sender, gmap: dict,
                 brightness: float = 1.0, color_order: str = "RGB"):
        self.sender = sender
        self.map = gmap
        self.brightness = max(0.0, min(1.0, brightness))
        self.color_order = color_order.upper()
        self._by_receiver = {r["id"]: r for r in gmap["receivers"]}
        self.pix_per_tube = gmap["meta"]["pixels_per_tube"]
        # One controller = one flat pixel space, and universes are shared
        # across receivers, so keep a whole-car buffer and always transmit
        # the full span. Receivers not touched this session go out as black.
        self.start_universe = gmap["controller"]["start_universe"]
        self._buf = bytearray(gmap["meta"]["total_pixels"] * 3)

    # --- lookups ---
    def receiver(self, token) -> dict:
        n = normalize_receiver(token)
        if n not in self._by_receiver:
            raise KeyError(f"receiver R{n} not in map "
                           f"(have R1..R{len(self._by_receiver)})")
        return self._by_receiver[n]

    def receivers_for_zone(self, zone: str) -> list[dict]:
        z = zone.upper()
        return [r for r in self.map["receivers"] if r["zone"].upper() == z]

    def all_receivers(self) -> list[dict]:
        return list(self.map["receivers"])

    # --- rendering ---
    def _pixel_bytes(self, rgb) -> bytes:
        r, g, b = (int(c * self.brightness) & 0xFF for c in rgb)
        ch = {"R": r, "G": g, "B": b}
        return bytes(ch[c] for c in self.color_order)

    def _frame(self, pixels) -> bytes:
        return b"".join(self._pixel_bytes(p) for p in pixels)

    def _send(self, recv: dict, pixels) -> None:
        frame = self._frame(pixels)
        off = recv["start_channel"] - 1
        self._buf[off:off + len(frame)] = frame
        # send_pixels ends each frame with a latch (DDP push / E1.31 sync)
        # so fppd outputs it immediately and whole (see ddp.py).
        self.sender.send_pixels(self.start_universe, bytes(self._buf))

    # --- static patterns ---
    def solid(self, token, rgb=(255, 255, 255)) -> None:
        r = self.receiver(token)
        self._send(r, [rgb] * r["pixels"])

    def off(self, token) -> None:
        self.solid(token, (0, 0, 0))

    def per_tube(self, token) -> None:
        """Each tube a distinct color — confirms which output feeds which tube."""
        r = self.receiver(token)
        pixels = []
        for i in range(r["tube_count"]):
            pixels += [TUBE_COLORS[i % len(TUBE_COLORS)]] * self.pix_per_tube
        self._send(r, pixels)
        order = ", ".join(f"out{o['output']} {o['tube']}={n}"
                          for o, n in zip(r["outputs"],
                                          ("RED", "GREEN", "BLUE", "WHITE")))
        print(f"R{r['id']}: {order}")

    # --- animated patterns (Ctrl-C to stop) ---
    def colorcheck(self, token, hold: float = 1.5) -> None:
        """Cycle R/G/B/W on the whole receiver; prints expected color."""
        r = self.receiver(token)
        print(f"R{r['id']} color-order check ({self.color_order}). "
              "Watch the tubes match the printed color; Ctrl-C to stop.")
        try:
            while True:
                for name, rgb in COLORCHECK:
                    print(f"  expect {name}")
                    self._send(r, [rgb] * r["pixels"])
                    time.sleep(hold)
        except KeyboardInterrupt:
            self.off(token)
            print("stopped.")

    def chase(self, token, fps: float = 40.0, comet: int = 4,
              rgb=(255, 255, 255)) -> None:
        """Comet walks the receiver's 4 tubes in output order — confirms
        pixel count and that each tube runs top-to-bottom."""
        r = self.receiver(token)
        n = r["pixels"]
        period = 1.0 / fps
        print(f"R{r['id']} chase over {n} px ({r['tube_count']} tubes, "
              f"{' -> '.join(r['tubes'])}). Ctrl-C to stop.")
        try:
            head = 0
            while True:
                pixels = [(0, 0, 0)] * n
                for k in range(comet):
                    idx = head - k
                    if 0 <= idx < n:
                        fade = int(255 * (1 - k / comet))
                        pixels[idx] = tuple(v * fade // 255 for v in rgb)
                self._send(r, pixels)
                head = (head + 1) % (n + comet)
                time.sleep(period)
        except KeyboardInterrupt:
            self.off(token)
            print("stopped.")
