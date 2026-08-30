"""Generate the galloping-horse keyframe SVGs used by the `horses` pattern.

Four frames of a rotary gallop (gather -> hind stance -> extension -> front
stance), silhouette facing right (the direction sprites travel). Run this
script to regenerate frame0.svg..frame3.svg; the pattern rasterizes them at
startup with svg_sprite.load_sprite and crossfades between them.

All frames share one viewBox so the rasterized masks align pixel-for-pixel.
"""

import math
from pathlib import Path

VIEW_W, VIEW_H = 120.0, 78.0

# Body silhouette, facing right. y is down (SVG coords). Drawn as a proper
# horse: long boxy muzzle held near-horizontal, arched neck, deep chest,
# rounded rump.
# Traced from the classic pixel-art galloping-horse silhouette: head held
# high and near-horizontal on a steeply arched neck, slim horizontal body,
# long tail hanging in a curve behind.
BODY = [
    (22, 30), (30, 27), (44, 26), (58, 27), (66, 24),    # tail root -> withers
    (78, 14), (86, 8),                                    # neck rises steeply
    (90, 8), (100, 12), (103, 16),                        # forehead -> muzzle
    (101, 19), (92, 20), (88, 22),                        # lip -> jaw -> cheek
    (82, 26), (78, 32), (80, 40), (76, 46),               # throat -> chest
    (60, 48), (44, 46), (32, 44), (24, 38),               # belly -> rear
]
EAR = [(83, 9), (86, 3), (89, 8)]
MANE = [(64, 24), (70, 17), (76, 11), (82, 6), (86, 8),
        (80, 13), (73, 19), (67, 23)]
TAIL = [(24, 30), (16, 34), (10, 44), (9, 56), (13, 60), (14, 50),
        (18, 40), (25, 36)]

HIP = (34.0, 40.0)
SHOULDER = (74.0, 40.0)
L_UPPER, L_LOWER = 15.0, 14.0
W_UPPER = (8.0, 4.0)      # taper: at pivot -> at knee
W_LOWER = (4.0, 2.8)      # knee -> fetlock
HOOF_LEN, HOOF_W = 4.5, 4.5

# Per-frame leg angles in degrees from straight-down; positive = toward the
# head. Each leg is (upper, lower), both absolute. Order:
# hind_lead, hind_trail, front_lead, front_trail.
FRAMES = [
    # 0: gather / suspension -- hinds tucked forward, fronts folded back
    [(35, 60), (45, 75), (-25, -80), (-35, -95)],
    # 1: hind stance -- hinds under the body, fronts reaching out
    [(-5, 5), (10, 25), (30, 60), (15, 40)],
    # 2: full extension (the flying-gallop pose)
    [(-35, -45), (-45, -55), (40, 55), (28, 38)],
    # 3: front stance -- fronts planted, hinds swinging forward
    [(10, 30), (0, 15), (-5, 0), (-20, -35)],
]


def seg_quad(start, angle_deg, length, w_start, w_end):
    """A tapered quad for one limb segment; returns (polygon, end_point)."""
    a = math.radians(angle_deg)
    dx, dy = math.sin(a), math.cos(a)          # angle 0 points down
    nx, ny = -dy, dx                            # unit normal
    ex, ey = start[0] + dx * length, start[1] + dy * length
    poly = [
        (start[0] + nx * w_start / 2, start[1] + ny * w_start / 2),
        (ex + nx * w_end / 2, ey + ny * w_end / 2),
        (ex - nx * w_end / 2, ey - ny * w_end / 2),
        (start[0] - nx * w_start / 2, start[1] - ny * w_start / 2),
    ]
    return poly, (ex, ey)


def leg_polys(pivot, upper_deg, lower_deg):
    upper, knee = seg_quad(pivot, upper_deg, L_UPPER, *W_UPPER)
    lower, fetlock = seg_quad(knee, lower_deg, L_LOWER, *W_LOWER)
    hoof, _ = seg_quad(fetlock, lower_deg, HOOF_LEN, HOOF_W, HOOF_W * 0.8)
    return [upper, lower, hoof]


def path_d(poly):
    pts = " L ".join(f"{x:.2f},{y:.2f}" for x, y in poly)
    return f"M {pts} Z"


def frame_svg(legs):
    polys = [BODY, EAR, MANE, TAIL]
    hind_lead, hind_trail, front_lead, front_trail = legs
    # Far-side legs first so near-side silhouette overlaps them (union anyway,
    # but keeps the source readable).
    polys += leg_polys(HIP, *hind_trail)
    polys += leg_polys(SHOULDER, *front_trail)
    polys += leg_polys(HIP, *hind_lead)
    polys += leg_polys(SHOULDER, *front_lead)
    paths = "\n".join(f'  <path d="{path_d(p)}" fill="#fff"/>' for p in polys)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {VIEW_W:g} {VIEW_H:g}">\n{paths}\n</svg>\n')


def main():
    out = Path(__file__).resolve().parent
    for i, legs in enumerate(FRAMES):
        (out / f"frame{i}.svg").write_text(frame_svg(legs))
        print(f"wrote frame{i}.svg")


if __name__ == "__main__":
    main()
