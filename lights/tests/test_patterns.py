import copy
import json
import random
import unittest
from pathlib import Path
from unittest.mock import patch

from glorbleds.webui.model import CarModel
from glorbleds.webui.patterns import (
    Confetti, Fire, REGISTRY, Sparkle, Storm, _event_probability,
)


LIGHTS = Path(__file__).resolve().parents[1]


class PatternTimingHelperTests(unittest.TestCase):
    def test_event_probability_scales_over_fractional_reference_steps(self):
        self.assertAlmostEqual(_event_probability(0.2, 0.5), 1.0 - 0.8 ** 0.5)
        self.assertAlmostEqual(_event_probability(0.2, 2.0), 0.36)
        self.assertEqual(_event_probability(0.2, 0.0), 0.0)


class PatternFrameRateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gmap = json.loads((LIGHTS / "tube-map.json").read_text())
        cls.model = CarModel(gmap)
        cls.buf = bytearray(cls.model.nbytes)

    def run_for_one_second(self, pattern, fps, params, random_value=1.0):
        with patch("glorbleds.webui.patterns.random.randrange", return_value=1), \
             patch("glorbleds.webui.patterns.random.random", return_value=random_value):
            for frame in range(1, fps + 1):
                pattern.render(self.model, params, frame / fps, self.buf)

    def test_sparkle_decay_is_independent_of_output_fps(self):
        p30, p60 = Sparkle(), Sparkle()
        p30.render(self.model, p30.params(), 0.0, self.buf)
        p60.render(self.model, p60.params(), 0.0, self.buf)
        p30.level = [0.0] * self.model.total_pixels
        p60.level = [0.0] * self.model.total_pixels
        p30.level[0] = p60.level[0] = 1.0
        params = p30.params()

        self.run_for_one_second(p30, 30, params)
        self.run_for_one_second(p60, 60, params)

        self.assertAlmostEqual(p30.level[0], p60.level[0], places=6)

    def test_confetti_decay_is_independent_of_output_fps(self):
        p30, p60 = Confetti(), Confetti()
        p30.render(self.model, p30.params(), 0.0, self.buf)
        p60.render(self.model, p60.params(), 0.0, self.buf)
        p30.lev = [0.0] * self.model.total_pixels
        p60.lev = [0.0] * self.model.total_pixels
        p30.col = p60.col = [(255, 0, 0)] * self.model.total_pixels
        p30.lev[0] = p60.lev[0] = 1.0
        params = p30.params()

        self.run_for_one_second(p30, 30, params)
        self.run_for_one_second(p60, 60, params)

        self.assertAlmostEqual(p30.lev[0], p60.lev[0], places=6)

    def test_fire_simulation_is_independent_of_output_fps(self):
        p30, p60 = Fire(), Fire()
        p30.render(self.model, p30.params(), 0.0, self.buf)
        p60.render(self.model, p60.params(), 0.0, self.buf)
        initial = [(i % self.model.px_per_tube) / self.model.px_per_tube
                   for i in range(self.model.total_pixels)]
        p30.heat = list(initial)
        p60.heat = list(initial)
        params = p30.params()

        self.run_for_one_second(p30, 30, params, random_value=0.2)
        self.run_for_one_second(p60, 60, params, random_value=0.2)

        difference = max(abs(a - b) for a, b in zip(p30.heat, p60.heat))
        self.assertLess(difference, 1e-9)

    def test_storm_flash_decay_is_independent_of_output_fps(self):
        p30, p60 = Storm(), Storm()
        p30.render(self.model, p30.params(), 0.0, self.buf)
        p60.render(self.model, p60.params(), 0.0, self.buf)
        p30.flash = [0.0] * len(self.model.tubes)
        p60.flash = [0.0] * len(self.model.tubes)
        p30.flash[0] = p60.flash[0] = 1.0
        params = p30.params()

        self.run_for_one_second(p30, 30, params)
        self.run_for_one_second(p60, 60, params)

        self.assertAlmostEqual(p30.flash[0], p60.flash[0], places=6)


class PatternRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        gmap = json.loads((LIGHTS / "tube-map.json").read_text())
        cls.model = CarModel(gmap)

    def test_every_pattern_replaces_the_complete_frame(self):
        for name, registered in REGISTRY.items():
            with self.subTest(pattern=name):
                clean_pattern = copy.deepcopy(registered)
                dirty_pattern = copy.deepcopy(registered)
                params = registered.params()
                clean = bytearray(self.model.nbytes)
                dirty = bytearray([0xA5]) * self.model.nbytes

                random.seed(0x474C4F52)
                clean_pattern.render(self.model, params, 1.25, clean)
                random.seed(0x474C4F52)
                dirty_pattern.render(self.model, params, 1.25, dirty)

                self.assertEqual(dirty, clean)

    def test_every_pattern_preserves_frame_size(self):
        for name, registered in REGISTRY.items():
            with self.subTest(pattern=name):
                pattern = copy.deepcopy(registered)
                frame = bytearray(self.model.nbytes)
                pattern.render(self.model, pattern.params(), 0.0, frame)
                self.assertEqual(len(frame), self.model.nbytes)

    def test_show_patterns_render_nontrivial_frames(self):
        for name in ("scrub", "ribbons", "voronoi", "life", "reaction",
                     "breakout", "invaders", "collider", "lasers", "supernova"):
            with self.subTest(pattern=name):
                pattern = copy.deepcopy(REGISTRY[name])
                frame = bytearray(self.model.nbytes)
                early = None
                for step in range(45):
                    pattern.render(self.model, pattern.params(), step / 30.0,
                                   frame)
                    if step == 10:
                        early = bytes(frame)
                colors = set(zip(frame[0::3], frame[1::3], frame[2::3]))
                self.assertGreater(len(colors), 16)
                self.assertGreater(max(frame), 128)
                changed = sum(a != b for a, b in zip(early, frame))
                self.assertGreater(changed, self.model.nbytes * 0.05)

    def test_scrub_sweeps_from_the_front_to_the_rear(self):
        pattern = copy.deepcopy(REGISTRY["scrub"])
        params = pattern.params()
        front = bytearray(self.model.nbytes)
        rear = bytearray(self.model.nbytes)
        pattern.render(self.model, params, 0.0, front)
        half_cycle = 0.5 / (0.055 + params["speed"] * 0.20)
        pattern.render(self.model, params, half_cycle, rear)
        longitudinal = pattern._longitudinal(self.model)

        def region_energy(frame, predicate):
            return sum(sum(frame[i * 3:i * 3 + 3])
                       for i, x in enumerate(longitudinal) if predicate(x))

        self.assertGreater(region_energy(front, lambda x: x < 0.15),
                           region_energy(front, lambda x: x > 0.85))
        self.assertGreater(region_energy(rear, lambda x: x > 0.85),
                           region_energy(rear, lambda x: x < 0.15))

    def test_arcade_patterns_play_forward_instead_of_looping_a_scene(self):
        cases = (("breakout", "bricks"), ("invaders", "alive"))
        for name, state_name in cases:
            with self.subTest(pattern=name):
                pattern = copy.deepcopy(REGISTRY[name])
                frame = bytearray(self.model.nbytes)
                pattern.render(self.model, pattern.params(), 0.0, frame)
                initial = sum(getattr(pattern, state_name))
                minimum = initial
                for step in range(1, 301):
                    pattern.render(self.model, pattern.params(), step / 30.0,
                                   frame)
                    minimum = min(minimum, sum(getattr(pattern, state_name)))
                self.assertLess(minimum, initial)


if __name__ == "__main__":
    unittest.main()
