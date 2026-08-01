"""Flattens tube-map.json into a per-pixel model of the whole car.

Canonical pixel order = groups in map order, each group's tubes in order,
each tube pixel 0..N-1. Groups are contiguous per Angio, so an Angio's
pixel space (packed 170 px/universe from its start universe) is just a
flat slice of the frame buffer.
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
        self.angio_slices = []    # [(start_universe, byte_start, byte_len)]
        self._rev_offsets = []    # frame byte offset of each reversed tube
        start_univ = {a["name"]: a["start_universe"] for a in gmap["angios"]}
        byte_start = 0
        cur_angio, cur_start = None, 0
        for g in gmap["groups"]:
            if g["angio"] != cur_angio:
                if cur_angio is not None:
                    self.angio_slices.append(
                        (start_univ[cur_angio], cur_start,
                         byte_start - cur_start))
                cur_angio, cur_start = g["angio"], byte_start
            for k, label in enumerate(g["tubes"]):
                # "pos" = physical slot within the side (labels are
                # positional: L01 front..L56 back, B01 left..B24 right,
                # R01 back..R56 front). Canonical (electrical) order can
                # differ from physical order on mirrored-hung lines
                # (see REVERSED_LINES in tube_map.py), so anything spatial
                # must use pos, not canonical index.
                self.tubes.append({
                    "label": label, "side": label[0],
                    "pos": int(label[1:]) - 1,
                    "group": g["group"], "angio": g["angio"],
                })
                if serpentine and k % 2 == 1:
                    self._rev_offsets.append(
                        (len(self.tubes) - 1) * self.px_per_tube * 3)
            byte_start += g["tube_count"] * self.px_per_tube * 3
        if cur_angio is not None:
            self.angio_slices.append(
                (start_univ[cur_angio], cur_start, byte_start - cur_start))

        self.total_pixels = len(self.tubes) * self.px_per_tube
        self.nbytes = self.total_pixels * 3

        # Per-pixel static attributes patterns can read. perim uses the
        # tube's *physical* slot so spatial patterns stay correct even when
        # electrical order is mirrored.
        self.side = []            # 'L' / 'B' / 'R'
        self.along = []           # 0..1 position along the tube
        self.perim = []           # 0..1 physical position around the perimeter
        self.tube_of = []         # index into self.tubes
        ppt = self.px_per_tube
        counts = self.sides_count()
        ntubes = len(self.tubes)
        side_off = {"L": 0, "B": counts["L"],
                    "R": counts["L"] + counts["B"]}
        for ti, t in enumerate(self.tubes):
            phys = side_off[t["side"]] + t["pos"]
            # Constant per tube: a tube is one vertical column at one spot on
            # the perimeter. Varying perim with j sheared vertical edges
            # diagonally across each tube.
            x = (phys + 0.5) / ntubes
            for j in range(ppt):
                self.side.append(t["side"])
                self.along.append(j / (ppt - 1) if ppt > 1 else 0.0)
                self.perim.append(x)
                self.tube_of.append(ti)

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
                 "line": g["line"], "tubes": g["tubes"]}
                for g in self.map["groups"]
            ],
        }
