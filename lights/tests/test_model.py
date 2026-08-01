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
        self.assertEqual(len(self.model.tubes), 136)
        self.assertEqual(self.model.total_pixels, 5440)
        self.assertEqual(self.model.nbytes, 16320)
        self.assertEqual(self.model.sides_count(), {"L": 56, "B": 24, "R": 56})

    def test_physical_conversion_returns_snapshot_without_mutating_input(self):
        logical = bytes(i % 251 for i in range(self.model.nbytes))
        before = bytes(logical)

        physical = self.model.to_physical(logical)

        self.assertEqual(logical, before)
        self.assertIsInstance(physical, bytes)
        self.assertEqual(len(physical), len(logical))

    def test_every_second_tube_in_group_is_reversed(self):
        ppt_bytes = self.model.px_per_tube * 3
        logical = bytearray(self.model.nbytes)
        for pixel in range(self.model.px_per_tube):
            start = ppt_bytes + pixel * 3
            logical[start:start + 3] = bytes((pixel, pixel + 1, pixel + 2))

        physical = self.model.to_physical(bytes(logical))

        first = physical[ppt_bytes:ppt_bytes + 3]
        last = physical[2 * ppt_bytes - 3:2 * ppt_bytes]
        self.assertEqual(first, bytes((39, 40, 41)))
        self.assertEqual(last, bytes((0, 1, 2)))


if __name__ == "__main__":
    unittest.main()
