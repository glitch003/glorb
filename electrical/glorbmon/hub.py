"""Runs the three pollers side by side and keeps one shared snapshot.

Each system gets its own thread, its own serial port and its own reconnect
loop, so a pack that goes quiet, an adapter that gets unplugged or a vendor
tool that grabs a COM port only ever takes out that one tab. Everything
else keeps updating.
"""

import csv
import queue
import threading
import time
from functools import partial

import serial

from . import eg4, orion, ports, slcan, teslabms

# How often each system is asked for a reading. The EG4 chain is slow to
# answer and its own driver documentation warns against polling it faster
# than every couple of seconds; the Orion side is just draining a buffer that
# fills continuously, so it can run quickly.
INTERVALS = {"12v": 2.0, "24v": 3.0, "72v": 1.0}
# A reading older than this is shown as stale rather than as current truth.
STALE_AFTER_S = 12.0
RECONNECT_MIN_S = 2.0
RECONNECT_MAX_S = 30.0


def _serial_factory(device):
    return partial(serial.Serial, device)


def build_driver(system, device):
    """Construct the driver for one system, bound to a device."""
    factory = _serial_factory(device)
    if system == "12v":
        return eg4.EG4Bus(factory)
    if system == "24v":
        return teslabms.TeslaBMS(factory)
    if system == "72v":
        return orion.OrionBus(slcan.SlcanPort(factory))
    raise ValueError(f"unknown system {system!r}")


class SystemWorker(threading.Thread):
    """Polls one system forever, reconnecting with backoff after failures."""

    def __init__(self, system, device, hub, interval=None):
        super().__init__(name=f"glorbmon-{system}", daemon=True)
        self.system = system
        self.device = device
        self.hub = hub
        self.interval = interval or INTERVALS.get(system, 2.0)
        self.driver = None
        self._stop = threading.Event()
        self._backoff = RECONNECT_MIN_S

    def stop(self):
        self._stop.set()

    def run(self):
        while not self._stop.is_set():
            try:
                if self.driver is None:
                    self.driver = build_driver(self.system, self.device)
                payload, raw = self.driver.poll()
                self._backoff = RECONNECT_MIN_S
                self.hub.update(self.system, self.device, payload, raw)
            except Exception as exc:                # noqa: BLE001
                # Any failure here -- port busy, adapter unplugged, garbled
                # reply -- is a transient to recover from, not a crash.
                self._drop(exc)
                self._stop.wait(self._backoff)
                self._backoff = min(self._backoff * 2, RECONNECT_MAX_S)
                continue
            self._stop.wait(self.interval)
        self._close()

    def _drop(self, exc):
        self.hub.fail(self.system, self.device, exc)
        self._close()

    def _close(self):
        if self.driver is not None:
            try:
                self.driver.close()
            except Exception:                       # noqa: BLE001
                pass
            self.driver = None


DRIVER_META = {
    "12v": (eg4.EG4Bus.title, eg4.EG4Bus.subtitle),
    "24v": (teslabms.TeslaBMS.title, teslabms.TeslaBMS.subtitle),
    "72v": (orion.OrionBus.title, orion.OrionBus.subtitle),
}
ORDER = ["12v", "24v", "72v"]


def explain(exc):
    """Turn a driver exception into something readable at 3am in the dust."""
    text = str(exc) or exc.__class__.__name__
    if isinstance(exc, serial.SerialException):
        if "Access is denied" in text or "PermissionError" in text:
            return "port is held by another program -- close the vendor tool"
        if "could not open port" in text:
            return "adapter not found -- check the USB connection"
    return text


class Hub:
    """Shared state: latest reading per system, plus SSE subscribers."""

    def __init__(self, devices, log_path=None):
        self.devices = dict(devices)
        self._lock = threading.Lock()
        self._systems = {}
        self._raw = {}
        self._subs = []
        self._workers = []
        self._log_path = log_path
        self._log_file = None
        self._log_writer = None
        for system, device in self.devices.items():
            title, subtitle = DRIVER_META[system]
            self._systems[system] = {
                "id": system, "title": title, "subtitle": subtitle,
                "port": device, "state": "down",
                "status_text": "starting up", "summary": [], "updated": 0.0,
            }

    # ---- worker callbacks -------------------------------------------------

    def update(self, system, device, payload, raw):
        now = time.time()
        title, subtitle = DRIVER_META[system]
        entry = {"id": system, "title": title, "subtitle": subtitle,
                 "port": device, "updated": now}
        entry.update(payload)
        with self._lock:
            self._systems[system] = entry
            self._raw[system] = list(raw or [])
        self._log(system, entry)
        self._publish()

    def fail(self, system, device, exc):
        title, subtitle = DRIVER_META[system]
        with self._lock:
            previous = self._systems.get(system, {})
            self._systems[system] = {
                "id": system, "title": title, "subtitle": subtitle,
                "port": device, "state": "down",
                "status_text": explain(exc),
                "summary": [], "updated": previous.get("updated", 0.0),
            }
        self._publish()

    # ---- snapshot ---------------------------------------------------------

    def snapshot(self):
        now = time.time()
        systems, alerts = {}, []
        with self._lock:
            for system in ORDER:
                if system not in self._systems:
                    continue
                entry = dict(self._systems[system])
                updated = entry.pop("updated", 0.0)
                entry["age_s"] = round(now - updated, 1) if updated else None
                if entry["state"] != "down" and updated and \
                        now - updated > STALE_AFTER_S:
                    entry["state"] = "stale"
                    entry["status_text"] = (
                        f"no reading for {now - updated:.0f}s")
                systems[system] = entry
                if entry["state"] in ("fault", "down", "warn", "stale"):
                    level = "fault" if entry["state"] == "fault" else "warn"
                    alerts.append({"system": system, "level": level,
                                   "text": f"{entry['title']}: "
                                           f"{entry['status_text']}"})
        return {"t": now, "systems": systems, "alerts": alerts}

    def raw(self):
        with self._lock:
            return {k: list(v) for k, v in self._raw.items()}

    # ---- SSE fan-out ------------------------------------------------------

    def subscribe(self):
        q = queue.Queue(maxsize=4)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q):
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def _publish(self):
        snap = self.snapshot()
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(snap)
            except queue.Full:
                # A browser that stopped reading must not stall the pollers.
                pass

    # ---- CSV log ----------------------------------------------------------

    def _log(self, system, entry):
        if not self._log_path:
            return
        row = {"time": time.strftime("%Y-%m-%dT%H:%M:%S"), "system": system,
               "state": entry.get("state", "")}
        for item in entry.get("summary", []):
            row[f"{item['label'].lower()}_{item.get('unit', '')}".strip("_")] \
                = item["value"]
        if self._log_writer is None:
            self._log_file = open(self._log_path, "a", newline="",
                                  encoding="utf-8")
            self._log_writer = csv.writer(self._log_file)
            self._log_writer.writerow(["time", "system", "state", "fields"])
        fields = " ".join(f"{k}={v}" for k, v in row.items()
                          if k not in ("time", "system", "state"))
        self._log_writer.writerow([row["time"], system, row["state"], fields])
        self._log_file.flush()

    # ---- lifecycle --------------------------------------------------------

    def start(self):
        for system, device in self.devices.items():
            worker = SystemWorker(system, device, self)
            worker.start()
            self._workers.append(worker)

    def stop(self):
        for worker in self._workers:
            worker.stop()
        for worker in self._workers:
            worker.join(timeout=3.0)
        if self._log_file is not None:
            self._log_file.close()
            self._log_file = None
            self._log_writer = None


def build(overrides=None, log_path=None):
    """Discover adapters and return a Hub wired to whatever is plugged in."""
    devices = ports.resolve(overrides)
    return Hub(devices, log_path=log_path)
