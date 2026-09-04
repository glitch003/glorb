"""Tests for the combined dashboard.

These cover the wiring the merge introduced -- that one process really does
serve both subsystems, that the LED renderer is reused rather than forked,
and that the front-end still finds every element the lights package's app.js
reaches for. The subsystems' own behaviour is tested in lights/tests and
electrical/tests.
"""

import json
import re
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import glorbdash                                            # noqa: E402
from glorbdash import server as dash_server                  # noqa: E402
from glorbleds.controller import load_map                    # noqa: E402
from glorbleds.webui.server import STATIC as LED_STATIC      # noqa: E402
from glorbmon.hub import Hub                                 # noqa: E402

STATIC = dash_server.STATIC


class FakeEngine:
    """Stands in for the LED engine: no render thread, no hardware."""

    class _Model:
        total_pixels = 6068

        def layout(self):
            return {"tubes": [], "pixels_per_tube": 41}

    def __init__(self):
        self.model = self._Model()
        self.controls = []

    def state(self):
        return {"pattern": "plasma", "fps": 60.0, "brightness": 0.4,
                "params": {}, "controls": [], "hardware": {}}

    def set_control(self, update):
        if "explode" in update:
            raise ValueError("nope")
        self.controls.append(update)


class TestStaticWiring(unittest.TestCase):
    """The merged page has to satisfy app.js, which this package does not own."""

    def setUp(self):
        self.html = (STATIC / "index.html").read_text(encoding="utf-8")
        self.app_js = (LED_STATIC / "app.js").read_text(encoding="utf-8")

    def test_every_element_app_js_needs_is_present(self):
        needed = set(re.findall(r'getElementById\("([^"]+)"\)', self.app_js))
        # app.js guards this one -- it only exists on the standalone LED page.
        needed.discard("powerlink")
        missing = [i for i in sorted(needed)
                   if f'id="{i}"' not in self.html]
        self.assertEqual(missing, [], f"index.html is missing {missing}")

    def test_selectors_app_js_queries_are_present(self):
        # It toggles .colors wholesale when a pattern has no colour controls.
        self.assertIn('class="group colors"', self.html)
        self.assertIn('id="patterns"', self.html)
        self.assertIn('id="emojis"', self.html)

    def test_controls_come_before_the_pattern_list(self):
        # The whole point of the overhaul: 52 patterns must not push the
        # sliders off the bottom of the screen.
        self.assertLess(self.html.index('id="brightness"'),
                        self.html.index('id="patterns"'))
        self.assertLess(self.html.index('id="density"'),
                        self.html.index('id="patterns"'))

    def test_pattern_list_height_is_capped(self):
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        block = css[css.index(".patterns {"):]
        self.assertIn("max-height", block[:220])
        self.assertIn("overflow-y: auto", block[:220])

    def test_battery_bar_is_pinned(self):
        css = (STATIC / "style.css").read_text(encoding="utf-8")
        block = css[css.index("#topbar {"):css.index("#topbar {") + 260]
        self.assertIn("position: sticky", block)

    def test_scripts_are_all_served(self):
        for name in ("app.js", "battery.js", "ui.js", "style.css"):
            self.assertIn(name, self.html)

    def test_app_js_is_not_forked_into_this_package(self):
        # It must keep coming from the lights package.
        self.assertFalse((STATIC / "app.js").exists())


class TestRoutes(unittest.TestCase):
    """One process, one port, both APIs."""

    @classmethod
    def setUpClass(cls):
        cls.hub = Hub({"12v": "COM_FAKE"})
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), dash_server.Handler)
        cls.httpd.daemon_threads = True
        cls.httpd.engine = FakeEngine()
        cls.httpd.hub = cls.hub
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever,
                                      daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def get(self, path):
        with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
            return resp.status, resp.headers.get("Content-Type"), resp.read()

    def test_dashboard_page(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "text/html")
        self.assertIn(b"id=\"meters\"", body)

    def test_app_js_comes_from_the_lights_package(self):
        status, ctype, body = self.get("/app.js")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "application/javascript")
        self.assertEqual(body, (LED_STATIC / "app.js").read_bytes())

    def test_own_assets(self):
        for path in ("/style.css", "/battery.js", "/ui.js"):
            status, _, body = self.get(path)
            self.assertEqual(status, 200, path)
            self.assertTrue(body)

    def test_led_endpoints(self):
        status, _, body = self.get("/state")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["pattern"], "plasma")
        status, _, body = self.get("/layout")
        self.assertEqual(status, 200)
        self.assertIn("pixels_per_tube", json.loads(body))

    def test_battery_endpoints(self):
        status, _, body = self.get("/api/status")
        self.assertEqual(status, 200)
        self.assertIn("12v", json.loads(body)["systems"])
        status, _, body = self.get("/api/raw")
        self.assertEqual(status, 200)

    def test_led_and_battery_paths_do_not_collide(self):
        _, _, led = self.get("/state")
        _, _, battery = self.get("/api/status")
        self.assertIn("pattern", json.loads(led))
        self.assertIn("systems", json.loads(battery))

    def test_control_post_reaches_the_engine(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/control",
            data=json.dumps({"brightness": 0.5}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            payload = json.loads(resp.read())
        self.assertTrue(payload["ok"])
        self.assertIn({"brightness": 0.5}, self.httpd.engine.controls)

    def test_bad_control_is_rejected_not_crashed(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/control",
            data=b"{not json",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=5)
        self.assertEqual(ctx.exception.code, 400)

    def test_unknown_paths_404(self):
        for path in ("/nope", "/api/nope", "/../server.py"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(path)
            self.assertEqual(ctx.exception.code, 404, path)


class TestPackageBootstrap(unittest.TestCase):
    def test_both_subsystems_are_importable_from_the_repo_root(self):
        for sub in ("lights", "electrical"):
            self.assertIn(str(glorbdash.ROOT / sub), sys.path)

    def test_the_real_map_still_loads(self):
        gmap = load_map()
        self.assertIn("receivers", gmap)
        self.assertIn("meta", gmap)


if __name__ == "__main__":
    unittest.main()
