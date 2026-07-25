"""Pattern library. Each pattern fills a canonical-order RGB byte buffer.

Add a pattern: subclass Pattern, set `name`, implement render(); then add an
instance to REGISTRY at the bottom. Brightness is applied by the engine, so
patterns render at full range. Params: speed 0..1, density 0..1,
color1/color2 = (r,g,b).
"""

import math
import random
from pathlib import Path

from .svg_sprite import load_sprite


def hsv(h: float, s: float, v: float):
    i = int(h * 6) % 6
    f = h * 6 - int(h * 6)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    r, g, b = [(v, t, p), (q, v, p), (p, v, t),
               (p, q, v), (t, p, v), (v, p, q)][i]
    return int(r * 255), int(g * 255), int(b * 255)


def _scale(c, f):
    return int(c[0] * f), int(c[1] * f), int(c[2] * f)


def _fire(h):
    """Heat 0..1 -> black->red->orange->yellow-white fire palette."""
    h = 0.0 if h < 0 else (1.0 if h > 1 else h)
    r = min(1.0, h * 1.8)
    g = min(1.0, max(0.0, h * 1.8 - 0.6))
    b = min(1.0, max(0.0, h * 1.8 - 1.4))
    return int(r * 255), int(g * 255), int(b * 255)


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


class RainbowSnake(Pattern):
    """A rainbow snake that slithers around the car while working top->bottom.

    The three lit sides are treated as an unrolled sheet (x = around the
    perimeter, y = down the tubes). The snake follows a boustrophedon path
    over that sheet: around the whole car, drop a row, back around, drop, ...
    so it spirals from the top edge to the bottom, then loops.
    """
    name = "snake"

    def __init__(self):
        self.path = None

    def render(self, m, p, t, buf):
        n = m.total_pixels
        if self.path is None or len(self.path) != n:
            rows = 12
            perim, along = m.perim, m.along
            path = [0.0] * n
            for i in range(n):
                row = int(along[i] * rows)
                if row >= rows:
                    row = rows - 1
                x = perim[i] if row % 2 == 0 else 1.0 - perim[i]
                path[i] = (row + x) / rows
            self.path = path
        path = self.path
        head = (t * p["speed"] * 0.22) % 1.0
        body = 0.06 + p["density"] * 0.5
        cyc = 3
        for i in range(n):
            d = (head - path[i]) % 1.0
            j = i * 3
            if d < body:
                f = 1.0 - d / body
                buf[j], buf[j + 1], buf[j + 2] = hsv(
                    (path[i] * cyc - t * 0.1) % 1.0, 1.0, f)
            else:
                buf[j] = buf[j + 1] = buf[j + 2] = 0


class Brooms(Pattern):
    """Little rainbow brooms sweep around the car, each a vertical rainbow bar
    with a soft trailing wake."""
    name = "brooms"

    def render(self, m, p, t, buf):
        n = m.total_pixels
        count = 1 + int(p["density"] * 5)     # 1..6 brooms
        pos = (t * p["speed"] * 0.22) % 1.0
        width = 0.035                          # bright head half-width (perim)
        tail = 0.16                            # trailing wake length
        perim, along = m.perim, m.along
        centers = [(pos + k / count) % 1.0 for k in range(count)]
        for i in range(n):
            x = perim[i]
            best = 0.0
            for c in centers:
                d = (c - x) % 1.0              # how far the broom swept past
                if d < width:
                    f = 1.0
                elif d < tail:
                    f = 0.7 * (1.0 - (d - width) / (tail - width))
                else:
                    f = 0.0
                if f > best:
                    best = f
            j = i * 3
            if best > 0.0:
                buf[j], buf[j + 1], buf[j + 2] = hsv(
                    (along[i] * 0.85 + t * 0.15) % 1.0, 1.0, best)
            else:
                buf[j] = buf[j + 1] = buf[j + 2] = 0


class Plasma(Pattern):
    """Organic flowing plasma field, rainbow-mapped."""
    name = "plasma"

    def render(self, m, p, t, buf):
        perim, along = m.perim, m.along
        sc = 3.0 + p["density"] * 10.0
        sp = t * p["speed"] * 0.6
        for i in range(m.total_pixels):
            x = perim[i] * sc
            y = along[i] * 3.0
            v = (math.sin(x + sp)
                 + math.sin(y * 1.5 + sp * 0.7)
                 + math.sin((x + y) * 0.8 + sp * 1.3))
            j = i * 3
            buf[j], buf[j + 1], buf[j + 2] = hsv(
                (v / 6.0 + 0.5 + t * 0.02) % 1.0, 1.0, 1.0)


class Fire(Pattern):
    """Flames licking up each tube from the bottom, flickering."""
    name = "fire"

    def __init__(self):
        self.flick = None

    def render(self, m, p, t, buf):
        nt = len(m.tubes)
        ppt = m.px_per_tube
        if self.flick is None or len(self.flick) != nt:
            self.flick = [1.0] * nt
        flick = self.flick
        height = 0.45 + p["density"] * 0.5
        top = 1.0 - height                     # along where the flame starts
        rnd = random.random
        rng = random.uniform
        for ti in range(nt):
            flick[ti] = flick[ti] * 0.72 + rng(0.55, 1.0) * 0.28
            fl = flick[ti]
            base = ti * ppt
            for j in range(ppt):
                a = j / (ppt - 1)              # 0 top, 1 bottom
                heat = (a - top) / height
                idx = (base + j) * 3
                if heat <= 0.0:
                    buf[idx] = buf[idx + 1] = buf[idx + 2] = 0
                else:
                    r, g, b = _fire(heat * fl * (0.8 + 0.2 * rnd()))
                    buf[idx] = r
                    buf[idx + 1] = g
                    buf[idx + 2] = b


class Rain(Pattern):
    """Glowing droplets fall down the bristles, each a random color."""
    name = "rain"

    def __init__(self):
        self.drops = []
        self.last_t = None

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        nt = len(m.tubes)
        ppt = m.px_per_tube
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        fall = 0.3 + p["speed"] * 1.6
        tail = 0.12 + p["density"] * 0.18
        rate = 3.0 + p["density"] * 45.0       # drops/sec
        expected = rate * dt
        spawn = int(expected) + (1 if random.random() < expected - int(expected) else 0)
        for _ in range(spawn):
            self.drops.append([random.randrange(nt), 0.0, random.random()])
        if len(self.drops) > 150:
            self.drops = self.drops[-150:]
        alive = []
        for d in self.drops:
            d[1] += fall * dt
            pos = d[1]
            if pos - tail > 1.0:
                continue
            alive.append(d)
            ti, hue = d[0], d[2]
            base = ti * ppt
            for j in range(ppt):
                dd = pos - j / (ppt - 1)
                if 0.0 <= dd < tail:
                    r, g, b = hsv(hue, 0.55, 1.0 - dd / tail)
                    idx = (base + j) * 3
                    buf[idx] = r
                    buf[idx + 1] = g
                    buf[idx + 2] = b
        self.drops = alive


class Confetti(Pattern):
    """Random multicolor pops that fade out — like glittering confetti."""
    name = "confetti"

    def __init__(self):
        self.lev = None
        self.col = None

    def render(self, m, p, t, buf):
        n = m.total_pixels
        if self.lev is None or len(self.lev) != n:
            self.lev = [0.0] * n
            self.col = [(0, 0, 0)] * n
        lev, col = self.lev, self.col
        for _ in range(1 + int(p["density"] * 30)):
            idx = random.randrange(n)
            lev[idx] = 1.0
            col[idx] = hsv(random.random(), 1.0, 1.0)
        decay = 0.80 + p["speed"] * 0.18
        for i in range(n):
            v = lev[i] * decay
            lev[i] = v
            c = col[i]
            j = i * 3
            buf[j] = int(c[0] * v)
            buf[j + 1] = int(c[1] * v)
            buf[j + 2] = int(c[2] * v)


class Sprite(Pattern):
    """Stamp a rasterized vector icon onto the car surface and sweep it around.

    The three lit sides are an unrolled sheet: x = around the perimeter (perim),
    y = down the tubes (along). The sprite rides across that sheet, wrapping
    around the perimeter, bobbing gently as it goes — a broom sweeping the car.
    """
    TUBE_M = 2.5          # tube length (metres)
    PERIM_M = 9.8         # lit perimeter run (metres)

    def __init__(self, name, sprite):
        self.name = name
        self.sp = sprite
        self.W = sprite["w"]
        self.H = sprite["h"]
        self.alpha = sprite["alpha"]
        self.aspect = sprite["aspect"]

    def render(self, m, p, t, buf):
        n = m.total_pixels
        W, H, alpha = self.W, self.H, self.alpha
        c1, c2 = p["color1"], p["color2"]
        # Sprite height in `along` units; width scaled so the icon keeps aspect
        # (perimeter is ~4x longer in metres than a tube, so x needs squishing).
        sh = 0.35 + p["density"] * 0.5
        wp = sh * self.aspect * (self.TUBE_M / self.PERIM_M)
        cx = (t * p["speed"] * 0.2) % (1.0 + wp) - wp / 2.0
        cy = 0.5 + 0.05 * math.sin(t * 1.7)
        top = cy - sh / 2.0
        perim, along = m.perim, m.along
        for i in range(n):
            u = (perim[i] - cx) / wp
            v = (along[i] - top) / sh
            j = i * 3
            if 0.0 <= u < 1.0 and 0.0 <= v < 1.0:
                a = alpha[int(v * H) * W + int(u * W)]
            else:
                a = 0.0
            if a > 0.0:
                # tint from color1 (body) toward color2 by height, scaled by coverage
                mix = v
                r = (c1[0] * (1 - mix) + c2[0] * mix) * a
                g = (c1[1] * (1 - mix) + c2[1] * mix) * a
                b = (c1[2] * (1 - mix) + c2[2] * mix) * a
                buf[j] = int(r)
                buf[j + 1] = int(g)
                buf[j + 2] = int(b)
            else:
                buf[j] = buf[j + 1] = buf[j + 2] = 0


class Off(Pattern):
    name = "off"

    def render(self, m, p, t, buf):
        for i in range(len(buf)):
            buf[i] = 0


def _load_sprite_patterns():
    """One animated pattern per *.svg in lights/vectors/. Drop in a vector,
    get a sweeping sprite. Failures are skipped so a bad file can't break the UI.
    """
    out = []
    vdir = Path(__file__).resolve().parents[2] / "vectors"
    if not vdir.is_dir():
        return out
    for svg in sorted(vdir.glob("*.svg")):
        try:
            out.append(Sprite(svg.stem, load_sprite(svg)))
        except Exception as e:
            print(f"sprite load failed for {svg.name}: {e}")
    return out


_BASE = [
    Solid(), Rainbow(), RainbowSnake(), Brooms(), Comet(), Wave(),
    BroomStroke(), Sides(), Plasma(), Fire(), Rain(), Confetti(),
    Sparkle(),
]

REGISTRY = {pat.name: pat for pat in _BASE + _load_sprite_patterns() + [Off()]}

NAMES = list(REGISTRY.keys())
