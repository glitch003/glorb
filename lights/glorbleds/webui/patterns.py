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


def _mix(c1, c2, w):
    """Blend c1 -> c2 by w in 0..1."""
    return (int(c1[0] + (c2[0] - c1[0]) * w),
            int(c1[1] + (c2[1] - c1[1]) * w),
            int(c1[2] + (c2[2] - c1[2]) * w))


class Pattern:
    """`controls` = which UI controls this pattern uses (drives visibility).
    `defaults` = per-pattern starting values, merged over _BASE_DEFAULTS.
    Each pattern keeps its own live params dict in the engine."""
    name = "base"
    controls = ("speed", "density", "color1", "color2")
    defaults = {}
    _BASE_DEFAULTS = {"speed": 0.5, "density": 0.4,
                      "color1": (0, 150, 255), "color2": (255, 60, 0)}

    def params(self) -> dict:
        p = dict(self._BASE_DEFAULTS)
        p.update(self.defaults)
        return p

    def render(self, m, p, t, buf):
        raise NotImplementedError


class Solid(Pattern):
    name = "solid"
    controls = ("color1",)
    defaults = {"color1": (255, 120, 30)}

    def render(self, m, p, t, buf):
        buf[:] = bytes(p["color1"]) * m.total_pixels


class Rainbow(Pattern):
    name = "rainbow"
    controls = ("speed", "density")

    def render(self, m, p, t, buf):
        cyc = 1 + int(p["density"] * 5)
        off = t * p["speed"] * 0.25
        perim = m.perim
        for i in range(m.total_pixels):
            r, g, b = hsv((perim[i] * cyc + off) % 1.0, 1.0, 1.0)
            j = i * 3
            buf[j], buf[j + 1], buf[j + 2] = r, g, b


class Comet(Pattern):
    """Comet circles the car: color1 head fading through color2 tail."""
    name = "comet"
    defaults = {"color1": (255, 255, 255), "color2": (60, 60, 255)}

    def render(self, m, p, t, buf):
        head = (t * p["speed"] * 0.3) % 1.0
        tail = 0.03 + p["density"] * 0.4
        c1, c2 = p["color1"], p["color2"]
        perim = m.perim
        for i in range(m.total_pixels):
            d = (head - perim[i]) % 1.0
            f = (1 - d / tail) if d < tail else 0.0
            j = i * 3
            buf[j] = int((c1[0] * f + c2[0] * (1 - f)) * f)
            buf[j + 1] = int((c1[1] * f + c2[1] * (1 - f)) * f)
            buf[j + 2] = int((c1[2] * f + c2[2] * (1 - f)) * f)


class Wave(Pattern):
    """Waves of color1 <-> color2 rolling around the car."""
    name = "wave"

    def render(self, m, p, t, buf):
        waves = 1 + int(p["density"] * 8)
        c1, c2 = p["color1"], p["color2"]
        phase = t * p["speed"] * 0.3
        perim = m.perim
        two_pi = 2 * math.pi
        for i in range(m.total_pixels):
            w = 0.5 + 0.5 * math.sin(two_pi * (perim[i] * waves - phase))
            j = i * 3
            buf[j] = int(c1[0] + (c2[0] - c1[0]) * w)
            buf[j + 1] = int(c1[1] + (c2[1] - c1[1]) * w)
            buf[j + 2] = int(c1[2] + (c2[2] - c1[2]) * w)


class BroomStroke(Pattern):
    """Bright color1 band sweeps down the tubes over a faint color2 wash."""
    name = "broomstroke"

    def render(self, m, p, t, buf):
        band = 0.1 + p["density"] * 0.3
        c1, c2 = p["color1"], p["color2"]
        bg = (c2[0] * 0.12, c2[1] * 0.12, c2[2] * 0.12)
        pos = (t * p["speed"] * 0.4) % 1.0
        along = m.along
        for i in range(m.total_pixels):
            d = abs(along[i] - pos)
            f = max(0.0, 1 - d / band)
            j = i * 3
            buf[j] = int(c1[0] * f + bg[0] * (1 - f))
            buf[j + 1] = int(c1[1] * f + bg[1] * (1 - f))
            buf[j + 2] = int(c1[2] * f + bg[2] * (1 - f))


class Sparkle(Pattern):
    """color1 glints over a dim color2 base."""
    name = "sparkle"
    defaults = {"color1": (255, 255, 255), "color2": (20, 30, 120)}

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
        c2 = p["color2"]
        b0, b1, b2 = int(c2[0] * 0.10), int(c2[1] * 0.10), int(c2[2] * 0.10)
        for i in range(n):
            v = lev[i] * decay
            lev[i] = v
            j = i * 3
            buf[j] = max(b0, int(c[0] * v))
            buf[j + 1] = max(b1, int(c[1] * v))
            buf[j + 2] = max(b2, int(c[2] * v))


class RainbowSnake(Pattern):
    controls = ("speed", "density")
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


class Plasma(Pattern):
    """Organic flowing plasma field, rainbow-mapped."""
    name = "plasma"
    controls = ("speed", "density")

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
    """Fire2012-style heat simulation per tube: sparks ignite at the bottom,
    heat convects upward, cools, and flames dance independently on every
    bristle. speed = spark rate, density = flame height."""
    name = "fire"
    controls = ("speed", "density")
    defaults = {"density": 0.5}

    # 256-step palette lookup so the hot loop avoids per-pixel function calls
    PAL = [_fire(i / 255.0) for i in range(256)]

    def __init__(self):
        self.heat = None

    def render(self, m, p, t, buf):
        nt = len(m.tubes)
        ppt = m.px_per_tube
        if self.heat is None or len(self.heat) != nt * ppt:
            self.heat = [0.0] * (nt * ppt)
        heat = self.heat
        cool = (1.05 - p["density"]) * 0.09     # more density = taller flames
        sparks = 0.35 + p["speed"] * 0.55       # ignition chance per tube/frame
        rnd = random.random
        pal = self.PAL
        for ti in range(nt):
            base = ti * ppt
            # cool every cell a random amount
            for j in range(ppt):
                h = heat[base + j] - rnd() * cool
                heat[base + j] = h if h > 0.0 else 0.0
            # convect upward (j decreasing = up the tube)
            for j in range(ppt - 3):
                heat[base + j] = (heat[base + j + 1] * 2.0
                                  + heat[base + j + 2]) / 3.05
            # ignite sparks near the bottom
            if rnd() < sparks:
                j = base + ppt - 1 - int(rnd() * 4)
                h = heat[j] + 0.5 + rnd() * 0.5
                heat[j] = h if h < 1.0 else 1.0
            # paint
            for j in range(ppt):
                r, g, b = pal[int(heat[base + j] * 255)]
                idx = (base + j) * 3
                buf[idx] = r
                buf[idx + 1] = g
                buf[idx + 2] = b


class Rain(Pattern):
    """Glowing droplets fall down the bristles, each a random color."""
    name = "rain"
    controls = ("speed", "density")

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
    controls = ("speed", "density")

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
        # Tile as many copies as fit, marching together. Position wraps mod 1
        # so a sprite leaving one end of the U pops out on the other side.
        count = max(1, min(8, int(1.0 / (wp * 1.7))))
        slot = 1.0 / count
        cx = (t * p["speed"] * 0.2) % 1.0
        sin = math.sin
        bob = [0.5 + 0.05 * sin(t * 1.7 + k * 1.3) - sh / 2.0
               for k in range(count)]
        perim, along = m.perim, m.along
        for i in range(n):
            x = (perim[i] - cx) % 1.0
            k = int(x * count)
            u = (x - k * slot) / wp
            j = i * 3
            a = 0.0
            if 0.0 <= u < 1.0:
                v = (along[i] - bob[k]) / sh
                if 0.0 <= v < 1.0:
                    a = alpha[int(v * H) * W + int(u * W)]
            if a > 0.0:
                # tint from color1 (body) toward color2 by height, scaled by coverage
                r = (c1[0] * (1 - v) + c2[0] * v) * a
                g = (c1[1] * (1 - v) + c2[1] * v) * a
                b = (c1[2] * (1 - v) + c2[2] * v) * a
                buf[j] = int(r)
                buf[j + 1] = int(g)
                buf[j + 2] = int(b)
            else:
                buf[j] = buf[j + 1] = buf[j + 2] = 0


class PacMan(Pattern):
    """Pac-Man chomps a boustrophedon path down the car eating a trail of dots,
    a ghost hot on his tail. The three lit sides are an unrolled sheet: he runs
    right across a row, drops down, runs left across the next, spiralling top to
    bottom, then loops back to the top with a fresh field of dots.
    """
    name = "pacman"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (255, 40, 40)}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        n = m.total_pixels
        perim, along = m.perim, m.along
        rows = 4 + int(p["density"] * 4)              # 4..8 rows top->bottom
        g = (t * p["speed"] * 0.15) % 1.0             # descent progress
        # Pac-Man head position on the boustrophedon path.
        row_f = g * rows
        hrow = min(rows - 1, int(row_f))
        frac = row_f - hrow
        h_even = hrow % 2 == 0
        hx = frac if h_even else 1.0 - frac
        hy = (hrow + 0.5) / rows
        hdir = 1.0 if h_even else -1.0
        # Ghost trails behind by a fixed gap in path-progress. Clamp at the top
        # so a fresh lap starts with the ghost on Pac-Man's tail rather than
        # teleporting to the bottom as progress wraps.
        ghost_g = g - 0.32 / rows
        if ghost_g < 0.0:
            ghost_g = 0.0
        grow_f = ghost_g * rows
        grow = min(rows - 1, int(grow_f))
        gfrac = grow_f - grow
        g_even = grow % 2 == 0
        gx = gfrac if g_even else 1.0 - gfrac
        gy = (grow + 0.5) / rows
        # Body radii: round in real metres (perim is ~4x longer than a tube).
        ry = 0.5 / rows
        rx = ry * (self.TUBE_M / self.PERIM_M)
        m_ang = 0.95 * (0.5 + 0.5 * math.sin(t * 7.0))   # mouth half-angle
        ndots = 10
        dot_step = 1.0 / ndots
        dot_ry = ry * 0.32
        dot_rx = 0.006
        pac = (255, 220, 0)
        ghost = p["color1"]
        dot = (255, 255, 255)
        atan2, sqrt = math.atan2, math.sqrt
        for i in range(n):
            px, py = perim[i], along[i]
            j = i * 3
            r = gc = b = 0
            # --- dots on each row's centre-line, eaten once Pac-Man passes ---
            prow = min(rows - 1, int(py * rows))
            cy = (prow + 0.5) / rows
            ddy = py - cy
            if -dot_ry < ddy < dot_ry:
                near = round(px / dot_step) * dot_step
                ddx = px - near
                if -dot_rx < ddx < dot_rx:
                    within = near if prow % 2 == 0 else 1.0 - near
                    if (prow + within) / rows > g:        # not yet eaten
                        r, gc, b = dot
            # --- ghost ---
            dyg = py - gy
            if -ry < dyg < ry:
                dxg = px - gx
                if -rx < dxg < rx:
                    nx, ny = dxg / rx, dyg / ry
                    if nx * nx + ny * ny <= 1.0:
                        r, gc, b = ghost
            # --- Pac-Man (drawn last so he rides on top) ---
            dy = py - hy
            if -ry < dy < ry:
                dx = px - hx
                if -rx < dx < rx:
                    nx, ny = dx / rx, dy / ry
                    if nx * nx + ny * ny <= 1.0:
                        if -m_ang < atan2(ny, nx * hdir) < m_ang:
                            r = gc = b = 0               # open mouth
                        else:
                            r, gc, b = pac
            buf[j], buf[j + 1], buf[j + 2] = r, gc, b


class Breathe(Pattern):
    """Whole car slowly crossfades color1 <-> color2 while breathing."""
    name = "breathe"
    controls = ("speed", "color1", "color2")
    defaults = {"color1": (255, 60, 0), "color2": (120, 0, 255)}

    def render(self, m, p, t, buf):
        ph = (t * (0.03 + p["speed"] * 0.15)) % 1.0
        w = 0.5 - 0.5 * math.cos(2 * math.pi * ph)          # color crossfade
        v = 0.30 + 0.70 * (0.5 - 0.5 * math.cos(4 * math.pi * ph))  # swell
        c = _mix(p["color1"], p["color2"], w)
        buf[:] = bytes(_scale(c, v)) * m.total_pixels


class RainbowBreathe(Pattern):
    """Whole car breathes while the color drifts through the rainbow.
    density = breath depth."""
    name = "rainbreathe"
    controls = ("speed", "density")
    defaults = {"density": 0.7}

    def render(self, m, p, t, buf):
        hue = (t * (0.015 + p["speed"] * 0.09)) % 1.0
        ph = (t * (0.06 + p["speed"] * 0.3)) % 1.0
        depth = 0.15 + p["density"] * 0.75
        v = (1.0 - depth) + depth * (0.5 - 0.5 * math.cos(2 * math.pi * ph))
        buf[:] = bytes(hsv(hue, 1.0, v)) * m.total_pixels


class Aurora(Pattern):
    """Northern-lights curtains drifting around the car, color1 low ->
    color2 high, with slow shimmer."""
    name = "aurora"
    defaults = {"color1": (30, 255, 110), "color2": (140, 40, 255),
                "speed": 0.4, "density": 0.5}

    def render(self, m, p, t, buf):
        nt = len(m.tubes)
        ppt = m.px_per_tube
        c1, c2 = p["color1"], p["color2"]
        sp = t * (0.15 + p["speed"] * 0.6)
        waves = 1.5 + p["density"] * 4.0
        sin, two_pi = math.sin, 2 * math.pi
        # vertical profile + per-row color blend, computed once per frame
        prof = [sin(math.pi * min(1.0, (j / (ppt - 1)) * 1.25)) ** 1.5
                for j in range(ppt)]
        rowc = [_mix(c2, c1, j / (ppt - 1)) for j in range(ppt)]
        for ti in range(nt):
            x = ti / nt
            it = 0.5 + 0.5 * sin(two_pi * x * waves + sp * 2.1)
            it *= 0.6 + 0.4 * sin(two_pi * x * 3.1 - sp * 1.3)
            it *= 0.75 + 0.25 * sin(two_pi * x * 7.3 + sp * 3.7)
            it = it * it * 1.35
            if it > 1.0:
                it = 1.0
            base = ti * ppt * 3
            for j in range(ppt):
                f = it * prof[j]
                c = rowc[j]
                k = base + j * 3
                buf[k] = int(c[0] * f)
                buf[k + 1] = int(c[1] * f)
                buf[k + 2] = int(c[2] * f)


class Meteors(Pattern):
    """Shooting stars streak diagonally down across the bristles: white-hot
    head, color1 tail."""
    name = "meteors"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (80, 140, 255)}

    DRIFT = 0.18      # perimeter drift per unit of fall (diagonal angle)
    TAIL = 0.55       # tail length in along-units

    def __init__(self):
        self.mets = []          # [x0, y, twinkle_seed]
        self.last_t = None

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        nt = len(m.tubes)
        ppt = m.px_per_tube
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        fall = 0.35 + p["speed"] * 1.6
        rate = 0.8 + p["density"] * 10.0
        expected = rate * dt
        spawn = int(expected) + (1 if random.random() < expected - int(expected) else 0)
        for _ in range(spawn):
            self.mets.append([random.random(), -0.05, random.random()])
        if len(self.mets) > 60:
            self.mets = self.mets[-60:]
        c1 = p["color1"]
        alive = []
        step = 1.0 / (ppt - 1)
        for met in self.mets:
            met[1] += fall * dt
            y = met[1]
            if y - self.TAIL > 1.0:
                continue
            alive.append(met)
            # sample the trajectory one tube-pixel at a time, head -> tail
            k = 0
            yy = y
            while yy > y - self.TAIL:
                if 0.0 <= yy <= 1.0:
                    x = (met[0] + yy * self.DRIFT) % 1.0
                    ti = int(x * nt) % nt
                    j = int(yy * (ppt - 1))
                    f = 1.0 - k * step / self.TAIL
                    idx = (ti * ppt + j) * 3
                    if k < 2:                      # white-hot head
                        r, g, b = 255, 255, 255
                    else:
                        r = int(c1[0] * f)
                        g = int(c1[1] * f)
                        b = int(c1[2] * f)
                    if r > buf[idx]:
                        buf[idx] = r
                    if g > buf[idx + 1]:
                        buf[idx + 1] = g
                    if b > buf[idx + 2]:
                        buf[idx + 2] = b
                yy -= step
                k += 1
        self.mets = alive


class Stripes(Pattern):
    """Diagonal candy stripes of color1/color2 spinning around the car."""
    name = "stripes"
    defaults = {"color1": (255, 0, 60), "color2": (255, 255, 255)}

    def render(self, m, p, t, buf):
        k = 2 + int(p["density"] * 10)
        off = t * p["speed"] * 0.35
        c1, c2 = bytes(p["color1"]), bytes(p["color2"])
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            v = (perim[i] * k + along[i] * 0.9 - off) % 1.0
            j = i * 3
            buf[j:j + 3] = c1 if v < 0.5 else c2


class Storm(Pattern):
    """Brooding color1 ambience, ripped by white lightning strikes that
    flicker across neighboring tubes."""
    name = "storm"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (25, 35, 90), "density": 0.4}

    def __init__(self):
        self.flash = None
        self.last_t = None

    def render(self, m, p, t, buf):
        nt = len(m.tubes)
        ppt = m.px_per_tube
        if self.flash is None or len(self.flash) != nt:
            self.flash = [0.0] * nt
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        flash = self.flash
        # strikes
        expected = (0.4 + p["density"] * 4.0) * dt
        if random.random() < expected:
            c = random.randrange(nt)
            spread = 1 + int(random.random() * 3)
            for d in range(-spread, spread + 1):
                lvl = 1.0 - abs(d) / (spread + 1)
                ti = (c + d) % nt
                if lvl > flash[ti]:
                    flash[ti] = lvl
        decay = 0.93 - p["speed"] * 0.12
        c1 = p["color1"]
        sin = math.sin
        for ti in range(nt):
            fl = flash[ti]
            flash[ti] = fl * decay
            if fl > 0.03 and random.random() < 0.25:
                fl *= 0.35                      # strobe-y re-dip
            amb = 0.5 + 0.5 * sin(t * 0.7 + ti * 0.37)
            a = 0.22 + 0.25 * amb
            r = int(min(255, c1[0] * a + 255 * fl))
            g = int(min(255, c1[1] * a + 255 * fl))
            b = int(min(255, c1[2] * a + 255 * fl))
            buf[ti * ppt * 3:(ti + 1) * ppt * 3] = bytes((r, g, b)) * ppt


class EmojiSprite(Pattern):
    """Full-color bitmaps (emoji rasterized by the browser) parading around
    the car. One emoji gets tiled into several copies; pasting several
    different emojis cycles through them around the perimeter."""
    name = "emoji"
    controls = ("speed", "density")

    TUBE_M = 2.5
    PERIM_M = 9.8

    def __init__(self):
        self.images = []        # [(w, h, rgba), ...]
        self.label = ""

    def set_images(self, images, label=""):
        for w, h, rgba in images:
            if w * h * 4 != len(rgba):
                raise ValueError("rgba size mismatch")
        self.images = list(images)
        self.label = label

    def render(self, m, p, t, buf):
        if not self.images:
            buf[:] = bytes(len(buf))
            return
        n = m.total_pixels
        sh = 0.35 + p["density"] * 0.5
        w0, h0, _ = self.images[0]
        wp = sh * (w0 / h0) * (self.TUBE_M / self.PERIM_M)
        # As many copies as fit with breathing room, at least one per image.
        count = max(len(self.images), min(8, int(1.0 / (wp * 1.7))))
        slot = 1.0 / count
        cx = (t * p["speed"] * 0.2) % 1.0
        perim, along = m.perim, m.along
        imgs = self.images
        nimg = len(imgs)
        sin = math.sin
        bob = [0.5 + 0.05 * sin(t * 1.7 + k * 1.3) - sh / 2.0
               for k in range(count)]
        for i in range(n):
            x = (perim[i] - cx) % 1.0
            k = int(x * count)
            u = (x - k * slot) / wp
            j = i * 3
            if 0.0 <= u < 1.0:
                W, H, rgba = imgs[k % nimg]
                v = (along[i] - bob[k]) / sh
                if 0.0 <= v < 1.0:
                    q = (int(v * H) * W + int(u * W)) * 4
                    a = rgba[q + 3]
                    if a:
                        buf[j] = rgba[q] * a // 255
                        buf[j + 1] = rgba[q + 1] * a // 255
                        buf[j + 2] = rgba[q + 2] * a // 255
                        continue
            buf[j] = buf[j + 1] = buf[j + 2] = 0


class Mapping(Pattern):
    """Diagnostic for verifying physical tube order + data direction.

    Per tube (by position within its group): 1=red, 2=green, 3=blue,
    4=yellow. First 8 px = white (logical pixel 0), then the tube color
    fading bright->dim toward the logical end. Static, so a photo of the
    install shows which tubes are swapped or upside down.
    """
    name = "mapping"
    controls = ()

    COLORS = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
    HEAD = 8

    def render(self, m, p, t, buf):
        ppt = m.px_per_tube
        per_group = m.map["meta"]["tubes_per_group"]
        for ti in range(len(m.tubes)):
            c = self.COLORS[ti % per_group]
            base = ti * ppt
            for j in range(ppt):
                idx = (base + j) * 3
                if j < self.HEAD:
                    buf[idx] = buf[idx + 1] = buf[idx + 2] = 255
                else:
                    f = 1.0 - 0.75 * (j - self.HEAD) / (ppt - 1 - self.HEAD)
                    buf[idx] = int(c[0] * f)
                    buf[idx + 1] = int(c[1] * f)
                    buf[idx + 2] = int(c[2] * f)


class Off(Pattern):
    name = "off"
    controls = ()

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
    tuned = {"burningman": {"color1": (255, 150, 0), "color2": (255, 30, 0),
                            "density": 0.9, "speed": 0.4}}
    for svg in sorted(vdir.glob("*.svg")):
        try:
            pat = Sprite(svg.stem, load_sprite(svg))
            if svg.stem in tuned:
                pat.defaults = tuned[svg.stem]
            out.append(pat)
        except Exception as e:
            print(f"sprite load failed for {svg.name}: {e}")
    return out


_BASE = [
    Rainbow(), Aurora(), Fire(), Plasma(), RainbowSnake(), Meteors(),
    Storm(), Stripes(), Breathe(), RainbowBreathe(), Wave(), Comet(),
    Rain(), Sparkle(), Confetti(), BroomStroke(), PacMan(), Solid(),
    EmojiSprite(),
]

REGISTRY = {pat.name: pat for pat in
            _BASE + _load_sprite_patterns() + [Mapping(), Off()]}

NAMES = list(REGISTRY.keys())
