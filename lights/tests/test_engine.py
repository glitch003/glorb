import json
import queue
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from glorbleds.webui.engine import Engine


LIGHTS = Path(__file__).resolve().parents[1]


def load_map():
    return json.loads((LIGHTS / "tube-map.json").read_text())


def make_engine(fps=30.0):
    with patch("glorbleds.webui.engine.iface_for", return_value=None), \
         patch("glorbleds.webui.engine.Sender"):
        return Engine(load_map(), fps=fps)


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
            self.release.wait(timeout=1.0)
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
        refreshing.start()
        time.sleep(0.02)

        self.assertTrue(refreshing.is_alive())
        self.assertFalse(sender.closed)

        sender.release.set()
        sending.join(timeout=1.0)
        refreshing.join(timeout=1.0)
        self.assertFalse(sending.is_alive())
        self.assertFalse(refreshing.is_alive())
        self.assertTrue(sender.closed)
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
    def test_nonpositive_fps_is_rejected_at_configuration_time(self):
        for fps in (0.0, -1.0, float("nan"), float("inf")):
            with self.subTest(fps=fps):
                with self.assertRaises(ValueError):
                    make_engine(fps=fps)

    def setUp(self):
        self.engine = make_engine(fps=120.0)
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
            time.sleep(0.02)
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

        stopper = threading.Thread(target=engine.stop)
        stopper.start()
        for _ in range(100):
            if not engine._running:
                break
            time.sleep(0.001)
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
        engine = make_engine(fps=120.0)
        engine.stop()
        self.assertIsNone(engine._sender)

        with patch("glorbleds.webui.engine.Sender") as sender_class:
            engine.start()

        sender_class.assert_called_once()
        self.assertIs(engine._sender, sender_class.return_value)
        engine.stop()


if __name__ == "__main__":
    unittest.main()
