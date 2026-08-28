import unittest
from unittest.mock import patch

from glorbleds.benchmark import run
from glorbleds.webui.patterns import REGISTRY


class BenchmarkTests(unittest.TestCase):
    class RecordingSender:
        instances = []

        def __init__(self, host):
            self.host = host
            self.calls = []
            self.closed = False
            self.instances.append(self)

        def send(self, universe, dmx):
            self.calls.append((universe, dmx))

        def close(self):
            self.closed = True

    def test_benchmark_does_not_mutate_live_pattern_instances(self):
        fire = REGISTRY["fire"]
        fire.last_t = None
        fire._accumulator = 0.0

        run(frames=1, fps=30.0)

        self.assertIsNone(fire.last_t)
        self.assertEqual(fire._accumulator, 0.0)

    def test_invalid_arguments_are_rejected(self):
        with self.assertRaises(ValueError):
            run(frames=0, fps=30.0)
        for fps in (0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(fps=fps):
                with self.assertRaises(ValueError):
                    run(frames=1, fps=fps)
        with self.assertRaises(ValueError):
            run(frames=1, fps=30.0,
                udp_host="127.0.0.1", udp_frames=0)

    def test_optional_udp_benchmark_sends_complete_frames(self):
        self.RecordingSender.instances.clear()
        with patch("glorbleds.benchmark.Sender", self.RecordingSender):
            result = run(frames=1, fps=30.0,
                         udp_host="127.0.0.1", udp_frames=2)

        # 6,068 px (148 tubes x 41) packed 170 px/universe = 36 universes
        # per frame, x2 frames.
        expected = 36 * 2
        sender = self.RecordingSender.instances[0]
        self.assertEqual(len(sender.calls), expected)
        self.assertTrue(sender.closed)
        self.assertEqual(result["udp_send"]["frames"], 2)
        self.assertEqual(result["udp_send"]["packets"], expected)


if __name__ == "__main__":
    unittest.main()
