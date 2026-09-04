"""Stdlib HTTP server: the dashboard, a JSON snapshot, and an SSE stream."""

import json
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC = Path(__file__).resolve().parent / "static"
CTYPES = {".html": "text/html", ".js": "application/javascript",
          ".css": "text/css"}
KEEPALIVE_S = 5.0


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def hub(self):
        return self.server.hub

    def log_message(self, *args):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _file(self, name):
        path = STATIC / name
        # Serve only the three known assets; never join user input onto STATIC.
        if not path.is_file():
            return self.send_error(404)
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", CTYPES.get(path.suffix, "text/plain"))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            return self._file("index.html")
        if path in ("/app.js", "/style.css"):
            return self._file(path.lstrip("/"))
        if path == "/api/status":
            return self._json(self.hub.snapshot())
        if path == "/api/raw":
            return self._json(self.hub.raw())
        if path == "/api/stream":
            return self._stream()
        self.send_error(404)

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        q = self.hub.subscribe()
        try:
            self.wfile.write(b"retry: 2000\n\n")
            self._send_event(self.hub.snapshot())
            while True:
                try:
                    snap = q.get(timeout=KEEPALIVE_S)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self._send_event(snap)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.hub.unsubscribe(q)

    def _send_event(self, snap):
        self.wfile.write(b"data: " + json.dumps(snap).encode() + b"\n\n")
        self.wfile.flush()


def run(hub, host="127.0.0.1", port=8081):
    hub.start()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    httpd.hub = hub
    print(f"glorb power monitor  ->  http://{host}:{port}/")
    if hub.devices:
        for system, device in sorted(hub.devices.items()):
            print(f"  {system:>4}  {device}")
    else:
        print("  no known adapters found -- check USB, or pass --port-*")
    print("  Ctrl-C to stop.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopping...")
    finally:
        hub.stop()
        httpd.server_close()
