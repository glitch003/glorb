"""Animation engine: one loop -> browser viz + (optional) E1.31 hardware."""

import queue
import threading
import time

from ..e131 import Sender
from .model import CarModel
from .patterns import REGISTRY, NAMES

_ORDER = {"RGB": (0, 1, 2), "RBG": (0, 2, 1), "GRB": (1, 0, 2),
          "GBR": (1, 2, 0), "BRG": (2, 0, 1), "BGR": (2, 1, 0)}


class Engine:
    def __init__(self, gmap: dict, fps: float = 30.0):
        self.model = CarModel(gmap)
        self.fps = fps
        self._buf = bytearray(self.model.nbytes)
        self.frame = bytes(self.model.nbytes)

        self.lock = threading.Lock()
        self.params = {
            "pattern": "rainbow",
            "brightness": 0.30,
            "speed": 0.5,
            "density": 0.4,
            "color1": (0, 150, 255),
            "color2": (255, 60, 0),
        }
        self.hw = {"enabled": False, "host": None, "iface": None,
                   "color_order": "RGB", "error": None}
        self._sender = None
        self._lut = self._make_lut(self.params["brightness"])

        self.subs: set[queue.Queue] = set()
        self._running = False
        self._t0 = time.monotonic()
        self._meas_fps = 0.0
        self._frames = 0
        self._last_fps_t = self._t0

    # --- lookup table for brightness scaling ---
    @staticmethod
    def _make_lut(b):
        b = max(0.0, min(1.0, b))
        return bytes(int(i * b) & 0xFF for i in range(256))

    # --- subscribers (SSE clients) ---
    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=2)
        with self.lock:
            self.subs.add(q)
        return q

    def unsubscribe(self, q) -> None:
        with self.lock:
            self.subs.discard(q)

    def _broadcast(self, frame) -> None:
        for q in list(self.subs):
            try:
                q.put_nowait(frame)
            except queue.Full:
                pass

    # --- control ---
    def set_control(self, upd: dict) -> None:
        with self.lock:
            for k in ("pattern", "speed", "density", "brightness"):
                if k in upd:
                    self.params[k] = upd[k]
            for k in ("color1", "color2"):
                if k in upd and upd[k]:
                    self.params[k] = tuple(int(v) & 0xFF for v in upd[k])
            if "brightness" in upd:
                self._lut = self._make_lut(self.params["brightness"])
            if self.params["pattern"] not in REGISTRY:
                self.params["pattern"] = "rainbow"

            hwu = upd.get("hardware")
            if hwu is not None:
                for k in ("enabled", "host", "iface", "color_order"):
                    if k in hwu:
                        self.hw[k] = hwu[k]
                self._refresh_sender()

    def _refresh_sender(self) -> None:
        if self._sender:
            self._sender.close()
            self._sender = None
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
            p = dict(self.params)
            hw = dict(self.hw)
        return {
            "patterns": NAMES,
            "params": p,
            "hardware": hw,
            "fps": round(self._meas_fps, 1),
            "target_fps": self.fps,
        }

    # --- main loop ---
    def _tick(self) -> None:
        with self.lock:
            p = dict(self.params)
            lut = self._lut
            hw_on = self.hw["enabled"]
            order = self.hw["color_order"]
            sender = self._sender
        t = time.monotonic() - self._t0
        REGISTRY[p["pattern"]].render(self.model, p, t, self._buf)
        frame = self._buf.translate(lut)     # brightness in one C call
        self.frame = frame
        self._broadcast(frame)
        if hw_on and sender is not None:
            self._send_hw(frame, sender, order)

    def _send_hw(self, frame, sender, order) -> None:
        perm = _ORDER.get(order, (0, 1, 2))
        try:
            for universe, start, length in self.model.group_slices:
                chunk = frame[start:start + length]
                if perm != (0, 1, 2):
                    chunk = self._reorder(chunk, perm)
                sender.send(universe, chunk)
        except OSError as e:
            with self.lock:
                self.hw["error"] = str(e)

    @staticmethod
    def _reorder(chunk, perm):
        out = bytearray(len(chunk))
        a, b, c = perm
        for i in range(0, len(chunk), 3):
            out[i] = chunk[i + a]
            out[i + 1] = chunk[i + b]
            out[i + 2] = chunk[i + c]
        return bytes(out)

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
            nxt += period
            time.sleep(max(0.0, nxt - time.monotonic()))

    def start(self) -> None:
        self._running = True
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        if self._sender:
            self._sender.close()
