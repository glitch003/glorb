#!/usr/bin/env python3
"""Source of truth for the per-2×4 power bus-bar map (side & back variants).

Each 2×4 hanger board = one section = one +/- bus-bar pair. Every free-hanging
tube feeds V (+) and G (−) off its female pigtail (22 AWG) to the bus bars;
data goes separately to the SRx4 receiver (controllers.md). Landing scheme:
  - 3-pin WAGO : 2 tubes' 22 AWG -> 1x 16 AWG jumper -> bus terminal
  - 2-pin WAGO : 1 tube's 22 AWG -> 1x 16 AWG jumper -> bus terminal
  - direct     : 1 tube's 22 AWG crimped to a #8 spade -> bus terminal
Placement: direct spades are the SHORTEST runs, centered; 3-pin WAGO pairs at
each end; the 2-pin WAGO (side board only) sits next to the middle.

Side boards carry 14 tubes (→ 10 terminals), back boards 12 (→ 8 terminals).
The + bus takes the V wires, the − bus the G wires — identical scheme on both.

Run to regenerate next to this file:
  - bus-bar-map.svg        side board (14 tubes)
  - bus-bar-map-back.svg   back board (12 tubes)
  - bus-bar-map.md         human doc + per-terminal tables for both
"""

from pathlib import Path

HERE = Path(__file__).parent

# list order = physical layout along the rail = bus terminal order (1..N)
SECTIONS = [
    {
        "key": "side", "tubes": 14, "svg": "bus-bar-map.svg",
        "title": "one 14-tube SIDE board (2×4)",
        "scheme": [
            ("wago3", [1, 2]), ("wago3", [3, 4]),
            ("wago2", [5]),
            ("spade", [6]), ("spade", [7]), ("spade", [8]),
            ("spade", [9]), ("spade", [10]),
            ("wago3", [11, 12]), ("wago3", [13, 14]),
        ],
    },
    {
        "key": "back", "tubes": 12, "svg": "bus-bar-map-back.svg",
        "title": "one 12-tube BACK board (2×4)",
        "scheme": [
            ("wago3", [1, 2]), ("wago3", [3, 4]),
            ("spade", [5]), ("spade", [6]), ("spade", [7]), ("spade", [8]),
            ("wago3", [9, 10]), ("wago3", [11, 12]),
        ],
    },
]
LABELS = {"wago3": "3-pin WAGO", "wago2": "2-pin WAGO", "spade": "#8 spade"}

# ---- geometry / colors -----------------------------------------------------
W, H = 1000, 640
MX = 70
BW = 50
Y_TITLE = 30
Y_PBUS, BUS_H = 66, 16
Y_PCONN, CONN_H = 116, 42
Y_TUBE, TUBE_H = 240, 110
Y_NCONN = 402
Y_NBUS = 478
Y_LEG = 560

BG, FG, MUTED = "#0d1b2a", "#e8eef5", "#9db3c8"
POS, NEG = "#e63946", "#4f93c4"
C = {"wago3": "#f4a261", "wago2": "#e9c46a", "spade": "#2a9d8f"}
TUBE_FILL, TUBE_STK = "#22303f", "#3d5266"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def counts(scheme):
    n3 = sum(1 for k, _ in scheme if k == "wago3")
    n2 = sum(1 for k, _ in scheme if k == "wago2")
    ns = sum(1 for k, _ in scheme if k == "spade")
    return n3, n2, ns


# ---- svg -------------------------------------------------------------------
def svg(tubes, scheme, title):
    step = (W - 2 * MX) / (tubes - 1)

    def tx(t):
        return MX + (t - 1) * step

    def cx(members):
        return sum(tx(m) for m in members) / len(members)

    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" '
         f'font-family="DejaVu Sans, Arial, sans-serif">']
    e.append(f'<rect width="{W}" height="{H}" fill="{BG}"/>')
    e.append(f'<text x="{W/2}" y="{Y_TITLE}" fill="{FG}" font-size="22" '
             f'font-weight="bold" text-anchor="middle">Glorb broom — power '
             f'bus-bar map ({esc(title)})</text>')
    e.append(f'<text x="{W/2}" y="{Y_TITLE+22}" fill="{MUTED}" font-size="13" '
             f'text-anchor="middle">V (+) &amp; G (−) off each female pigtail '
             f'(22 AWG), run under the 2×4 between tubes · direct spades '
             f'centered (shortest) · a WAGO pair at each end.</text>')

    # bus bars (labels outside so terminal ① doesn't collide)
    e.append(f'<rect x="40" y="{Y_PBUS}" width="{W-80}" height="{BUS_H}" '
             f'rx="4" fill="{POS}"/>')
    e.append(f'<text x="44" y="{Y_PBUS-5}" fill="{POS}" font-size="12" '
             f'font-weight="bold">+ (V) BUS BAR</text>')
    e.append(f'<rect x="40" y="{Y_NBUS}" width="{W-80}" height="{BUS_H}" '
             f'rx="4" fill="{NEG}"/>')
    e.append(f'<text x="44" y="{Y_NBUS+BUS_H+15}" fill="{NEG}" font-size="12" '
             f'font-weight="bold">− (GND) BUS BAR</text>')

    # tubes
    for t in range(1, tubes + 1):
        x = tx(t)
        e.append(f'<rect x="{x-13:.1f}" y="{Y_TUBE}" width="26" '
                 f'height="{TUBE_H}" rx="8" fill="{TUBE_FILL}" '
                 f'stroke="{TUBE_STK}" stroke-width="1.5"/>')
        e.append(f'<text x="{x:.1f}" y="{Y_TUBE+TUBE_H/2+4:.1f}" fill="{FG}" '
                 f'font-size="12" text-anchor="middle" '
                 f'transform="rotate(-90 {x:.1f} {Y_TUBE+TUBE_H/2:.1f})">'
                 f'T{t}</text>')

    def draw_side(term_no, kind, members, top):
        x = cx(members)
        if top:
            bus_y = Y_PBUS + BUS_H
            conn_y, conn_b = Y_PCONN, Y_PCONN + CONN_H
            tube_edge = Y_TUBE
            term_y = Y_PBUS + BUS_H / 2
        else:
            bus_y = Y_NBUS
            conn_b, conn_y = Y_NCONN, Y_NCONN + CONN_H
            tube_edge = Y_TUBE + TUBE_H
            term_y = Y_NBUS + BUS_H / 2
        col = C[kind]
        e.append(f'<circle cx="{x:.1f}" cy="{term_y:.1f}" r="6" fill="#fff" '
                 f'stroke="#0d1b2a" stroke-width="1.5"/>')
        e.append(f'<text x="{x:.1f}" y="{term_y+3.5:.1f}" fill="#0d1b2a" '
                 f'font-size="9" font-weight="bold" text-anchor="middle">'
                 f'{term_no}</text>')
        if kind == "spade":
            e.append(f'<line x1="{x:.1f}" y1="{tube_edge}" x2="{x:.1f}" '
                     f'y2="{bus_y:.1f}" stroke="{col}" stroke-width="2"/>')
            my = (tube_edge + bus_y) / 2
            e.append(f'<rect x="{x-6:.1f}" y="{my-6:.1f}" width="12" '
                     f'height="12" fill="{col}"/>')
        else:
            e.append(f'<line x1="{x:.1f}" y1="{conn_y:.1f}" x2="{x:.1f}" '
                     f'y2="{bus_y:.1f}" stroke="{col}" stroke-width="2.5"/>')
            e.append(f'<rect x="{x-BW/2:.1f}" y="{min(conn_y,conn_b):.1f}" '
                     f'width="{BW}" height="{CONN_H}" rx="4" fill="{col}"/>')
            e.append(f'<text x="{x:.1f}" y="{(conn_y+conn_b)/2-2:.1f}" '
                     f'fill="#0d1b2a" font-size="9" font-weight="bold" '
                     f'text-anchor="middle">'
                     f'{"3-pin" if kind=="wago3" else "2-pin"}</text>')
            e.append(f'<text x="{x:.1f}" y="{(conn_y+conn_b)/2+9:.1f}" '
                     f'fill="#0d1b2a" font-size="9" text-anchor="middle">'
                     f'WAGO</text>')
            for m in members:
                e.append(f'<line x1="{tx(m):.1f}" y1="{tube_edge}" '
                         f'x2="{x:.1f}" y2="{conn_b:.1f}" stroke="{col}" '
                         f'stroke-width="2"/>')

    for i, (kind, members) in enumerate(scheme, start=1):
        draw_side(i, kind, members, top=True)
        draw_side(i, kind, members, top=False)

    # gauge callouts (representative)
    e.append(f'<text x="{cx(scheme[0][1])+30:.1f}" '
             f'y="{(Y_PBUS+BUS_H+Y_PCONN)/2:.1f}" fill="{MUTED}" '
             f'font-size="10">16 AWG</text>')
    e.append(f'<text x="{tx(1)-2:.1f}" y="{Y_TUBE-6:.1f}" fill="{MUTED}" '
             f'font-size="10" text-anchor="end">22 AWG</text>')

    # legend (dynamic; 2 per row)
    n3, n2, ns = counts(scheme)
    nterm = len(scheme)
    items = [(POS, f"+ / − bus bar ({nterm} terminals each)"),
             (C["wago3"], f"3-pin WAGO = 2 tubes → 1 terminal  (×{n3})")]
    if n2:
        items.append((C["wago2"], f"2-pin WAGO = 1 tube → 1 terminal  (×{n2})"))
    items.append((C["spade"], f"#8 spade = 1 tube direct → terminal  (×{ns})"))
    for idx, (col, label) in enumerate(items):
        lx = 60 + (idx % 2) * 470
        ly = Y_LEG + (idx // 2) * 26
        e.append(f'<rect x="{lx}" y="{ly-11}" width="16" height="16" '
                 f'rx="3" fill="{col}"/>')
        e.append(f'<text x="{lx+22}" y="{ly+1}" fill="{FG}" font-size="12">'
                 f'{esc(label)}</text>')
    foot_y = Y_LEG + (len(items) + 1) // 2 * 26 + 8
    e.append(f'<text x="60" y="{foot_y}" fill="{MUTED}" font-size="12">'
             f'{tubes} tubes × (V + G) → two {nterm}-terminal bus bars. '
             f'One board = one 2×4 · side boards 14 tubes · back boards 12.'
             f'</text>')
    e.append("</svg>")
    return "\n".join(e)


# ---- markdown --------------------------------------------------------------
def md():
    L = []
    L.append("# Power bus-bar map — per 2×4 board")
    L.append("")
    L.append("> **Generated by [bus_bar_map.py](bus_bar_map.py) — do not "
             "hand-edit.** Change `SECTIONS` and re-run.")
    L.append("")
    L.append("Each **2×4 hanger board = one section = one +/− bus-bar pair** "
             "(one SRx4 receiver per board too — see "
             "[../lights/controllers.md](../lights/controllers.md)). Every "
             "free-hanging tube feeds **V (+)** and **G (−)** off its female "
             "pigtail (22 AWG) to the bus bars; **data goes separately** to "
             "the receiver. **Side boards carry 14 tubes, back boards 12.** "
             "The + bus takes the V wires, the − bus the G wires — identical "
             "scheme on both.")
    L.append("")

    for s in SECTIONS:
        scheme, tubes = s["scheme"], s["tubes"]
        n3, n2, ns = counts(scheme)
        nterm = len(scheme)
        L.append(f"## {s['title'].capitalize()}")
        L.append("")
        L.append(f"![Bus-bar map]({s['svg']})")
        L.append("")
        L.append("| Terminal | Connector | Tubes | Into connector | To bus |")
        L.append("| ---: | --- | --- | --- | --- |")
        for i, (kind, members) in enumerate(scheme, start=1):
            tt = ", ".join(f"T{m}" for m in members)
            if kind == "wago3":
                win, tobus = "2× 22 AWG", "16 AWG jumper"
            elif kind == "wago2":
                win, tobus = "1× 22 AWG", "16 AWG jumper"
            else:
                win, tobus = "1× 22 AWG", "#8 spade crimp (22–16 AWG)"
            L.append(f"| **{i}** | {LABELS[kind]} | {tt} | {win} | {tobus} |")
        L.append("")
        parts = [f"{n3}× 3-pin WAGO"]
        if n2:
            parts.append(f"{n2}× 2-pin WAGO")
        parts.append(f"{ns}× direct spade")
        L.append(f"**Per bus bar:** {' + '.join(parts)} = **{nterm} "
                 f"terminals**, serving **{tubes} tubes**. BOM per board "
                 f"(×2 for + and −): {n3*2}× 3-pin WAGO, "
                 + (f"{n2*2}× 2-pin WAGO, " if n2 else "")
                 + f"{ns*2}× #8 spade, {(n3+n2)*2}× 16 AWG jumpers, "
                 f"2× ≥{tubes//2*10}-A bus bar.")
        L.append("")

    L.append("## Layout rule (both boards)")
    L.append("")
    L.append("Wires run **under the 2×4, between the tubes**; terminal order "
             "matches the rail: **direct #8-spade tubes centered** (shortest "
             "runs), **3-pin WAGO pairs at each end**, and — on the 14-tube "
             "side board only — the **2-pin WAGO between the left WAGOs and "
             "the spades**.")
    L.append("")
    L.append("## Notes")
    L.append("")
    L.append("- **Build order:** strip V & G on each female pigtail → pair "
             "tubes into WAGOs / crimp spades → land all terminals on each "
             "bus.")
    L.append("- Data is **separate**: each tube's data wire splices to a "
             "20 AWG extension (marine butt connector) back to the SRx4 "
             "receiver — see [../lights/controllers.md](../lights/controllers.md) "
             "and [led-wiring.md](led-wiring.md).")
    L.append("- **11 boards for the car:** 8 side boards × 14 tubes = 112 "
             "+ 3 back-style boards × 12 = 36 → **148 tubes** (zones A, B, D, E "
             "are 2 side boards each; C is 2 back boards; **F is 1 back-left "
             "board**, added 2026-08).")
    L.append("")
    return "\n".join(L)


def main():
    for s in SECTIONS:
        (HERE / s["svg"]).write_text(svg(s["tubes"], s["scheme"], s["title"]))
    (HERE / "bus-bar-map.md").write_text(md())
    print("wrote " + ", ".join(s["svg"] for s in SECTIONS) + ", bus-bar-map.md")


if __name__ == "__main__":
    main()
