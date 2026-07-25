"""Maps tube-map.json onto E1.31 universes and renders test patterns."""

import json
import time
from pathlib import Path

from .e131 import Sender

DEFAULT_MAP = Path(__file__).resolve().parent.parent / "tube-map.json"

# Per-tube distinct colors for the "tubes" test (up to 4/group).
TUBE_COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 255)]
COLORCHECK = [("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
              ("BLUE", (0, 0, 255)), ("WHITE", (255, 255, 255))]


def load_map(path=DEFAULT_MAP) -> dict:
    return json.loads(Path(path).read_text())


def normalize_group(token) -> int:
    s = str(token).upper().lstrip("G")
    return int(s)


class Show:
    def __init__(self, sender: Sender, gmap: dict,
                 brightness: float = 0.3, color_order: str = "RGB"):
        self.sender = sender
        self.map = gmap
        self.brightness = max(0.0, min(1.0, brightness))
        self.color_order = color_order.upper()
        self._by_group = {g["group"]: g for g in gmap["groups"]}
        self.pix_per_tube = gmap["meta"]["pixels_per_tube"]

    # --- lookups ---
    def group(self, token) -> dict:
        n = normalize_group(token)
        if n not in self._by_group:
            raise KeyError(f"group G{n} not in map (have G1..G{len(self._by_group)})")
        return self._by_group[n]

    def groups_for_angio(self, angio: str) -> list[dict]:
        a = angio.upper()
        return [g for g in self.map["groups"] if g["angio"].upper() == a]

    def all_groups(self) -> list[dict]:
        return list(self.map["groups"])

    # --- rendering ---
    def _pixel_bytes(self, rgb) -> bytes:
        r, g, b = (int(c * self.brightness) & 0xFF for c in rgb)
        ch = {"R": r, "G": g, "B": b}
        return bytes(ch[c] for c in self.color_order)

    def _frame(self, pixels) -> bytes:
        return b"".join(self._pixel_bytes(p) for p in pixels)

    def _send(self, group: dict, pixels) -> None:
        self.sender.send(group["universe"], self._frame(pixels))

    # --- static patterns ---
    def solid(self, token, rgb=(255, 255, 255)) -> None:
        g = self.group(token)
        self._send(g, [rgb] * g["pixels"])

    def off(self, token) -> None:
        self.solid(token, (0, 0, 0))

    def per_tube(self, token) -> None:
        """Each tube a distinct color — confirms tube count + order."""
        g = self.group(token)
        pixels = []
        for i in range(g["tube_count"]):
            pixels += [TUBE_COLORS[i % len(TUBE_COLORS)]] * self.pix_per_tube
        self._send(g, pixels)

    # --- animated patterns (Ctrl-C to stop) ---
    def colorcheck(self, token, hold: float = 1.5) -> None:
        """Cycle R/G/B/W on the whole group; prints expected color."""
        g = self.group(token)
        print(f"G{g['group']} color-order check ({self.color_order}). "
              "Watch the tubes match the printed color; Ctrl-C to stop.")
        try:
            while True:
                for name, rgb in COLORCHECK:
                    print(f"  expect {name}")
                    self._send(g, [rgb] * g["pixels"])
                    time.sleep(hold)
        except KeyboardInterrupt:
            self.off(token)
            print("stopped.")

    def chase(self, token, fps: float = 40.0, comet: int = 4,
              rgb=(255, 255, 255)) -> None:
        """Single comet walks the chain — confirms pixel count + direction."""
        g = self.group(token)
        n = g["pixels"]
        period = 1.0 / fps
        print(f"G{g['group']} chase over {n} px ({g['tube_count']} tubes). "
              "Ctrl-C to stop.")
        try:
            head = 0
            while True:
                pixels = [(0, 0, 0)] * n
                for k in range(comet):
                    idx = head - k
                    if 0 <= idx < n:
                        fade = int(255 * (1 - k / comet))
                        pixels[idx] = tuple(v * fade // 255 for v in rgb)
                self._send(g, pixels)
                head = (head + 1) % (n + comet)
                time.sleep(period)
        except KeyboardInterrupt:
            self.off(token)
            print("stopped.")
