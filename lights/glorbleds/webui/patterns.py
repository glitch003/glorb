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


def _frame_steps(last_t, t):
    """Elapsed time as 30 Hz simulation steps, capped after pauses."""
    if last_t is None:
        return 1.0
    return max(0.0, min(3.0, (t - last_t) * 30.0))


def _event_count(events_per_step, steps):
    """Stochastically round an event rate while preserving its time basis."""
    expected = events_per_step * steps
    whole = int(expected)
    fraction = expected - whole
    return whole + (1 if fraction > 0.0 and random.random() < fraction else 0)


def _event_probability(probability_per_step, steps):
    """Probability of at least one event across fractional reference steps."""
    probability_per_step = max(0.0, min(1.0, probability_per_step))
    return 1.0 - (1.0 - probability_per_step) ** steps


def _side_unroll(m):
    """Per-pixel side-local coords, cached on the model. Returns (sx, sid,
    fracs): sx[i] = 0..1 across the pixel's own side, sid[i] = side index,
    fracs[s] = that side's share of the whole perimeter."""
    cached = getattr(m, "_side_unroll_cache", None)
    if cached is None:
        n = m.total_pixels
        counts = []
        last = None
        for s in m.side:
            if s != last:
                counts.append(0)
                last = s
            counts[-1] += 1
        fracs = [c / n for c in counts]
        # sx from the tube's physical slot (tube "pos"), not canonical
        # order — mirrored-hung lines make those differ (tube_map.py
        # REVERSED_LINES).
        side_k = {}
        last = None
        for s in m.side:
            if s != last:
                side_k[s] = len(side_k)
                last = s
        ppt = m.px_per_tube
        sx = [0.0] * n
        sid = [0] * n
        for i in range(n):
            t = m.tubes[m.tube_of[i]]
            k = side_k[t["side"]]
            sx[i] = (t["pos"] * ppt + (i - m.tube_of[i] * ppt)) / counts[k]
            sid[i] = k
        cached = (sx, sid, fracs)
        m._side_unroll_cache = cached
    return cached


def _side_slots(m, wp, gap):
    """Slot tiling that restarts at every corner of the car, so shapes never
    bend around one. wp = sprite width in whole-perimeter units, gap = slot
    breathing-room factor. Returns (sx, sid, counts, koff, widths, scale):
    per-pixel side-local x + side index; per-side slot count, global
    slot-index offset (for phase tables), sprite width in side-local units,
    and a shrink factor (<1 when a side is too short for the sprite —
    apply it to the vertical extent too, to keep the shape's aspect)."""
    sx, sid, fracs = _side_unroll(m)
    counts = [max(1, int(f / (wp * gap))) for f in fracs]
    koff = []
    acc = 0
    for c in counts:
        koff.append(acc)
        acc += c
    widths = []
    scale = []
    for f, c in zip(fracs, counts):
        w = wp / f
        sc = min(1.0, (0.92 / c) / w)
        widths.append(w * sc)
        scale.append(sc)
    return sx, sid, counts, koff, widths, scale


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
        self.last_t = None

    def render(self, m, p, t, buf):
        n = m.total_pixels
        if self.level is None or len(self.level) != n:
            self.level = [0.0] * n
        lev = self.level
        steps = _frame_steps(self.last_t, t)
        self.last_t = t
        spawn = _event_count(1 + p["density"] * 40, steps)
        for _ in range(spawn):
            lev[random.randrange(n)] = 1.0
        decay = (0.80 + p["speed"] * 0.18) ** steps
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
        self.last_t = None
        self._accumulator = 0.0

    def _step(self, nt, ppt, p):
        heat = self.heat
        assert heat is not None
        cool = (1.05 - p["density"]) * 0.09     # more density = taller flames
        sparks = 0.35 + p["speed"] * 0.55       # ignition chance per tube/step
        rnd = random.random
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

    def render(self, m, p, t, buf):
        nt = len(m.tubes)
        ppt = m.px_per_tube
        if self.heat is None or len(self.heat) != nt * ppt:
            self.heat = [0.0] * (nt * ppt)
        if self.last_t is None:
            elapsed = 1.0 / 30.0
        else:
            elapsed = max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        self._accumulator += elapsed
        steps = int(self._accumulator * 30.0 + 1e-9)
        self._accumulator -= steps / 30.0
        for _ in range(steps):
            self._step(nt, ppt, p)

        heat = self.heat
        pal = self.PAL
        for i, value in enumerate(heat):
            r, g, b = pal[int(value * 255)]
            idx = i * 3
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
        self.last_t = None

    def render(self, m, p, t, buf):
        n = m.total_pixels
        if self.lev is None or len(self.lev) != n:
            self.lev = [0.0] * n
            self.col = [(0, 0, 0)] * n
        lev, col = self.lev, self.col
        steps = _frame_steps(self.last_t, t)
        self.last_t = t
        for _ in range(_event_count(1 + int(p["density"] * 30), steps)):
            idx = random.randrange(n)
            lev[idx] = 1.0
            col[idx] = hsv(random.random(), 1.0, 1.0)
        decay = (0.80 + p["speed"] * 0.18) ** steps
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


_CUBE_VERTS = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
_CUBE_EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8)
               if sum(1 for i in range(3)
                      if _CUBE_VERTS[a][i] != _CUBE_VERTS[b][i]) == 1]


class Cubes(Pattern):
    """3D wireframe cubes tumbling in place around the car. Edges shade
    color2 (far) -> color1 (near) by depth. density = cube size,
    speed = spin rate."""
    name = "cubes"
    defaults = {"color1": (0, 255, 190), "color2": (170, 0, 255),
                "density": 0.5}

    TUBE_M = 2.5
    PERIM_M = 9.8

    VERTS = _CUBE_VERTS
    EDGES = _CUBE_EDGES

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        n = m.total_pixels
        sh = 0.30 + p["density"] * 0.5          # cube box height (along units)
        wp = sh * (self.TUBE_M / self.PERIM_M)  # same box width (perim units)
        count = max(1, min(6, int(1.0 / (wp * 1.6))))
        slot = 1.0 / count
        drift = (t * p["speed"] * 0.06) % 1.0
        spin = t * (0.3 + p["speed"] * 1.4)
        c1, c2 = p["color1"], p["color2"]
        sin, cos, sqrt = math.sin, math.cos, math.sqrt

        # Per-cube: rotate vertices, project orthographically to the cube's
        # local square (u,v in -1..1), keep z for depth shading.
        cubes = []
        for k in range(count):
            ax = spin * 0.9 + k * 2.1
            ay = spin * 0.7 + k * 1.3
            ca, sa = cos(ax), sin(ax)
            cb, sb = cos(ay), sin(ay)
            pts = []
            for x, y, z in self.VERTS:
                y, z = y * ca - z * sa, y * sa + z * ca
                x, z = x * cb + z * sb, -x * sb + z * cb
                pts.append((x * 0.62, y * 0.62, z * 0.62))
            segs = []
            for a, b in self.EDGES:
                x1, y1, z1 = pts[a]
                x2, y2, z2 = pts[b]
                dx, dy = x2 - x1, y2 - y1
                l2 = dx * dx + dy * dy
                if l2 < 1e-9:           # edge seen end-on: a point
                    l2 = 1.0
                    dx = dy = 0.0
                segs.append((x1, y1, dx, dy, l2, (z1 + z2) * 0.5))
            cubes.append(segs)

        th = 0.16                               # edge half-thickness (local units)
        cy = 0.5                                # cubes ride the vertical center
        perim, along = m.perim, m.along
        for i in range(n):
            v = (along[i] - cy) / (sh * 0.5)
            if v < -1.1 or v > 1.1:
                continue
            x = (perim[i] - drift) % 1.0
            k = int(x * count)
            u = (x - (k + 0.5) * slot) / (wp * 0.5)
            if u < -1.1 or u > 1.1:
                continue
            best = th
            bz = 0.0
            for x1, y1, dx, dy, l2, z in cubes[k]:
                px, py = u - x1, v - y1
                w = (px * dx + py * dy) / l2
                if w < 0.0:
                    w = 0.0
                elif w > 1.0:
                    w = 1.0
                ex, ey = px - dx * w, py - dy * w
                d = sqrt(ex * ex + ey * ey)
                if d < best:
                    best = d
                    bz = z
            if best < th:
                f = 1.0 - best / th
                w = (bz / 0.62 + 1.0) * 0.5     # 0 = far, 1 = near
                if w < 0.0:
                    w = 0.0
                elif w > 1.0:
                    w = 1.0
                depth = 0.35 + 0.65 * w
                j = i * 3
                buf[j] = int((c2[0] + (c1[0] - c2[0]) * w) * f * depth)
                buf[j + 1] = int((c2[1] + (c1[1] - c2[1]) * w) * f * depth)
                buf[j + 2] = int((c2[2] + (c1[2] - c2[2]) * w) * f * depth)


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
        steps = _frame_steps(self.last_t, t)
        self.last_t = t
        flash = self.flash
        # strikes
        strike_per_step = (0.4 + p["density"] * 4.0) / 30.0
        if random.random() < _event_probability(strike_per_step, steps):
            c = random.randrange(nt)
            spread = 1 + int(random.random() * 3)
            for d in range(-spread, spread + 1):
                lvl = 1.0 - abs(d) / (spread + 1)
                ti = (c + d) % nt
                if lvl > flash[ti]:
                    flash[ti] = lvl
        decay = (0.93 - p["speed"] * 0.12) ** steps
        redip = _event_probability(0.25, steps)
        c1 = p["color1"]
        sin = math.sin
        for ti in range(nt):
            fl = flash[ti]
            flash[ti] = fl * decay
            if fl > 0.03 and random.random() < redip:
                fl *= 0.35                      # strobe-y re-dip
            amb = 0.5 + 0.5 * sin(t * 0.7 + ti * 0.37)
            a = 0.22 + 0.25 * amb
            r = int(min(255, c1[0] * a + 255 * fl))
            g = int(min(255, c1[1] * a + 255 * fl))
            b = int(min(255, c1[2] * a + 255 * fl))
            buf[ti * ppt * 3:(ti + 1) * ppt * 3] = bytes((r, g, b)) * ppt


class EmojiSprite(Pattern):
    """Full-color bitmaps (emoji rasterized by the browser) bouncing around
    the car DVD-logo style. Several copies drift on their own trajectories
    and bounce off the edges of the unrolled sheet; pasting several
    different emojis gives each bouncer its own image."""
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
        buf[:] = bytes(len(buf))
        if not self.images:
            return
        imgs = self.images
        nimg = len(imgs)
        # density = how many bouncers; size shrinks a little as the swarm grows
        count = max(nimg, 1 + int(p["density"] * 7.99))
        sh = 0.55 - 0.025 * count
        base_v = 0.02 + p["speed"] * 0.06
        sprites = []
        for k in range(count):
            W, H, rgba = imgs[k % nimg]
            wp = sh * (W / H) * (self.TUBE_M / self.PERIM_M)
            # each bouncer gets its own speed and starting corner
            vx = base_v * (0.7 + 0.6 * ((k * 0.37) % 1.0))
            vy = vx * self.PERIM_M / self.TUBE_M * 0.83
            spx = max(1e-6, 1.0 - wp)
            spy = max(1e-6, 1.0 - sh)
            px_ = (t * vx + k * 0.71) % (2 * spx)
            py_ = (t * vy + k * 1.37) % (2 * spy)
            x0 = px_ if px_ < spx else 2 * spx - px_
            y0 = py_ if py_ < spy else 2 * spy - py_
            sprites.append((x0, y0, wp, W, H, rgba))
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            x, y = perim[i], along[i]
            j = i * 3
            for x0, y0, wp, W, H, rgba in sprites:
                u = (x - x0) / wp
                if not 0.0 <= u < 1.0:
                    continue
                v = (y - y0) / sh
                if not 0.0 <= v < 1.0:
                    continue
                q = (int(v * H) * W + int(u * W)) * 4
                a = rgba[q + 3]
                if a:
                    buf[j] = rgba[q] * a // 255
                    buf[j + 1] = rgba[q + 1] * a // 255
                    buf[j + 2] = rgba[q + 2] * a // 255
                    break


class Butthole(Pattern):
    """Puckered starburst rings around winking centers. It is what it looks
    like. density = size, speed = wink rate. color1 = outer skin,
    color2 = inner rim."""
    name = "butthole"
    defaults = {"color1": (255, 130, 150), "color2": (140, 55, 25),
                "density": 0.6, "speed": 0.4}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.45 + p["density"] * 0.5           # diameter in along units
        wp = sh * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.5)
        c1, c2 = p["color1"], p["color2"]
        sin, atan2, sqrt = math.sin, math.atan2, math.sqrt
        # each pucker clenches and relaxes on its own rhythm
        wink = [0.5 + 0.5 * sin(t * (0.6 + p["speed"] * 2.4) + k * 2.4)
                for k in range(koff[-1] + counts[-1])]
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            v = (along[i] - 0.5) / (sh * 0.5 * scale[s])
            if not -1.0 < v < 1.0:
                continue
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            k += koff[s]
            r = sqrt(u * u + v * v)
            if r >= 1.0:
                continue
            w = wink[k]
            hole = 0.08 + 0.14 * w
            j = i * 3
            if r < hole:
                d = r / hole
                buf[j] = int(35 * d)
                buf[j + 1] = int(10 * d)
                buf[j + 2] = int(10 * d)
                continue
            g = (r - hole) / (1.0 - hole)        # 0 at rim -> 1 at edge
            ang = atan2(v, u)
            # radial wrinkles that tighten as it clenches
            wr = 0.5 + 0.5 * sin(ang * 17.0 + r * 5.0 * (1.0 + w))
            base = _mix(c2, c1, g)
            f = (0.45 + 0.55 * wr) * (1.0 - g * g * 0.6)
            buf[j] = int(base[0] * f)
            buf[j + 1] = int(base[1] * f)
            buf[j + 2] = int(base[2] * f)


class GooglyEyes(Pattern):
    """A ring of googly eyes around the car: pupils wander, eyes blink at
    random-ish moments. color1 = iris. density = eye size, speed = fidgetiness."""
    name = "eyes"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (40, 90, 255), "density": 0.6}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.40 + p["density"] * 0.45
        wp = sh * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.5)
        c1 = p["color1"]
        sin, sqrt = math.sin, math.sqrt
        sp = 0.4 + p["speed"] * 1.6
        looks = []      # (pupil dx, pupil dy, lid openness) per eye
        for k in range(koff[-1] + counts[-1]):
            lx = 0.38 * sin(t * sp * 0.7 + k * 1.9) * sin(t * 0.31 + k)
            ly = 0.30 * sin(t * sp * 1.1 + k * 3.1)
            ph = (t * (0.15 + p["speed"] * 0.35) + k * 0.37) % 1.0
            open_ = min(1.0, abs(ph - 0.05) / 0.05) if ph < 0.10 else 1.0
            looks.append((lx, ly, max(0.04, open_)))
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            v = (along[i] - 0.5) / (sh * 0.5 * scale[s])
            if not -1.0 < v < 1.0:
                continue
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            lx, ly, open_ = looks[koff[s] + k]
            vv = v / open_                       # blink = vertical squash
            if u * u + vv * vv > 1.0:
                continue
            j = i * 3
            du, dv = u - lx, v - ly
            d = sqrt(du * du + dv * dv)
            if d < 0.18:                         # pupil
                buf[j] = buf[j + 1] = buf[j + 2] = 8
            elif d < 0.40:                       # iris
                f = 1.0 - (d - 0.18) / 0.22 * 0.5
                buf[j] = int(c1[0] * f)
                buf[j + 1] = int(c1[1] * f)
                buf[j + 2] = int(c1[2] * f)
            else:                                # sclera
                buf[j] = buf[j + 1] = buf[j + 2] = 235


class Lava(Pattern):
    """Lava-lamp metaball blobs oozing up and down the bristles,
    color1 core -> color2 glow. density = blob count/size, speed = ooze rate."""
    name = "lava"
    defaults = {"color1": (255, 40, 0), "color2": (255, 170, 0),
                "speed": 0.35, "density": 0.5}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        nb = 4 + int(p["density"] * 6)
        sp = 0.05 + p["speed"] * 0.25
        aspect = self.PERIM_M / self.TUBE_M
        sin = math.sin
        blobs = []
        for k in range(nb):
            bx = (k / nb + 0.13 * sin(t * sp * 0.6 + k * 2.7)) % 1.0
            by = 0.5 + 0.44 * sin(t * sp * (1.0 + 0.31 * k) + k * 1.7)
            s = 0.18 + 0.10 * sin(k * 5.1 + t * sp * 0.9)
            blobs.append((bx, by, s * s))
        c1, c2 = p["color1"], p["color2"]
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            px, py = perim[i], along[i]
            f = 0.0
            for bx, by, s2 in blobs:
                dx = px - bx
                if dx > 0.5:
                    dx -= 1.0
                elif dx < -0.5:
                    dx += 1.0
                dx *= aspect
                dy = py - by
                f += s2 / (dx * dx + dy * dy + 1e-4)
            j = i * 3
            if f > 1.0:
                w = min(1.0, (f - 1.0) * 0.8)    # 0 at surface -> 1 deep inside
                c = _mix(c2, c1, w)
                buf[j], buf[j + 1], buf[j + 2] = c
            else:
                g = f * f * 0.25                 # faint ambient glow outside
                buf[j] = int(c1[0] * g)
                buf[j + 1] = int(c1[1] * g)
                buf[j + 2] = int(c1[2] * g)


class Hypno(Pattern):
    """Spinning hypno-spirals. Stare into the broom. density = spiral
    tightness, speed = spin."""
    name = "hypno"
    defaults = {"color1": (255, 255, 255), "color2": (190, 0, 255),
                "density": 0.5}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.9
        wp = sh * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.4)
        turns = 2.0 + p["density"] * 5.0
        spin = t * (0.2 + p["speed"] * 1.2)
        c1, c2 = bytes(p["color1"]), bytes(p["color2"])
        atan2, sqrt, two_pi = math.atan2, math.sqrt, 2 * math.pi
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            v = (along[i] - 0.5) / (sh * 0.5 * scale[s])
            if not -1.0 < v < 1.0:
                continue
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            k += koff[s]
            r = sqrt(u * u + v * v)
            if r >= 1.0:
                continue
            ang = atan2(v, u) / two_pi
            s = (ang + r * turns - spin * (1 if k % 2 == 0 else -1)) % 1.0
            buf[i * 3:i * 3 + 3] = c1 if s < 0.5 else c2


class Fireworks(Pattern):
    """Rockets shoot up the bristles and burst into gravity-bent spark
    showers. speed = launch rate, density = burst size."""
    name = "fireworks"
    controls = ("speed", "density")

    PERIM_OVER_TUBE = 9.8 / 2.5

    def __init__(self):
        self.shells = []        # [x, y, vy, hue, age, sparks|None]
        self.last_t = None

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        nt = len(m.tubes)
        ppt = m.px_per_tube
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        rate = 0.5 + p["speed"] * 3.0
        expected = rate * dt
        if random.random() < expected:
            self.shells.append([random.random(), 1.05,
                                0.8 + random.random() * 0.6,
                                random.random(), 0.0, None])
        if len(self.shells) > 12:
            self.shells = self.shells[-12:]
        cos, sin = math.cos, math.sin

        def stamp(x, y, r, g, b):
            if 0.0 <= y <= 1.0:
                ti = int((x % 1.0) * nt) % nt
                idx = (ti * ppt + int(y * (ppt - 1))) * 3
                if r > buf[idx]:
                    buf[idx] = r
                if g > buf[idx + 1]:
                    buf[idx + 1] = g
                if b > buf[idx + 2]:
                    buf[idx + 2] = b

        alive = []
        for sh in self.shells:
            x, y, vy, hue, age, sparks = sh
            if sparks is None:                       # ---- launch phase ----
                y -= vy * dt
                sh[1] = y
                burst_y = 0.15 + 0.25 * hue
                if y <= burst_y:                     # explode
                    n = 14 + int(p["density"] * 26)
                    sh[5] = [(cos(a * 2 * math.pi / n + hue) * 0.55,
                              sin(a * 2 * math.pi / n + hue) * 0.55
                              * (0.6 + 0.4 * random.random()))
                             for a in range(n)]
                    sh[4] = 0.0
                else:
                    stamp(x, y, 255, 220, 160)
                    stamp(x, y + 1.5 / ppt, 160, 90, 30)
                alive.append(sh)
            else:                                    # ---- burst phase ----
                age += dt
                sh[4] = age
                life = 1.3
                if age < life:
                    f = 1.0 - age / life
                    if f < 0.4 and random.random() < 0.4:
                        f *= 0.3                     # dying twinkle
                    r0, g0, b0 = hsv(hue, 0.75, f)
                    for vx, vs in sparks:
                        sy = y + vs * age + 0.35 * age * age   # gravity
                        sx = x + vx * age / self.PERIM_OVER_TUBE
                        stamp(sx, sy, r0, g0, b0)
                    alive.append(sh)
        self.shells = alive


class Matrix(Pattern):
    """Digital rain: green code streams down every bristle, white-hot heads,
    flickering glyph tails. speed = fall rate, density = stream count."""
    name = "matrix"
    controls = ("speed", "density")

    def __init__(self):
        self.streams = []       # [tube, y, speed, length]
        self.last_t = None

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        nt = len(m.tubes)
        ppt = m.px_per_tube
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        rate = 2.0 + p["density"] * 30.0
        expected = rate * dt
        spawn = int(expected) + (1 if random.random() < expected - int(expected) else 0)
        for _ in range(spawn):
            self.streams.append([random.randrange(nt), -0.02,
                                 (0.25 + random.random() * 0.5)
                                 * (0.4 + p["speed"] * 1.8),
                                 5 + int(random.random() * 14)])
        if len(self.streams) > 120:
            self.streams = self.streams[-120:]
        rnd = random.random
        alive = []
        for s in self.streams:
            s[1] += s[2] * dt
            ti, y, _, ln = s
            hj = int(y * (ppt - 1))
            if hj - ln > ppt:
                continue
            alive.append(s)
            base = ti * ppt
            for k in range(ln):
                j = hj - k
                if 0 <= j < ppt:
                    idx = (base + j) * 3
                    if k == 0:                       # head: white-green
                        buf[idx], buf[idx + 1], buf[idx + 2] = 180, 255, 180
                    else:
                        f = (1.0 - k / ln) * (0.55 + 0.45 * rnd())
                        g = int(255 * f)
                        if g > buf[idx + 1]:
                            buf[idx] = g // 5
                            buf[idx + 1] = g
                            buf[idx + 2] = g // 6
        self.streams = alive


class Disco(Pattern):
    """Mirrorball: the whole car shimmers with sharp white glints sweeping
    over a slowly-shifting color wash. density = facet size."""
    name = "disco"
    controls = ("speed", "density")

    def render(self, m, p, t, buf):
        cells_x = 6 + int(p["density"] * 18)
        cells_y = 5
        sp = t * (0.5 + p["speed"] * 3.0)
        hue_t = t * 0.03
        sin = math.sin
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            cx = int(perim[i] * cells_x)
            cy = int(along[i] * cells_y)
            h = sin(cx * 12.9898 + cy * 78.233) * 43758.5453
            h -= int(h)                          # per-facet random phase 0..1
            g = sin(sp + h * 6.2832)
            g = g * g * g * g * g * g * g * g    # ^8: sharp glints
            r0, g0, b0 = hsv((hue_t + h * 0.15) % 1.0, 0.8, 0.18)
            j = i * 3
            buf[j] = min(255, r0 + int(255 * g))
            buf[j + 1] = min(255, g0 + int(255 * g))
            buf[j + 2] = min(255, b0 + int(255 * g))


def _ekg(u):
    """One heartbeat: P wave, QRS spike, T wave. u in 0..1 -> -0.25..1."""
    if u < 0.10:
        return 0.15 * math.sin(u / 0.10 * math.pi)
    if u < 0.16:
        return 0.0
    if u < 0.19:
        return -(u - 0.16) / 0.03 * 0.12
    if u < 0.23:
        return -0.12 + (u - 0.19) / 0.04 * 1.12
    if u < 0.27:
        return 1.0 - (u - 0.23) / 0.04 * 1.25
    if u < 0.30:
        return -0.25 + (u - 0.27) / 0.03 * 0.25
    if u < 0.45:
        return 0.0
    if u < 0.60:
        return 0.3 * math.sin((u - 0.45) / 0.15 * math.pi)
    return 0.0


class EKG(Pattern):
    """Hospital-monitor heartbeat trace sweeping around the car; the trace
    surges brighter on every R spike. color1 = trace. speed = heart rate."""
    name = "ekg"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (0, 255, 70), "density": 0.4}

    TRACE = [_ekg(i / 255.0) for i in range(256)]

    def render(self, m, p, t, buf):
        c1 = p["color1"]
        trace = self.TRACE
        head = (t * (0.25 + p["speed"] * 0.9)) % 1.0
        beat = trace[int(head * 255)]
        surge = 1.0 + max(0.0, beat) ** 2 * 0.6  # trace brightens on R spike
        th = 0.03 + p["density"] * 0.05
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            x = perim[i]
            age = (head - x) % 1.0
            j = i * 3
            y = 0.55 - trace[int(x * 255)] * 0.38
            d = along[i] - y
            if -th < d < th and age < 0.85:
                f = (1.0 - abs(d) / th) * (1.0 - age / 0.85) * surge
                buf[j] = min(255, int(c1[0] * f))
                buf[j + 1] = min(255, int(c1[1] * f))
                buf[j + 2] = min(255, int(c1[2] * f))
            else:
                buf[j] = buf[j + 1] = buf[j + 2] = 0


class DVD(Pattern):
    """The bouncing DVD logo. Drifts around the unrolled sheet, bounces off
    the edges, changes color every hit. One day it will nail the corner."""
    name = "dvd"
    controls = ("speed", "density")

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.22 + p["density"] * 0.25          # logo height (along units)
        sw = sh * 0.62 * (2.5 / 9.8)             # width (perim units)
        vx = (0.02 + p["speed"] * 0.06)
        vy = vx * 9.8 / 2.5 * 0.83               # oddball ratio: corner is rare
        spx = 1.0 - sw
        spy = 1.0 - sh
        px_ = (t * vx) % (2 * spx)
        py_ = (t * vy) % (2 * spy)
        x0 = px_ if px_ < spx else 2 * spx - px_
        y0 = py_ if py_ < spy else 2 * spy - py_
        bounces = int(t * vx / spx) + int(t * vy / spy)
        c = hsv((bounces * 0.161) % 1.0, 1.0, 1.0)
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            u = (perim[i] - x0) / sw
            if not 0.0 <= u < 1.0:
                continue
            v = (along[i] - y0) / sh
            if not 0.0 <= v < 1.0:
                continue
            # stylized logo: fat ellipse on top, solid bar below
            hit = False
            if v < 0.62:
                eu = (u - 0.5) / 0.5
                ev = (v - 0.31) / 0.31
                e = eu * eu + ev * ev
                hit = 0.30 < e <= 1.0            # ring with a hole
            elif v > 0.75:
                hit = True                       # the disc bar
            if hit:
                j = i * 3
                buf[j], buf[j + 1], buf[j + 2] = c


class DVDPenis(Pattern):
    """The bouncing DVD logo, except it's a penis. Several of them drift
    around the unrolled sheet on their own trajectories, bounce off the
    edges, change color every hit. density = how many. One day one of them
    will nail the corner."""
    name = "dvd penis"
    controls = ("speed", "density")

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        count = 1 + int(p["density"] * 7.99)
        sh = 0.45 - 0.02 * count                 # height (along units)
        sw = sh * 0.55 * (2.5 / 9.8)             # width (perim units)
        base_v = 0.02 + p["speed"] * 0.06
        spx = 1.0 - sw
        spy = 1.0 - sh
        sprites = []
        for k in range(count):
            vx = base_v * (0.7 + 0.6 * ((k * 0.37) % 1.0))
            vy = vx * 9.8 / 2.5 * 0.83           # oddball ratio: corner is rare
            px_ = (t * vx + k * 0.71) % (2 * spx)
            py_ = (t * vy + k * 1.37) % (2 * spy)
            x0 = px_ if px_ < spx else 2 * spx - px_
            y0 = py_ if py_ < spy else 2 * spy - py_
            bounces = (int((t * vx + k * 0.71) / spx)
                       + int((t * vy + k * 1.37) / spy))
            sprites.append((x0, y0,
                            hsv(((bounces + k * 3) * 0.161) % 1.0, 1.0, 1.0)))
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            x, y = perim[i], along[i]
            j = i * 3
            for x0, y0, c in sprites:
                u = (x - x0) / sw
                if not 0.0 <= u < 1.0:
                    continue
                v = (y - y0) / sh
                if not 0.0 <= v < 1.0:
                    continue
                bx = (u - 0.5) * 0.55            # box coords, aspect-true
                hit = False
                hx, hy = bx / 0.14, (v - 0.13) / 0.13
                if hx * hx + hy * hy <= 1.0:     # head
                    hit = True
                elif -0.095 < bx < 0.095 and 0.13 <= v <= 0.85:
                    hit = True                   # shaft
                else:                            # balls
                    for s_ in (-1.0, 1.0):
                        gx = (bx - s_ * 0.15) / 0.15
                        gy = (v - 0.85) / 0.14
                        if gx * gx + gy * gy <= 1.0:
                            hit = True
                            break
                if hit:
                    buf[j], buf[j + 1], buf[j + 2] = c
                    break


class Police(Pattern):
    """You are being pulled over by the fun police. Red/blue halves spin
    around the car with alternating strobe bursts. speed = panic level."""
    name = "police"
    controls = ("speed",)

    def render(self, m, p, t, buf):
        rot = t * (0.05 + p["speed"] * 0.3)
        s = (t * (1.5 + p["speed"] * 4.0)) % 1.0
        active = 0 if s < 0.5 else 1             # which side is strobing
        blink = ((s * 8.0) % 1.0) < 0.55
        perim = m.perim
        red, blue = (255, 0, 0), (0, 40, 255)
        dim_r, dim_b = (60, 0, 0), (0, 10, 60)
        for i in range(m.total_pixels):
            side = 0 if (perim[i] + rot) % 1.0 < 0.5 else 1
            if side == active and blink:
                c = red if side == 0 else blue
            else:
                c = dim_r if side == 0 else dim_b
            j = i * 3
            buf[j], buf[j + 1], buf[j + 2] = c


class Boobs(Pattern):
    """Pairs of bouncing boobs around the car, jiggling out of phase.
    color1 = skin, color2 = nipple. speed = bounce, density = size."""
    name = "boobs"
    defaults = {"color1": (255, 185, 150), "color2": (215, 95, 70),
                "density": 0.6, "speed": 0.5}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.45 + p["density"] * 0.4           # pair box height
        wp = 2.1 * sh * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.4)
        c1, c2 = p["color1"], p["color2"]
        sin, sqrt = math.sin, math.sqrt
        bf = 2.0 + p["speed"] * 6.0
        total = koff[-1] + counts[-1]
        jig = [(abs(sin(t * bf + k * 1.3)) * 0.16,
                abs(sin(t * bf + k * 1.3 + 0.5)) * 0.16)
               for k in range(total)]
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            v = (along[i] - 0.42) / (sh * 0.5 * scale[s])
            if not -1.4 < v < 1.4:
                continue
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            k += koff[s]
            j = i * 3
            for side in (0, 1):
                bu = -0.48 + side * 0.96
                du = (u - bu) / 0.46
                dv = (v - jig[k][side]) * 0.5 / 0.46
                r2 = du * du + dv * dv
                if r2 <= 1.0:
                    nd = sqrt(du * du + (dv - 0.25) ** 2)
                    if nd < 0.13:                # nipple
                        f = 1.25 if nd < 0.05 else 1.0
                        buf[j] = min(255, int(c2[0] * f))
                        buf[j + 1] = min(255, int(c2[1] * f))
                        buf[j + 2] = min(255, int(c2[2] * f))
                    else:                        # skin, shaded round
                        f = 1.0 - r2 * 0.45
                        buf[j] = int(c1[0] * f)
                        buf[j + 1] = int(c1[1] * f)
                        buf[j + 2] = int(c1[2] * f)
                    break


class Sperm(Pattern):
    """The great race: glowing swimmers wriggle around the car, tails
    whipping. color1 = swimmer. speed = swim rate, density = how many."""
    name = "sperm"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (200, 220, 255)}

    def __init__(self):
        self.swim = None        # [x0, cy_seed, phase] per swimmer

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        nt = len(m.tubes)
        ppt = m.px_per_tube
        n = 3 + int(p["density"] * 12)
        if self.swim is None or len(self.swim) != n:
            self.swim = [[random.random(), random.random() * 6.28,
                          random.random() * 6.28] for _ in range(n)]
        c1 = p["color1"]
        sin = math.sin
        v = 0.03 + p["speed"] * 0.12
        wig = 6.0 + p["speed"] * 10.0
        tail_len = 22
        step = 0.9 / nt                          # one tube-column per sample
        for x0, cys, phs in self.swim:
            hx = (x0 + t * v) % 1.0
            cy = 0.5 + 0.32 * sin(t * 0.23 + cys)
            for s in range(tail_len):
                xs = hx - s * step
                amp = 0.02 + 0.10 * (s / tail_len)
                ys = cy + amp * sin(s * 0.85 - t * wig + phs)
                if not 0.0 <= ys <= 1.0:
                    continue
                ti = int((xs % 1.0) * nt) % nt
                jj = int(ys * (ppt - 1))
                f = 1.0 if s == 0 else (1.0 - s / tail_len) * 0.8
                idx = (ti * ppt + jj) * 3
                r = int(c1[0] * f)
                g = int(c1[1] * f)
                b = int(c1[2] * f)
                if r > buf[idx]:
                    buf[idx] = r
                if g > buf[idx + 1]:
                    buf[idx + 1] = g
                if b > buf[idx + 2]:
                    buf[idx + 2] = b
                if s == 0:                       # fat bright head
                    for dj in (-1, 1):
                        j2 = jj + dj
                        if 0 <= j2 < ppt:
                            idx2 = (ti * ppt + j2) * 3
                            buf[idx2] = max(buf[idx2], int(c1[0] * 0.7))
                            buf[idx2 + 1] = max(buf[idx2 + 1], int(c1[1] * 0.7))
                            buf[idx2 + 2] = max(buf[idx2 + 2], int(c1[2] * 0.7))


class Penis(Pattern):
    """Slowly rises to the occasion, holds the moment, celebrates with a
    little fountain, then recovers. Each one around the car is on its own
    schedule. color1 = shaft, color2 = head. speed = how fast the mood
    builds, density = size."""
    name = "penis"
    defaults = {"color1": (255, 185, 150), "color2": (235, 115, 115),
                "density": 0.6, "speed": 0.4}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.55 + p["density"] * 0.4           # full height (along units)
        wp = sh * 0.55 * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.6)
        c1, c2 = p["color1"], p["color2"]
        sin = math.sin
        rate = 0.25 + p["speed"] * 1.2
        exc = [0.5 + 0.5 * sin(t * rate + k * 2.1)
               for k in range(koff[-1] + counts[-1])]
        base_y = 0.90
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            k += koff[s]
            shs = sh * scale[s]
            by = (along[i] - (base_y - shs)) / shs   # 0 = full-mast tip, 1 = base
            if not -0.05 < by < 1.15:
                continue
            bx = u * 0.275                       # box coords, aspect-true
            e = exc[k]
            vt = 1.0 - (0.28 + 0.72 * e)         # current tip height
            j = i * 3
            # celebration fountain at peak excitement
            if e > 0.92 and by < vt:
                hit = False
                for nd in range(3):
                    dy = vt - 0.10 - ((t * 0.9 + nd * 0.33) % 0.5)
                    dx = 0.05 * sin(t * 3.0 + nd * 2.0)
                    if (bx - dx) ** 2 + (by - dy) ** 2 < 0.0042:
                        hit = True
                        break
                if hit:
                    buf[j] = buf[j + 1] = buf[j + 2] = 255
                continue
            # head
            hx, hy = bx / 0.14, (by - (vt + 0.10)) / 0.12
            if hx * hx + hy * hy <= 1.0:
                f = 1.0 - 0.35 * hx * hx
                c = _mix(c2, (255, 255, 255), 0.6) if e > 0.92 else c2
                buf[j] = int(c[0] * f)
                buf[j + 1] = int(c[1] * f)
                buf[j + 2] = int(c[2] * f)
                continue
            # shaft
            if -0.095 < bx < 0.095 and vt + 0.10 <= by <= 1.0:
                f = 1.0 - 0.45 * (bx / 0.095) ** 2
                buf[j] = int(c1[0] * f)
                buf[j + 1] = int(c1[1] * f)
                buf[j + 2] = int(c1[2] * f)
                continue
            # balls
            for s in (-1.0, 1.0):
                gx, gy = (bx - s * 0.15) / 0.15, (by - 0.98) / 0.13
                r2 = gx * gx + gy * gy
                if r2 <= 1.0:
                    f = 0.9 - 0.35 * r2
                    buf[j] = int(c1[0] * f)
                    buf[j + 1] = int(c1[1] * f)
                    buf[j + 2] = int(c1[2] * f)
                    break


class Twerk(Pattern):
    """Butts twerking around the car: cheeks clap in rapid alternation.
    color1 = skin. speed = twerk intensity, density = size."""
    name = "twerk"
    controls = ("speed", "density", "color1")
    defaults = {"color1": (255, 185, 150), "density": 0.6, "speed": 0.6}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.45 + p["density"] * 0.4
        wp = 1.6 * sh * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.4)
        c1 = p["color1"]
        sin = math.sin
        tw = 5.0 + p["speed"] * 12.0
        bounce = []
        for k in range(koff[-1] + counts[-1]):
            b0 = sin(t * tw + k * 1.9)
            bounce.append((0.15 * max(0.0, b0), 0.15 * max(0.0, -b0)))
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            k += koff[s]
            v = (along[i] - 0.45) / (sh * 0.5 * scale[s])
            if not -1.5 < v < 1.5:
                continue
            bx = u * 0.8                         # box coords, aspect-true
            bv = v * 0.5
            j = i * 3
            for side in (0, 1):
                cx = -0.30 + side * 0.60
                dy = bv - bounce[k][side]
                gx, gy = (bx - cx) / 0.40, dy / 0.44
                r2 = gx * gx + gy * gy
                if r2 <= 1.0:
                    if abs(bx) < 0.04:           # the crack
                        f = 0.15
                    else:
                        f = 1.0 - 0.40 * r2
                    buf[j] = int(c1[0] * f)
                    buf[j + 1] = int(c1[1] * f)
                    buf[j + 2] = int(c1[2] * f)
                    break


class Poop(Pattern):
    """Proud swirly piles with orbiting flies and rising stink lines.
    speed = fly frenzy, density = pile size."""
    name = "poop"
    controls = ("speed", "density")

    TUBE_M = 2.5
    PERIM_M = 9.8

    # (cx, cy, rx, ry) stacked swirl blobs, box coords
    PILE = [(0.0, 0.80, 0.34, 0.15), (0.0, 0.60, 0.24, 0.13),
            (0.02, 0.44, 0.15, 0.11), (0.08, 0.33, 0.07, 0.06)]

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sh = 0.5 + p["density"] * 0.4
        wp = 0.9 * sh * (self.TUBE_M / self.PERIM_M)
        sx, sid, counts, koff, widths, scale = _side_slots(m, wp, 1.5)
        sin = math.sin
        fz = 4.0 + p["speed"] * 8.0
        brown = (150, 90, 35)
        along = m.along
        for i in range(m.total_pixels):
            s = sid[i]
            k = int(sx[i] * counts[s])
            u = (sx[i] - (k + 0.5) / counts[s]) / (widths[s] * 0.5)
            if not -1.0 < u < 1.0:
                continue
            k += koff[s]
            shs = sh * scale[s]
            by = (along[i] - (0.45 - shs * 0.45)) / shs
            if not -0.1 < by < 1.1:
                continue
            bx = u * 0.45
            j = i * 3
            # flies buzzing erratically around the pile
            hit = False
            for n in range(3):
                fx = 0.32 * sin(t * fz + n * 2.1 + k) * sin(t * 1.3 + n)
                fy = 0.45 + 0.28 * sin(t * fz * 1.37 + n * 4.0 + k * 2)
                if (bx - fx) ** 2 + (by - fy) ** 2 < 0.0012:
                    buf[j], buf[j + 1], buf[j + 2] = 230, 230, 170
                    hit = True
                    break
            if hit:
                continue
            # the pile
            for cx, cy, rx, ry in self.PILE:
                gx, gy = (bx - cx) / rx, (by - cy) / ry
                r2 = gx * gx + gy * gy
                if r2 <= 1.0:
                    f = 1.0 - 0.45 * r2
                    buf[j] = int(brown[0] * f)
                    buf[j + 1] = int(brown[1] * f)
                    buf[j + 2] = int(brown[2] * f)
                    hit = True
                    break
            if hit:
                continue
            # stink lines wafting up
            if by < 0.34:
                fade = max(0.0, by / 0.34) * 0.8
                for ln in (-0.16, 0.0, 0.16):
                    wx = ln + 0.05 * sin(by * 14.0 - t * 2.5 + ln * 20.0)
                    if abs(bx - wx) < 0.022:
                        buf[j] = int(70 * fade)
                        buf[j + 1] = int(190 * fade)
                        buf[j + 2] = int(40 * fade)
                        break


class UFO(Pattern):
    """A flying saucer cruises the car, tractor-beaming a hapless little
    blob up from the ground. Over and over. It never learns.
    speed = cruise rate, density = beam width."""
    name = "ufo"
    controls = ("speed", "density")

    PERIM_OVER_TUBE = 9.8 / 2.5

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        sx = (t * (0.02 + p["speed"] * 0.1)) % 1.0
        sy = 0.16
        rx = 0.30 / self.PERIM_OVER_TUBE         # saucer half-width (perim)
        bw = (0.10 + p["density"] * 0.20) / self.PERIM_OVER_TUBE
        ay = 0.88 - 0.72 * ((t * 0.12) % 1.0)    # abductee rising
        sin = math.sin
        wob = 0.02 * sin(t * 6.0) / self.PERIM_OVER_TUBE
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            px, py = perim[i], along[i]
            dx = px - sx
            if dx > 0.5:
                dx -= 1.0
            elif dx < -0.5:
                dx += 1.0
            j = i * 3
            # dome
            gx, gy = dx / (rx * 0.45), (py - (sy - 0.055)) / 0.06
            if gx * gx + gy * gy <= 1.0 and py <= sy:
                buf[j], buf[j + 1], buf[j + 2] = 120, 230, 255
                continue
            # hull with blinking rim lights
            gx, gy = dx / rx, (py - sy) / 0.045
            if gx * gx + gy * gy <= 1.0:
                if gx * gx > 0.55 and sin(t * 9.0 + (1 if gx > 0 else 4)) > 0.2:
                    buf[j], buf[j + 1], buf[j + 2] = 255, 80, 200
                else:
                    buf[j] = buf[j + 1] = buf[j + 2] = 165
                continue
            # abductee: little pink blob flailing in the beam
            adx = (dx - wob) / (0.05 / self.PERIM_OVER_TUBE)
            ady = (py - ay) / 0.05
            if adx * adx + ady * ady <= 1.0:
                buf[j], buf[j + 1], buf[j + 2] = 255, 140, 180
                continue
            # tractor beam cone
            if py > sy:
                spread = bw * (py - sy) / (1.0 - sy) + 0.008
                if -spread < dx < spread:
                    f = (0.30 - 0.18 * (py - sy)) \
                        * (0.7 + 0.3 * sin(t * 10.0 + py * 18.0))
                    buf[j] = int(90 * f)
                    buf[j + 1] = int(255 * f)
                    buf[j + 2] = int(120 * f)


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
    for svg in sorted(vdir.glob("*.svg")):
        try:
            out.append(Sprite(svg.stem, load_sprite(svg)))
        except Exception as e:
            print(f"sprite load failed for {svg.name}: {e}")
    return out


_BASE = [
    Rainbow(), Aurora(), Fire(), Plasma(), RainbowSnake(), Meteors(),
    Storm(), Stripes(), Cubes(), Breathe(), RainbowBreathe(), Wave(), Comet(),
    Rain(), Sparkle(), Confetti(), BroomStroke(), PacMan(), Fireworks(),
    Matrix(), Disco(), EKG(), DVD(), DVDPenis(), Police(), Butthole(), Boobs(), Penis(),
    Twerk(), Poop(), UFO(), GooglyEyes(), Sperm(), Lava(), Hypno(), Solid(),
    EmojiSprite(),
]

REGISTRY = {pat.name: pat for pat in
            _BASE + _load_sprite_patterns() + [Mapping(), Off()]}

NAMES = list(REGISTRY.keys())
