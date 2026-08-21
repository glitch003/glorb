"""Stdlib HTTP server: static UI + SSE frame stream + control POST."""

import base64
import json
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from ..controller import load_map
from .engine import Engine

STATIC = Path(__file__).resolve().parent / "static"
CTYPES = {".html": "text/html", ".js": "application/javascript",
          ".css": "text/css"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def engine(self) -> Engine:
        return self.server.engine

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name):
        path = STATIC / name
        if not path.is_file():
            self.send_error(404)
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CTYPES.get(path.suffix, "text/plain"))
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            return self._file("index.html")
        if self.path in ("/app.js", "/style.css"):
            return self._file(self.path.lstrip("/"))
        if self.path == "/layout":
            return self._json(self.engine.model.layout())
        if self.path == "/state":
            return self._json(self.engine.state())
        if self.path == "/stream":
            return self._stream()
        self.send_error(404)

    def do_POST(self):
        if self.path != "/control":
            return self.send_error(404)
        length = int(self.headers.get("Content-Length", 0))
        try:
            upd = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"ok": False, "error": "bad json"}, 400)
        try:
            self.engine.set_control(upd)
        except (KeyError, ValueError, TypeError) as e:
            return self._json({"ok": False, "error": f"bad control: {e!r}"}, 400)
        self._json({"ok": True, "state": self.engine.state()})

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        q = self.engine.subscribe()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            while True:
                try:
                    frame = q.get(timeout=5.0)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    continue
                payload = base64.b64encode(frame)
                self.wfile.write(b"data: " + payload + b"\n\n")
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.engine.unsubscribe(q)


def run(gmap=None, host="127.0.0.1", port=8080, fps=60.0,
        fpp_brightness=10.0, dither=False):
    gmap = gmap or load_map()
    engine = Engine(gmap, fps=fps, fpp_brightness=fpp_brightness,
                    dither=dither)
    engine.start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.engine = engine
    url = f"http://{host}:{port}/"
    print(f"glorb control UI  ->  {url}")
    print(f"  {engine.model.total_pixels} px, "
          f"{len(gmap['receivers'])} receivers. Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        engine.stop()
        httpd.server_close()
