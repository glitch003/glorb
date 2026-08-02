"""Animation engine: one loop -> browser viz + (optional) E1.31 hardware."""

import base64
import math
import queue
import threading
import time

from ..e131 import Sender, iface_for, send_span
from .model import CarModel
from .patterns import REGISTRY, NAMES

_ORDER = {"RGB": (0, 1, 2), "RBG": (0, 2, 1), "GRB": (1, 0, 2),
          "GBR": (1, 2, 0), "BRG": (2, 0, 1), "BGR": (2, 1, 0)}
MAX_FPS = 60.0


class Engine:
    def __init__(self, gmap: dict, fps: float = 30.0):
        if not math.isfinite(fps) or not 0 < fps <= MAX_FPS:
            raise ValueError(f"fps must be finite and in the range (0, {MAX_FPS:g}]")
        self.model = CarModel(gmap)
        self.fps = fps
        self._buf = bytearray(self.model.nbytes)
        self.frame = bytes(self.model.nbytes)

        self.lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self.pattern = "plasma"
        # Boards output full range (force-max-brightness on) now that we're
        # on the real batteries — start conservative, raise from the UI.
        self.brightness = 0.05
        # Every pattern remembers its own knob settings.
        self.pp = {name: pat.params() for name, pat in REGISTRY.items()}
        # Pin multicast to the NIC that routes to the Angios (multi-homed
        # hosts otherwise send it out the default route).
        probe = next((a.get("ip") for a in gmap.get("angios", [])
                      if a.get("ip")), None)
        self.hw = {"enabled": True, "host": None,
                   "iface": iface_for(probe) if probe else None,
                   "color_order": "RGB", "error": None}
        self._sender_lock = threading.Lock()
        self._sender = None
        self._sender_order = "RGB"
        self._sender_generation = 0
        self._refresh_sender()
        self._lut = self._make_lut(self.brightness)

        self.subs: set[queue.Queue] = set()
        self._running = False
        self._thread: threading.Thread | None = None
        self._t0 = time.monotonic()
        self._meas_fps = 0.0
        self._frames = 0
        self._dropped_frames = 0
        self._last_fps_t = self._t0

    # --- lookup table for brightness scaling ---
    @staticmethod
    def _make_lut(b):
        b = max(0.0, min(1.0, b))
        return bytes(int(i * b) & 0xFF for i in range(256))

    # --- subscribers (SSE clients) ---
    def subscribe(self) -> queue.Queue:
        # A preview wants the newest complete frame, never a FIFO backlog.
        q: queue.Queue = queue.Queue(maxsize=1)
        with self.lock:
            self.subs.add(q)
        return q

    def unsubscribe(self, q) -> None:
        with self.lock:
            self.subs.discard(q)

    def _broadcast(self, frame) -> None:
        with self.lock:
            subscribers = tuple(self.subs)
        for q in subscribers:
            try:
                q.put_nowait(frame)
            except queue.Full:
                # Replace the stale frame. The consumer can race the get, so
                # tolerate an already-empty queue and retry the put once.
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(frame)
                except queue.Full:
                    pass

    # --- control ---
    def set_control(self, upd: dict) -> None:
        with self.lock:
            if "pattern" in upd and upd["pattern"] in REGISTRY:
                self.pattern = upd["pattern"]
            if "brightness" in upd:
                self.brightness = max(0.0, min(1.0, float(upd["brightness"])))
                self._lut = self._make_lut(self.brightness)
            p = self.pp[self.pattern]
            for k in ("speed", "density"):
                if k in upd:
                    p[k] = max(0.0, min(1.0, float(upd[k])))
            for k in ("color1", "color2"):
                if k in upd and upd[k]:
                    p[k] = tuple(int(v) & 0xFF for v in upd[k])

            emo = upd.get("emoji")
            if emo is not None:
                images = [(int(im["w"]), int(im["h"]),
                           base64.b64decode(im["rgba"]))
                          for im in emo["images"]]
                REGISTRY["emoji"].set_images(images, str(emo.get("label", "")))
                self.pattern = "emoji"

            hwu = upd.get("hardware")
            if hwu is not None:
                for k in ("enabled", "host", "iface", "color_order"):
                    if k in hwu:
                        self.hw[k] = hwu[k]
                self._refresh_sender()

    def _refresh_sender(self) -> None:
        with self._sender_lock:
            self._sender_generation += 1
            if self._sender:
                self._sender.close()
                self._sender = None
            self._sender_order = self.hw["color_order"]
            self.hw["error"] = None
            if self.hw["enabled"]:
                try:
                    self._sender = Sender(host=self.hw["host"] or None,
                                          iface=self.hw["iface"] or None,
                                          source_name="glorb-ui")
                except OSError as e:
                    self.hw["error"] = str(e)
                    self.hw["enabled"] = False

    def state(self) -> dict:
        with self.lock:
            pattern = self.pattern
            p = dict(self.pp[pattern])
            hw = dict(self.hw)
            bri = self.brightness
        return {
            "patterns": [{"name": n, "controls": list(REGISTRY[n].controls)}
                         for n in NAMES],
            "pattern": pattern,
            "controls": list(REGISTRY[pattern].controls),
            "params": p,
            "brightness": bri,
            "emoji": REGISTRY["emoji"].label,
            "hardware": hw,
            "fps": round(self._meas_fps, 1),
            "target_fps": self.fps,
            "dropped_frames": self._dropped_frames,
        }

    # --- main loop ---
    def _tick(self) -> None:
        with self.lock:
            pattern = self.pattern
            p = dict(self.pp[pattern])
            lut = self._lut
        t = time.monotonic() - self._t0
        REGISTRY[pattern].render(self.model, p, t, self._buf)
        frame = self._buf.translate(lut)     # brightness in one C call
        self.frame = frame
        self._broadcast(frame)
        self._send_hw(frame)

    def _send_hw(self, frame) -> None:
        error = None
        frame = self.model.to_physical(frame)
        # Sender and color order are one generation under this lock. State
        # reads stay responsive while the nonblocking UDP burst is emitted.
        with self._sender_lock:
            sender = self._sender
            if sender is None:
                return
            generation = self._sender_generation
            perm = _ORDER.get(self._sender_order, (0, 1, 2))
            try:
                for start_universe, start, length in self.model.angio_slices:
                    chunk = frame[start:start + length]
                    if perm != (0, 1, 2):
                        chunk = self._reorder(chunk, perm)
                    send_span(sender, start_universe, chunk)
            except OSError as e:
                error = str(e)
        if error is not None:
            with self.lock:
                with self._sender_lock:
                    if (self._sender is sender
                            and self._sender_generation == generation):
                        self.hw["error"] = error

    @staticmethod
    def _reorder(chunk, perm):
        out = bytearray(len(chunk))
        a, b, c = perm
        for i in range(0, len(chunk), 3):
            out[i] = chunk[i + a]
            out[i + 1] = chunk[i + b]
            out[i + 2] = chunk[i + c]
        return bytes(out)

    @staticmethod
    def _advance_deadline(deadline: float, now: float,
                          period: float) -> tuple[float, int]:
        """Return the next future deadline and count skipped frame slots."""
        deadline += period
        if deadline <= now:
            dropped = int((now - deadline) // period) + 1
            deadline += dropped * period
            return deadline, dropped
        return deadline, 0

    def _loop(self) -> None:
        period = 1.0 / self.fps
        nxt = time.monotonic()
        while self._running:
            self._tick()
            self._frames += 1
            now = time.monotonic()
            if now - self._last_fps_t >= 1.0:
                self._meas_fps = self._frames / (now - self._last_fps_t)
                self._frames = 0
                self._last_fps_t = now
            nxt, dropped = self._advance_deadline(nxt, now, period)
            self._dropped_frames += dropped
            time.sleep(max(0.0, nxt - time.monotonic()))

    def _start_locked(self) -> None:
        """Start a worker while the state lock is held."""
        if self.hw["enabled"] and self._sender is None:
            self._refresh_sender()
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="glorbleds-engine")
        # Publish only a started worker: stop() must never join a Thread
        # object in the gap between construction and Thread.start().
        self._thread.start()

    def start(self) -> None:
        # Serialize complete lifecycle transitions. A start arriving during a
        # stop waits for cleanup, then starts a fresh worker/sender generation.
        with self._lifecycle_lock:
            with self.lock:
                if self._thread is not None and self._thread.is_alive():
                    return
                self._start_locked()

    def stop(self) -> None:
        with self._lifecycle_lock:
            with self.lock:
                self._running = False
                thread = self._thread
            if thread is not None and thread is not threading.current_thread():
                # UDP output is nonblocking and every built-in pattern is bounded;
                # wait for the worker before closing its sender.
                thread.join()
            with self.lock:
                if self._thread is not thread:
                    return
                if thread is None or not thread.is_alive():
                    self._thread = None
                with self._sender_lock:
                    if self._sender:
                        self._sender.close()
                        self._sender = None
