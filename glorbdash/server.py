"""Combined HTTP server: LED control and battery monitoring on one port.

Route map, chosen so both existing front-ends keep working unchanged:

    /                    the merged dashboard
    /app.js              served straight out of the glorbleds package, so the
                         car renderer stays in one place and cannot drift
    /style.css           merged styling (this package)
    /battery.js          the battery meters (this package)

    /layout /state       LED engine, same paths glorbleds serves
    /stream              LED frame stream (SSE)
    /control  (POST)     LED control

    /api/status          battery snapshot
    /api/stream          battery updates (SSE)
    /api/raw             recent raw protocol lines

The battery hub runs its pollers on their own threads and swallows their
failures, so a stuck adapter cannot reach the LED render loop. Both
subsystems still run standalone from their own packages.
"""

import base64
import json
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from glorbleds.webui.engine import Engine
from glorbleds.webui.server import STATIC as LED_STATIC

STATIC = Path(__file__).resolve().parent / "static"
CTYPES = {".html": "text/html", ".js": "application/javascript",
          ".css": "text/css"}
KEEPALIVE_S = 5.0

# Files served from this package, and the one file we hand off to glorbleds.
OWN_FILES = {"/style.css": "style.css", "/battery.js": "battery.js",
             "/ui.js": "ui.js"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def engine(self):
        return self.server.engine

    @property
    def hub(self):
        return self.server.hub

    def log_message(self, *args):
        pass

    # ---- plumbing ---------------------------------------------------------

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path):
        if not path.is_file():
            return self.send_error(404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CTYPES.get(path.suffix, "text/plain"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _open_sse(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b"retry: 2000\n\n")

    # ---- routes -----------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]

        if path in ("/", "/index.html"):
            return self._send_file(STATIC / "index.html")
        if path in OWN_FILES:
            return self._send_file(STATIC / OWN_FILES[path])
        if path == "/app.js":
            # The car renderer stays owned by the lights package.
            return self._send_file(LED_STATIC / "app.js")

        if path == "/layout":
            return self._json(self.engine.model.layout())
        if path == "/state":
            return self._json(self.engine.state())
        if path == "/stream":
            return self._led_stream()

        if path == "/api/status":
            return self._json(self.hub.snapshot())
        if path == "/api/raw":
            return self._json(self.hub.raw())
        if path == "/api/stream":
            return self._battery_stream()

        self.send_error(404)

    def do_POST(self):
        if self.path.split("?", 1)[0] != "/control":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", 0))
        try:
            update = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"ok": False, "error": "bad json"}, 400)
        try:
            self.engine.set_control(update)
        except (KeyError, ValueError, TypeError) as exc:
            return self._json({"ok": False, "error": f"bad control: {exc!r}"},
                              400)
        self._json({"ok": True, "state": self.engine.state()})

    # ---- streams ----------------------------------------------------------

    def _led_stream(self):
        self._open_sse()
        q = self.engine.subscribe()
        try:
            while True:
                try:
                    frame = q.get(timeout=KEEPALIVE_S)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self.wfile.write(b"data: " + base64.b64encode(frame) + b"\n\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.engine.unsubscribe(q)

    def _battery_stream(self):
        self._open_sse()
        q = self.hub.subscribe()
        try:
            self._send_snapshot(self.hub.snapshot())
            while True:
                try:
                    snap = q.get(timeout=KEEPALIVE_S)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self._send_snapshot(snap)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.unsubscribe(q)

    def _send_snapshot(self, snap):
        self.wfile.write(b"data: " + json.dumps(snap).encode() + b"\n\n")
        self.wfile.flush()


def run(gmap, monitor, host="127.0.0.1", port=8080, fps=60.0,
        fpp_brightness=30.0, dither=False, subpixel=1 / 3):
    engine = Engine(gmap, fps=fps, fpp_brightness=fpp_brightness,
                    dither=dither, subpixel=subpixel)
    engine.start()
    monitor.start()

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.engine = engine
    httpd.hub = monitor

    # flush: the banner carries the URL, and it must appear immediately even
    # when the launcher is redirecting stdout to a log.
    say = lambda line: print(line, flush=True)
    say(f"glorb dashboard  ->  http://{host}:{port}/")
    say(f"  lights   {engine.model.total_pixels} px, "
        f"{len(gmap['receivers'])} receivers")
    if monitor.devices:
        for system, device in sorted(monitor.devices.items()):
            say(f"  {system:>7}  {device}")
    else:
        say("  batteries  no adapters found (UI still starts)")
    say("  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        monitor.stop()
        engine.stop()
        httpd.server_close()
