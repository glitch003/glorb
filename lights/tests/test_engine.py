import json
import queue
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from glorbleds.webui.engine import DITHER_CELLS, Engine


LIGHTS = Path(__file__).resolve().parents[1]


def load_map():
    return json.loads((LIGHTS / "tube-map.json").read_text())


def make_engine(fps=30.0):
    with patch("glorbleds.webui.engine.iface_for", return_value=None), \
         patch("glorbleds.webui.engine.Sender"):
        return Engine(load_map(), fps=fps)


class ObservableLock:
    """Lock that signals when a chosen acquisition attempt begins."""
    def __init__(self, signal_attempt=2):
        self._lock = threading.Lock()
        self._counter_lock = threading.Lock()
        self._attempts = 0
        self.attempted = threading.Event()
        self.signal_attempt = signal_attempt

    def __enter__(self):
        with self._counter_lock:
            self._attempts += 1
            if self._attempts == self.signal_attempt:
                self.attempted.set()
        self._lock.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._lock.release()


class EngineDefaultTests(unittest.TestCase):
    def test_plasma_is_the_launch_pattern(self):
        engine = make_engine()
        try:
            self.assertEqual(engine.pattern, "plasma")
            self.assertEqual(engine.state()["pattern"], "plasma")
        finally:
            engine.stop()


class EngineBufferingTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine(fps=30.0)
        self.engine.set_control({"hardware": {"enabled": False}})

    def tearDown(self):
        self.engine.stop()

    def test_slow_subscriber_receives_latest_frame_without_backlog(self):
        subscriber = self.engine.subscribe()

        self.engine._broadcast(b"old")
        self.engine._broadcast(b"latest")

        self.assertEqual(subscriber.get_nowait(), b"latest")
        with self.assertRaises(queue.Empty):
            subscriber.get_nowait()

    def test_broadcast_snapshots_subscribers_under_the_engine_lock(self):
        engine = self.engine

        class LockCheckingSet(set):
            def __iter__(self):
                if not engine.lock.locked():
                    raise AssertionError("subscriber set iterated without lock")
                return super().__iter__()

        subscriber = queue.Queue(maxsize=1)
        engine.subs = LockCheckingSet([subscriber])

        engine._broadcast(b"frame")

        self.assertEqual(subscriber.get_nowait(), b"frame")


class EngineSenderConcurrencyTests(unittest.TestCase):
    class BlockingSender:
        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()
            self.closed = False

        def send(self, universe, dmx):
            self.entered.set()
            self.release.wait()
            if self.closed:
                raise OSError("socket closed during frame")

        def close(self):
            self.closed = True

    def test_sender_is_not_closed_mid_frame_during_hardware_refresh(self):
        engine = make_engine(fps=30.0)
        if engine._sender:
            engine._sender.close()
        sender = self.BlockingSender()
        engine._sender = sender
        engine.hw["enabled"] = True
        frame = bytes(engine.model.nbytes)

        sending = threading.Thread(
            target=engine._send_hw, args=(frame,)
        )
        sending.start()
        self.assertTrue(sender.entered.wait(timeout=1.0))

        refreshing = threading.Thread(
            target=engine.set_control,
            args=({"hardware": {"enabled": False}},),
        )
        refresh_entered = threading.Event()
        original_refresh = engine._refresh_sender

        def tracked_refresh():
            refresh_entered.set()
            original_refresh()

        engine._refresh_sender = tracked_refresh
        refreshing.start()
        try:
            self.assertTrue(refresh_entered.wait(timeout=1.0))
            self.assertTrue(refreshing.is_alive())
            self.assertFalse(sender.closed)
        finally:
            sender.release.set()
        sending.join(timeout=1.0)
        refreshing.join(timeout=1.0)
        self.assertFalse(sending.is_alive())
        self.assertFalse(refreshing.is_alive())
        self.assertTrue(sender.closed)
        engine.stop()

    def test_obsolete_sender_error_does_not_replace_new_hardware_state(self):
        engine = make_engine(fps=30.0)

        class FailingSender(self.BlockingSender):
            def send(self, universe, dmx):
                self.entered.set()
                self.release.wait()
                raise OSError("old sender failed")

        if engine._sender:
            engine._sender.close()
        sender = FailingSender()
        engine._sender = sender  # type: ignore[assignment]
        engine.hw["enabled"] = True

        sending = threading.Thread(
            target=engine._send_hw, args=(bytes(engine.model.nbytes),)
        )
        sending.start()
        self.assertTrue(sender.entered.wait(timeout=1.0))

        refreshing = threading.Thread(
            target=engine.set_control,
            args=({"hardware": {"enabled": False}},),
        )
        refresh_entered = threading.Event()
        original_refresh = engine._refresh_sender

        def tracked_refresh():
            refresh_entered.set()
            original_refresh()

        engine._refresh_sender = tracked_refresh
        refreshing.start()
        try:
            self.assertTrue(refresh_entered.wait(timeout=1.0))
            self.assertTrue(refreshing.is_alive())
        finally:
            sender.release.set()
        sending.join(timeout=1.0)
        refreshing.join(timeout=1.0)

        self.assertFalse(sending.is_alive())
        self.assertFalse(refreshing.is_alive())
        self.assertIsNone(engine.hw["error"])
        self.assertFalse(engine.hw["enabled"])
        engine.stop()

    def test_state_reads_do_not_wait_for_udp_frame_send(self):
        engine = make_engine(fps=30.0)
        if engine._sender:
            engine._sender.close()
        sender = self.BlockingSender()
        engine._sender = sender
        engine.hw["enabled"] = True
        sending = threading.Thread(
            target=engine._send_hw, args=(bytes(engine.model.nbytes),)
        )
        sending.start()
        self.assertTrue(sender.entered.wait(timeout=1.0))

        state_done = threading.Event()

        def read_state():
            engine.state()
            state_done.set()

        reader = threading.Thread(target=read_state)
        reader.start()
        responsive = state_done.wait(timeout=0.05)
        sender.release.set()
        sending.join(timeout=1.0)
        reader.join(timeout=1.0)
        engine.stop()

        self.assertTrue(responsive)

    def test_frame_uses_current_color_order_and_sender_atomically(self):
        engine = make_engine(fps=30.0)

        class RecordingSender:
            def __init__(self):
                self.calls = []

            def send(self, universe, dmx):
                self.calls.append((universe, dmx))

            def close(self):
                pass

        sender = RecordingSender()
        engine._sender = sender
        engine._sender_order = "BGR"
        engine.hw["enabled"] = True
        engine.hw["color_order"] = "BGR"
        frame = bytes((10, 20, 30)) + bytes(engine.model.nbytes - 3)

        engine._send_hw(frame)

        self.assertEqual(sender.calls[0][1][:3], bytes((30, 20, 10)))
        engine.stop()


class EnginePacingTests(unittest.TestCase):
    def test_missed_deadlines_are_skipped_instead_of_replayed_as_bursts(self):
        next_deadline, dropped = Engine._advance_deadline(
            deadline=10.0, now=10.35, period=0.1
        )

        self.assertAlmostEqual(next_deadline, 10.4)
        self.assertEqual(dropped, 3)

    def test_on_time_frame_keeps_the_original_cadence(self):
        next_deadline, dropped = Engine._advance_deadline(
            deadline=10.0, now=10.05, period=0.1
        )

        self.assertAlmostEqual(next_deadline, 10.1)
        self.assertEqual(dropped, 0)

    def test_exactly_elapsed_deadline_is_skipped(self):
        next_deadline, dropped = Engine._advance_deadline(
            deadline=10.0, now=10.1, period=0.1
        )

        self.assertAlmostEqual(next_deadline, 10.2)
        self.assertEqual(dropped, 1)


class EngineLifecycleTests(unittest.TestCase):
    def test_out_of_range_fps_is_rejected_at_configuration_time(self):
        for fps in (0.0, -1.0, 60.1, float("nan"), float("inf")):
            with self.subTest(fps=fps):
                with self.assertRaises(ValueError):
                    make_engine(fps=fps)
        engine = make_engine(fps=60.0)
        engine.stop()

    def setUp(self):
        self.engine = make_engine(fps=60.0)
        self.engine.set_control({"hardware": {"enabled": False}})

    def tearDown(self):
        self.engine.stop()

    def test_start_is_idempotent_and_stop_joins_worker(self):
        self.engine.start()
        worker = self.engine._thread
        self.engine.start()

        self.assertIs(self.engine._thread, worker)
        self.assertTrue(worker.is_alive())

        self.engine.stop()
        self.assertFalse(worker.is_alive())

    def test_start_and_stop_are_safe_when_called_concurrently(self):
        engine = self.engine
        lifecycle_lock = ObservableLock(signal_attempt=2)
        engine._lifecycle_lock = lifecycle_lock  # type: ignore[assignment]
        original_start = threading.Thread.start
        start_entered = threading.Event()
        allow_start = threading.Event()
        errors = []

        def delayed_start(thread):
            start_entered.set()
            allow_start.wait(timeout=2.0)
            return original_start(thread)

        with patch.object(threading.Thread, "start", delayed_start):
            starter = threading.Thread(target=lambda: engine.start())
            original_start(starter)
            self.assertTrue(start_entered.wait(timeout=1.0))

            def stop_engine():
                try:
                    engine.stop()
                except Exception as exc:  # capture failures from the other thread
                    errors.append(exc)

            stopper = threading.Thread(target=stop_engine)
            original_start(stopper)
            self.assertTrue(lifecycle_lock.attempted.wait(timeout=1.0))
            allow_start.set()
            starter.join(timeout=2.0)
            stopper.join(timeout=2.0)

        self.assertFalse(starter.is_alive())
        self.assertFalse(stopper.is_alive())
        self.assertEqual(errors, [])

    def test_start_requested_during_stop_restarts_after_old_worker_exits(self):
        engine = self.engine
        entered = threading.Event()
        release = threading.Event()
        original_tick = engine._tick

        def blocking_first_tick():
            if not entered.is_set():
                entered.set()
                release.wait(timeout=2.0)
            else:
                original_tick()

        engine._tick = blocking_first_tick
        engine.start()
        self.assertTrue(entered.wait(timeout=1.0))

        join_entered = threading.Event()
        worker = engine._thread
        assert worker is not None
        original_join = worker.join

        def tracked_join(*args, **kwargs):
            join_entered.set()
            return original_join(*args, **kwargs)

        worker.join = tracked_join  # type: ignore[method-assign]

        stopper = threading.Thread(target=engine.stop)
        stopper.start()
        self.assertTrue(join_entered.wait(timeout=1.0))
        self.assertFalse(engine._running)

        start_returned = threading.Event()

        def restart_engine():
            engine.start()
            start_returned.set()

        starter = threading.Thread(target=restart_engine)
        starter.start()
        self.assertFalse(start_returned.wait(timeout=0.02))
        release.set()
        stopper.join(timeout=2.0)
        starter.join(timeout=2.0)

        self.assertFalse(stopper.is_alive())
        self.assertFalse(starter.is_alive())
        self.assertTrue(start_returned.is_set())
        self.assertTrue(engine._running)
        self.assertIsNotNone(engine._thread)
        self.assertTrue(engine._thread.is_alive())
        engine.stop()

    def test_stop_waits_for_worker_completion_before_cleanup(self):
        worker = MagicMock()
        worker.is_alive.return_value = False
        self.engine._thread = worker
        self.engine._running = True

        self.engine.stop()

        worker.join.assert_called_once_with()
        self.assertIsNone(self.engine._thread)

    def test_restart_recreates_hardware_sender(self):
        engine = make_engine(fps=60.0)
        engine.stop()
        self.assertIsNone(engine._sender)

        with patch("glorbleds.webui.engine.Sender") as sender_class:
            engine.start()

        sender_class.assert_called_once()
        self.assertIs(engine._sender, sender_class.return_value)
        engine.stop()


if __name__ == "__main__":
    unittest.main()



class DitherTests(unittest.TestCase):
    """Spatial ordered dithering recovers resolution lost to FPP's
    requantisation, without introducing any temporal artefact.

    FPP's per-string brightness LUT is round(x * B * 2.55 / 255), i.e. steps of
    100/B in our 0..255 space, so precision finer than that step is discarded.
    The dither amplitude has to match the step to survive it.
    """

    @staticmethod
    def _fpp(x, bri=10.0):
        return min(255, max(0, round(bri * 2.55 * (x / 255.0))))

    def test_adjacent_pixels_average_to_the_unreachable_value(self):
        luts = Engine._make_hw_luts(1.0, 10.0)
        # 65 wants 6.5 levels, which the hardware cannot hold at 10%
        levels = [self._fpp(luts[k][65]) for k in range(DITHER_CELLS)]
        self.assertEqual(sorted(levels), [6, 6, 7, 7])
        self.assertAlmostEqual(sum(levels) / len(levels), 6.5, places=6)

    def test_dither_increases_distinct_levels(self):
        luts = Engine._make_hw_luts(1.0, 10.0)
        undithered = {self._fpp(v) for v in range(256)}
        dithered = {sum(self._fpp(luts[k][v]) for k in range(DITHER_CELLS))
                    / DITHER_CELLS for v in range(256)}
        self.assertGreater(len(dithered), 3 * len(undithered))

    def test_mean_tracks_the_target_within_half_a_step(self):
        for gb in (1.0, 0.5, 0.25):
            luts = Engine._make_hw_luts(gb, 10.0)
            for v in range(0, 256, 7):
                want = v * gb / 10.0
                got = sum(self._fpp(luts[k][v])
                          for k in range(DITHER_CELLS)) / DITHER_CELLS
                self.assertLess(abs(got - want), 0.5,
                                f"b={gb} v={v}: {got} vs {want}")

    def test_static_frame_is_bit_identical_every_time(self):
        """The reason this dither is spatial. A per-frame phase term gave each
        pixel a 30/4 = 7.5 Hz cycle -- near the worst frequency for human
        flicker perception -- and near-black strobed at 100% modulation depth.
        """
        luts = Engine._make_hw_luts(1.0, 10.0)
        buf = bytearray((i * 7) % 251 for i in range(3 * 4 * 40))
        first = Engine._apply_dither(buf, luts)
        for _ in range(8):
            self.assertEqual(Engine._apply_dither(buf, luts), first)

    def test_all_three_channels_of_a_pixel_share_a_phase(self):
        """A byte-indexed mask puts R, G and B of one pixel on different
        phases, which reads as per-pixel hue speckle (worst on blue)."""
        luts = Engine._make_hw_luts(1.0, 10.0)
        flat = bytearray([65] * (3 * 4 * 8))
        out = Engine._apply_dither(flat, luts)
        for i in range(len(out) // 3):
            r, g, b = out[i * 3:i * 3 + 3]
            self.assertEqual((r, g), (r, b), f"pixel {i} channels disagree")

    def test_neighbouring_pixels_do_differ(self):
        """Otherwise there is no dithering happening at all."""
        luts = Engine._make_hw_luts(1.0, 10.0)
        flat = bytearray([65] * (3 * 4 * 8))
        out = Engine._apply_dither(flat, luts)
        px = {tuple(out[i * 3:i * 3 + 3]) for i in range(DITHER_CELLS)}
        self.assertGreater(len(px), 1)

    def test_true_black_stays_black(self):
        luts = Engine._make_hw_luts(1.0, 10.0)
        black = bytearray(3 * 4 * 8)
        self.assertEqual(set(Engine._apply_dither(black, luts)), {0})

    def test_zero_brightness_is_black_on_every_phase(self):
        luts = Engine._make_hw_luts(0.0, 10.0)
        for k in range(DITHER_CELLS):
            self.assertEqual(set(luts[k]), {0})

    def test_output_length_and_type_preserved(self):
        luts = Engine._make_hw_luts(1.0, 10.0)
        buf = bytearray(i % 251 for i in range(3 * 4 * 33))
        out = Engine._apply_dither(buf, luts)
        self.assertIsInstance(out, bytes)
        self.assertEqual(len(out), len(buf))

    def test_preview_lut_stays_smooth(self):
        """The browser should see the integrated value, not the dither."""
        lut = Engine._make_lut(1.0)
        self.assertEqual(lut[65], 65)
        self.assertEqual(lut[255], 255)
