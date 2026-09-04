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


def _cov(x, w):
    """Edge coverage: 0 below the edge, 1 past it, a linear ramp of width w
    between. The cheap anti-aliasing primitive: a shape edge at x=0 rendered
    as _cov(x, ~1 pixel) glides between pixels instead of popping."""
    if x <= 0.0:
        return 0.0
    return 1.0 if x >= w else x / w


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


def _surface_grid(m):
    """Map the physically unrolled LED surface to a dense x/y grid.

    The frame buffer follows electrical order, which is not always spatial
    order. Cellular patterns use this lookup so their neighbors cross group
    and side boundaries in the same order that the tubes meet on the car.
    Returns (width, height, canonical_pixel_for_grid_cell).
    """
    cached = getattr(m, "_surface_grid_cache", None)
    if cached is None:
        offsets = m.side_offsets()
        width, height = len(m.tubes), m.px_per_tube
        pixel_of = [0] * (width * height)
        for ti, tube in enumerate(m.tubes):
            x = offsets[tube["side"]] + tube["pos"]
            for y in range(height):
                pixel_of[x * height + y] = ti * height + y
        cached = (width, height, pixel_of)
        m._surface_grid_cache = cached
    return cached


def _surface_to_buffer(surface, pixel_of, buf):
    """Copy an x-major RGB surface grid into canonical electrical order."""
    for grid_i, pixel_i in enumerate(pixel_of):
        src, dst = grid_i * 3, pixel_i * 3
        buf[dst] = surface[src]
        buf[dst + 1] = surface[src + 1]
        buf[dst + 2] = surface[src + 2]


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
            step = 1.0 / (ppt - 1)
            for j in range(ppt):
                dd = pos - j / (ppt - 1)
                if -step <= dd < tail:
                    # leading edge ramps in over one pixel, so the head
                    # glides down the tube instead of popping pixel to pixel
                    v = (1.0 - dd / tail) if dd >= 0.0 else (1.0 + dd / step)
                    r, g, b = hsv(hue, 0.55, v)
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
                    # bilinear sample of the alpha mask: edges glide as the
                    # sprite sweeps instead of crawling texel by texel
                    fx = u * W - 0.5
                    fy = v * H - 0.5
                    x0 = int(fx) if fx > 0.0 else 0
                    y0 = int(fy) if fy > 0.0 else 0
                    if x0 > W - 2:
                        x0 = W - 2
                    if y0 > H - 2:
                        y0 = H - 2
                    tx = fx - x0
                    ty = fy - y0
                    if tx < 0.0:
                        tx = 0.0
                    elif tx > 1.0:
                        tx = 1.0
                    if ty < 0.0:
                        ty = 0.0
                    elif ty > 1.0:
                        ty = 1.0
                    q = y0 * W + x0
                    a00, a10 = alpha[q], alpha[q + 1]
                    a01, a11 = alpha[q + W], alpha[q + W + 1]
                    a = (a00 * (1 - tx) * (1 - ty) + a10 * tx * (1 - ty)
                         + a01 * (1 - tx) * ty + a11 * tx * ty)
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


class Horses(Pattern):
    """A herd of horses galloping around the car.

    Four rasterized keyframes of a rotary gallop (gather -> hind stance ->
    extension -> front stance) cycle per horse, with a body bob synced to the
    stride, so the herd reads as running rather than sliding. Keyframes are
    generated by vectors/horses/make_frames.py; frames share one viewBox so
    the masks align. Horses face the direction sprites travel (toward
    increasing perim), each with its own stride phase and lane so the herd
    doesn't move in lockstep.
    """
    name = "horses"
    defaults = {"color1": (255, 150, 40), "color2": (255, 244, 200)}

    TUBE_M = 2.5
    PERIM_M = 9.8

    def __init__(self):
        vdir = Path(__file__).resolve().parents[2] / "vectors" / "horses"
        self.frames = []
        try:
            self.frames = [load_sprite(vdir / f"frame{i}.svg")
                           for i in range(4)]
        except Exception as e:
            print(f"horses keyframes failed to load: {e}")

    def render(self, m, p, t, buf):
        if not self.frames:
            buf[:] = bytes(len(buf))
            return
        n = m.total_pixels
        W, H = self.frames[0]["w"], self.frames[0]["h"]
        aspect = self.frames[0]["aspect"]
        c1, c2 = p["color1"], p["color2"]
        # Horse height in `along` units; width squished to keep aspect on the
        # unrolled sheet (perimeter metres >> tube metres), same as Sprite.
        sh = 0.32 + p["density"] * 0.4
        wp = sh * aspect * (self.TUBE_M / self.PERIM_M)
        count = max(1, min(6, int(1.0 / (wp * 1.6))))
        slot = 1.0 / count
        cx = (t * p["speed"] * 0.25) % 1.0
        # Stride cadence scales with ground speed so legs never moonwalk.
        strides = 0.8 + p["speed"] * 2.2
        cos = math.cos
        masks = []
        tops = []
        for k in range(count):
            phase = (t * strides + k * 0.37) % 1.0
            masks.append(self.frames[int(phase * 4.0) % 4]["alpha"])
            # Airborne on the gather (0) and extension (0.5) beats, planted on
            # the stance beats between -- two bobs per stride.
            lane = ((k * 0.618) % 1.0 - 0.5) * 0.08
            bob = -0.03 * cos(4.0 * math.pi * phase)
            tops.append(0.5 + lane + bob - sh / 2.0)
        perim, along = m.perim, m.along
        for i in range(n):
            x = (perim[i] - cx) % 1.0
            k = int(x * count)
            u = (x - k * slot) / wp
            j = i * 3
            a = 0.0
            if 0.0 <= u < 1.0:
                v = (along[i] - tops[k]) / sh
                if 0.0 <= v < 1.0:
                    # bilinear mask sample so edges glide (house rule:
                    # coverage, not booleans)
                    alpha = masks[k]
                    fx = u * W - 0.5
                    fy = v * H - 0.5
                    x0 = int(fx) if fx > 0.0 else 0
                    y0 = int(fy) if fy > 0.0 else 0
                    if x0 > W - 2:
                        x0 = W - 2
                    if y0 > H - 2:
                        y0 = H - 2
                    tx = fx - x0
                    ty = fy - y0
                    if tx < 0.0:
                        tx = 0.0
                    elif tx > 1.0:
                        tx = 1.0
                    if ty < 0.0:
                        ty = 0.0
                    elif ty > 1.0:
                        ty = 1.0
                    q = y0 * W + x0
                    a00, a10 = alpha[q], alpha[q + 1]
                    a01, a11 = alpha[q + W], alpha[q + W + 1]
                    a = (a00 * (1 - tx) * (1 - ty) + a10 * tx * (1 - ty)
                         + a01 * (1 - tx) * ty + a11 * tx * ty)
            if a > 0.0:
                r = (c1[0] * (1 - v) + c2[0] * v) * a
                g = (c1[1] * (1 - v) + c2[1] * v) * a
                b = (c1[2] * (1 - v) + c2[2] * v) * a
                buf[j] = int(r)
                buf[j + 1] = int(g)
                buf[j + 2] = int(b)
            else:
                buf[j] = buf[j + 1] = buf[j + 2] = 0


# 5x7 marquee font, row 0 = tube top. Only the glyphs the message needs.
_MARQUEE_FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".###.", "#...#", "#....", "#....", "#....", "#...#", ".###."),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("###", ".#.", ".#.", ".#.", ".#.", ".#.", "###"),
    "N": ("#...#", "##..#", "#.#.#", "#.#.#", "#..##", "#...#", "#...#"),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "♥": (".##.##.", "#######", "#######", ".#####.", "..###..", "...#...",
          "......."),
    " ": ("...", "...", "...", "...", "...", "...", "..."),
}


class Bianca(Pattern):
    """HAPPY BIRTHDAY BIANCA marquee scrolling around the car.

    The message is rendered from a 5x7 bitmap font onto the unrolled sheet
    (x = perim, y = along) with square cells on the physical car, and marches
    around the perimeter like a stock ticker. The strip is ~2.5 perimeters
    long, so one pass shows the whole message with a gap before it repeats.
    Letters tint color1 (top) -> color2 (bottom); bilinear sampling of the
    font bitmap so edges glide between tubes instead of popping (house rule:
    coverage, not booleans). speed = scroll rate, density = letter height.
    """
    name = "bianca"
    defaults = {"color1": (255, 60, 170), "color2": (255, 210, 60)}

    MESSAGE = "HAPPY BIRTHDAY BIANCA ♥   "
    TUBE_M = 2.5
    PERIM_M = 9.8

    def __init__(self):
        # Flatten the message into one 7-row column strip, one blank column
        # between glyphs. alpha[row * W + col] in 0.0/1.0.
        cols = []
        for ch in self.MESSAGE:
            glyph = _MARQUEE_FONT[ch]
            for x in range(len(glyph[0])):
                cols.append(tuple(1.0 if row[x] == "#" else 0.0
                                  for row in glyph))
            cols.append((0.0,) * 7)
        self.W = len(cols)
        self.alpha = [cols[x][y] for y in range(7) for x in range(self.W)]

    def render(self, m, p, t, buf):
        buf[:] = bytes(len(buf))
        W, alpha = self.W, self.alpha
        c1, c2 = p["color1"], p["color2"]
        sh = 0.35 + p["density"] * 0.45          # text height (along units)
        top = 0.5 - sh / 2.0
        # Square cells on the car: a font cell spans sh/7 of a tube, so the
        # same span of the (much longer) perimeter per column.
        cw = (sh / 7.0) * (self.TUBE_M / self.PERIM_M)
        scroll = t * (0.5 + p["speed"] * 4.0)    # columns per second
        perim, along = m.perim, m.along
        for i in range(m.total_pixels):
            v = (along[i] - top) / sh
            if not 0.0 <= v < 1.0:
                continue
            fy = v * 7.0 - 0.5
            y0 = int(fy) if fy > 0.0 else 0
            if y0 > 5:
                y0 = 5
            ty = fy - y0
            if ty < 0.0:
                ty = 0.0
            elif ty > 1.0:
                ty = 1.0
            fx = (perim[i] / cw + scroll) % W
            x0 = int(fx)
            tx = fx - x0
            x1 = x0 + 1 if x0 + 1 < W else 0     # strip wraps around
            q0, q1 = y0 * W, (y0 + 1) * W
            a = (alpha[q0 + x0] * (1 - tx) * (1 - ty)
                 + alpha[q0 + x1] * tx * (1 - ty)
                 + alpha[q1 + x0] * (1 - tx) * ty
                 + alpha[q1 + x1] * tx * ty)
            if a > 0.0:
                j = i * 3
                buf[j] = int((c1[0] * (1 - v) + c2[0] * v) * a)
                buf[j + 1] = int((c1[1] * (1 - v) + c2[1] * v) * a)
                buf[j + 2] = int((c1[2] * (1 - v) + c2[2] * v) * a)


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
            # --- ghost (feathered rim so it glides between pixels) ---
            dyg = py - gy
            if -ry < dyg < ry:
                dxg = px - gx
                if -rx < dxg < rx:
                    nx, ny = dxg / rx, dyg / ry
                    a = _cov(1.0 - (nx * nx + ny * ny), 0.35)
                    if a > 0.0:
                        r = int(ghost[0] * a)
                        gc = int(ghost[1] * a)
                        b = int(ghost[2] * a)
            # --- Pac-Man (drawn last so he rides on top) ---
            dy = py - hy
            if -ry < dy < ry:
                dx = px - hx
                if -rx < dx < rx:
                    nx, ny = dx / rx, dy / ry
                    a = _cov(1.0 - (nx * nx + ny * ny), 0.35)
                    if a > 0.0:
                        if -m_ang < atan2(ny, nx * hdir) < m_ang:
                            r = gc = b = 0               # open mouth
                        else:
                            r = int(pac[0] * a)
                            gc = int(pac[1] * a)
                            b = int(pac[2] * a)
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
                    jf = yy * (ppt - 1)
                    j = int(jf)
                    f = 1.0 - k * step / self.TAIL
                    idx = (ti * ppt + j) * 3
                    if k == 0:                     # white-hot head, sub-pixel:
                        fr = jf - j                # split so it glides
                        for jj, w in ((j, 1.0 - fr), (j + 1, fr)):
                            if 0 <= jj < ppt:
                                v = int(255 * w)
                                idx2 = (ti * ppt + jj) * 3
                                if v > buf[idx2]:
                                    buf[idx2] = v
                                    buf[idx2 + 1] = v
                                    buf[idx2 + 2] = v
                        yy -= step
                        k += 1
                        continue
                    if k < 2:                      # second head pixel
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
        c1, c2 = p["color1"], p["color2"]
        bc1, bc2 = bytes(c1), bytes(c2)
        perim, along = m.perim, m.along
        cos, tau = math.cos, 2 * math.pi
        # soft square wave: the stripe boundaries blend over ~a pixel so the
        # spin glides instead of crawling in hard steps
        for i in range(m.total_pixels):
            v = perim[i] * k + along[i] * 0.9 - off
            f = 0.5 - 4.0 * cos(tau * v)
            j = i * 3
            if f <= 0.0:
                buf[j:j + 3] = bc1
            elif f >= 1.0:
                buf[j:j + 3] = bc2
            else:
                buf[j] = int(c1[0] + (c2[0] - c1[0]) * f)
                buf[j + 1] = int(c1[1] + (c2[1] - c1[1]) * f)
                buf[j + 2] = int(c1[2] + (c2[2] - c1[2]) * f)


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
            f = (0.45 + 0.55 * wr) * (1.0 - g * g * 0.6) \
                * _cov(1.0 - r, 0.06)            # feathered outer edge
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
            er2 = u * u + vv * vv
            if er2 > 1.0:
                continue
            rim = _cov(1.0 - er2, 0.25)          # feathered eyeball edge
            j = i * 3
            du, dv = u - lx, v - ly
            d = sqrt(du * du + dv * dv)
            if d < 0.18:                         # pupil
                buf[j] = buf[j + 1] = buf[j + 2] = 8
            elif d < 0.40:                       # iris
                f = (1.0 - (d - 0.18) / 0.22 * 0.5) * rim
                buf[j] = int(c1[0] * f)
                buf[j + 1] = int(c1[1] * f)
                buf[j + 2] = int(c1[2] * f)
            else:                                # sclera
                buf[j] = buf[j + 1] = buf[j + 2] = int(235 * rim)


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
                # outside glow rises continuously to the full rim color at
                # the surface (f=1), so blobs have no hard pop edge
                g = f * f
                g *= g                           # f^4: tight, bright halo
                buf[j] = int(c2[0] * g)
                buf[j + 1] = int(c2[1] * g)
                buf[j + 2] = int(c2[2] * g)


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
            s = ang + r * turns - spin * (1 if k % 2 == 0 else -1)
            # soft band boundaries + a feathered outer rim: the spiral spins
            # smoothly instead of crawling
            f = 0.5 - 4.0 * math.cos(two_pi * s)
            rim = _cov(1.0 - r, 0.08)
            j = i * 3
            if f <= 0.0:
                cr, cg, cb = c1
            elif f >= 1.0:
                cr, cg, cb = c2
            else:
                cr = c1[0] + (c2[0] - c1[0]) * f
                cg = c1[1] + (c2[1] - c1[1]) * f
                cb = c1[2] + (c2[2] - c1[2]) * f
            buf[j] = int(cr * rim)
            buf[j + 1] = int(cg * rim)
            buf[j + 2] = int(cb * rim)


class Scrub(Pattern):
    """The car behaves like one enormous brush scrubbing front-to-back and
    back again. A broad compression front sweeps both long sides, wraps the
    rear, flexes down the bristles, and leaves luminous motion echoes."""
    name = "scrub"
    defaults = {"color1": (20, 220, 255), "color2": (255, 30, 150),
                "speed": 0.48, "density": 0.55}

    @staticmethod
    def _longitudinal(m):
        cached = getattr(m, "_longitudinal_cache", None)
        if cached is None:
            counts = m.sides_count()
            values = [0.0] * m.total_pixels
            for i, ti in enumerate(m.tube_of):
                tube = m.tubes[ti]
                if tube["side"] == "L":
                    x = 0.78 * tube["pos"] / max(1, counts["L"] - 1)
                elif tube["side"] == "R":
                    x = 0.78 * (1.0 - tube["pos"] / max(1, counts["R"] - 1))
                else:
                    across = tube["pos"] / max(1, counts["B"] - 1)
                    # Both side strokes enter at the rear corners, converge
                    # toward its center, and reverse there.
                    x = 0.78 + 0.22 * (1.0 - abs(across * 2.0 - 1.0))
                values[i] = x
            cached = values
            m._longitudinal_cache = cached
        return cached

    def render(self, m, p, t, buf):
        longitudinal = self._longitudinal(m)
        tau = 2.0 * math.pi
        phase = t * (0.055 + p["speed"] * 0.20) * tau
        direction = math.sin(phase)
        width = 0.10 + p["density"] * 0.14
        centers = [0.5 - 0.5 * math.cos(phase - echo * 0.19)
                   for echo in range(3)]
        c1, c2 = p["color1"], p["color2"]
        along = m.along
        sin = math.sin
        for i in range(m.total_pixels):
            x, y = longitudinal[i], along[i]
            energy = 0.0
            signed = 0.0
            for echo, center in enumerate(centers):
                rel = (x - center) / width
                if -1.0 < rel < 1.0:
                    envelope = (1.0 - abs(rel)) ** 2 / (1.0 + echo * 1.25)
                    energy += envelope
                    if echo == 0:
                        signed = rel
            energy = min(1.0, energy)
            # The diagonal phase shift changes sign at each turnaround, which
            # makes light appear to flex along the hanging bristles.
            bristle = 0.5 + 0.5 * sin(
                tau * (y * (1.15 + p["density"] * 0.9)
                       - signed * direction * 0.24) - phase * 0.48)
            bristle = 0.30 + bristle * 0.70
            lead = max(0.0, 1.0 - abs(signed - direction * 0.54) / 0.16)
            lead = lead * lead * energy
            level = energy * bristle
            blend = 0.5 + 0.5 * sin(tau * (y * 0.72 + x * 0.38) - phase * 0.14)
            color = _mix(c1, c2, blend)
            hot = lead * abs(direction) * (0.45 + bristle * 0.55)
            j = i * 3
            buf[j] = min(255, int(color[0] * level + 255 * hot))
            buf[j + 1] = min(255, int(color[1] * level + 255 * hot))
            buf[j + 2] = min(255, int(color[2] * level + 255 * hot))


class Ribbons(Pattern):
    """Intertwined neon ribbons flow continuously around all three sides.
    They brighten from color1 to color2 and burn white wherever several
    strands braid across one another."""
    name = "ribbons"
    defaults = {"color1": (0, 255, 210), "color2": (255, 20, 190),
                "speed": 0.42, "density": 0.52}

    def render(self, m, p, t, buf):
        count = 3 + int(p["density"] * 6.0)
        width = 0.020 + p["density"] * 0.018
        motion = t * (0.045 + p["speed"] * 0.23)
        c1, c2 = p["color1"], p["color2"]
        tau = 2.0 * math.pi
        sin = math.sin
        perim, along = m.perim, m.along
        ppt = m.px_per_tube
        reach = width * 3.5
        colors = [_mix(c1, c2, k / max(1, count - 1)) for k in range(count)]
        # Every pixel of a tube shares one perim value, so each ribbon's
        # center is a per-COLUMN quantity: hoisting the two sines out of the
        # pixel loop cuts the render cost by ~the tube length.
        for ti in range(len(m.tubes)):
            base = ti * ppt
            x = perim[base]
            centers = []
            for k in range(count):
                freq = 1 + (k % 3)
                phase = k * 1.618
                center = (0.5
                          + 0.31 * sin(tau * (x * freq
                                             + motion * (0.65 + k * 0.07))
                                       + phase)
                          + 0.075 * sin(tau * (x * (freq + 2)
                                              - motion * 0.47) - phase * 0.63))
                centers.append((center, colors[k]))
            for pj in range(ppt):
                i = base + pj
                y = along[i]
                red = green = blue = 0
                total = 0.0
                for center, color in centers:
                    d = y - center
                    if d < 0.0:
                        d = -d
                    if d >= reach:
                        continue
                    bloom = 1.0 - d / reach
                    bloom = bloom * bloom * bloom * 0.22
                    if d < width:
                        core = 1.0 - d / width
                        core *= core
                    else:
                        core = 0.0
                    strength = bloom + core * 0.82
                    total += strength
                    red += int(color[0] * strength)
                    green += int(color[1] * strength)
                    blue += int(color[2] * strength)
                crossing = max(0.0, total - 0.92)
                crossing = min(1.0, crossing * crossing * 0.72)
                j = i * 3
                buf[j] = min(255, red + int(255 * crossing))
                buf[j + 1] = min(255, green + int(255 * crossing))
                buf[j + 2] = min(255, blue + int(255 * crossing))


class Voronoi(Pattern):
    """Living stained glass: drifting color seeds divide the entire car into
    soft polygonal cells. Their shared walls flare as cells squeeze, split,
    and exchange neighbors."""
    name = "voronoi"
    controls = ("speed", "density")
    defaults = {"speed": 0.34, "density": 0.5}

    PERIM_OVER_TUBE = 9.8 / 2.5

    def render(self, m, p, t, buf):
        count = 14 + int(p["density"] * 21.0)
        motion = t * (0.035 + p["speed"] * 0.18)
        sites = []
        sin = math.sin
        aspect = self.PERIM_OVER_TUBE
        for k in range(count):
            base_x = (k * 0.61803398875 + 0.07) % 1.0
            base_y = 0.07 + 0.86 * ((k * 0.38196601125 + 0.23) % 1.0)
            x = (base_x + 0.065 * sin(motion * (0.73 + k % 4 * 0.08)
                                     + k * 2.17)) % 1.0
            y = base_y + 0.095 * sin(-motion * (0.61 + k % 5 * 0.06)
                                     + k * 1.31)
            y = max(0.015, min(0.985, y))
            hue = (k * 0.61803398875 + t * 0.012) % 1.0
            pulse = 0.5 + 0.5 * sin(motion * 0.7 + k * 2.4)
            sites.append((x, y, hue, pulse))

        boundary_w = 0.010 + p["density"] * 0.012
        perim, along = m.perim, m.along
        ppt = m.px_per_tube
        # perim is per-column, so the wrapped + aspect-scaled dx^2 to every
        # site is too — hoist it out of the pixel loop.
        for ti in range(len(m.tubes)):
            base = ti * ppt
            px = perim[base]
            col = []
            for x, y, hue, pulse in sites:
                dx = px - x
                if dx < 0.0:
                    dx = -dx
                if dx > 0.5:
                    dx = 1.0 - dx
                dx *= aspect
                col.append((dx * dx, y, hue, pulse))
            for pj in range(ppt):
                i = base + pj
                py = along[i]
                best = second = 999.0
                bhue = bpulse = 0.0
                for dx2, y, hue, pulse in col:
                    if dx2 >= second:
                        continue
                    dy = py - y
                    d2 = dx2 + dy * dy
                    if d2 < best:
                        second, best = best, d2
                        bhue, bpulse = hue, pulse
                    elif d2 < second:
                        second = d2
                gap = second - best
                edge = max(0.0, 1.0 - gap / boundary_w)
                edge = edge * edge * edge
                value = min(1.0, 0.14 + bpulse * 0.17 + edge * 0.88)
                saturation = 0.88 - edge * 0.48
                r, g, b = hsv(bhue, saturation, value)
                j = i * 3
                buf[j], buf[j + 1], buf[j + 2] = r, g, b


class Life(Pattern):
    """Conway's Game of Life wraps around the complete unrolled car.
    New cells flare white, survivors age from color1 to color2, and extinct
    cells leave phosphorescent trails. Occasional seeds keep the ecosystem
    from settling into a museum of still lifes."""
    name = "life"
    defaults = {"color1": (80, 255, 40), "color2": (150, 0, 255),
                "speed": 0.5, "density": 0.45}

    SEED_SHAPES = (
        ((0, 1), (1, 0), (1, 1), (1, 2), (2, 0)),       # R-pentomino
        ((0, 1), (1, 2), (2, 0), (2, 1), (2, 2)),       # glider
        ((0, 0), (0, 1), (0, 2), (1, 0), (2, 1)),
    )

    def __init__(self):
        self.cells = None
        self.next_cells = None
        self.age = None
        self.trail = None
        self.neighbors = None
        self.pixel_of = None
        self.width = self.height = 0
        self.last_t = None
        self.accumulator = 0.0
        self.generation = 0

    def _init(self, m, p):
        w, h, pixel_of = _surface_grid(m)
        self.width, self.height, self.pixel_of = w, h, pixel_of
        n = w * h
        chance = 0.16 + p["density"] * 0.13
        self.cells = bytearray(1 if random.random() < chance else 0
                               for _ in range(n))
        self.next_cells = bytearray(n)
        self.age = bytearray(1 if cell else 0 for cell in self.cells)
        self.trail = bytearray(220 if cell else 0 for cell in self.cells)
        neighbors = []
        for x in range(w):
            xm, xp = (x - 1) % w, (x + 1) % w
            for y in range(h):
                ym, yp = (y - 1) % h, (y + 1) % h
                neighbors.append((xm * h + ym, xm * h + y, xm * h + yp,
                                  x * h + ym, x * h + yp,
                                  xp * h + ym, xp * h + y, xp * h + yp))
        self.neighbors = neighbors

    def _inject(self, target, count=1):
        w, h = self.width, self.height
        for _ in range(count):
            shape = random.choice(self.SEED_SHAPES)
            ox, oy = random.randrange(w), random.randrange(h)
            for dx, dy in shape:
                idx = ((ox + dx) % w) * h + (oy + dy) % h
                target[idx] = 1
                self.age[idx] = 1
                self.trail[idx] = 255

    def _step(self, density):
        cells, nxt = self.cells, self.next_cells
        age, trail = self.age, self.trail
        assert cells is not None and nxt is not None
        assert age is not None and trail is not None and self.neighbors is not None
        for i, nb in enumerate(self.neighbors):
            near = (cells[nb[0]] + cells[nb[1]] + cells[nb[2]]
                    + cells[nb[3]] + cells[nb[4]] + cells[nb[5]]
                    + cells[nb[6]] + cells[nb[7]])
            alive = near == 3 or (cells[i] and near == 2)
            nxt[i] = 1 if alive else 0
            if alive:
                age[i] = min(255, age[i] + 7) if cells[i] else 1
                trail[i] = 255
            else:
                age[i] = 0
                trail[i] = trail[i] * 21 // 25
        self.cells, self.next_cells = nxt, cells
        self.generation += 1
        interval = 18 + int((1.0 - density) * 46)
        if self.generation % interval == 0:
            self._inject(self.cells, 1 + int(density * 2.0))

    def render(self, m, p, t, buf):
        if self.cells is None or len(self.cells) != m.total_pixels:
            self._init(m, p)
        if self.last_t is None:
            dt = 1.0 / 30.0
        else:
            dt = max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        self.accumulator += dt * (3.0 + p["speed"] * 15.0)
        steps = int(self.accumulator)
        self.accumulator -= steps
        for _ in range(steps):
            self._step(p["density"])

        c1, c2 = p["color1"], p["color2"]
        assert self.cells is not None and self.age is not None
        assert self.trail is not None and self.pixel_of is not None
        for grid_i, pixel_i in enumerate(self.pixel_of):
            out = pixel_i * 3
            if self.cells[grid_i]:
                lived = self.age[grid_i]
                tone = min(1.0, lived / 105.0)
                color = _mix(c1, c2, tone)
                newborn = max(0.0, 1.0 - lived / 18.0) * 0.72
                buf[out] = min(255, int(color[0] * 0.85 + 255 * newborn))
                buf[out + 1] = min(255, int(color[1] * 0.85 + 255 * newborn))
                buf[out + 2] = min(255, int(color[2] * 0.85 + 255 * newborn))
            else:
                glow = self.trail[grid_i] / 255.0
                glow = glow * glow * 0.30
                buf[out] = int(c2[0] * glow)
                buf[out + 1] = int(c2[1] * glow)
                buf[out + 2] = int(c2[2] * glow)


class Reaction(Pattern):
    """A Gray-Scott reaction-diffusion chemistry grows alien coral, cells,
    and crawling labyrinths over the whole car. Unlike a looped texture, the
    organism continuously evolves and never renders the same frame twice."""
    name = "reaction"
    defaults = {"color1": (30, 255, 120), "color2": (170, 20, 255),
                "speed": 0.45, "density": 0.52}

    def __init__(self):
        self.u = self.v = self.next_u = self.next_v = None
        self.neighbors = None
        self.pixel_of = None
        self.width = self.height = 0
        self.last_t = None
        self.accumulator = 0.0
        self.generation = 0

    def _seed_patch(self, cx, cy, radius=2):
        w, h = self.width, self.height
        for dx in range(-radius, radius + 1):
            for dy in range(-radius, radius + 1):
                if dx * dx + dy * dy <= radius * radius:
                    i = ((cx + dx) % w) * h + (cy + dy) % h
                    self.u[i], self.v[i] = 0.08, 0.92

    def _init(self, m, density):
        w, h, pixel_of = _surface_grid(m)
        self.width, self.height, self.pixel_of = w, h, pixel_of
        n = w * h
        self.u, self.v = [1.0] * n, [0.0] * n
        self.next_u, self.next_v = [0.0] * n, [0.0] * n
        self.neighbors = []
        for x in range(w):
            for y in range(h):
                self.neighbors.append((((x - 1) % w) * h + y,
                                       ((x + 1) % w) * h + y,
                                       x * h + (y - 1) % h,
                                       x * h + (y + 1) % h))
        # Many irregular, overlapping inoculation sites reach the interesting
        # merge/competition phase immediately instead of opening as a row of
        # tidy circular colonies.
        seeds = 22 + int(density * 22.0)
        for k in range(seeds):
            self._seed_patch((11 + k * 37 + k * k * 3) % w,
                             (7 + k * 17 + k * k * 5) % h,
                             1 + (k % 3))

    def _step(self, density):
        u, v, nu, nv = self.u, self.v, self.next_u, self.next_v
        assert u is not None and v is not None and nu is not None and nv is not None
        assert self.neighbors is not None
        # This path through Gray-Scott parameter space favors connected coral
        # and maze regimes over isolated circular spots.
        feed = 0.026 + density * 0.012
        kill = 0.055 + density * 0.006
        for i, nb in enumerate(self.neighbors):
            ui, vi = u[i], v[i]
            lap_u = u[nb[0]] + u[nb[1]] + u[nb[2]] + u[nb[3]] - 4.0 * ui
            lap_v = v[nb[0]] + v[nb[1]] + v[nb[2]] + v[nb[3]] - 4.0 * vi
            uvv = ui * vi * vi
            a = ui + 0.16 * lap_u - uvv + feed * (1.0 - ui)
            b = vi + 0.08 * lap_v + uvv - (feed + kill) * vi
            nu[i] = 0.0 if a < 0.0 else (1.0 if a > 1.0 else a)
            nv[i] = 0.0 if b < 0.0 else (1.0 if b > 1.0 else b)
        self.u, self.next_u = nu, u
        self.v, self.next_v = nv, v
        self.generation += 1
        if self.generation % 360 == 0:
            self._seed_patch((self.generation * 17) % self.width,
                             (self.generation * 7) % self.height, 2)

    def render(self, m, p, t, buf):
        if self.u is None or len(self.u) != m.total_pixels:
            self._init(m, p["density"])
        if self.last_t is None:
            dt = 1.0 / 30.0
        else:
            dt = max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        self.accumulator += dt * (6.0 + p["speed"] * 24.0)
        steps = int(self.accumulator)
        self.accumulator -= steps
        for _ in range(steps):
            self._step(p["density"])

        c1, c2 = p["color1"], p["color2"]
        assert self.u is not None and self.v is not None
        assert self.neighbors is not None and self.pixel_of is not None
        for grid_i, pixel_i in enumerate(self.pixel_of):
            ui, vi = self.u[grid_i], self.v[grid_i]
            nb = self.neighbors[grid_i]
            avg_v = (self.v[nb[0]] + self.v[nb[1]]
                     + self.v[nb[2]] + self.v[nb[3]]) * 0.25
            edge = min(1.0, abs(vi - avg_v) * 14.0)
            tone = min(1.0, vi * 2.35 + (1.0 - ui) * 0.28)
            level = min(1.0, 0.025 + tone * 0.78 + edge * 0.62)
            color = _mix(c1, c2, tone)
            hot = edge * edge * 0.30
            out = pixel_i * 3
            buf[out] = min(255, int(color[0] * level + 255 * hot))
            buf[out + 1] = min(255, int(color[1] * level + 255 * hot))
            buf[out + 2] = min(255, int(color[2] * level + 255 * hot))


class Breakout(Pattern):
    """An autonomous game of Breakout spanning the full car. The paddle
    chases the ball, bricks really disappear on impact, and every hit throws
    a little shower of colored debris."""
    name = "breakout"
    controls = ("speed", "density")
    defaults = {"speed": 0.48, "density": 0.48}

    BRICK_TOP = 0.075
    BRICK_HEIGHT = 0.068
    PADDLE_Y = 0.91

    def __init__(self):
        self.width = self.height = 0
        self.pixel_of = None
        self.rows = self.cols = 0
        self.bricks = None
        self.ball_x = self.ball_y = 0.0
        self.ball_vx = self.ball_vy = 0.0
        self.paddle_x = 0.5
        self.trail = []
        self.sparks = []
        self.last_t = None

    def _new_ball(self):
        self.ball_x, self.ball_y = self.paddle_x, self.PADDLE_Y - 0.055
        self.ball_vx, self.ball_vy = 0.17, -0.38
        self.trail = []

    def _reset(self, m, density):
        self.width, self.height, self.pixel_of = _surface_grid(m)
        self.rows = 4 + int(density * 4.0)
        self.cols = 14 + int(density * 11.0)
        self.bricks = bytearray([1]) * (self.rows * self.cols)
        self.paddle_x = 0.5
        self.sparks = []
        self._new_ball()

    def _burst(self, row, col):
        hue = (row / max(1, self.rows) * 0.72 + col * 0.013) % 1.0
        for k in range(9):
            angle = k * 2.0 * math.pi / 9.0 + row * 0.31
            speed = 0.045 + (k % 3) * 0.018
            self.sparks.append([
                self.ball_x, self.ball_y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                0.0, hue,
            ])

    def _physics(self, p, dt):
        pace = 0.52 + p["speed"] * 1.48
        steps = max(1, int(dt * 180.0) + 1)
        step = dt * pace / steps
        paddle_w = 0.11 + (1.0 - p["density"]) * 0.055
        for _ in range(steps):
            # The paddle is fallible: it follows the ball with finite speed,
            # rather than teleporting underneath it.
            delta = self.ball_x - self.paddle_x
            move = min(abs(delta), step * 0.53)
            self.paddle_x += move if delta > 0.0 else -move
            self.paddle_x = max(paddle_w * 0.5,
                                min(1.0 - paddle_w * 0.5, self.paddle_x))

            old_y = self.ball_y
            self.ball_x += self.ball_vx * step
            self.ball_y += self.ball_vy * step
            if self.ball_x <= 0.008:
                self.ball_x, self.ball_vx = 0.008, abs(self.ball_vx)
            elif self.ball_x >= 0.992:
                self.ball_x, self.ball_vx = 0.992, -abs(self.ball_vx)
            if self.ball_y <= 0.015:
                self.ball_y, self.ball_vy = 0.015, abs(self.ball_vy)

            # Only the solid interior of a brick counts; the gaps stay dark.
            row = int((self.ball_y - self.BRICK_TOP) / self.BRICK_HEIGHT)
            col = min(self.cols - 1, max(0, int(self.ball_x * self.cols)))
            if 0 <= row < self.rows:
                local_x = self.ball_x * self.cols - col
                local_y = ((self.ball_y - self.BRICK_TOP)
                           / self.BRICK_HEIGHT - row)
                brick_i = row * self.cols + col
                if (self.bricks[brick_i] and 0.07 < local_x < 0.93
                        and 0.10 < local_y < 0.90):
                    self.bricks[brick_i] = 0
                    self.ball_y = old_y
                    self.ball_vy = -self.ball_vy
                    self._burst(row, col)

            if (self.ball_vy > 0.0 and old_y < self.PADDLE_Y <= self.ball_y
                    and abs(self.ball_x - self.paddle_x) <= paddle_w * 0.55):
                english = (self.ball_x - self.paddle_x) / (paddle_w * 0.5)
                self.ball_y = self.PADDLE_Y - 0.012
                self.ball_vy = -abs(self.ball_vy)
                self.ball_vx = max(-0.34, min(0.34,
                                             self.ball_vx + english * 0.075))
            if self.ball_y > 1.03:
                self._new_ball()
        if self.bricks is not None and not any(self.bricks):
            self.bricks[:] = bytes([1]) * len(self.bricks)
            self._new_ball()

    def render(self, m, p, t, buf):
        wanted = (4 + int(p["density"] * 4.0),
                  14 + int(p["density"] * 11.0))
        if self.bricks is None or (self.rows, self.cols) != wanted:
            self._reset(m, p["density"])
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        self._physics(p, dt)

        alive_sparks = []
        for spark in self.sparks:
            spark[0] += spark[2] * dt
            spark[1] += spark[3] * dt
            spark[3] += 0.12 * dt
            spark[4] += dt
            if spark[4] < 1.0:
                alive_sparks.append(spark)
        self.sparks = alive_sparks[-90:]
        self.trail.append((self.ball_x, self.ball_y))
        self.trail = self.trail[-11:]

        w, h = self.width, self.height
        surface = bytearray(w * h * 3)

        def put(x, y, color):
            if 0 <= x < w and 0 <= y < h:
                q = (x * h + y) * 3
                surface[q] = max(surface[q], color[0])
                surface[q + 1] = max(surface[q + 1], color[1])
                surface[q + 2] = max(surface[q + 2], color[2])

        for k in range(32):
            put((k * 47 + 9) % w, (k * 19 + 5) % h, (2, 4, 12 + k % 9))
        for row in range(self.rows):
            for col in range(self.cols):
                if not self.bricks[row * self.cols + col]:
                    continue
                color = hsv((row * 0.115 + col * 0.006 + t * 0.008) % 1.0,
                            0.88, 1.0)
                x0 = int(col * w / self.cols) + 1
                x1 = int((col + 1) * w / self.cols) - 1
                y0 = int((self.BRICK_TOP + row * self.BRICK_HEIGHT) * h) + 1
                y1 = int((self.BRICK_TOP + (row + 1) * self.BRICK_HEIGHT) * h) - 1
                for x in range(x0, x1 + 1):
                    for y in range(y0, y1 + 1):
                        put(x, y, color)

        for k, (x, y) in enumerate(self.trail):
            f = (k + 1) / len(self.trail) * 0.34
            put(int(x * w), int(y * h), (int(60 * f), int(150 * f), int(255 * f)))
        bx, by = int(self.ball_x * w), int(self.ball_y * h)
        for dx, dy in ((0, 0), (-1, 0), (1, 0), (0, -1), (0, 1)):
            put(bx + dx, by + dy, (255, 255, 255) if dx == dy == 0
                else (90, 190, 255))
        paddle_w = 0.11 + (1.0 - p["density"]) * 0.055
        px0 = int((self.paddle_x - paddle_w * 0.5) * w)
        px1 = int((self.paddle_x + paddle_w * 0.5) * w)
        py = int(self.PADDLE_Y * h)
        for x in range(px0, px1 + 1):
            put(x, py, (255, 40, 190))
            put(x, py + 1, (90, 220, 255))
        for x, y, _, _, age, hue in self.sparks:
            value = max(0.0, 1.0 - age)
            put(int(x * w), int(y * h), hsv(hue, 0.75, value))
        _surface_to_buffer(surface, self.pixel_of, buf)


class SpaceInvaders(Pattern):
    """A complete self-playing Space Invaders battle. The formation marches,
    descends, shoots, and animates while the cannon tracks targets, returns
    fire, destroys individual invaders, and starts a fresh wave."""
    name = "invaders"
    controls = ("speed", "density")
    defaults = {"speed": 0.48, "density": 0.52}

    ALIENS = (
        ("01110", "11111", "10101", "01010"),
        ("01110", "11111", "01010", "10101"),
    )
    PLAYER = ("00100", "01110", "11111")
    UFO = ("0111110", "1111111", "1010101")
    SHIELD = ("0111110", "1111111", "1100011")

    def __init__(self):
        self.width = self.height = 0
        self.pixel_of = None
        self.rows = self.cols = 0
        self.alive = None
        self.fleet_x = self.fleet_y = 0.0
        self.direction = 1.0
        self.player_x = 0.0
        self.player_bullet = None
        self.enemy_bullets = []
        self.explosions = []
        self.enemy_accumulator = 0.0
        self.enemy_emission = 0
        self.target = 0
        self.reset_timer = 0.0
        self.last_t = None

    def _reset(self, m, density):
        self.width, self.height, self.pixel_of = _surface_grid(m)
        self.rows = 3 + int(density * 2.99)
        self.cols = 9 + int(density * 5.0)
        self.alive = bytearray([1]) * (self.rows * self.cols)
        formation_w = (self.cols - 1) * 8 + 5
        self.fleet_x = (self.width - formation_w) * 0.5
        self.fleet_y = 3.0
        self.direction = 1.0
        self.player_x = self.width * 0.5
        self.player_bullet = None
        self.enemy_bullets = []
        self.explosions = []
        self.enemy_accumulator = 0.0
        self.reset_timer = 0.0

    def _alien_xy(self, idx):
        row, col = divmod(idx, self.cols)
        return self.fleet_x + col * 8, self.fleet_y + row * 5

    def _update(self, m, p, dt):
        if self.reset_timer > 0.0:
            self.reset_timer -= dt
            if self.reset_timer <= 0.0:
                self._reset(m, p["density"])
            return
        alive_indices = [i for i, value in enumerate(self.alive) if value]
        if not alive_indices:
            self.reset_timer = 0.8
            return

        killed = len(self.alive) - len(alive_indices)
        fleet_speed = ((3.2 + p["speed"] * 7.5)
                       * (1.0 + killed / len(self.alive) * 1.8))
        formation_w = (self.cols - 1) * 8 + 5
        next_x = self.fleet_x + self.direction * fleet_speed * dt
        if next_x < 1.0 or next_x + formation_w >= self.width - 1.0:
            self.direction *= -1.0
            self.fleet_y += 1.25
        else:
            self.fleet_x = next_x
        if self.fleet_y + self.rows * 5 >= self.height - 7:
            self.reset_timer = 0.8

        if self.player_bullet is None:
            alive_indices = [i for i, value in enumerate(self.alive) if value]
            target = alive_indices[self.target % len(alive_indices)]
            target_x = self._alien_xy(target)[0] + 2.0
            delta = target_x - self.player_x
            move = min(abs(delta), dt * (22.0 + p["speed"] * 22.0))
            self.player_x += move if delta > 0.0 else -move
            if abs(delta) < 1.3:
                self.player_bullet = [self.player_x, self.height - 5.0]
                self.target += 3
        else:
            self.player_bullet[1] -= (15.0 + p["speed"] * 17.0) * dt
            bx, by = self.player_bullet
            hit = None
            for idx in alive_indices:
                ax, ay = self._alien_xy(idx)
                if ax - 0.5 <= bx <= ax + 4.5 and ay <= by <= ay + 4.0:
                    hit = idx
                    break
            if hit is not None:
                self.alive[hit] = 0
                alive_indices.remove(hit)
                ax, ay = self._alien_xy(hit)
                self.explosions.append([ax + 2.0, ay + 1.5, 0.0,
                                        hit / max(1, len(self.alive) - 1)])
                self.player_bullet = None
            elif by < -1.0:
                self.player_bullet = None

        self.enemy_accumulator += dt * (0.30 + p["density"] * 1.05)
        while self.enemy_accumulator >= 1.0 and alive_indices:
            self.enemy_accumulator -= 1.0
            shooter = alive_indices[(self.enemy_emission * 7) % len(alive_indices)]
            ax, ay = self._alien_xy(shooter)
            self.enemy_bullets.append([ax + 2.0, ay + 4.0])
            self.enemy_emission += 1
        falling = []
        for shot in self.enemy_bullets:
            shot[1] += (8.0 + p["speed"] * 8.0) * dt
            if shot[1] >= self.height - 3 and abs(shot[0] - self.player_x) < 3.0:
                self.explosions.append([self.player_x, self.height - 3.0, 0.0, 0.0])
                self.reset_timer = 0.8
            elif shot[1] < self.height:
                falling.append(shot)
        self.enemy_bullets = falling[-24:]
        live_explosions = []
        for explosion in self.explosions:
            explosion[2] += dt
            if explosion[2] < 0.75:
                live_explosions.append(explosion)
        self.explosions = live_explosions

    def render(self, m, p, t, buf):
        wanted = (3 + int(p["density"] * 2.99),
                  9 + int(p["density"] * 5.0))
        if self.alive is None or (self.rows, self.cols) != wanted:
            self._reset(m, p["density"])
        dt = 0.0 if self.last_t is None else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        self._update(m, p, dt)

        w, h = self.width, self.height
        surface = bytearray(w * h * 3)

        def put(x, y, color):
            if 0 <= x < w and 0 <= y < h:
                q = (x * h + y) * 3
                surface[q] = max(surface[q], color[0])
                surface[q + 1] = max(surface[q + 1], color[1])
                surface[q + 2] = max(surface[q + 2], color[2])

        def sprite(mask, x0, y0, color):
            for y, line in enumerate(mask):
                for x, pixel in enumerate(line):
                    if pixel == "1":
                        put(x0 + x, y0 + y, color)

        for k in range(42):
            value = 12 + ((k * 13 + int(t * 5.0)) % 18)
            put((k * 43 + 7) % w, (k * 17 + 1) % h, (value // 3, value // 2, value))
        alien_frame = int(t * (2.5 + p["speed"] * 4.0)) & 1
        for idx, alive in enumerate(self.alive):
            if not alive:
                continue
            row, _ = divmod(idx, self.cols)
            x, y = self._alien_xy(idx)
            color = hsv((0.28 + row * 0.13 + t * 0.006) % 1.0, 0.86, 1.0)
            sprite(self.ALIENS[alien_frame], int(x), int(y), color)

        for k in range(4):
            x = int((k + 1) * w / 5) - 3
            sprite(self.SHIELD, x, h - 10, (30, 190, 80))
        player_color = (255, 80, 60) if self.reset_timer > 0.0 else (80, 220, 255)
        sprite(self.PLAYER, int(self.player_x) - 2, h - 4, player_color)
        if self.player_bullet is not None:
            x, y = int(self.player_bullet[0]), int(self.player_bullet[1])
            put(x, y, (255, 255, 255))
            put(x, y + 1, (80, 220, 255))
        for x, y in self.enemy_bullets:
            put(int(x), int(y), (255, 245, 50))
            put(int(x), int(y) - 1, (255, 50, 30))
        for x, y, age, tone in self.explosions:
            color = hsv(tone, 0.65, max(0.0, 1.0 - age / 0.75))
            radius = 1 + int(age * 7.0)
            for dx, dy in ((-radius, 0), (radius, 0), (0, -radius), (0, radius),
                           (-radius, -radius), (radius, -radius),
                           (-radius, radius), (radius, radius)):
                put(int(x) + dx, int(y) + dy, color)

        ufo_cycle = t % 8.0
        if ufo_cycle < 3.8:
            ufo_x = int(-8 + (w + 16) * ufo_cycle / 3.8)
            sprite(self.UFO, ufo_x, 0, (255, 35, 80))
        _surface_to_buffer(surface, self.pixel_of, buf)


class Lasers(Pattern):
    """A sweeping fan of neon laser beams. Intersections flare white;
    density controls the number of independently moving beams."""
    name = "lasers"
    defaults = {"color1": (0, 255, 220), "color2": (255, 0, 180),
                "speed": 0.55, "density": 0.55}

    def render(self, m, p, t, buf):
        sx, sid, fracs = _side_unroll(m)
        count = 3 + int(p["density"] * 6.0)
        motion = t * (0.28 + p["speed"] * 1.55)
        c1, c2 = p["color1"], p["color2"]
        beams = []
        for side in range(len(fracs)):
            side_beams = []
            for k in range(count):
                x0 = (k + 0.5) / count
                ph = motion * (0.72 + (k % 4) * 0.11) + k * 1.73 + side * 0.91
                x1 = 0.5 + 0.52 * math.sin(ph)
                slope = x1 - x0
                inv_len = 1.0 / math.sqrt(1.0 + slope * slope)
                color = _mix(c1, c2, k / max(1, count - 1))
                side_beams.append((x0, slope, inv_len, color))
            beams.append(side_beams)

        # Wide colored bloom plus a narrow white-hot beam. The bloom ensures
        # that a moving line never disappears between physical tube columns.
        bloom_w = 0.052
        core_w = 0.014
        along = m.along
        for i in range(m.total_pixels):
            x, y, side = sx[i], along[i], sid[i]
            red = green = blue = 1
            for x0, slope, inv_len, color in beams[side]:
                d = abs(x - (x0 + slope * y)) * inv_len
                if d >= bloom_w:
                    continue
                bloom = 1.0 - d / bloom_w
                bloom = bloom * bloom * bloom
                if d < core_w:
                    core = 1.0 - d / core_w
                    core *= core
                else:
                    core = 0.0
                level = bloom * 0.18 + core * 0.95
                hot = core * core * core * core * 0.42
                red += int(color[0] * level + 255 * hot)
                green += int(color[1] * level + 255 * hot)
                blue += int(color[2] * level + 255 * hot)

            # A dim horizontal scan line gives the fan another plane of motion.
            scan_y = (motion * 0.115 + side * 0.29) % 1.0
            scan_d = abs(y - scan_y)
            if scan_d < 0.035:
                scan = (1.0 - scan_d / 0.035) ** 3 * 0.42
                red += int(c2[0] * scan)
                green += int(c2[1] * scan)
                blue += int(c2[2] * scan)
            j = i * 3
            buf[j] = min(255, red)
            buf[j + 1] = min(255, green)
            buf[j + 2] = min(255, blue)


class Collider(Pattern):
    """Restless filaments cross and react. Every genuine line intersection
    emits a growing shockwave; when that wave hits another filament, the
    contact point re-ignites white. The geometry creates the events instead
    of playing back a canned burst sequence."""
    name = "collider"
    defaults = {"color1": (0, 255, 180), "color2": (255, 20, 120),
                "speed": 0.48, "density": 0.5}

    PERIM_OVER_TUBE = 9.8 / 2.5

    def __init__(self):
        self.ripples = []       # [side, x, y, age, color_blend]
        self.last_t = None
        self.emit_accumulator = 0.0
        self.emission = 0

    @staticmethod
    def _geometry(p, t, nsides):
        count = 4 + int(p["density"] * 4.0)
        motion = t * (0.20 + p["speed"] * 0.92)
        c1, c2 = p["color1"], p["color2"]
        all_beams, all_hits = [], []
        for side in range(nsides):
            beams = []
            for k in range(count):
                phase = k * 1.83 + side * 0.74
                top = 0.5 + 0.53 * math.sin(
                    motion * (0.61 + (k % 3) * 0.13) + phase)
                bottom = 0.5 + 0.53 * math.sin(
                    -motion * (0.47 + (k % 4) * 0.09) + phase * 1.37 + 1.1)
                slope = bottom - top
                inv_len = 1.0 / math.sqrt(1.0 + slope * slope)
                color = _mix(c1, c2, k / max(1, count - 1))
                beams.append((top, slope, inv_len, color))
            hits = []
            for a in range(count):
                for b in range(a + 1, count):
                    top_a, slope_a = beams[a][0], beams[a][1]
                    top_b, slope_b = beams[b][0], beams[b][1]
                    denom = slope_a - slope_b
                    if abs(denom) < 1e-6:
                        continue
                    y = (top_b - top_a) / denom
                    x = top_a + slope_a * y
                    if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                        tone = (a + b) / max(1, 2 * count - 2)
                        hits.append((x, y, tone))
            all_beams.append(beams)
            all_hits.append(hits)
        return all_beams, all_hits

    def _emit(self, hits, initial=False):
        for side, side_hits in enumerate(hits):
            if not side_hits:
                continue
            if initial:
                chosen = side_hits[:2]
            else:
                chosen = [side_hits[(self.emission + side) % len(side_hits)]]
            for x, y, tone in chosen:
                self.ripples.append([side, x, y, 0.08 if initial else 0.0, tone])
        self.emission += 1
        if len(self.ripples) > 21:
            self.ripples = self.ripples[-21:]

    def render(self, m, p, t, buf):
        beams, hits = self._geometry(p, t, len(_side_unroll(m)[2]))
        first = self.last_t is None
        dt = 0.0 if first else max(0.0, min(0.1, t - self.last_t))
        self.last_t = t
        alive = []
        for ripple in self.ripples:
            ripple[3] += dt
            if ripple[3] < 2.0:
                alive.append(ripple)
        self.ripples = alive
        if first:
            self._emit(hits, initial=True)
        else:
            interval = 0.21 + (1.0 - p["density"]) * 0.25
            self.emit_accumulator += dt
            while self.emit_accumulator >= interval:
                self.emit_accumulator -= interval
                self._emit(hits)

        sx, sid, fracs = _side_unroll(m)
        aspects = [f * self.PERIM_OVER_TUBE for f in fracs]
        c1, c2 = p["color1"], p["color2"]
        # Per-ripple geometry is a per-FRAME quantity: radius, widths, fade
        # and color were being recomputed for all 5,576 pixels.
        speed_r = 0.13 + p["speed"] * 0.29
        by_side = [[] for _ in fracs]
        for side_r, cx, cy, age, tone in self.ripples:
            radius = age * speed_r
            width = 0.020 + age * 0.010
            fade = max(0.0, 1.0 - age / 2.0)
            core_age = max(0.0, 1.0 - age / 0.6)
            by_side[side_r].append((cx, cy, radius, width, width * 4.0,
                                    fade, core_age, _mix(c1, c2, tone)))
        bloom_w, core_w = 0.047, 0.012
        along = m.along
        hypot = math.hypot
        for i in range(m.total_pixels):
            # sx ramps slightly WITHIN each tube (side-local shear), so x is
            # genuinely per-pixel here — only the per-frame work is hoisted.
            x, y, side = sx[i], along[i], sid[i]
            asp = aspects[side]
            red, green, blue = 1, 0, 2
            line_energy = 0.0
            for top, slope, inv_len, color in beams[side]:
                d = x - (top + slope * y)
                if d < 0.0:
                    d = -d
                d *= inv_len
                if d >= bloom_w:
                    continue
                bloom = 1.0 - d / bloom_w
                bloom = bloom * bloom * bloom
                if d < core_w:
                    core = 1.0 - d / core_w
                    core *= core
                else:
                    core = 0.0
                strength = bloom * 0.16 + core * 0.76
                line_energy = min(1.0, line_energy + strength)
                red += int(color[0] * strength + 210 * core * core)
                green += int(color[1] * strength + 210 * core * core)
                blue += int(color[2] * strength + 210 * core * core)

            for (cx, cy, radius, width, glow_w,
                 fade, core_age, color) in by_side[side]:
                d = hypot((x - cx) * asp, y - cy)
                delta = d - radius
                if delta < 0.0:
                    delta = -delta
                if delta >= glow_w and d >= 0.09:
                    continue
                if delta < width:
                    ring = 1.0 - delta / width
                    ring *= ring
                else:
                    ring = 0.0
                if delta < glow_w:
                    glow = 1.0 - delta / glow_w
                    glow = glow * glow * glow
                else:
                    glow = 0.0
                core = max(0.0, 1.0 - d / 0.09) * core_age
                reaction = ring * line_energy
                level = (ring * 0.72 + glow * 0.20 + core * 0.75) * fade
                hot = (ring * ring * 0.34 + reaction * 0.90
                       + core * 0.55) * fade
                red += int(color[0] * level + 255 * hot)
                green += int(color[1] * level + 255 * hot)
                blue += int(color[2] * level + 255 * hot)
            j = i * 3
            buf[j] = min(255, red)
            buf[j + 1] = min(255, green)
            buf[j + 2] = min(255, blue)


class Supernova(Pattern):
    """Overlapping stellar shockwaves bloom across each side: white-hot
    rims fade from color1 into color2 as they expand."""
    name = "supernova"
    defaults = {"color1": (255, 70, 15), "color2": (80, 30, 255),
                "speed": 0.5, "density": 0.5}

    PERIM_OVER_TUBE = 9.8 / 2.5
    CENTERS = ((0.16, 0.24), (0.72, 0.68), (0.43, 0.46),
               (0.84, 0.30), (0.27, 0.78), (0.58, 0.16))

    def render(self, m, p, t, buf):
        sx, sid, fracs = _side_unroll(m)
        aspects = [f * self.PERIM_OVER_TUBE for f in fracs]
        count = 2 + int(p["density"] * 4.0)
        rate = 0.045 + p["speed"] * 0.17
        c1, c2 = p["color1"], p["color2"]
        bursts = []
        for side in range(len(fracs)):
            sb = []
            reach = 0.76 + aspects[side] * 0.45
            for k in range(count):
                phase = (t * rate + k / count + side * 0.217) % 1.0
                bx, by = self.CENTERS[(k + side * 2) % len(self.CENTERS)]
                bx = (bx + side * 0.137) % 1.0
                color = _mix(c1, c2, ((k + side) % count) / max(1, count - 1))
                sb.append((bx, by, phase * reach, phase, color))
            bursts.append(sb)

        # thickness/glow/fade/core-window depend only on the burst's phase —
        # per-frame quantities, hoisted out of the pixel loop.
        for side in range(len(fracs)):
            bursts[side] = [(bx, by, radius, 0.022 + phase * 0.032,
                             (0.022 + phase * 0.032) * 4.5,
                             1.0 - phase * 0.70,
                             (1.0 - phase / 0.20) if phase < 0.20 else 0.0,
                             color)
                            for bx, by, radius, phase, color in bursts[side]]
        along = m.along
        hypot = math.hypot
        for i in range(m.total_pixels):
            # sx ramps slightly WITHIN each tube (side-local shear), so x is
            # genuinely per-pixel here — only the per-frame work is hoisted.
            side = sid[i]
            x, y = sx[i], along[i]
            asp = aspects[side]
            red, green, blue = 1, 0, 3
            for (bx, by, radius, thickness, glow_width,
                 fade, core_ph, color) in bursts[side]:
                d = hypot((x - bx) * asp, y - by)
                delta = d - radius
                if delta < 0.0:
                    delta = -delta
                if delta >= glow_width and d >= 0.10:
                    continue
                if delta < thickness:
                    ring = 1.0 - delta / thickness
                    ring *= ring
                else:
                    ring = 0.0
                if delta < glow_width:
                    glow = 1.0 - delta / glow_width
                    glow = glow * glow * glow
                else:
                    glow = 0.0
                if core_ph and d < 0.10:
                    core = 1.0 - d / 0.10
                    core = core * core * core_ph
                else:
                    core = 0.0
                level = (ring * 0.95 + glow * 0.24) * fade + core
                hot = ring ** 3 * 0.60 * fade + core * 0.85
                red += int(color[0] * level + 255 * hot)
                green += int(color[1] * level + 255 * hot)
                blue += int(color[2] * level + 255 * hot)
            j = i * 3
            buf[j] = min(255, red)
            buf[j + 1] = min(255, green)
            buf[j + 2] = min(255, blue)


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
            # sub-pixel along the tube: split between the two pixels the
            # point straddles, so rising rockets and falling sparks glide
            if 0.0 <= y <= 1.0:
                ti = int((x % 1.0) * nt) % nt
                jf = y * (ppt - 1)
                j = int(jf)
                fr = jf - j
                base = ti * ppt
                for jj, w in ((j, 1.0 - fr), (j + 1, fr)):
                    if 0 <= jj < ppt and w > 0.02:
                        idx = (base + jj) * 3
                        rw, gw, bw = int(r * w), int(g * w), int(b * w)
                        if rw > buf[idx]:
                            buf[idx] = rw
                        if gw > buf[idx + 1]:
                            buf[idx + 1] = gw
                        if bw > buf[idx + 2]:
                            buf[idx + 2] = bw

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
            hf = y * (ppt - 1)
            hj = math.floor(hf)                      # floor: y starts negative
            fr = hf - hj                             # sub-pixel head position
            if hj - ln > ppt:
                continue
            alive.append(s)
            base = ti * ppt
            # the white-hot head glides: split between its two pixels
            for j, w in ((hj, 1.0 - fr), (hj + 1, fr)):
                if 0 <= j < ppt and w > 0.0:
                    idx = (base + j) * 3
                    if int(255 * w) > buf[idx + 1]:
                        buf[idx] = int(180 * w)
                        buf[idx + 1] = int(255 * w)
                        buf[idx + 2] = int(180 * w)
            for k in range(1, ln):
                j = hj - k
                if 0 <= j < ppt:
                    idx = (base + j) * 3
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
        cr, cg, cb = hsv((bounces * 0.161) % 1.0, 1.0, 1.0)
        perim, along = m.perim, m.along
        # ~1-pixel feather in logo units, so the edges glide between pixels
        # instead of popping as the logo drifts.
        au = (1.0 / len(m.tubes)) / sw           # one tube column, in u
        av = (1.0 / (m.px_per_tube - 1)) / sh    # one tube pixel, in v
        for i in range(m.total_pixels):
            u = (perim[i] - x0) / sw
            if not 0.0 <= u < 1.0:
                continue
            v = (along[i] - y0) / sh
            if not 0.0 <= v < 1.0:
                continue
            # stylized logo: fat ellipse ring on top, solid bar below,
            # every edge rendered as coverage rather than a hard test
            a = 0.0
            if v < 0.62 + av:
                eu = (u - 0.5) / 0.5
                ev = (v - 0.31) / 0.31
                e = eu * eu + ev * ev
                ring = min(_cov(1.0 - e, 0.18),  # outer rim of the ellipse
                           _cov(e - 0.30, 0.12))  # hole in the middle
                a = ring * _cov(0.62 - v, av)    # fade at the ring/gap seam
            if v > 0.75 - av:
                bar = min(_cov(v - 0.75, av), _cov(1.0 - v, av),
                          _cov(u, au), _cov(1.0 - u, au))
                if bar > a:
                    a = bar
            if a > 0.0:
                j = i * 3
                buf[j] = int(cr * a)
                buf[j + 1] = int(cg * a)
                buf[j + 2] = int(cb * a)


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
                # coverage per part, so edges glide instead of popping
                hx, hy = bx / 0.14, (v - 0.13) / 0.13
                a = _cov(1.0 - (hx * hx + hy * hy), 0.30)        # head
                shaft = min(_cov(0.095 - bx, 0.03),
                            _cov(bx + 0.095, 0.03),
                            _cov(v - 0.13, 0.04), _cov(0.85 - v, 0.04))
                if shaft > a:
                    a = shaft
                for s_ in (-1.0, 1.0):                           # balls
                    gx = (bx - s_ * 0.15) / 0.15
                    gy = (v - 0.85) / 0.14
                    ball = _cov(1.0 - (gx * gx + gy * gy), 0.30)
                    if ball > a:
                        a = ball
                if a > 0.0:
                    buf[j] = int(c[0] * a)
                    buf[j + 1] = int(c[1] * a)
                    buf[j + 2] = int(c[2] * a)
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
                    rim = _cov(1.0 - r2, 0.22)   # feathered outline: jiggles
                    nd = sqrt(du * du + (dv - 0.25) ** 2)   # glide, not pop
                    if nd < 0.13:                # nipple
                        f = (1.25 if nd < 0.05 else 1.0) * rim
                        buf[j] = min(255, int(c2[0] * f))
                        buf[j + 1] = min(255, int(c2[1] * f))
                        buf[j + 2] = min(255, int(c2[2] * f))
                    else:                        # skin, shaded round
                        f = (1.0 - r2 * 0.45) * rim
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
                jf = ys * (ppt - 1)
                jj = int(jf)
                fr = jf - jj
                f = 1.0 if s == 0 else (1.0 - s / tail_len) * 0.8
                # split each sample between its two pixels: the whipping
                # tail and head glide instead of stair-stepping
                for j2, w in ((jj, (1.0 - fr) * f), (jj + 1, fr * f)):
                    if not 0 <= j2 < ppt:
                        continue
                    idx = (ti * ppt + j2) * 3
                    r = int(c1[0] * w)
                    g = int(c1[1] * w)
                    b = int(c1[2] * w)
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
            # head (feathered rim so the rise glides, not pops)
            hx, hy = bx / 0.14, (by - (vt + 0.10)) / 0.12
            hr2 = hx * hx + hy * hy
            if hr2 <= 1.0:
                f = (1.0 - 0.35 * hx * hx) * _cov(1.0 - hr2, 0.30)
                c = _mix(c2, (255, 255, 255), 0.6) if e > 0.92 else c2
                buf[j] = int(c[0] * f)
                buf[j + 1] = int(c[1] * f)
                buf[j + 2] = int(c[2] * f)
                continue
            # shaft (soft side edges + soft tip seam)
            if -0.095 < bx < 0.095 and vt + 0.10 <= by <= 1.0:
                f = (1.0 - 0.45 * (bx / 0.095) ** 2) \
                    * _cov(0.095 - abs(bx), 0.025) \
                    * _cov(by - (vt + 0.10), 0.03)
                buf[j] = int(c1[0] * f)
                buf[j + 1] = int(c1[1] * f)
                buf[j + 2] = int(c1[2] * f)
                continue
            # balls
            for s in (-1.0, 1.0):
                gx, gy = (bx - s * 0.15) / 0.15, (by - 0.98) / 0.13
                r2 = gx * gx + gy * gy
                if r2 <= 1.0:
                    f = (0.9 - 0.35 * r2) * _cov(1.0 - r2, 0.30)
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
                    rim = _cov(1.0 - r2, 0.22)   # feathered outline: the
                    if abs(bx) < 0.04:           # twerk glides, not pops
                        f = 0.15 * rim           # (the crack)
                    else:
                        f = (1.0 - 0.40 * r2) * rim
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
            # dome (feathered so the cruise glides)
            gx, gy = dx / (rx * 0.45), (py - (sy - 0.055)) / 0.06
            r2 = gx * gx + gy * gy
            if r2 <= 1.0 and py <= sy:
                a = _cov(1.0 - r2, 0.30)
                buf[j] = int(120 * a)
                buf[j + 1] = int(230 * a)
                buf[j + 2] = int(255 * a)
                continue
            # hull with blinking rim lights
            gx, gy = dx / rx, (py - sy) / 0.045
            r2 = gx * gx + gy * gy
            if r2 <= 1.0:
                a = _cov(1.0 - r2, 0.25)
                if gx * gx > 0.55 and sin(t * 9.0 + (1 if gx > 0 else 4)) > 0.2:
                    buf[j] = int(255 * a)
                    buf[j + 1] = int(80 * a)
                    buf[j + 2] = int(200 * a)
                else:
                    buf[j] = buf[j + 1] = buf[j + 2] = int(165 * a)
                continue
            # abductee: little pink blob flailing in the beam
            adx = (dx - wob) / (0.05 / self.PERIM_OVER_TUBE)
            ady = (py - ay) / 0.05
            r2 = adx * adx + ady * ady
            if r2 <= 1.0:
                a = _cov(1.0 - r2, 0.35)
                buf[j] = int(255 * a)
                buf[j + 1] = int(140 * a)
                buf[j + 2] = int(180 * a)
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
        # color by the tube's actual receiver output (1-4), not tube index
        # modulo group size -- boards carry 14 tubes (groups of 4,4,4,2), so
        # index parity shears off the physical outputs after the first board
        for ti in range(len(m.tubes)):
            c = self.COLORS[(m.tubes[ti]["output"] - 1) % len(self.COLORS)]
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
        buf[:] = bytes(len(buf))


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
    Rainbow(), Scrub(), Ribbons(), Voronoi(), Life(), Reaction(),
    Breakout(),
    SpaceInvaders(), Aurora(), Supernova(), Lasers(), Collider(), Fire(),
    Plasma(), RainbowSnake(),
    Meteors(), Storm(), Stripes(), Cubes(),
    Breathe(), RainbowBreathe(), Wave(), Comet(), Rain(), Sparkle(), Confetti(),
    BroomStroke(), PacMan(), Horses(), Bianca(), Fireworks(),
    Matrix(), Disco(), EKG(), DVD(), DVDPenis(), Police(), Butthole(), Boobs(), Penis(),
    Twerk(), Poop(), UFO(), GooglyEyes(), Sperm(), Lava(), Hypno(), Solid(),
    EmojiSprite(),
]

REGISTRY = {pat.name: pat for pat in
            _BASE + _load_sprite_patterns() + [Mapping(), Off()]}

NAMES = list(REGISTRY.keys())
