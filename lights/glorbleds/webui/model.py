"""Flattens tube-map.json into a per-pixel model of the whole car.

Canonical pixel order = tubes in map order, each tube's pixels 0..N-1. That
is exactly the channel order FPP expects: tube n starts at channel
n * px_per_tube * 3 + 1. The whole car is one contiguous pixel space on one
K128D controller, so hardware output is a single flat span of universes.
"""


class CarModel:
    def __init__(self, gmap: dict):
        self.map = gmap
        self.px_per_tube = gmap["meta"]["pixels_per_tube"]

        # Every tube now has its own data line and takes data at the top, so
        # nothing is chained and nothing is reversed on the wire. The flag
        # stays so an odd future hang can be handled without a rewrite.
        serpentine = gmap["meta"].get("serpentine", False)

        self.tubes = []           # canonical order: [{label, side, pos, ...}]
        self._rev_offsets = []    # frame byte offset of each reversed tube
        for i, t in enumerate(gmap["tubes"]):
            # "pos" = physical slot within the side (labels are positional:
            # L01 front..L56 back, B01 left..B24 right, R01 back..R56 front).
            # Canonical order and physical order now agree, but patterns keep
            # using pos for anything spatial so a re-patch can't shear them.
            self.tubes.append({
                "label": t["label"], "side": t["side"], "pos": t["pos"],
                "zone": t["zone"], "receiver": t["receiver"],
                "port": t["port"], "output": t["output"],
            })
            if serpentine and t.get("direction") == "reverse":
                self._rev_offsets.append(i * self.px_per_tube * 3)

        self.total_pixels = len(self.tubes) * self.px_per_tube
        self.nbytes = self.total_pixels * 3

        # One controller, one flat pixel space: a single span of universes
        # packed px_per_universe from the start universe.
        # [(start_universe, byte_start, byte_len)]
        c = gmap["controller"]
        self.output_spans = [(c["start_universe"], 0, self.nbytes)]

        # Per-pixel static attributes patterns can read.
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
        """Logical frame -> wire order: reverse pixels of any flipped tube."""
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
            "receivers": [
                {"id": r["id"], "zone": r["zone"], "port": r["port"],
                 "chain_letter": r["chain_letter"], "tubes": r["tubes"]}
                for r in self.map["receivers"]
            ],
        }
