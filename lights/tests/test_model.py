import json
import unittest
from pathlib import Path

from glorbleds.webui.model import CarModel


LIGHTS = Path(__file__).resolve().parents[1]


class CarModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gmap = json.loads((LIGHTS / "tube-map.json").read_text())
        cls.model = CarModel(gmap)

    def test_layout_matches_physical_inventory(self):
        # 41 px/tube measured on the real strips 2026-08-21 (not nominal 40)
        self.assertEqual(len(self.model.tubes), 136)
        self.assertEqual(self.model.total_pixels, 136 * 41)
        self.assertEqual(self.model.nbytes, 136 * 41 * 3)
        self.assertEqual(self.model.sides_count(), {"L": 56, "B": 24, "R": 56})

    def test_physical_conversion_returns_snapshot_without_mutating_input(self):
        logical = bytes(i % 251 for i in range(self.model.nbytes))
        before = bytes(logical)

        physical = self.model.to_physical(logical)

        self.assertEqual(logical, before)
        self.assertIsInstance(physical, bytes)
        self.assertEqual(len(physical), len(logical))

    def test_no_tube_is_reversed_on_the_wire(self):
        """Every tube has its own data line and takes data at the top, so
        the physical frame is the logical frame — nothing is flipped."""
        logical = bytes(i % 251 for i in range(self.model.nbytes))

        self.assertEqual(self.model._rev_offsets, [])
        self.assertEqual(self.model.to_physical(logical), logical)

    def test_output_is_one_flat_span_from_universe_one(self):
        self.assertEqual(self.model.output_spans,
                         [(1, 0, self.model.nbytes)])

    def test_each_tube_owns_contiguous_channels(self):
        """The channel layout FPP is configured against: tube n starts at
        channel n * px_per_tube * 3 + 1."""
        tubes = self.model.map["tubes"]
        ch = self.model.px_per_tube * 3
        self.assertEqual(len(tubes), 136)
        for n, t in enumerate(tubes):
            self.assertEqual(t["start_channel"], n * ch + 1)
            self.assertEqual(t["end_channel"], n * ch + ch)
        self.assertEqual(tubes[-1]["end_channel"], self.model.nbytes)


if __name__ == "__main__":
    unittest.main()
