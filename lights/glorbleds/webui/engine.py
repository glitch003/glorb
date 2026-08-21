"""Animation engine: one loop -> browser viz + (optional) LED hardware.

Hardware transport is DDP unicast to the K128D when the controller resolves
(each frame ends with a PUSH packet, so fppd latches exactly one complete
frame per tick — sender-paced, like the WLED boards were). Fallback is
E1.31 multicast with a trailing sync packet, which latches the same way.
Without that end-of-frame latch, FPP free-runs its outputs at 20 fps against
our 30 fps stream and moving patterns flicker — see ddp.py.
"""

import base64
import math
import queue
import threading
import time

from ..ddp import DDPSender
from ..e131 import Sender, iface_for, resolve_controller
from .model import CarModel
from .patterns import REGISTRY, NAMES

_ORDER = {"RGB": (0, 1, 2), "RBG": (0, 2, 1), "GRB": (1, 0, 2),
          "GBR": (1, 2, 0), "BRG": (2, 0, 1), "BGR": (2, 1, 0)}
MAX_FPS = 120.0

# Ordered-dither mask size, in pixels. OFF by default: the flicker it was
# added to fight turned out to be FPP's 20 fps bridge free-run (fixed by the
# per-frame latch in the transports), not quantisation. It remains available
# as an opt-in smoother for banding on dim gradients under a low FPP cap.
# The dither is purely SPATIAL: pixel p always uses phase p % DITHER_CELLS,
# and that never changes between frames.
#
# An earlier version rotated the phase with the frame number (temporal
# dithering) and it was clearly visible: 30 fps / 4 phases = 7.5 Hz per pixel,
# which is near the WORST frequency for human flicker perception, not above
# fusion. At low levels the modulation depth is 100% (LED off vs level 1), so
# near-black areas strobed. Never reintroduce a per-frame phase term here
# unless the frame rate is high enough that the cycle clears ~60 Hz.
DITHER_CELLS = 4
# FPP's per-string brightness is a hard ceiling and it re-quantises whatever we
# send: at B%, its LUT is round(x * B * 2.55 / 255), i.e. steps of 100/B in our
# 0..255 space. Any precision we add finer than that step is thrown away, so
# the dither amplitude has to MATCH the step. Default 10 = FPP at 10%.
DEFAULT_FPP_BRIGHTNESS = 10.0


class Engine:
    def __init__(self, gmap: dict, fps: float = 30.0,
                 fpp_brightness: float = DEFAULT_FPP_BRIGHTNESS,
                 dither: bool = False):
        if not math.isfinite(fps) or not 0 < fps <= MAX_FPS:
            raise ValueError(f"fps must be finite and in the range (0, {MAX_FPS:g}]")
        self.model = CarModel(gmap)
        self.fps = fps
        self._buf = bytearray(self.model.nbytes)
        self.frame = bytes(self.model.nbytes)

        self.lock = threading.Lock()
        self._lifecycle_lock = threading.Lock()
        self.pattern = "plasma"
        # FPP's per-string brightness is the hard hardware ceiling; this is
        # the show-time dimmer on top of it. Start conservative, raise in UI.
        self.brightness = 0.05
        # Every pattern remembers its own knob settings.
        self.pp = {name: pat.params() for name, pat in REGISTRY.items()}
        # Resolve the K128D once up front: DDP needs its IP, and multicast
        # fallback needs the NIC that routes to it (multi-homed hosts
        # otherwise send multicast out the default route).
        self._controller = gmap.get("controller", {})
        probe = resolve_controller(self._controller)
        self.hw = {"enabled": True, "protocol": "ddp", "host": None,
                   "iface": iface_for(probe) if probe else None,
                   "color_order": "RGB", "transport": None, "error": None}
        self._sender_lock = threading.Lock()
        self._sender = None
        self._sender_order = "RGB"
        self._sender_generation = 0
        self._refresh_sender()
        # Downstream (FPP) brightness, so the dither can match its step size.
        self.fpp_brightness = max(0.1, min(100.0, float(fpp_brightness)))
        self.dither = bool(dither)
        self._rebuild_luts()

        self.subs: set[queue.Queue] = set()
        self._running = False
        self._thread: threading.Thread | None = None
        self._t0 = time.monotonic()
        self._meas_fps = 0.0
        self._frames = 0
        self._dropped_frames = 0
        self._dropped_packets = 0
        self._last_fps_t = self._t0

    # --- lookup tables for brightness scaling ---
    @staticmethod
    def _make_lut(b):
        """Smooth (undithered) brightness. Used for the browser preview, which
        should show what the eye integrates, not the dither itself."""
        b = max(0.0, min(1.0, b))
        return bytes(int(i * b) & 0xFF for i in range(256))

    @staticmethod
    def _make_hw_luts(b, fpp_brightness, frames=DITHER_CELLS):
        """One LUT per dither phase, for the hardware path.

        FPP quantises our byte to steps of `q = 100 / fpp_brightness`. So pick
        the *output level* we want, dither the rounding of that level, then
        send level*q back -- FPP's own rounding maps it to exactly that level.

        LUT_k[i] = clamp(floor(i*b/q + (k+0.5)/frames) * q)

        Averaged over the phases this lands on i*b/q, so a region wanting 6.5
        levels comes out as neighbouring pixels at 6,6,7,7 and reads as 6.5 --
        spatially, with no change over time.
        """
        b = max(0.0, min(1.0, b))
        q = max(1.0, 100.0 / max(0.1, fpp_brightness))
        luts = []
        for k in range(frames):
            bias = (k + 0.5) / frames
            luts.append(bytes(
                min(255, int((int(i * b / q + bias)) * q)) & 0xFF
                for i in range(256)))
        return tuple(luts)

    def _rebuild_luts(self) -> None:
        self._lut = self._make_lut(self.brightness)
        self._hw_luts = self._make_hw_luts(self.brightness,
                                           self.fpp_brightness)

    @staticmethod
    def _apply_dither(buf, luts):
        """Spatial ordered dither: pixel p uses phase p % N, fixed in time.

        The phase is chosen per PIXEL, not per byte, so all three channels of a
        pixel round the same way -- a byte-indexed mask makes R, G and B of one
        pixel land on different phases, which shows up as per-pixel hue
        speckle (most obvious on blue).

        Because the mask never moves, a static frame is bit-identical every
        frame: no temporal artefacts at all. Neighbouring pixels differ by at
        most one output level and the eye averages them at any real viewing
        distance.

        Each of the 3*N slices is one C-level translate, so this stays roughly
        as cheap as the single translate it replaces.
        """
        n = len(luts)
        out = bytearray(len(buf))
        stride = 3 * n                     # bytes spanned by N pixels
        for k in range(n):
            lut = luts[k]
            base = k * 3
            for c in range(3):             # R, G, B share this pixel's phase
                out[base + c::stride] = buf[base + c::stride].translate(lut)
        return bytes(out)

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
                self._rebuild_luts()
            if "dither" in upd:
                self.dither = bool(upd["dither"])
            if "fpp_brightness" in upd:
                self.fpp_brightness = max(0.1, min(
                    100.0, float(upd["fpp_brightness"])))
                self._rebuild_luts()
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
                for k in ("enabled", "protocol", "host", "iface",
                          "color_order"):
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
            self.hw["transport"] = None
            if not self.hw["enabled"]:
                return
            host = self.hw["host"] or None
            proto = self.hw.get("protocol") or "ddp"
            if proto == "ddp" and not host:
                host = resolve_controller(self._controller)
            try:
                if proto == "ddp" and host:
                    self._sender = DDPSender(host)
                    self.hw["transport"] = f"ddp -> {host}"
                else:
                    # Controller IP unknown (or e131 requested): multicast
                    # E1.31 with a per-frame sync latch. Same pacing, no IP.
                    self._sender = Sender(host=host,
                                          iface=self.hw["iface"] or None,
                                          source_name="glorb-ui")
                    self.hw["transport"] = (f"e131 -> {host}" if host
                                            else "e131 multicast")
            except (OSError, ValueError) as e:
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
            "dither": self.dither,
            "fpp_brightness": self.fpp_brightness,
            "emoji": REGISTRY["emoji"].label,
            "hardware": hw,
            "fps": round(self._meas_fps, 1),
            "target_fps": self.fps,
            "dropped_frames": self._dropped_frames,
            # UDP packets the kernel refused even after the retry budget --
            # a torn frame on the tubes. Should stay 0; if it climbs, the
            # send path is the flicker suspect.
            "dropped_packets": self._dropped_packets,
        }

    # --- main loop ---
    def _tick(self) -> None:
        with self.lock:
            pattern = self.pattern
            p = dict(self.pp[pattern])
            lut = self._lut
            hw_luts = self._hw_luts
            dither = self.dither
        t = time.monotonic() - self._t0
        REGISTRY[pattern].render(self.model, p, t, self._buf)

        # The preview gets the smooth frame: dithering exists so the eye
        # integrates a value the hardware cannot hold, and the browser should
        # show that integrated value, not the alternation.
        frame = self._buf.translate(lut)
        self.frame = frame
        self._broadcast(frame)

        # The tubes get the dithered frame, pre-multiplied so FPP's own
        # quantisation lands on the level we chose this phase.
        if dither:
            hw = self._apply_dither(self._buf, hw_luts)
        else:
            hw = frame
        self._send_hw(hw)

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
                for start_universe, start, length in self.model.output_spans:
                    chunk = frame[start:start + length]
                    if perm != (0, 1, 2):
                        chunk = self._reorder(chunk, perm)
                    # send_pixels ends the frame with a latch (DDP push /
                    # E1.31 sync) so fppd outputs it whole, immediately.
                    sender.send_pixels(start_universe, chunk)
                # getattr: a stand-in sender need not carry the counter.
                # Cached as a plain int so state() never has to take the
                # sender lock and stall behind an in-flight frame.
                self._dropped_packets = getattr(sender, "dropped_packets", 0)
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
        monotonic, sleep = time.monotonic, time.sleep
        while self._running:
            self._tick()
            self._frames += 1
            now = monotonic()
            if now - self._last_fps_t >= 1.0:
                self._meas_fps = self._frames / (now - self._last_fps_t)
                self._frames = 0
                self._last_fps_t = now
            nxt, dropped = self._advance_deadline(nxt, now, period)
            self._dropped_frames += dropped
            # Coarse sleep, then a short spin to the deadline: time.sleep can
            # overshoot by more than a millisecond (notably on Windows, where
            # the timer tick is 15.6 ms before Python 3.11), which matters at
            # 60 fps. The spin burns at most ~2 ms of CPU per frame.
            remaining = nxt - monotonic()
            if remaining > 0.002:
                sleep(remaining - 0.002)
            while monotonic() < nxt:
                pass

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
