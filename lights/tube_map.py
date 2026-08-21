#!/usr/bin/env python3
"""Source of truth for the broom LED tube -> receiver/output -> channel map.

Run this to (re)generate three artifacts next to it:
  - tube-map.json  machine-readable map (consumed by the control software)
  - tube-map.md    human doc + install/test checklist
  - tube-map.png   physical layout diagram

Change the knobs at the top and re-run; everything downstream stays in sync.

Topology (2026-08-20 rebuild): ONE Kulp K128D-B controller (BeagleBone + FPP)
replaces the five WLED Angio-8 boards. Tubes are no longer chained — every
tube gets its own data line from a differential receiver output. See
controllers.md for the wiring and k128/README.md for controller bring-up.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---- knobs -----------------------------------------------------------------
PIX_PER_TUBE = 40            # 16 px/m * 2.5 m
CHAN_PER_PIX = 3             # RGB
TUBES_PER_RECEIVER = 4       # a differential receiver board has 4 pixel outputs
MAX_RECEIVERS_PER_PORT = 6   # FPP v2 SmartReceiver chain limit (MAX_SMART_RECEIVERS)
MAX_PX_PER_PORT = 800        # Kulp spec: 800 px/port @ 40 fps, shared by the chain

# FPP E1.31 bridge input. The whole car is ONE flat pixel space on one
# controller, so universes are contiguous from 1. 170 px = 510 ch/universe
# keeps universe boundaries on pixel boundaries.
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
# 2x4 hangers and busbars all still mean the same thing. What changed: a zone
# is now a cluster of differential receivers fed by RJ45 ports on the single
# K128D, not its own controller.
#
# (name, location, label prefix, first, last, receivers per RJ45 port)
# Each entry in the last tuple = one RJ45 port and how many receivers chain
# off it. Receivers x TUBES_PER_RECEIVER must equal the zone's tube count.
ZONES = [
    ("A", "Left-Front",  "L",  1, 28, (4, 3)),
    ("B", "Left-Back",   "L", 29, 56, (4, 3)),
    ("C", "Back",        "B",  1, 24, (3, 3)),
    ("D", "Right-Back",  "R",  1, 28, (4, 3)),
    ("E", "Right-Front", "R", 29, 56, (4, 3)),
]

# RJ45 ports on the K128D, assigned in ZONES order. Ten of the 32 ports carry
# the whole car; the rest are spare. Renumber here if the physical patching
# differs -- and see the note in k128/README.md about confirming how FPP
# numbers the strings behind a smart-receiver port on this cape.
FIRST_RJ45_PORT = 1

ZONE_COLORS = {
    "A": "#E63946", "B": "#F4A261", "C": "#2A9D8F",
    "D": "#457B9D", "E": "#9D4EDD",
}

# FPP smart-receiver chain positions are labeled A-F in the UI and map to the
# virtualStrings / virtualStringsB..F keys in co-bbbStrings.json.
CHAIN_LETTERS = "ABCDEF"

# +24 V is still injected every 2 tubes (tube 1 and tube 3 of each group of
# 4) and jumpered to its neighbour -- power wiring is unchanged from the
# Angio build. Only the data lines changed.
POWER_EVERY = 2


# ---- build the map ---------------------------------------------------------
def build():
    tubes = []
    receivers = []
    zones = []
    rid = 0
    port = FIRST_RJ45_PORT

    for zname, zloc, prefix, first, last, port_spec in ZONES:
        numbers = list(range(first, last + 1))
        n_recv = sum(port_spec)
        assert n_recv * TUBES_PER_RECEIVER == len(numbers), (
            f"{zname}: {n_recv} receivers x {TUBES_PER_RECEIVER} outputs "
            f"!= {len(numbers)} tubes")
        assert all(n <= MAX_RECEIVERS_PER_PORT for n in port_spec), (
            f"{zname}: more than {MAX_RECEIVERS_PER_PORT} receivers on a port")

        zone_ports = []
        zone_recv = []
        ti = 0
        for n_on_port in port_spec:
            port_recv = []
            port_tubes = []
            for chain_pos in range(n_on_port):
                rid += 1
                chunk = numbers[ti:ti + TUBES_PER_RECEIVER]
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
                    tube = {
                        "label": label,
                        "side": prefix,
                        "pos": num - 1,
                        "index": idx,
                        "zone": zname,
                        "receiver": rid,
                        "chain_pos": chain_pos + 1,
                        "chain_letter": CHAIN_LETTERS[chain_pos],
                        "port": port,
                        "port_silkscreen": f"{(port - 1) * TUBES_PER_RECEIVER + 1}-"
                                           f"{port * TUBES_PER_RECEIVER}",
                        "output": out_num,
                        "pixels": PIX_PER_TUBE,
                        "px_offset": px_off,
                        "start_channel": start_ch,
                        "end_channel": end_ch,
                        "universes": list(range(u0, u1 + 1)),
                        # data enters every tube at the top now, so no tube
                        # is ever reversed in software
                        "direction": "forward",
                        "power_in": (out_num - 1) % POWER_EVERY == 0,
                    }
                    tubes.append(tube)
                    outputs.append({
                        "output": out_num, "tube": label,
                        "pixels": PIX_PER_TUBE,
                        "start_channel": start_ch, "end_channel": end_ch,
                    })
                receivers.append({
                    "id": rid,
                    "zone": zname,
                    "port": port,
                    "chain_pos": chain_pos + 1,
                    "chain_letter": CHAIN_LETTERS[chain_pos],
                    "tubes": labels,
                    "tube_count": len(labels),
                    "pixels": len(labels) * PIX_PER_TUBE,
                    "start_channel": outputs[0]["start_channel"],
                    "end_channel": outputs[-1]["end_channel"],
                    "outputs": outputs,
                    "power_in": labels[::POWER_EVERY],
                })
                port_recv.append(rid)
                port_tubes.extend(labels)
            px = len(port_tubes) * PIX_PER_TUBE
            assert px <= MAX_PX_PER_PORT, (
                f"port {port}: {px} px exceeds the {MAX_PX_PER_PORT} px "
                f"per-port budget")
            # The board silkscreens each RJ45 with the STRING range it owns,
            # not a port number -- jack "1-4" is port 1, "17-20" is port 5.
            # Jacks run right-to-left, bottom-to-top in columns of four
            # (rightmost column = strings 1-16). Confirmed against the board
            # 2026-08-21, and it validates port_number() in k128/fpp_setup.py.
            first_string = (port - 1) * TUBES_PER_RECEIVER + 1
            zone_ports.append({
                "port": port,
                "silkscreen": f"{first_string}-"
                              f"{first_string + TUBES_PER_RECEIVER - 1}",
                "receivers": port_recv,
                "receiver_count": len(port_recv),
                "tubes": port_tubes,
                "tube_count": len(port_tubes),
                "pixels": px,
                "differential_type": ("standard" if len(port_recv) == 1
                                      else f"v2 smart x{len(port_recv)}"),
            })
            zone_recv.extend(port_recv)
            port += 1

        zones.append({
            "name": zname,
            "location": zloc,
            "tube_count": len(numbers),
            "receivers": zone_recv,
            "ports": zone_ports,
            "pixels": len(numbers) * PIX_PER_TUBE,
        })

    total_px = len(tubes) * PIX_PER_TUBE
    total_ch = total_px * CHAN_PER_PIX
    n_univ = -(-total_ch // UNIVERSE_SIZE)   # ceil
    ports_used = sum(len(z["ports"]) for z in zones)

    controller = dict(CONTROLLER)
    controller.update({
        "rj45_ports_used": ports_used,
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
            "tubes_per_receiver": TUBES_PER_RECEIVER,
            "pixels_per_tube": PIX_PER_TUBE,
            "channels_per_pixel": CHAN_PER_PIX,
            "px_per_universe": PX_PER_UNIVERSE,
            "universe_size": UNIVERSE_SIZE,
            "total_tubes": len(tubes),
            "total_receivers": len(receivers),
            "total_pixels": total_px,
            "total_channels": total_ch,
            "chip": "SM16703",
            "protocol": "sACN / E1.31",
            "color_order": "RGB",
            # every tube has its own data line now: no chaining, so no
            # serpentine flip and nothing to reverse in software
            "serpentine": False,
        },
        "controller": controller,
        "zones": zones,
        "receivers": receivers,
        "tubes": tubes,
    }


# ---- markdown doc + checklist ----------------------------------------------
def _uspan(us):
    return f"{us[0]}" if len(us) == 1 else f"{us[0]}–{us[-1]}"


def write_md(data):
    m = data["meta"]
    c = data["controller"]
    L = []
    L.append("# Broom LED tube map — receivers, outputs, channels")
    L.append("")
    L.append("> **Generated by [tube_map.py](tube_map.py) — do not hand-edit.** "
             "Change the knobs in that script and re-run.")
    L.append("")
    L.append(f"**{m['total_tubes']} tubes**, each on its **own data line**, "
             f"driven by **{m['total_receivers']} differential receivers** "
             f"({m['tubes_per_receiver']} outputs each) off "
             f"**{c['rj45_ports_used']} of {c['rj45_ports_total']} RJ45 ports** "
             f"on one **{c['model']}**.")
    L.append("")
    L.append(f"Chip **{m['chip']}**, color order **{m['color_order']}**, "
             f"**{m['pixels_per_tube']} px/tube** → "
             f"**{m['total_pixels']:,} px / {m['total_channels']:,} channels**. "
             f"The whole car is one flat pixel space on one controller: "
             f"FPP E1.31 bridge input, universes "
             f"**{c['universes'][0]}–{c['universes'][-1]}** of "
             f"{c['universe_size']} channels, starting at FPP channel 1.")
    L.append("")
    L.append("**No chaining, no serpentine.** Every tube takes data at its "
             "**top** end from one receiver output, so every string is "
             "*Forward* in FPP and nothing is reversed in software. A tube is "
             "exactly 120 contiguous channels; tube *n* (0-based) starts at "
             "channel `n × 120 + 1`.")
    L.append("")

    L.append("## Zones and ports (walking the open-front U)")
    L.append("")
    L.append("Tubes numbered around the U from **front-left → back → "
             "front-right**: left `L01`(front)→`L56`(back), "
             "back `B01`(left)→`B24`(right), "
             "right `R01`(back)→`R56`(front).")
    L.append("")
    L.append("Zone letters A–E are carried over from the Angio build so the "
             "existing tube labels, 2×4 hangers and busbars still mean the "
             "same thing. A zone is now a cluster of receivers on RJ45 ports, "
             "not its own controller.")
    L.append("")
    L.append("| Zone | Location | Tubes | Receivers | RJ45 port | Jack "
             "silkscreen | Receivers on port | Px on port | Receiver mode |")
    L.append("| --- | --- | ---: | --- | ---: | :-: | ---: | ---: | --- |")
    for z in data["zones"]:
        rs = z["receivers"]
        for i, p in enumerate(z["ports"]):
            zcell = (f"{z['name']} | {z['location']} | {z['tube_count']} | "
                     f"R{rs[0]}–R{rs[-1]}" if i == 0 else " | | | ")
            L.append(f"| {zcell} | {p['port']} | `{p['silkscreen']}` | "
                     f"{p['receiver_count']} | "
                     f"{p['pixels']} | {p['differential_type']} |")
    L.append("")
    L.append("**Finding the right jack:** the board silkscreens each RJ45 "
             "with the *string range* it owns, not a port number — port 1 is "
             "the jack marked `1-4`, port 5 is `17-20`. Jacks run "
             "**right-to-left, bottom-to-top in columns of four**, so the "
             "rightmost column is strings 1–16. All ten ports we use are in "
             "the three rightmost columns.")
    L.append("")
    L.append(f"Per-port budget is {MAX_PX_PER_PORT} px at 40 fps shared "
             f"across the whole receiver chain — the busiest port here runs "
             f"{max(p['pixels'] for z in data['zones'] for p in z['ports'])} "
             f"px, so there is plenty of headroom.")
    L.append("")

    L.append("## Receiver map")
    L.append("")
    L.append("One receiver per 4 tubes. `Chain` is the receiver's position in "
             "the daisy-chain off its RJ45 port, which is also the letter FPP "
             "shows for it (A = first board on the cable). Outputs 1–4 are the "
             "receiver's four pixel ports, in tube-label order.")
    L.append("")
    L.append("| Receiver | Zone | Port (jack) | Chain | Tubes | Outputs 1–4 | "
             "Channels | Power in |")
    L.append("| ---: | --- | :-: | :-: | --- | --- | ---: | --- |")
    for r in data["receivers"]:
        outs = " · ".join(f"{o['output']}→`{o['tube']}`" for o in r["outputs"])
        pw = ", ".join(f"`{t}`" for t in r["power_in"])
        jack = f"{(r['port'] - 1) * TUBES_PER_RECEIVER + 1}-" \
               f"{r['port'] * TUBES_PER_RECEIVER}"
        L.append(f"| **R{r['id']}** | {r['zone']} | {r['port']} (`{jack}`) | "
                 f"{r['chain_letter']} | `{r['tubes'][0]}`–`{r['tubes'][-1]}` | "
                 f"{outs} | {r['start_channel']}–{r['end_channel']} | {pw} |")
    L.append("")

    L.append("## Per-tube channel map")
    L.append("")
    L.append("What FPP needs per string: port, receiver, output, start "
             "channel, 40 px, Forward, RGB.")
    L.append("")
    L.append("| Tube | Zone | Port | Recv | Out | Start ch | End ch | "
             "Universes |")
    L.append("| --- | --- | ---: | ---: | :-: | ---: | ---: | --- |")
    for t in data["tubes"]:
        L.append(f"| `{t['label']}` | {t['zone']} | {t['port']} | "
                 f"R{t['receiver']}{t['chain_letter']} | {t['output']} | "
                 f"{t['start_channel']} | {t['end_channel']} | "
                 f"{_uspan(t['universes'])} |")
    L.append("")

    L.append("## Labeling scheme")
    L.append("")
    L.append("Label every tube at **both ends** with its tube ID and its "
             "receiver + output. Example flag: `L05 / R2-1` = tube L05, "
             "receiver 2, output 1. Label the cat5 run at both ends with the "
             "RJ45 port number and the chain letter.")
    L.append("")
    L.append("```")
    L.append("K128D RJ45 port ──cat5──▶ [recv A] ──cat5──▶ [recv B] ──▶ …  "
             "(≤6 v2 smart receivers, ≤250 ft to the last one)")
    L.append("                            │")
    L.append("                            ├─out1─[330–470Ω]─▶ DIN tube 1 (top)")
    L.append("                            ├─out2─[330–470Ω]─▶ DIN tube 2 (top)")
    L.append("                            ├─out3─[330–470Ω]─▶ DIN tube 3 (top)")
    L.append("                            └─out4─[330–470Ω]─▶ DIN tube 4 (top)")
    L.append("```")
    L.append("")

    L.append("## FPP config")
    L.append("")
    L.append("Run **[k128/fpp_setup.py](k128/fpp_setup.py)** to push this map "
             "into FPP — it writes the E1.31 bridge input "
             f"(universes {c['universes'][0]}–{c['universes'][-1]} × "
             f"{c['universe_size']} ch) and the BBB Strings channel outputs "
             "(one string per tube, 40 px, Forward, RGB), then restarts fppd:")
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
    L.append("Do it **one receiver at a time**. For each receiver: run the "
             "cat5 → hang its 4 tubes → land each tube's DIN on its own output "
             "→ tap +24 V + shared GND → label both ends → light it from "
             "software → confirm all 4 tubes and the color order → check the "
             "box.")
    L.append("")
    for z in data["zones"]:
        ports = ", ".join(str(p["port"]) for p in z["ports"])
        L.append(f"### {z['name']} — {z['location']} "
                 f"({z['tube_count']} tubes, RJ45 port {ports})")
        for r in [r for r in data["receivers"] if r["zone"] == z["name"]]:
            tr = f"{r['tubes'][0]}–{r['tubes'][-1]}"
            L.append(f"- [ ] **R{r['id']}** · port {r['port']} chain "
                     f"{r['chain_letter']} · tubes {tr} · ch "
                     f"{r['start_channel']}–{r['end_channel']}")
        L.append("")

    L.append("## Diagram")
    L.append("")
    L.append("![Tube layout](tube-map.png)")
    L.append("")
    L.append("## Related")
    L.append("")
    L.append("- [k128/README.md](k128/README.md) — controller bring-up: wifi, "
             "FPP install, bench test")
    L.append("- [controllers.md](controllers.md) — data wiring, receivers, "
             "shared ground")
    L.append("- [led-tubes.md](led-tubes.md) — SM16703 electricals "
             "(16 px/m, 5 V data, RGB, series resistor)")
    L.append("- [../electrical/led-wiring.md](../electrical/led-wiring.md) "
             "— power injection (separate from data)")
    L.append("- [tube-map.json](tube-map.json) — machine-readable map "
             "for the control software")
    L.append("")
    (HERE / "tube-map.md").write_text("\n".join(L))


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


def _cell(draw, x, y, w, h, color, r):
    draw.rounded_rectangle([x, y, x + w, y + h], radius=6, fill=color)
    f_big = _font(20, bold=True)
    f_sm = _font(13)
    f_xs = _font(12)
    trange = f"{r['tubes'][0]}–{r['tubes'][-1]}"
    draw.text((x + w / 2, y + 8), f"R{r['id']}", font=f_big, fill="white",
              anchor="mt")
    draw.text((x + w / 2, y + 34), trange, font=f_sm, fill="white", anchor="mt")
    draw.text((x + w / 2, y + h - 34),
              f"port {r['port']}{r['chain_letter']} · out 1-4", font=f_xs,
              fill="#ffe08a", anchor="mt")
    draw.text((x + w / 2, y + h - 18),
              "pwr " + "+".join(r["power_in"]), font=f_xs,
              fill="#9bf0ff", anchor="mt")


def write_png(data):
    W = 1500
    cw, ch, gap = 150, 104, 10
    by = data["receivers"]
    left = [r for r in by if r["zone"] in ("A", "B")]
    back = [r for r in by if r["zone"] == "C"]
    right = [r for r in by if r["zone"] in ("D", "E")]

    top = 110
    col_rows = max(len(left), len(right))
    col_bottom = top + col_rows * (ch + gap)
    back_y = col_bottom + 20
    legend_y = back_y + ch + 44
    H = int(legend_y + 70)

    img = Image.new("RGB", (W, H), "#0d1b2a")
    d = ImageDraw.Draw(img)
    d.text((W / 2, 24), "Glorb broom — LED receivers (open-front U)",
           font=_font(30, bold=True), fill="white", anchor="mt")
    d.text((W / 2, 62), "front-left OPEN (driver sightline)  ·  "
           "front is the TOP edge", font=_font(16), fill="#a9c0d6", anchor="mt")
    d.text((W / 2, 84), "bird's-eye view from ABOVE — standing BEHIND the car "
           "you see B01 on your LEFT  ·  one K128D, one data line per tube",
           font=_font(16), fill="#ffe08a", anchor="mt")
    col_x_left = 120
    col_x_right = W - 120 - cw

    # Place cells by *physical* tube position (labels are positional).
    def tkey(r):
        return min(int(t[1:]) for t in r["tubes"])

    # left column: front (top, L01) -> back (bottom, L56)
    for i, r in enumerate(sorted(left, key=tkey)):
        y = top + i * (ch + gap)
        _cell(d, col_x_left, y, cw, ch, ZONE_COLORS[r["zone"]], r)

    # right column: front (top, R56) -> back (bottom, R01)
    for i, r in enumerate(sorted(right, key=tkey, reverse=True)):
        y = top + i * (ch + gap)
        _cell(d, col_x_right, y, cw, ch, ZONE_COLORS[r["zone"]], r)

    # back row: left (B01) -> right (B24), along the bottom
    n = len(back)
    total_w = n * cw + (n - 1) * gap
    start_x = (W - total_w) / 2
    for i, r in enumerate(sorted(back, key=tkey)):
        x = start_x + i * (cw + gap)
        _cell(d, x, back_y, cw, ch, ZONE_COLORS[r["zone"]], r)

    # side labels
    d.text((col_x_left + cw / 2, top - 26), "LEFT (L01→L56)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    d.text((col_x_right + cw / 2, top - 26), "RIGHT (R01→R56)",
           font=_font(16, bold=True), fill="white", anchor="mt")
    d.text((W / 2, back_y + ch + 8), "BACK (B01→B24)",
           font=_font(16, bold=True), fill="white", anchor="mt")

    # legend
    ly = legend_y
    d.text((60, ly), "Zones:", font=_font(16, bold=True), fill="white")
    lx = 150
    for z in data["zones"]:
        c = ZONE_COLORS[z["name"]]
        d.rounded_rectangle([lx, ly - 2, lx + 22, ly + 18], radius=4, fill=c)
        ports = "/".join(str(p["port"]) for p in z["ports"])
        d.text((lx + 30, ly), f"{z['name']} {z['location']} (port {ports})",
               font=_font(15), fill="white")
        lx += 240

    img.save(HERE / "tube-map.png")
    # Same diagram as a printable PDF, so the two can't drift apart. (The
    # hand-exported tube-map.pdf used to go stale every time this changed.)
    img.convert("RGB").save(HERE / "tube-map.pdf", "PDF", resolution=150.0)


def main():
    data = build()
    (HERE / "tube-map.json").write_text(json.dumps(data, indent=2))
    write_md(data)
    write_png(data)
    m, c = data["meta"], data["controller"]
    print(f"{m['total_tubes']} tubes / {m['total_receivers']} receivers on "
          f"{c['rj45_ports_used']} RJ45 ports, "
          f"{m['total_channels']:,} channels, "
          f"{c['universe_count']} universes written.")


if __name__ == "__main__":
    main()
