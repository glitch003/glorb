#!/usr/bin/env python3
"""Generate power-map.svg — how the broom LED 24 V power is connected.

Battery bank -> breaker/shunt -> split into two 4 AWG legs up the riser ->
each leg feeds a set of per-2x4 +/- bus-bar pairs -> tube V/G drops. Receivers
are powered separately (12 V buck off the 24 V bus); data is separate entirely
(controllers.md). See led-wiring.md + bus-bar-map.md.

Edit LEG1/LEG2 and re-run.
"""

from pathlib import Path

HERE = Path(__file__).parent

# board -> tube count
TUBES = {"A1": 14, "A2": 14, "B1": 14, "B2": 14, "C1": 12, "C2": 12,
         "D1": 14, "D2": 14, "E1": 14, "E2": 14, "F1": 12}
LEG1 = {"name": "LEG 1", "join": "B1", "boards": ["A1", "A2", "B1", "B2", "C1"],
        "amps": "~85 A typ"}
LEG2 = {"name": "LEG 2", "join": "D2",
        "boards": ["C2", "D1", "D2", "E1", "E2", "F1"], "amps": "~100 A typ"}

W = 1040
BG, FG, MUTED = "#0d1b2a", "#e8eef5", "#9db3c8"
POS, NEG = "#e63946", "#4f93c4"          # +24V red, GND blue
BANK, BUCK = "#e9c46a", "#2a9d8f"        # bank gold, receiver-power teal
BOARD_FILL, BOARD_STK = "#22303f", "#3d5266"


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg():
    e = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {{H}}" '
         f'font-family="DejaVu Sans, Arial, sans-serif">']
    e.append(f'<rect width="{W}" height="{{H}}" fill="{BG}"/>')
    e.append(f'<defs><marker id="ar" markerWidth="9" markerHeight="9" refX="6" '
             f'refY="4.5" orient="auto"><path d="M1,1 L7,4.5 L1,8 Z" '
             f'fill="{MUTED}"/></marker></defs>')
    e.append(f'<text x="{W/2}" y="30" fill="{FG}" font-size="22" '
             f'font-weight="bold" text-anchor="middle">Glorb broom — 24 V power '
             f'connection</text>')
    e.append(f'<text x="{W/2}" y="52" fill="{MUTED}" font-size="13" '
             f'text-anchor="middle">Battery → breaker → two 4 AWG legs up the '
             f'riser → per-2×4 bus-bar pairs → tube V/G. Data is separate '
             f'(controllers.md).</text>')

    cx = W / 2
    # bank
    e.append(_box(cx - 200, 70, 400, 50, BANK, "#0d1b2a",
                  [("24 V LED bank — 6× Tesla S (6s6p ~24 V, ~31.8 kWh)",
                    "#0d1b2a", 13, True)]))
    e.append(_arrow(cx, 120, cx, 150))
    # breaker + shunt
    e.append(_box(cx - 200, 150, 400, 46, "#2b3546", FG,
                  [("250 A DC breaker + manual disconnect  ·  shunt / ammeter",
                    FG, 13, True)]))
    e.append(_arrow(cx, 196, cx, 224))
    e.append(f'<text x="{cx}" y="218" fill="{MUTED}" font-size="11" '
             f'text-anchor="middle">both legs (4 AWG +/−) up the riser, then '
             f'split at the ceiling</text>')

    # split to two legs
    lx, rx = 270, 770
    e.append(f'<path d="M{cx},224 L{cx},240 L{lx},240 L{lx},262" '
             f'stroke="{MUTED}" stroke-width="2" fill="none" '
             f'marker-end="url(#ar)"/>')
    e.append(f'<path d="M{cx},240 L{rx},240 L{rx},262" stroke="{MUTED}" '
             f'stroke-width="2" fill="none" marker-end="url(#ar)"/>')

    board_top = 340
    step = 52
    bottom = board_top
    for leg, colx in ((LEG1, lx), (LEG2, rx)):
        # leg header
        e.append(_box(colx - 165, 264, 330, 44, "#1b2430", FG,
                      [(f"{leg['name']} — joins at {leg['join']}", FG, 14, True),
                       (f"{sum(TUBES[b] for b in leg['boards'])} tubes  ·  "
                        f"{leg['amps']}", MUTED, 11, False)]))
        # +/- trunk spine down the column
        sx_pos, sx_neg = colx - 150, colx + 150
        n = len(leg["boards"])
        spine_bot = board_top + (n - 1) * step + 20
        e.append(f'<line x1="{sx_pos}" y1="308" x2="{sx_pos}" y2="{spine_bot}" '
                 f'stroke="{POS}" stroke-width="3"/>')
        e.append(f'<line x1="{sx_neg}" y1="308" x2="{sx_neg}" y2="{spine_bot}" '
                 f'stroke="{NEG}" stroke-width="3"/>')
        e.append(f'<text x="{sx_pos-6}" y="326" fill="{POS}" font-size="11" '
                 f'text-anchor="end">+24V</text>')
        e.append(f'<text x="{sx_neg+6}" y="326" fill="{NEG}" font-size="11">GND'
                 f'</text>')
        for i, b in enumerate(leg["boards"]):
            by = board_top + i * step
            # taps from both spines into the board box
            e.append(f'<line x1="{sx_pos}" y1="{by+20}" x2="{colx-120}" '
                     f'y2="{by+20}" stroke="{POS}" stroke-width="2"/>')
            e.append(f'<line x1="{sx_neg}" y1="{by+20}" x2="{colx+120}" '
                     f'y2="{by+20}" stroke="{NEG}" stroke-width="2"/>')
            e.append(_box(colx - 120, by, 240, 40, BOARD_FILL, BOARD_STK,
                          [(f"{b}  +/− bus bar", FG, 13, True),
                           (f"→ {TUBES[b]} tubes (V+/G)", MUTED, 11, False)],
                          stroke_w=1.5))
            bottom = max(bottom, by + 40)

    # receiver-power branch (off the 24 V, before the tube legs)
    ry = bottom + 34
    e.append(_box(cx - 230, ry, 460, 46, "#16302c", BUCK,
                  [("Receivers: 24 V → 12 V buck ×11 → SRx4 (DATA only)",
                    BUCK, 13, True),
                   ("never 24 V to a receiver · grounds bonded to the − bus",
                    MUTED, 11, False)]))
    e.append(f'<line x1="{cx}" y1="196" x2="{cx-320}" y2="196" stroke="{BANK}" '
             f'stroke-width="2" stroke-dasharray="4 4"/>')
    e.append(f'<path d="M{cx-320},196 L{cx-320},{ry} L{cx-230},{ry+23}" '
             f'stroke="{BANK}" stroke-width="2" stroke-dasharray="4 4" '
             f'fill="none" marker-end="url(#ar)"/>')

    gy = ry + 74
    e.append(f'<text x="{cx}" y="{gy}" fill="{FG}" font-size="13" '
             f'font-weight="bold" text-anchor="middle">Common ground: every − '
             f'bus, all SRx4 / K128D grounds, and battery − tied together.'
             f'</text>')

    # legend
    ly = gy + 30
    items = [(POS, "+24 V (4 AWG leg → bus bar → tubes)"),
             (NEG, "GND / − bus (also the data return ref)"),
             (BANK, "24 V bank / buck feed"),
             (BUCK, "receiver power (data-only to tubes)")]
    for idx, (col, label) in enumerate(items):
        x = 70 + (idx % 2) * 500
        y = ly + (idx // 2) * 26
        e.append(f'<rect x="{x}" y="{y-11}" width="16" height="16" rx="3" '
                 f'fill="{col}"/>')
        e.append(f'<text x="{x+22}" y="{y+1}" fill="{FG}" font-size="12">'
                 f'{esc(label)}</text>')

    H = ly + 60
    e.append("</svg>")
    out = "\n".join(e).replace("{H}", str(H))
    return out


def _box(x, y, w, h, fill, stroke, lines, stroke_w=0):
    s = [f'<rect x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{h:.0f}" '
         f'rx="8" fill="{fill}"' +
         (f' stroke="{stroke}" stroke-width="{stroke_w}"' if stroke_w else '') +
         '/>']
    cx = x + w / 2
    n = len(lines)
    for i, (txt, col, size, bold) in enumerate(lines):
        ty = y + h / 2 + (i - (n - 1) / 2) * (size + 3) + size / 3
        b = ' font-weight="bold"' if bold else ''
        s.append(f'<text x="{cx:.0f}" y="{ty:.0f}" fill="{col}" '
                 f'font-size="{size}"{b} text-anchor="middle">{esc(txt)}</text>')
    return "\n".join(s)


def _arrow(x1, y1, x2, y2):
    return (f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
            f'stroke="{MUTED}" stroke-width="2" marker-end="url(#ar)"/>')


def main():
    (HERE / "power-map.svg").write_text(build_svg())
    print("wrote power-map.svg")


if __name__ == "__main__":
    main()
