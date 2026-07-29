#!/usr/bin/env python3
"""Source of truth for the broom LED tube -> group -> Angio/line -> universe map.

Run this to (re)generate three artifacts next to it:
  - tube-map.json  machine-readable map (consumed by the control software)
  - tube-map.md    human doc + install/test checklist
  - tube-map.png   physical layout diagram

Change the knobs at the top and re-run; everything downstream stays in sync.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---- knobs -----------------------------------------------------------------
TUBES_PER_GROUP = 4          # a group = 4 tubes labeled/powered together
PIX_PER_TUBE = 40            # 16 px/m * 2.5 m
CHAN_PER_PIX = 3             # RGB
# WLED's E1.31 "Multi" mode packs 170 px (510 ch) per universe, addressed
# sequentially across the whole board's pixel space from its start universe.
PX_PER_UNIVERSE = 170
HERE = Path(__file__).parent

# Physical walk of the open-front U, front-left -> back -> front-right.
# Each Angio covers a contiguous run and drives its groups on a few chained
# data lines. (name, physical label, prefix, first, last, groups per line)
ANGIOS = [
    ("A1", "Left-Front",  "L",  1, 28, (4, 3)),
    ("A2", "Left-Back",   "L", 29, 56, (4, 3)),
    ("A3", "Back",        "B",  1, 24, (3, 3)),
    ("A4", "Right-Back",  "R",  1, 28, (4, 3)),
    ("A5", "Right-Front", "R", 29, 56, (4, 3)),
]

ANGIO_COLORS = {
    "A1": "#E63946", "A2": "#F4A261", "A3": "#2A9D8F",
    "A4": "#457B9D", "A5": "#9D4EDD",
}

# Known controller IPs (DHCP reservations on the glorb router).
ANGIO_IPS = {"A3": "192.168.8.229"}

# Data enters each group at its first tube; +24V power is injected every
# 2 tubes (tube 1 and tube 3 of each group of 4).
POWER_EVERY = 2


# ---- build the map ---------------------------------------------------------
def build():
    groups = []
    angios = []
    gnum = 0
    ustart = 1
    for aname, aloc, prefix, first, last, line_sizes in ANGIOS:
        tubes = list(range(first, last + 1))
        agroups = [tubes[i:i + TUBES_PER_GROUP]
                   for i in range(0, len(tubes), TUBES_PER_GROUP)]
        assert sum(line_sizes) == len(agroups), f"{aname}: line sizes != groups"

        apx = len(tubes) * PIX_PER_TUBE
        lines = []
        px_off = 0
        gi = 0
        prev_group = None
        for lnum, nline in enumerate(line_sizes, start=1):
            line_groups = []
            for pos in range(1, nline + 1):
                gnum += 1
                chunk = agroups[gi]
                gi += 1
                labels = [f"{prefix}{n:02d}" for n in chunk]
                px = len(chunk) * PIX_PER_TUBE
                u0 = ustart + px_off // PX_PER_UNIVERSE
                u1 = ustart + (px_off + px - 1) // PX_PER_UNIVERSE
                groups.append({
                    "group": gnum,
                    "angio": aname,
                    "angio_location": aloc,
                    "line": lnum,
                    "line_pos": pos,
                    "tubes": labels,
                    "tube_count": len(chunk),
                    "pixels": px,
                    "channels": px * CHAN_PER_PIX,
                    "px_offset": px_off,
                    "universes": list(range(u0, u1 + 1)),
                    "data_in": labels[0],
                    "data_from": (f"{aname} line {lnum}" if pos == 1
                                  else f"G{prev_group} DOUT"),
                    "power_in": labels[::POWER_EVERY],
                })
                line_groups.append(gnum)
                prev_group = gnum
                px_off += px
            lines.append({
                "line": lnum,
                "groups": line_groups,
                "tube_count": nline * TUBES_PER_GROUP,
                "pixels": nline * TUBES_PER_GROUP * PIX_PER_TUBE,
                "start_px": px_off - nline * TUBES_PER_GROUP * PIX_PER_TUBE,
            })
            prev_group = None
        n_univ = -(-apx // PX_PER_UNIVERSE)   # ceil
        angios.append({
            "name": aname, "location": aloc,
            "groups": [g["group"] for g in groups if g["angio"] == aname],
            "lines": lines,
            "ports_used": len(lines),
            "tube_count": len(tubes),
            "pixels": apx,
            "start_universe": ustart,
            "universes": n_univ,
            **({"ip": ANGIO_IPS[aname]} if aname in ANGIO_IPS else {}),
        })
        ustart += n_univ
    return {
        "meta": {
            "tubes_per_group": TUBES_PER_GROUP,
            "pixels_per_tube": PIX_PER_TUBE,
            "channels_per_pixel": CHAN_PER_PIX,
            "px_per_universe": PX_PER_UNIVERSE,
            "total_tubes": sum(g["tube_count"] for g in groups),
            "total_groups": len(groups),
            "chip": "SM16703",
            "protocol": "sACN / E1.31",
            "color_order": "RGB",
            "serpentine": True,
        },
        "angios": angios,
        "groups": groups,
    }


# ---- markdown doc + checklist ----------------------------------------------
def _uspan(us):
    return f"{us[0]}" if len(us) == 1 else f"{us[0]}–{us[-1]}"


def write_md(data):
    m = data["meta"]
    lines = []
    lines.append("# Broom LED tube map — groups, Angios, lines, universes")
    lines.append("")
    lines.append("> **Generated by [tube_map.py](tube_map.py) — do not hand-edit.** "
                 "Change the knobs in that script and re-run.")
    lines.append("")
    lines.append(f"**{m['total_tubes']} tubes** in **{m['total_groups']} groups** "
                 f"of {m['tubes_per_group']} across **5 Angio-8s**. Each Angio "
                 f"drives **2 data lines** of 3–4 chained groups "
                 f"(one line = one Angio port, up to 640 px).")
    lines.append("")
    lines.append(f"Chip **{m['chip']}**, color order **{m['color_order']}**, "
                 f"transport **{m['protocol']}** in WLED *Multi* mode: each "
                 f"Angio owns one pixel space (lines concatenated in order), "
                 f"packed {m['px_per_universe']} px/universe from its start "
                 f"universe. A group can span a universe boundary — address "
                 f"by pixel offset, not universe.")
    lines.append("")

    lines.append("## Angio placement (walking the open-front U)")
    lines.append("")
    lines.append("Tubes numbered around the U from **front-left → back → "
                 "front-right**: left `L01`(front)→`L56`(back), "
                 "back `B01`(left)→`B24`(right), "
                 "right `R01`(back)→`R56`(front).")
    lines.append("")
    lines.append("| Angio | Location | Tubes | Groups | Lines (ports) | "
                 "Start univ | Universes |")
    lines.append("| --- | --- | --- | --- | --- | ---: | --- |")
    for a in data["angios"]:
        gs = a["groups"]
        span = f"G{gs[0]}–G{gs[-1]}"
        ldesc = " · ".join(
            f"L{ln['line']}: G{ln['groups'][0]}–G{ln['groups'][-1]} "
            f"({ln['pixels']} px)" for ln in a["lines"])
        lines.append(f"| {a['name']} | {a['location']} | {a['tube_count']} | "
                     f"{span} | {ldesc} | {a['start_universe']} | "
                     f"{a['start_universe']}–"
                     f"{a['start_universe'] + a['universes'] - 1} |")
    lines.append("")

    lines.append("## Full group map")
    lines.append("")
    lines.append("Data enters each group at its **first tube** (the DIN head) — "
                 "from the Angio port for the first group of a line, from the "
                 "previous group's DOUT for chained groups. +24 V power is "
                 "injected **every 2 tubes** — tube 1 and tube 3 of each group.")
    lines.append("")
    lines.append("| Group | Angio | Line | Tubes | Px | Px offset | Universes | "
                 "Data from | Power in |")
    lines.append("| ---: | --- | --- | --- | ---: | ---: | --- | --- | --- |")
    for g in data["groups"]:
        tr = f"`{g['tubes'][0]}`–`{g['tubes'][-1]}`"
        pw = ", ".join(f"`{t}`" for t in g["power_in"])
        lines.append(f"| **G{g['group']}** | {g['angio']} | "
                     f"{g['line']}.{g['line_pos']} | {tr} | "
                     f"{g['pixels']} | {g['px_offset']} | "
                     f"{_uspan(g['universes'])} | {g['data_from']} → "
                     f"`{g['data_in']}` | {pw} |")
    lines.append("")

    lines.append("## Labeling scheme")
    lines.append("")
    lines.append("Label every tube at **both ends** with its tube ID and its group. "
                 "Example flag on a tube: `L05 / G2` = tube L05, group 2. "
                 "Within a group the data chain runs **serpentine**: the tube nearest "
                 "the data source is the DIN head; flip alternate tubes so DOUT→DIN "
                 "hops stay short, then reverse those strands in software. "
                 "Chained groups continue the same data line: the last tube's DOUT "
                 "feeds the next group's `data_in` tube.")
    lines.append("")
    lines.append("```")
    lines.append("Angio port ─[330–470Ω]─▶ G_a (4 tubes serpentine) ─DOUT─▶ "
                 "G_b ─▶ G_c [─▶ G_d]   (one line, 3–4 groups)")
    lines.append("```")
    lines.append("")

    lines.append("## WLED / Angio config (per board)")
    lines.append("")
    lines.append("LED outputs: **output 1 = line 1** (start 0), **output 2 = "
                 "line 2** (start = line 1 px). Total LED count = board pixels. "
                 "E1.31: DMX mode *Multi RGB*, start universe per the table "
                 "above, multicast on.")
    lines.append("")

    lines.append("## Install + test sequence")
    lines.append("")
    lines.append("Do it **one line at a time**. First hardware bring-up was G15 "
                 "on A3 (2026-07-24). A3's currently-wired output (GPIO 12) is "
                 "now **line 2 = G18–G20** — next test target.")
    lines.append("")
    lines.append("For each group: hang the 4 tubes → chain data (serpentine) "
                 "→ tap +24 V + shared GND → label both ends → ping me "
                 "to light it from software → confirm all 4 tubes + color order "
                 "→ check the box.")
    lines.append("")
    for a in data["angios"]:
        lines.append(f"### {a['name']} — {a['location']} "
                     f"({a['tube_count']} tubes, univ "
                     f"{a['start_universe']}–"
                     f"{a['start_universe'] + a['universes'] - 1})")
        for g in [g for g in data["groups"] if g["angio"] == a["name"]]:
            tr = f"{g['tubes'][0]}–{g['tubes'][-1]}"
            lines.append(f"- [ ] **G{g['group']}** · line {g['line']} "
                         f"pos {g['line_pos']} · tubes {tr} · "
                         f"univ {_uspan(g['universes'])}")
        lines.append("")

    lines.append("## Diagram")
    lines.append("")
    lines.append("![Tube layout](tube-map.png)")
    lines.append("")
    lines.append("## Related")
    lines.append("")
    lines.append("- [controllers.md](controllers.md) — data wiring, "
                 "shared-ground, serpentine reverse")
    lines.append("- [led-tubes.md](led-tubes.md) — SM16703 electricals "
                 "(16 px/m, 5 V data, RGB, series resistor)")
    lines.append("- [../electrical/led-wiring.md](../electrical/led-wiring.md) "
                 "— power injection (separate from data)")
    lines.append("- [tube-map.json](tube-map.json) — machine-readable map "
                 "for the control software")
    lines.append("")
    (HERE / "tube-map.md").write_text("\n".join(lines))


# ---- diagram ---------------------------------------------------------------
def _font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold
             else ["DejaVuSans.ttf", "Arial.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _cell(draw, x, y, w, h, color, g):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=color)
    f_big = _font(20, bold=True)
    f_sm = _font(13)
    f_xs = _font(12)
    trange = f"{g['tubes'][0]}–{g['tubes'][-1]}"
    draw.text((x + w / 2, y + 8), f"G{g['group']}", font=f_big, fill="white",
              anchor="mt")
    draw.text((x + w / 2, y + 34),
              f"{trange}  ·  L{g['line']}.{g['line_pos']}", font=f_sm,
              fill="white", anchor="mt")
    draw.text((x + w / 2, y + h - 34), f"data {g['data_from']}", font=f_xs,
              fill="#ffe08a", anchor="mt")
    draw.text((x + w / 2, y + h - 18),
              "pwr " + "+".join(g["power_in"]), font=f_xs,
              fill="#9bf0ff", anchor="mt")


def write_png(data):
    W = 1500
    cw, ch, gap = 150, 104, 10
    by = data["groups"]
    left = [g for g in by if g["angio"] in ("A1", "A2")]
    back = [g for g in by if g["angio"] == "A3"]
    right = [g for g in by if g["angio"] in ("A4", "A5")]

    top = 110
    col_rows = max(len(left), len(right))
    col_bottom = top + col_rows * (ch + gap)
    back_y = col_bottom + 20
    legend_y = back_y + ch + 44
    H = int(legend_y + 70)

    img = Image.new("RGB", (W, H), "#0d1b2a")
    d = ImageDraw.Draw(img)
    d.text((W / 2, 24), "Glorb broom — LED tube groups (open-front U)",
           font=_font(30, bold=True), fill="white", anchor="mt")
    d.text((W / 2, 62), "front-left OPEN (driver sightline)  ·  "
           "front is the TOP edge", font=_font(16), fill="#a9c0d6", anchor="mt")
    d.text((W / 2, 84), "bird's-eye view from ABOVE — standing BEHIND the car "
           "you see B01 on your LEFT  ·  L1.2 = line 1, 2nd group in chain",
           font=_font(16), fill="#ffe08a", anchor="mt")
    col_x_left = 120
    col_x_right = W - 120 - cw

    # left column: front (top) -> back (bottom)
    for i, g in enumerate(left):
        y = top + i * (ch + gap)
        _cell(d, col_x_left, y, cw, ch, ANGIO_COLORS[g["angio"]], g)

    # right column: front (top) -> back (bottom): reverse so back is at bottom
    for i, g in enumerate(reversed(right)):
        y = top + i * (ch + gap)
        _cell(d, col_x_right, y, cw, ch, ANGIO_COLORS[g["angio"]], g)

    # back row: left -> right, along the bottom
    n = len(back)
    total_w = n * cw + (n - 1) * gap
    start_x = (W - total_w) / 2
    for i, g in enumerate(back):
        x = start_x + i * (cw + gap)
        _cell(d, x, back_y, cw, ch, ANGIO_COLORS[g["angio"]], g)

    # side labels
    d.text((col_x_left + cw / 2, top - 26), "LEFT (L01→L56)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    d.text((col_x_right + cw / 2, top - 26), "RIGHT (R01→R56)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    d.text((W / 2, back_y + ch + 8), "BACK (B01→B24)",
           font=_font(16, bold=True), fill="white", anchor="mt")

    # legend
    ly = legend_y
    d.text((60, ly), "Angios:", font=_font(16, bold=True), fill="white")
    lx = 150
    for a in data["angios"]:
        c = ANGIO_COLORS[a["name"]]
        d.rounded_rectangle([lx, ly - 2, lx + 22, ly + 18], radius=4, fill=c)
        d.text((lx + 30, ly), f"{a['name']} {a['location']}",
               font=_font(15), fill="white")
        lx += 240

    img.save(HERE / "tube-map.png")


def main():
    data = build()
    (HERE / "tube-map.json").write_text(json.dumps(data, indent=2))
    write_md(data)
    write_png(data)
    print(f"{data['meta']['total_tubes']} tubes, "
          f"{data['meta']['total_groups']} groups, "
          f"{sum(a['universes'] for a in data['angios'])} universes written.")


if __name__ == "__main__":
    main()
