"""Tiny pure-stdlib SVG-path rasterizer -> alpha mask.

Enough SVG to turn a monochrome icon (one or more <path> elements) into a
low-res coverage bitmap the pattern engine can stamp onto the car surface.
Supports M/L/H/V/C/S/Q/T/Z (absolute + relative); arcs are approximated by a
line. Fill uses the nonzero winding rule with 2x supersampling.
"""

import math
import re
from pathlib import Path

_NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")
_CMD = re.compile(r"([MmLlHhVvCcSsQqTtZzAa])")


def _flatten_cubic(p0, p1, p2, p3, out, n=8):
    for k in range(1, n + 1):
        t = k / n
        mt = 1 - t
        a, b, c, d = mt * mt * mt, 3 * mt * mt * t, 3 * mt * t * t, t * t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0],
                    a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))


def _flatten_quad(p0, p1, p2, out, n=8):
    for k in range(1, n + 1):
        t = k / n
        mt = 1 - t
        a, b, c = mt * mt, 2 * mt * t, t * t
        out.append((a * p0[0] + b * p1[0] + c * p2[0],
                    a * p0[1] + b * p1[1] + c * p2[1]))


def _parse_paths(d):
    """Return list of subpaths, each a list of (x, y) polygon vertices."""
    subpaths = []
    poly = []
    cur = (0.0, 0.0)
    start = (0.0, 0.0)
    prev_c2 = None       # reflected control for S
    prev_q1 = None       # reflected control for T
    tokens = _CMD.split(d)
    i = 0
    while i < len(tokens):
        tok = tokens[i].strip()
        i += 1
        if not tok or tok not in "MmLlHhVvCcSsQqTtZzAa":
            continue
        nums = [float(x) for x in _NUM.findall(tokens[i])] if i < len(tokens) else []
        i += 1
        rel = tok.islower()
        cmd = tok.upper()
        k = 0
        if cmd == "M":
            while k + 1 < len(nums) + 1 and k + 1 <= len(nums):
                x, y = nums[k], nums[k + 1]
                if rel:
                    x += cur[0]; y += cur[1]
                if k == 0:
                    if poly:
                        subpaths.append(poly)
                    poly = [(x, y)]
                    start = (x, y)
                else:
                    poly.append((x, y))
                cur = (x, y)
                k += 2
            prev_c2 = prev_q1 = None
        elif cmd == "L":
            while k + 1 < len(nums) + 1 and k + 1 <= len(nums):
                x, y = nums[k], nums[k + 1]
                if rel:
                    x += cur[0]; y += cur[1]
                poly.append((x, y)); cur = (x, y); k += 2
            prev_c2 = prev_q1 = None
        elif cmd == "H":
            for v in nums:
                x = v + cur[0] if rel else v
                poly.append((x, cur[1])); cur = (x, cur[1])
            prev_c2 = prev_q1 = None
        elif cmd == "V":
            for v in nums:
                y = v + cur[1] if rel else v
                poly.append((cur[0], y)); cur = (cur[0], y)
            prev_c2 = prev_q1 = None
        elif cmd == "C":
            while k + 5 < len(nums) + 1 and k + 5 <= len(nums):
                pts = []
                for j in range(0, 6, 2):
                    x, y = nums[k + j], nums[k + j + 1]
                    if rel:
                        x += cur[0]; y += cur[1]
                    pts.append((x, y))
                _flatten_cubic(cur, pts[0], pts[1], pts[2], poly)
                prev_c2 = pts[1]; cur = pts[2]; k += 6
            prev_q1 = None
        elif cmd == "S":
            while k + 3 < len(nums) + 1 and k + 3 <= len(nums):
                c1 = (2 * cur[0] - prev_c2[0], 2 * cur[1] - prev_c2[1]) if prev_c2 else cur
                pts = []
                for j in range(0, 4, 2):
                    x, y = nums[k + j], nums[k + j + 1]
                    if rel:
                        x += cur[0]; y += cur[1]
                    pts.append((x, y))
                _flatten_cubic(cur, c1, pts[0], pts[1], poly)
                prev_c2 = pts[0]; cur = pts[1]; k += 4
            prev_q1 = None
        elif cmd == "Q":
            while k + 3 < len(nums) + 1 and k + 3 <= len(nums):
                pts = []
                for j in range(0, 4, 2):
                    x, y = nums[k + j], nums[k + j + 1]
                    if rel:
                        x += cur[0]; y += cur[1]
                    pts.append((x, y))
                _flatten_quad(cur, pts[0], pts[1], poly)
                prev_q1 = pts[0]; cur = pts[1]; k += 4
            prev_c2 = None
        elif cmd == "T":
            while k + 1 < len(nums) + 1 and k + 1 <= len(nums):
                q1 = (2 * cur[0] - prev_q1[0], 2 * cur[1] - prev_q1[1]) if prev_q1 else cur
                x, y = nums[k], nums[k + 1]
                if rel:
                    x += cur[0]; y += cur[1]
                _flatten_quad(cur, q1, (x, y), poly)
                prev_q1 = q1; cur = (x, y); k += 2
            prev_c2 = None
        elif cmd == "A":
            # Approximate arc endpoints with a straight line (good enough for icons).
            while k + 6 < len(nums) + 1 and k + 6 <= len(nums):
                x, y = nums[k + 5], nums[k + 6]
                if rel:
                    x += cur[0]; y += cur[1]
                poly.append((x, y)); cur = (x, y); k += 7
            prev_c2 = prev_q1 = None
        elif cmd == "Z":
            if poly:
                poly.append(start)
                subpaths.append(poly)
                poly = []
            cur = start
            prev_c2 = prev_q1 = None
    if poly:
        subpaths.append(poly)
    return subpaths


def _viewbox(svg):
    m = re.search(r'viewBox\s*=\s*"([^"]+)"', svg)
    if m:
        vals = [float(x) for x in _NUM.findall(m.group(1))]
        if len(vals) == 4:
            return vals
    return None


def _winding(px, py, subpaths):
    """Nonzero winding number of point (px, py) over all subpaths."""
    wn = 0
    for poly in subpaths:
        for a in range(len(poly) - 1):
            x0, y0 = poly[a]
            x1, y1 = poly[a + 1]
            if y0 <= py:
                if y1 > py:
                    if (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0) > 0:
                        wn += 1
            else:
                if y1 <= py:
                    if (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0) < 0:
                        wn -= 1
    return wn


def load_sprite(path, height=44, ss=2):
    """Rasterize an SVG file to a coverage sprite.

    Returns {"w", "h", "alpha" (list of 0..1, row-major, y down), "aspect"}.
    """
    svg = Path(path).read_text()
    d_parts = re.findall(r'<path[^>]*\sd="([^"]+)"', svg)
    subpaths = []
    for d in d_parts:
        subpaths.extend(_parse_paths(d))

    vb = _viewbox(svg)
    if vb:
        minx, miny, vw, vh = vb
    else:
        xs = [p[0] for poly in subpaths for p in poly]
        ys = [p[1] for poly in subpaths for p in poly]
        minx, miny = min(xs), min(ys)
        vw, vh = max(xs) - minx, max(ys) - miny
    aspect = vw / vh if vh else 1.0
    H = height
    W = max(1, round(H * aspect))

    alpha = [0.0] * (W * H)
    for py in range(H):
        for px in range(W):
            cov = 0
            for sy in range(ss):
                for sx in range(ss):
                    # sample point in viewBox coords (y down matches image row order)
                    u = (px + (sx + 0.5) / ss) / W
                    v = (py + (sy + 0.5) / ss) / H
                    gx = minx + u * vw
                    gy = miny + v * vh
                    if _winding(gx, gy, subpaths) != 0:
                        cov += 1
            alpha[py * W + px] = cov / (ss * ss)
    return {"w": W, "h": H, "alpha": alpha, "aspect": aspect}
