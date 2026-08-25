#!/usr/bin/env python3
"""Source of truth for the broom LED tube -> board/receiver/output -> channel map.

Run this to (re)generate four artifacts next to it:
  - tube-map.json  machine-readable map (consumed by the control software)
  - tube-map.md    human doc + install/test checklist
  - tube-map.png   bird's-eye board layout diagram
  - tube-map.pdf   printable install sheets: the diagram + one page per zone
                   with each board's dial setting and output->tube hookup

Change the knobs at the top and re-run; everything downstream stays in sync.

Topology (as-built 2026-08): ONE Kulp K128D-B controller (BeagleBone + FPP).
The tubes hang from **2x4 boards** — two 2x4s per side zone, plus a single
12-tube front-right corner board (zone F) — and every 2x4
carries **one SRx4 v4.00 quad smart receiver** on its **own RJ45 port** (its
own cat5 run, nothing chained after it). Side 2x4s carry 14 tubes, back 2x4s
carry 12. Every tube gets its own data line from a receiver output.

One SRx4 = four chained receiver positions in one board (output groups
ID..ID+3, 16 outputs). Because each board is alone on its cable, **every
board's ID rotary is set to A** — and NEVER 0, which is dumb passthrough
mode and the cause of the great 2026-08 flicker. See k128/README.md.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---- knobs -----------------------------------------------------------------
PIX_PER_TUBE = 41            # measured 2026-08-21: probe with only pixel 39
                             # lit showed one more unlit pixel group below it
                             # on every tube — the strips are 41 groups, not
                             # the nominal 40 (16 px/m * 2.5 m)
CHAN_PER_PIX = 3             # RGB
OUTPUTS_PER_GROUP = 4        # pixel outputs per SRx4 chain position (group)
GROUPS_PER_BOARD = 4         # an SRx4 is 4 chain positions in one board
MAX_RECEIVERS_PER_PORT = 6   # FPP v2 SmartReceiver chain limit (MAX_SMART_RECEIVERS)
MAX_PX_PER_PORT = 800        # Kulp spec: 800 px/port @ 40 fps, shared by the port

# FPP bridge input (DDP preferred, E1.31 fallback). The whole car is ONE flat
# pixel space on one controller, so universes are contiguous from 1.
# 170 px = 510 ch/universe keeps universe boundaries on pixel boundaries.
PX_PER_UNIVERSE = 170
UNIVERSE_SIZE = PX_PER_UNIVERSE * CHAN_PER_PIX   # 510
START_UNIVERSE = 1
HERE = Path(__file__).parent

CONTROLLER = {
    "model": "Kulp K128D-B",
    "platform": "BeagleBone Black/Green + FPP (Falcon Player) 6.1+",
    "hostname": "glorb-k128.local",   # FPP HostName is still the default "FPP"
    "ip": "192.168.8.124",      # 2026-08-21; make this a DHCP reservation
    "rj45_ports_total": 32,
    "strings_total": 128,       # 32 RJ45 x 4 differential strings
}

# Physical walk of the open-front U, front-left -> back -> front-right.
# Zone names A-E are kept from the Angio build so the existing tube labels,
# 2x4 hangers and busbars all still mean the same thing.
#
# (name, location, label prefix, first, last, tubes per 2x4 board)
# Each entry in the last tuple = one 2x4 hanger board = one SRx4 quad
# receiver = one RJ45 port. The counts must sum to the zone's tube count and
# each board must fit on one SRx4 (<= 16 outputs).
ZONES = [
    ("A", "Left-Front",  "L",  1, 28, (14, 14)),
    ("B", "Left-Back",   "L", 29, 56, (14, 14)),
    ("C", "Back",        "B",  1, 24, (12, 12)),
    ("D", "Right-Back",  "R",  1, 28, (14, 14)),
    ("E", "Right-Front", "R", 29, 56, (14, 14)),
    ("F", "Front-Right", "F",  1, 12, (12,)),   # 12 NEW tubes, front-right corner (2026-08)
]

# RJ45 ports on the K128D, assigned in ZONES order (one per board). Ten of
# the 32 ports carry the whole car; the rest are spare. Renumber here if the
# physical patching differs.
FIRST_RJ45_PORT = 1

ZONE_COLORS = {
    "A": "#E63946", "B": "#F4A261", "C": "#2A9D8F",
    "D": "#457B9D", "E": "#9D4EDD", "F": "#E9C46A",
}

# FPP smart-receiver chain positions are labeled A-F in the UI and map to the
# virtualStrings / virtualStringsB..F keys in co-bbbStrings.json. On the
# SRx4 they are the four output groups ID..ID+3, so a board dialed to A owns
# groups A, B, C, D.
CHAIN_LETTERS = "ABCDEF"

# As-built physical swaps: the DATA map (labels/ports/channels) is unchanged;
# each pair only swaps where the two 2x4 boards are DRAWN in the layout diagram.
# Empty = every board is drawn in map order.
PHYSICAL_SWAP = []


# ---- build the map ---------------------------------------------------------
def build():
    tubes = []
    receivers = []
    boards = []
    zones = []
    rid = 0
    port = FIRST_RJ45_PORT

    for zname, zloc, prefix, first, last, board_spec in ZONES:
        numbers = list(range(first, last + 1))
        assert sum(board_spec) == len(numbers), (
            f"{zname}: boards carry {sum(board_spec)} tubes "
            f"!= the zone's {len(numbers)}")

        zone_boards = []
        zone_recv = []
        ti = 0
        for bi, n_on_board in enumerate(board_spec):
            n_groups = -(-n_on_board // OUTPUTS_PER_GROUP)   # ceil
            assert n_groups <= GROUPS_PER_BOARD, (
                f"{zname} board {bi + 1}: {n_on_board} tubes needs "
                f"{n_groups} groups, an SRx4 has {GROUPS_PER_BOARD}")
            assert n_groups <= MAX_RECEIVERS_PER_PORT
            px = n_on_board * PIX_PER_TUBE
            assert px <= MAX_PX_PER_PORT, (
                f"port {port}: {px} px exceeds the {MAX_PX_PER_PORT} px "
                f"per-port budget")

            # The K128D silkscreens each RJ45 with the STRING range it owns,
            # not a port number -- jack "1-4" is port 1, "17-20" is port 5.
            # Jacks run right-to-left, bottom-to-top in columns of four
            # (rightmost column = strings 1-16). Confirmed against the board
            # 2026-08-21, and it validates port_number() in k128/fpp_setup.py.
            first_string = (port - 1) * OUTPUTS_PER_GROUP + 1
            silkscreen = f"{first_string}-{first_string + OUTPUTS_PER_GROUP - 1}"
            board_id = f"{zname}{bi + 1}"
            board_recv = []
            board_tubes = []

            for gi in range(n_groups):
                rid += 1
                take = min(OUTPUTS_PER_GROUP,
                           n_on_board - gi * OUTPUTS_PER_GROUP)
                chunk = numbers[ti:ti + take]
                ti += len(chunk)
                labels = [f"{prefix}{n:02d}" for n in chunk]
                outputs = []
                for out_num, (num, label) in enumerate(zip(chunk, labels),
                                                       start=1):
                    idx = len(tubes)
                    px_off = idx * PIX_PER_TUBE
                    start_ch = px_off * CHAN_PER_PIX + 1
                    end_ch = start_ch + PIX_PER_TUBE * CHAN_PER_PIX - 1
                    u0 = START_UNIVERSE + px_off // PX_PER_UNIVERSE
                    u1 = START_UNIVERSE + (px_off + PIX_PER_TUBE - 1) \
                        // PX_PER_UNIVERSE
                    tubes.append({
                        "label": label,
                        "side": prefix,
                        "pos": num - 1,
                        "index": idx,
                        "zone": zname,
                        "board": board_id,
                        "receiver": rid,
                        "chain_pos": gi + 1,
                        "chain_letter": CHAIN_LETTERS[gi],
                        "port": port,
                        "port_silkscreen": silkscreen,
                        "output": out_num,
                        "pixels": PIX_PER_TUBE,
                        "px_offset": px_off,
                        "start_channel": start_ch,
                        "end_channel": end_ch,
                        "universes": list(range(u0, u1 + 1)),
                        # data enters every tube at the top, so no tube is
                        # ever reversed in software
                        "direction": "forward",
                    })
                    outputs.append({
                        "output": out_num, "tube": label,
                        "pixels": PIX_PER_TUBE,
                        "start_channel": start_ch, "end_channel": end_ch,
                    })
                receivers.append({
                    "id": rid,
                    "zone": zname,
                    "board": board_id,
                    "port": port,
                    "chain_pos": gi + 1,
                    "chain_letter": CHAIN_LETTERS[gi],
                    "tubes": labels,
                    "tube_count": len(labels),
                    "pixels": len(labels) * PIX_PER_TUBE,
                    "start_channel": outputs[0]["start_channel"],
                    "end_channel": outputs[-1]["end_channel"],
                    "outputs": outputs,
                })
                board_recv.append(rid)
                board_tubes.extend(labels)

            boards.append({
                "id": board_id,
                "zone": zname,
                "location": zloc,
                "port": port,
                "silkscreen": silkscreen,
                # one board per cable -> the first chain position is always A
                "rotary": CHAIN_LETTERS[0],
                "termination": "all 4 DIPs UP = Only/Last RCVR",
                "tubes": board_tubes,
                "tube_count": len(board_tubes),
                "pixels": px,
                "receivers": board_recv,
                "groups": n_groups,
                "differential_type": f"v2 smart x{n_groups}",
                "start_channel": (
                    receivers[board_recv[0] - 1]["start_channel"]),
                "end_channel": receivers[board_recv[-1] - 1]["end_channel"],
            })
            zone_boards.append(board_id)
            zone_recv.extend(board_recv)
            port += 1

        zones.append({
            "name": zname,
            "location": zloc,
            "tube_count": len(numbers),
            "boards": zone_boards,
            "receivers": zone_recv,
            "ports": [b["port"] for b in boards if b["zone"] == zname],
            "pixels": len(numbers) * PIX_PER_TUBE,
        })

    total_px = len(tubes) * PIX_PER_TUBE
    total_ch = total_px * CHAN_PER_PIX
    n_univ = -(-total_ch // UNIVERSE_SIZE)   # ceil

    controller = dict(CONTROLLER)
    controller.update({
        "rj45_ports_used": len(boards),
        "receivers": len(receivers),
        "start_universe": START_UNIVERSE,
        "universe_count": n_univ,
        "universe_size": UNIVERSE_SIZE,
        "universes": list(range(START_UNIVERSE, START_UNIVERSE + n_univ)),
        "start_channel": 1,
        "channel_count": total_ch,
    })

    return {
        "meta": {
            "tubes_per_receiver": OUTPUTS_PER_GROUP,
            "pixels_per_tube": PIX_PER_TUBE,
            "channels_per_pixel": CHAN_PER_PIX,
            "px_per_universe": PX_PER_UNIVERSE,
            "universe_size": UNIVERSE_SIZE,
            "total_tubes": len(tubes),
            "total_boards": len(boards),
            "total_receivers": len(receivers),
            "total_pixels": total_px,
            "total_channels": total_ch,
            "chip": "SM16703",
            "protocol": "DDP (E1.31 fallback)",
            # Measured on the real tubes 2026-08-21: sent red showed blue,
            # sent blue showed green -> the strips are wired BRG, despite
            # SM16703 datasheets claiming RGB. FPP reorders on output, so
            # everything upstream (patterns, preview, CLI) stays RGB.
            "color_order": "BRG",
            # every tube has its own data line: no chaining, so no
            # serpentine flip and nothing to reverse in software
            "serpentine": False,
        },
        "controller": controller,
        "zones": zones,
        "boards": boards,
        "receivers": receivers,
        "tubes": tubes,
    }


# ---- markdown doc + checklist ----------------------------------------------
def _uspan(us):
    return f"{us[0]}" if len(us) == 1 else f"{us[0]}–{us[-1]}"


def write_md(data):
    m = data["meta"]
    c = data["controller"]
    ch_per_tube = m["pixels_per_tube"] * m["channels_per_pixel"]
    L = []
    L.append("# Broom LED tube map — boards, receivers, outputs, channels")
    L.append("")
    L.append("> **Generated by [tube_map.py](tube_map.py) — do not hand-edit.** "
             "Change the knobs in that script and re-run.")
    L.append("")
    L.append(f"**{m['total_tubes']} tubes**, each on its **own data line**, "
             f"hung from **{m['total_boards']} 2×4 boards**. Every 2×4 "
             f"carries **one SRx4 v4.00 quad smart receiver** on its **own "
             f"RJ45 port** of one **{c['model']}** — side boards drive 14 "
             f"tubes, back boards 12. Nothing is chained after any board.")
    L.append("")
    L.append(f"Chip **{m['chip']}**, color order **{m['color_order']}**, "
             f"**{m['pixels_per_tube']} px/tube** → "
             f"**{m['total_pixels']:,} px / {m['total_channels']:,} channels**. "
             f"The whole car is one flat pixel space on one controller: "
             f"DDP (E1.31 fallback) into FPP's bridge, universes "
             f"**{c['universes'][0]}–{c['universes'][-1]}** of "
             f"{c['universe_size']} channels, starting at FPP channel 1.")
    L.append("")
    L.append(f"**No chaining, no serpentine.** Every tube takes data at its "
             f"**top** end from one receiver output, so every string is "
             f"*Forward* in FPP and nothing is reversed in software. A tube "
             f"is exactly {ch_per_tube} contiguous channels; tube *n* "
             f"(0-based) starts at channel `n × {ch_per_tube} + 1`.")
    L.append("")

    L.append("## The board map — hang each 2×4, set its dial")
    L.append("")
    L.append("**Every board's ID rotary dial goes to `A`.** Each board is "
             "alone on its cat5 run, so it is always the first (and only) "
             "receiver in its chain. Never leave a dial at `0` — that is "
             "dumb passthrough mode (the factory default, and the cause of "
             "the great 2026-08 flicker). The dial is read at **power-up**, "
             "so set it before powering, or power-cycle after changing it. "
             "Termination: **all 4 DIP switches UP** (\"Only/Last RCVR\") on "
             "every board.")
    L.append("")
    L.append("| Board (2×4) | Zone | Tubes | RJ45 port | Jack silkscreen | "
             "ID dial | DIPs | Groups used |")
    L.append("| :-: | --- | --- | ---: | :-: | :-: | :-: | --- |")
    for b in data["boards"]:
        groups = " ".join(
            f"{CHAIN_LETTERS[i]}:{data['receivers'][r - 1]['tube_count']}"
            for i, r in enumerate(b["receivers"]))
        L.append(f"| **{b['id']}** | {b['zone']} {b['location']} | "
                 f"`{b['tubes'][0]}`–`{b['tubes'][-1]}` | {b['port']} | "
                 f"`{b['silkscreen']}` | **{b['rotary']}** | all UP | "
                 f"{groups} |")
    L.append("")
    L.append("> **As-built (2026-08):** zone **F** (`F01–F12`, board F1, "
             "port 11) is the new **front-right corner** board. All other "
             "boards follow the map order.")
    L.append("")
    L.append("**Finding the right jack:** the K128D silkscreens each RJ45 "
             "with the *string range* it owns, not a port number — port 1 is "
             "the jack marked `1-4`, port 5 is `17-20`. Jacks run "
             "**right-to-left, bottom-to-top in columns of four**, so the "
             "rightmost column is strings 1–16. All ten ports we use are in "
             "the three rightmost columns.")
    L.append("")
    L.append(f"Per-port budget is {MAX_PX_PER_PORT} px at 40 fps — the "
             f"busiest board here runs "
             f"{max(b['pixels'] for b in data['boards'])} px, so there is "
             f"plenty of headroom.")
    L.append("")

    L.append("## Receiver groups (what FPP calls receivers)")
    L.append("")
    L.append("One SRx4 board = four chained receiver positions in one: "
             "output groups `A`–`D` of 4 outputs each (dialed to `A`). FPP "
             "sees each group as a chained smart receiver, so a 14-tube "
             "board is `v2 smart x4` with group D only half used, and a "
             "12-tube board is `v2 smart x3`.")
    L.append("")
    L.append("| Receiver | Board | Group | Outputs → tubes | Channels |")
    L.append("| ---: | :-: | :-: | --- | ---: |")
    for r in data["receivers"]:
        outs = " · ".join(f"{o['output']}→`{o['tube']}`" for o in r["outputs"])
        L.append(f"| **R{r['id']}** | {r['board']} | {r['chain_letter']} | "
                 f"{outs} | {r['start_channel']}–{r['end_channel']} |")
    L.append("")

    L.append("## Per-tube channel map")
    L.append("")
    L.append(f"What FPP needs per string: port, receiver group, output, "
             f"start channel, {m['pixels_per_tube']} px, Forward, "
             f"{m['color_order']}.")
    L.append("")
    L.append("| Tube | Board | Port | Recv | Out | Start ch | End ch | "
             "Universes |")
    L.append("| --- | :-: | ---: | ---: | :-: | ---: | ---: | --- |")
    for t in data["tubes"]:
        L.append(f"| `{t['label']}` | {t['board']} | {t['port']} | "
                 f"R{t['receiver']}{t['chain_letter']} | {t['output']} | "
                 f"{t['start_channel']} | {t['end_channel']} | "
                 f"{_uspan(t['universes'])} |")
    L.append("")

    L.append("## Labeling scheme")
    L.append("")
    L.append("Label every tube at **both ends** with its tube ID and its "
             "board + group + output. Example flag: `L05 / A1-B2` = tube "
             "L05, board A1, group B, output 2. Label the cat5 run at both "
             "ends with the board ID and the RJ45 jack silkscreen.")
    L.append("")
    L.append("```")
    L.append("K128D RJ45 port ──cat5──▶ [SRx4 board, dial=A, DIPs UP]  "
             "(one board per port, nothing chained)")
    L.append("     group A outs 1-4 ─[330–470Ω]─▶ DIN tubes 1-4  (top)")
    L.append("     group B outs 1-4 ─[330–470Ω]─▶ DIN tubes 5-8")
    L.append("     group C outs 1-4 ─[330–470Ω]─▶ DIN tubes 9-12")
    L.append("     group D outs 1-2 ─[330–470Ω]─▶ DIN tubes 13-14  "
             "(unused on 12-tube boards)")
    L.append("```")
    L.append("")

    L.append("## FPP config")
    L.append("")
    L.append("Run **[k128/fpp_setup.py](k128/fpp_setup.py)** to push this map "
             "into FPP — it writes the bridge input "
             f"(universes {c['universes'][0]}–{c['universes'][-1]} × "
             f"{c['universe_size']} ch) and the BBB Strings channel outputs "
             f"(one string per tube, {m['pixels_per_tube']} px, Forward, "
             f"{m['color_order']}), then restarts fppd:")
    L.append("")
    L.append("```bash")
    L.append("cd lights")
    L.append("python3 k128/fpp_setup.py --host glorb-k128.local --dry-run")
    L.append("python3 k128/fpp_setup.py --host glorb-k128.local")
    L.append("```")
    L.append("")
    L.append("Brightness: FPP's per-string brightness is a **hard ceiling** "
             "on what the tubes can draw, and `fpp_setup.py` defaults it to "
             "**5%** for bench work. glorbleds also has its own brightness and "
             "the two **multiply**, so pick one owner — see "
             "[k128/README.md](k128/README.md#brightness-who-owns-it).")
    L.append("")

    L.append("## Install + test sequence")
    L.append("")
    L.append("Do it **one 2×4 board at a time**. For each board: set the "
             "rotary to `A` and DIPs UP **before powering** → hang the 2×4 → "
             "run its cat5 to the right jack → land each tube's DIN on its "
             "output → label both ends → light it from software "
             "(`python3 -m glorbleds tubes R<n>` per group) → confirm every "
             "tube and the color order → check the box.")
    L.append("")
    for z in data["zones"]:
        L.append(f"### {z['name']} — {z['location']} ({z['tube_count']} tubes)")
        for b in [b for b in data["boards"] if b["zone"] == z["name"]]:
            rs = b["receivers"]
            L.append(f"- [ ] **{b['id']}** · port {b['port']} "
                     f"(jack `{b['silkscreen']}`) · dial `{b['rotary']}` · "
                     f"tubes `{b['tubes'][0]}`–`{b['tubes'][-1]}` · "
                     f"R{rs[0]}–R{rs[-1]} · ch "
                     f"{b['start_channel']}–{b['end_channel']}")
        L.append("")

    L.append("## Diagram")
    L.append("")
    L.append("![Tube layout](tube-map.png)")
    L.append("")
    L.append("**[tube-map.pdf](tube-map.pdf)** is the printable version: the "
             "diagram plus one page per zone with each board's dial setting "
             "and full output→tube hookup table.")
    L.append("")
    L.append("## Related")
    L.append("")
    L.append("- [k128/README.md](k128/README.md) — controller bring-up + the "
             "SRx4 dial/DIP traps")
    L.append("- [controllers.md](controllers.md) — data wiring, receivers, "
             "shared ground")
    L.append("- [led-tubes.md](led-tubes.md) — SM16703 electricals "
             "(16 px/m, 5 V data, series resistor)")
    L.append("- [../electrical/led-wiring.md](../electrical/led-wiring.md) "
             "— power injection (separate from data)")
    L.append("- [tube-map.json](tube-map.json) — machine-readable map "
             "for the control software")
    L.append("")
    (HERE / "tube-map.md").write_text("\n".join(L))


# ---- diagram + printable PDF -----------------------------------------------
def _font(size, bold=False):
    names = (["DejaVuSans-Bold.ttf", "Arial Bold.ttf"] if bold
             else ["DejaVuSans.ttf", "Arial.ttf"])
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _board_cell(draw, x, y, w, h, color, b):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, fill=color)
    f_big = _font(26, bold=True)
    f_md = _font(17, bold=True)
    f_sm = _font(14)
    cx = x + w / 2
    draw.text((cx, y + 10), b["id"], font=f_big, fill="white", anchor="mt")
    draw.text((cx, y + 42), f"{b['tubes'][0]}–{b['tubes'][-1]}"
              f"  ({b['tube_count']} tubes)",
              font=f_md, fill="white", anchor="mt")
    draw.text((cx, y + 68), f"port {b['port']} · jack {b['silkscreen']}",
              font=f_sm, fill="#ffe08a", anchor="mt")
    draw.text((cx, y + 88), f"DIAL {b['rotary']} · DIPs UP",
              font=f_sm, fill="#9bf0ff", anchor="mt")
    groups = "  ".join(
        f"{CHAIN_LETTERS[i]}:"
        f"{min(OUTPUTS_PER_GROUP, b['tube_count'] - i * OUTPUTS_PER_GROUP)}"
        for i in range(b["groups"]))
    draw.text((cx, y + 108), groups, font=f_sm, fill="white", anchor="mt")


def draw_overview(data):
    W = 1500
    cw, ch, gap = 240, 132, 16
    boards = data["boards"]
    by_id = {b["id"]: b for b in boards}
    left = [b for b in boards if b["zone"] in ("A", "B")]
    back = [b for b in boards if b["zone"] == "C"]
    right = [b for b in boards if b["zone"] in ("D", "E")]
    front_right = [b for b in boards if b["zone"] == "F"]

    top = 120
    col_rows = max(len(left), len(front_right) + len(right))
    col_bottom = top + col_rows * (ch + gap)
    back_y = col_bottom + 24
    legend_y = back_y + ch + 76
    H = int(legend_y + 104)

    img = Image.new("RGB", (W, H), "#0d1b2a")
    d = ImageDraw.Draw(img)
    d.text((W / 2, 22), "Glorb broom — receiver boards (one SRx4 per 2×4)",
           font=_font(30, bold=True), fill="white", anchor="mt")
    d.text((W / 2, 60), "front-left OPEN (driver sightline)  ·  "
           "front is the TOP edge  ·  bird's-eye view from ABOVE",
           font=_font(16), fill="#a9c0d6", anchor="mt")
    d.text((W / 2, 84), "EVERY BOARD: ID dial → A  ·  all 4 DIP switches UP "
           "(Only/Last)  ·  one cat5 per board, nothing chained",
           font=_font(17, bold=True), fill="#ffe08a", anchor="mt")
    col_x_left = 140
    col_x_right = W - 140 - cw

    def tkey(b):
        return min(int(t[1:]) for t in b["tubes"])

    pos = {}
    for i, b in enumerate(sorted(left, key=tkey)):
        pos[b["id"]] = (col_x_left, top + i * (ch + gap))
    # right column: F1 at the FRONT-RIGHT corner (top), then R56 -> R01 down
    right_ordered = front_right + sorted(right, key=tkey, reverse=True)
    for i, b in enumerate(right_ordered):
        pos[b["id"]] = (col_x_right, top + i * (ch + gap))
    # back row: C, left -> right
    back_sorted = sorted(back, key=tkey)
    nb = len(back_sorted)
    total_w = nb * cw + (nb - 1) * gap
    start_x = (W - total_w) / 2
    for i, b in enumerate(back_sorted):
        pos[b["id"]] = (start_x + i * (cw + gap), back_y)

    # As-built physical swaps (empty unless PHYSICAL_SWAP is set): only moves
    # where a board is drawn; data/ports/channels unchanged.
    for a, bb in PHYSICAL_SWAP:
        if a in pos and bb in pos:
            pos[a], pos[bb] = pos[bb], pos[a]

    for bid, (x, y) in pos.items():
        _board_cell(d, x, y, cw, ch, ZONE_COLORS[by_id[bid]["zone"]],
                    by_id[bid])

    # orientation labels
    d.text((col_x_left + cw / 2, top - 26), "LEFT (L01→L56)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    d.text((col_x_right + cw / 2, top - 26), "RIGHT (R01→R56)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    d.text((W / 2, back_y + ch + 10), "BACK (B01→B24)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    for a, bb in PHYSICAL_SWAP:
        d.text((W / 2, back_y + ch + 36),
               f"AS-BUILT: {a}⇄{bb} drawn at swapped positions "
               f"(data/channels unchanged)",
               font=_font(15, bold=True), fill="#ffd166", anchor="mt")

    # legend (3 per row so 6 zones fit)
    ly = legend_y
    d.text((60, ly), "Zones:", font=_font(16, bold=True), fill="white")
    for idx, z in enumerate(data["zones"]):
        lx = 150 + (idx % 3) * 440
        ly2 = ly + (idx // 3) * 28
        c = ZONE_COLORS[z["name"]]
        d.rounded_rectangle([lx, ly2 - 2, lx + 22, ly2 + 18], radius=4, fill=c)
        ports = "/".join(str(p) for p in z["ports"])
        d.text((lx + 30, ly2), f"{z['name']} {z['location']} (port {ports})",
               font=_font(15), fill="white")
    return img


def draw_zone_page(data, zone, size):
    """One printable page per zone: its two boards' full hookup tables."""
    W, H = size
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    zc = ZONE_COLORS[zone["name"]]
    d.rectangle([0, 0, W, 96], fill=zc)
    d.text((40, 26), f"Zone {zone['name']} — {zone['location']}",
           font=_font(38, bold=True), fill="white")
    d.text((W - 40, 34), f"{zone['tube_count']} tubes · {len(zone['boards'])} boards",
           font=_font(24), fill="white", anchor="rt")

    boards = [b for b in data["boards"] if b["zone"] == zone["name"]]
    by_id = {r["id"]: r for r in data["receivers"]}
    col_w = (W - 120) // 2
    for bi, b in enumerate(boards):
        x0 = 40 + bi * (col_w + 40)
        y = 130
        d.rounded_rectangle([x0, y, x0 + col_w, y + 118], radius=10,
                            outline=zc, width=4)
        d.text((x0 + 24, y + 14), f"Board {b['id']}",
               font=_font(32, bold=True), fill="#111")
        d.text((x0 + col_w - 24, y + 22),
               f"tubes {b['tubes'][0]}–{b['tubes'][-1]}",
               font=_font(22, bold=True), fill="#111", anchor="rt")
        d.text((x0 + 24, y + 58),
               f"cat5 → K128D jack {b['silkscreen']}  (port {b['port']})",
               font=_font(20), fill="#333")
        d.text((x0 + 24, y + 86),
               f"ID DIAL: {b['rotary']}   ·   DIPs: all 4 UP (Only/Last)",
               font=_font(20, bold=True), fill="#b00020")

        y += 146
        d.text((x0 + 24, y), "group · out → tube        channels",
               font=_font(17, bold=True), fill="#555")
        y += 32
        f_row = _font(19)
        f_mono = _font(19, bold=True)
        for rid in b["receivers"]:
            r = by_id[rid]
            for o in r["outputs"]:
                d.text((x0 + 24, y),
                       f"{r['chain_letter']} · out {o['output']}",
                       font=f_row, fill="#333")
                d.text((x0 + 190, y), o["tube"], font=f_mono, fill="#111")
                d.text((x0 + 300, y),
                       f"{o['start_channel']}–{o['end_channel']}",
                       font=f_row, fill="#777")
                y += 30
            n_unused = OUTPUTS_PER_GROUP - len(r["outputs"])
            if n_unused:
                d.text((x0 + 24, y),
                       f"{r['chain_letter']} · out "
                       f"{len(r['outputs']) + 1}-{OUTPUTS_PER_GROUP}"
                       f"  — unused", font=f_row, fill="#aaa")
                y += 30
            y += 8

    d.text((40, H - 52), "Dial is read at POWER-UP — set it before powering, "
           "or power-cycle after changing.  Never 0 (dumb mode = flicker).",
           font=_font(18, bold=True), fill="#b00020")
    return img


def write_images(data):
    overview = draw_overview(data)
    overview.save(HERE / "tube-map.png")

    # Printable PDF: page 1 = the overview, then one page per zone with the
    # dial settings and full output->tube hookup for its two boards.
    # Generated here so it can't drift from the map.
    page_size = (1500, 1160)
    pages = [draw_zone_page(data, z, page_size) for z in data["zones"]]
    first = overview.convert("RGB")
    first.save(HERE / "tube-map.pdf", "PDF", resolution=150.0,
               save_all=True, append_images=[p.convert("RGB") for p in pages])


def main():
    data = build()
    (HERE / "tube-map.json").write_text(json.dumps(data, indent=2))
    write_md(data)
    write_images(data)
    m, c = data["meta"], data["controller"]
    print(f"{m['total_tubes']} tubes / {m['total_boards']} boards "
          f"({m['total_receivers']} receiver groups) on "
          f"{c['rj45_ports_used']} RJ45 ports, "
          f"{m['total_channels']:,} channels, "
          f"{c['universe_count']} universes written.")


if __name__ == "__main__":
    main()
