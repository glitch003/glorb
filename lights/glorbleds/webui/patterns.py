"""Pattern library. Each pattern fills a canonical-order RGB byte buffer.

Add a pattern: subclass Pattern, set `name`, implement render(); then add an
instance to REGISTRY at the bottom. Brightness is applied by the engine, so
patterns render at full range. Params: speed 0..1, density 0..1,
color1/color2 = (r,g,b).
"""

import math
import random


def hsv(h: float, s: float, v: float):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def _scale(c, f):
    return int(c[0] * f), int(c[1] * f), int(c[2] * f)


class Pattern:
    name = "base"

    def render(self, m, p, t, buf):
        raise NotImplementedError


class Solid(Pattern):
    name = "solid"

    def render(self, m, p, t, buf):
        buf[:] = bytes(p["color1"]) * m.total_pixels


class Rainbow(Pattern):
    name = "rainbow"

    def render(self, m, p, t, buf):
        cyc = 1 + int(p["density"] * 5)
        off = t * p["speed"] * 0.25
        perim = m.perim
        for i in range(m.total_pixels):
            r, g, b = hsv((perim[i] * cyc + off) % 1.0, 1.0, 1.0)
            j = i * 3
            buf[j], buf[j + 1], buf[j + 2] = r, g, b


class Comet(Pattern):
    name = "comet"

    def render(self, m, p, t, buf):
        head = (t * p["speed"] * 0.3) % 1.0
        tail = 0.03 + p["density"] * 0.4
        c = p["color1"]
        perim = m.perim
        for i in range(m.total_pixels):
            d = (head - perim[i]) % 1.0
            f = (1 - d / tail) if d < tail else 0.0
            j = i * 3
            buf[j] = int(c[0] * f)
            buf[j + 1] = int(c[1] * f)
            buf[j + 2] = int(c[2] * f)


class Wave(Pattern):
    name = "wave"

    def render(self, m, p, t, buf):
        waves = 1 + int(p["density"] * 8)
        c = p["color1"]
        phase = t * p["speed"] * 0.3
        perim = m.perim
        two_pi = 2 * math.pi
        for i in range(m.total_pixels):
            b = 0.15 + 0.85 * (0.5 + 0.5 * math.sin(
                two_pi * (perim[i] * waves - phase)))
            j = i * 3
            buf[j] = int(c[0] * b)
            buf[j + 1] = int(c[1] * b)
            buf[j + 2] = int(c[2] * b)


class BroomStroke(Pattern):
    """Bright band sweeps along each tube (top->bottom), like a stroke."""
    name = "broomstroke"

    def render(self, m, p, t, buf):
        band = 0.1 + p["density"] * 0.3
        c = p["color1"]
        pos = (t * p["speed"] * 0.4) % 1.0
        along = m.along
        for i in range(m.total_pixels):
            d = abs(along[i] - pos)
            f = max(0.0, 1 - d / band)
            j = i * 3
            buf[j] = int(c[0] * f)
            buf[j + 1] = int(c[1] * f)
            buf[j + 2] = int(c[2] * f)


class Sides(Pattern):
    """Left = color1, Right = color2, Back = blend. Confirms orientation."""
    name = "sides"

    def render(self, m, p, t, buf):
        c1, c2 = p["color1"], p["color2"]
        cb = tuple((a + b) // 2 for a, b in zip(c1, c2))
        cols = {"L": bytes(c1), "R": bytes(c2), "B": bytes(cb)}
        side = m.side
        for i in range(m.total_pixels):
            j = i * 3
            buf[j:j + 3] = cols[side[i]]


class Sparkle(Pattern):
    name = "sparkle"

    def __init__(self):
        self.level = None

    def render(self, m, p, t, buf):
        n = m.total_pixels
        if self.level is None or len(self.level) != n:
            self.level = [0.0] * n
        lev = self.level
        spawn = int(1 + p["density"] * 40)
        for _ in range(spawn):
            lev[random.randrange(n)] = 1.0
        decay = 0.80 + p["speed"] * 0.18
        c = p["color1"]
        for i in range(n):
            v = lev[i] * decay
            lev[i] = v
            j = i * 3
            buf[j] = int(c[0] * v)
            buf[j + 1] = int(c[1] * v)
            buf[j + 2] = int(c[2] * v)


class Off(Pattern):
    name = "off"

    def render(self, m, p, t, buf):
        for i in range(len(buf)):
            buf[i] = 0


REGISTRY = {pat.name: pat for pat in [
    Solid(), Rainbow(), Comet(), Wave(), BroomStroke(), Sides(),
    Sparkle(), Off(),
]}

NAMES = list(REGISTRY.keys())
