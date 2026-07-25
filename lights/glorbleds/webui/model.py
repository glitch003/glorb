"""Flattens tube-map.json into a per-pixel model of the whole car.

Canonical pixel order = groups in map order, each group's tubes in order,
each tube pixel 0..N-1. That order is contiguous per group, so a group's
DMX universe is just a flat slice of the frame buffer.
"""


class CarModel:
    def __init__(self, gmap: dict):
        self.map = gmap
        self.px_per_tube = gmap["meta"]["pixels_per_tube"]

        # Serpentine wiring: within each group the data snakes, so every
        # 2nd tube (0-based odd) runs tail-first. Logical frames get those
        # tubes flipped on the way to the hardware (to_physical).
        serpentine = gmap["meta"].get("serpentine", False)

        self.tubes = []           # canonical order: [{label, side, group, angio}]
        self.group_slices = []    # [(universe, byte_start, byte_len)]
        self._rev_offsets = []    # frame byte offset of each reversed tube
        byte_start = 0
        for g in gmap["groups"]:
            for k, label in enumerate(g["tubes"]):
                self.tubes.append({
                    "label": label, "side": label[0],
                    "group": g["group"], "angio": g["angio"],
                })
                if serpentine and k % 2 == 1:
                    self._rev_offsets.append(
                        (len(self.tubes) - 1) * self.px_per_tube * 3)
            byte_len = g["tube_count"] * self.px_per_tube * 3
            self.group_slices.append((g["universe"], byte_start, byte_len))
            byte_start += byte_len

        self.total_pixels = len(self.tubes) * self.px_per_tube
        self.nbytes = self.total_pixels * 3

        # Per-pixel static attributes patterns can read.
        self.side = []            # 'L' / 'B' / 'R'
        self.along = []           # 0..1 position along the tube
        self.perim = []           # 0..1 position around the perimeter
        self.tube_of = []         # index into self.tubes
        n = self.total_pixels
        idx = 0
        ppt = self.px_per_tube
        for ti, t in enumerate(self.tubes):
            for j in range(ppt):
                self.side.append(t["side"])
                self.along.append(j / (ppt - 1) if ppt > 1 else 0.0)
                self.perim.append(idx / n)
                self.tube_of.append(ti)
                idx += 1

    def to_physical(self, frame: bytes) -> bytes:
        """Logical frame -> wire order: reverse pixels of serpentine tubes."""
        if not self._rev_offsets:
            return frame
        buf = bytearray(frame)
        n = self.px_per_tube * 3
        for off in self._rev_offsets:
            seg = frame[off:off + n]
            buf[off:off + n:3] = seg[n - 3::-3]
            buf[off + 1:off + n:3] = seg[n - 2::-3]
            buf[off + 2:off + n:3] = seg[n - 1::-3]
        return bytes(buf)

    def sides_count(self) -> dict:
        c = {"L": 0, "B": 0, "R": 0}
        for t in self.tubes:
            c[t["side"]] += 1
        return c

    def layout(self) -> dict:
        """JSON payload the browser uses to place tubes + index frames."""
        return {
            "px_per_tube": self.px_per_tube,
            "total_pixels": self.total_pixels,
            "sides": self.sides_count(),
            "tubes": self.tubes,
            "groups": [
                {"group": g["group"], "angio": g["angio"],
                 "universe": g["universe"], "tubes": g["tubes"]}
                for g in self.map["groups"]
            ],
        }
