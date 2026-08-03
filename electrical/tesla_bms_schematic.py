#!/usr/bin/env python3
"""Generate the single-module Tesla BMS / Arduino Due wiring schematic.

The SVG is generated with the Python standard library only.  If Google Chrome
is installed, --render also creates PDF and PNG copies.

Usage:
    python3 electrical/tesla_bms_schematic.py --render
"""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import tempfile
from pathlib import Path


WIDTH = 1600
HEIGHT = 1050


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


class SVG:
    def __init__(self) -> None:
        self.parts: list[str] = []

    def add(self, markup: str) -> None:
        self.parts.append(markup)

    def line(self, x1, y1, x2, y2, *, cls="wire", marker="") -> None:
        marker_attr = f' marker-end="url(#{marker})"' if marker else ""
        self.add(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
            f'class="{cls}"{marker_attr}/>'
        )

    def path(self, points, *, cls="wire", marker="") -> None:
        path = " ".join(f"{x},{y}" for x, y in points)
        marker_attr = f' marker-end="url(#{marker})"' if marker else ""
        self.add(f'<polyline points="{path}" class="{cls}"{marker_attr}/>' )

    def rect(self, x, y, w, h, *, cls="block", rx=5) -> None:
        self.add(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" '
            f'rx="{rx}" class="{cls}"/>'
        )

    def circle(self, x, y, r=5, *, cls="junction") -> None:
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" class="{cls}"/>')

    def text(self, x, y, value, *, cls="label", anchor="start", rotate=None) -> None:
        transform = f' transform="rotate({rotate} {x} {y})"' if rotate is not None else ""
        self.add(
            f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}"'
            f'{transform}>{esc(value)}</text>'
        )

    def multiline(self, x, y, lines, *, cls="note", line_height=22, anchor="start") -> None:
        spans = []
        for i, value in enumerate(lines):
            dy = 0 if i == 0 else line_height
            spans.append(f'<tspan x="{x}" dy="{dy}">{esc(value)}</tspan>')
        self.add(
            f'<text x="{x}" y="{y}" class="{cls}" text-anchor="{anchor}">'
            + "".join(spans)
            + "</text>"
        )

    def finish(self) -> str:
        style = """
        :root { color-scheme: light; }
        * { vector-effect: non-scaling-stroke; }
        .sheet { fill: #fffdfa; stroke: #1f2937; stroke-width: 2; }
        .block { fill: #f8fafc; stroke: #172033; stroke-width: 2.2; }
        .module { fill: #fff8e7; stroke: #8a5a00; stroke-width: 2.4; }
        .shifter { fill: #edf5ff; stroke: #1d4f91; stroke-width: 2.4; }
        .connector { fill: #fff; stroke: #374151; stroke-width: 2; }
        .loopbox { fill: #fff4f2; stroke: #a62c20; stroke-width: 2.2; }
        .note-box { fill: #fff9db; stroke: #9a7500; stroke-width: 1.8; }
        .warn-box { fill: #fff0f0; stroke: #b42318; stroke-width: 2; }
        .wire { fill: none; stroke: #111827; stroke-width: 3; stroke-linejoin: round; }
        .wire5 { fill: none; stroke: #c62828; stroke-width: 3.5; stroke-linejoin: round; }
        .wire3 { fill: none; stroke: #7b1fa2; stroke-width: 3.5; stroke-linejoin: round; }
        .wiretx { fill: none; stroke: #1565c0; stroke-width: 3.5; stroke-linejoin: round; }
        .wirerx { fill: none; stroke: #00876c; stroke-width: 3.5; stroke-linejoin: round; }
        .wirefault { fill: none; stroke: #d97706; stroke-width: 3; stroke-dasharray: 8 6; }
        .ground { fill: none; stroke: #111827; stroke-width: 3.5; stroke-linejoin: round; }
        .pin { stroke: #111827; stroke-width: 2; }
        .nc { stroke: #6b7280; stroke-width: 2; }
        .junction { fill: #111827; stroke: none; }
        .label { font: 18px Arial, Helvetica, sans-serif; fill: #111827; }
        .small { font: 15px Arial, Helvetica, sans-serif; fill: #374151; }
        .tiny { font: 13px Arial, Helvetica, sans-serif; fill: #4b5563; }
        .title { font: bold 30px Arial, Helvetica, sans-serif; fill: #111827; }
        .subtitle { font: 17px Arial, Helvetica, sans-serif; fill: #374151; }
        .block-title { font: bold 20px Arial, Helvetica, sans-serif; fill: #111827; }
        .pin-label { font: 15px 'Courier New', monospace; fill: #111827; }
        .net { font: bold 15px 'Courier New', monospace; fill: #111827; }
        .note { font: 16px Arial, Helvetica, sans-serif; fill: #332b00; }
        .warning { font: bold 15px Arial, Helvetica, sans-serif; fill: #8a1c13; }
        .footer { font: 13px Arial, Helvetica, sans-serif; fill: #4b5563; }
        """
        defs = """
        <defs>
          <marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4"
                  orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0,0 L10,4 L0,8 z" fill="#111827"/>
          </marker>
          <marker id="arrow-blue" markerWidth="10" markerHeight="8" refX="9" refY="4"
                  orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0,0 L10,4 L0,8 z" fill="#1565c0"/>
          </marker>
          <marker id="arrow-green" markerWidth="10" markerHeight="8" refX="9" refY="4"
                  orient="auto" markerUnits="userSpaceOnUse">
            <path d="M0,0 L10,4 L0,8 z" fill="#00876c"/>
          </marker>
        </defs>
        """
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
            f'viewBox="0 0 {WIDTH} {HEIGHT}">\n<style>{style}</style>\n{defs}\n'
            + "\n".join(self.parts)
            + "\n</svg>\n"
        )


def ground_symbol(s: SVG, x: int, y: int) -> None:
    s.line(x, y - 20, x, y, cls="ground")
    s.line(x - 18, y, x + 18, y, cls="ground")
    s.line(x - 12, y + 7, x + 12, y + 7, cls="ground")
    s.line(x - 6, y + 14, x + 6, y + 14, cls="ground")


def supply_symbol(s: SVG, x: int, y: int, label: str, cls="wire5") -> None:
    s.line(x, y + 22, x, y, cls=cls)
    s.path([(x - 10, y + 10), (x, y), (x + 10, y + 10)], cls=cls)
    s.text(x + 16, y + 8, label, cls="net")


def connector(s: SVG, x: int, y: int, title: str, *, end=False) -> dict[int, tuple[int, int]]:
    w, h = 270, 340
    s.rect(x, y, w, h, cls="loopbox" if end else "connector", rx=4)
    s.text(x + w / 2, y + 28, title, cls="block-title", anchor="middle")
    s.text(x + w / 2, y + 50, "Molex 15-97-5101", cls="tiny", anchor="middle")
    pins: dict[int, tuple[int, int]] = {}
    pin_y = {1: 85, 2: 127, 3: 169, 4: 211, 5: 253,
             6: 85, 7: 127, 8: 169, 9: 211, 10: 253}
    for p in range(1, 6):
        py = y + pin_y[p]
        s.line(x - 16, py, x + 12, py, cls="pin")
        s.circle(x - 16, py, 3)
        pins[p] = (x - 16, py)
        labels = {1: "+5V", 2: "RX-A", 3: "GND", 4: "TX-A", 5: "+5V"}
        s.text(x + 20, py + 5, f"{p}  {labels[p]}", cls="pin-label")
    for p in range(6, 11):
        py = y + pin_y[p]
        s.line(x + w - 12, py, x + w + 16, py, cls="pin")
        s.circle(x + w + 16, py, 3)
        pins[p] = (x + w + 16, py)
        labels = {6: "FAULT", 7: "RX-B", 8: "GND", 9: "TX-B", 10: "FAULT"}
        s.text(x + w - 20, py + 5, f"{labels[p]}  {p}", cls="pin-label", anchor="end")
    return pins


def build_detailed_svg() -> str:
    s = SVG()
    s.rect(18, 18, WIDTH - 36, HEIGHT - 36, cls="sheet", rx=0)
    s.text(55, 65, "Arduino Due to Tesla Model S/X module BMS", cls="title")
    s.text(
        55,
        92,
        "Single original 6S module • EVTV two-module harness • BMB powered from Due +5 V",
        cls="subtitle",
    )

    # Arduino Due block.
    ax, ay, aw, ah = 70, 190, 280, 410
    s.rect(ax, ay, aw, ah, cls="block")
    s.text(ax + aw / 2, ay + 35, "U1  ARDUINO DUE", cls="block-title", anchor="middle")
    s.text(ax + aw / 2, ay + 60, "SAM3X8E • 3.3 V I/O", cls="small", anchor="middle")
    due_pins = {
        "3V3": (ax + aw, ay + 95),
        "+5V": (ax + aw, ay + 145),
        "TX1": (ax + aw, ay + 205),
        "RX1": (ax + aw, ay + 265),
        "GND": (ax + aw, ay + 335),
    }
    for name, (px, py) in due_pins.items():
        s.line(px - 22, py, px + 18, py, cls="pin")
        s.circle(px + 18, py, 3)
        extra = {"TX1": "D18 / TX1", "RX1": "D19 / RX1"}.get(name, name)
        s.text(px - 30, py + 6, extra, cls="pin-label", anchor="end")
    s.multiline(
        ax + 20,
        ay + ah - 55,
        ["USB: Native USB port", "Console: 115200 baud"],
        cls="small",
        line_height=20,
    )

    # Level shifter block.
    lx, ly, lw, lh = 485, 165, 320, 455
    s.rect(lx, ly, lw, lh, cls="shifter")
    s.text(lx + lw / 2, ly + 34, "U2  4-CHANNEL LEVEL SHIFTER", cls="block-title", anchor="middle")
    s.text(lx + lw / 2, ly + 58, "HiLetgo BSS138-style module", cls="small", anchor="middle")
    lv_points = {
        "LV": (lx - 16, ly + 110),
        "LV1": (lx - 16, ly + 185),
        "LV2": (lx - 16, ly + 260),
        "GND": (lx - 16, ly + 335),
    }
    hv_points = {
        "HV": (lx + lw + 16, ly + 110),
        "HV1": (lx + lw + 16, ly + 185),
        "HV2": (lx + lw + 16, ly + 260),
        "GND": (lx + lw + 16, ly + 335),
    }
    for name, (px, py) in lv_points.items():
        s.line(px - 18, py, px + 18, py, cls="pin")
        s.circle(px - 18, py, 3)
        s.text(px + 27, py + 6, name, cls="pin-label")
    for name, (px, py) in hv_points.items():
        s.line(px - 18, py, px + 18, py, cls="pin")
        s.circle(px + 18, py, 3)
        s.text(px - 27, py + 6, name, cls="pin-label", anchor="end")
    s.line(lx + 55, ly + 185, lx + lw - 55, ly + 185, cls="wiretx")
    s.line(lx + 55, ly + 260, lx + lw - 55, ly + 260, cls="wirerx")
    s.text(lx + lw / 2, ly + 177, "CHANNEL 1", cls="tiny", anchor="middle")
    s.text(lx + lw / 2, ly + 252, "CHANNEL 2", cls="tiny", anchor="middle")
    s.multiline(
        lx + 20,
        ly + lh - 52,
        ["Channels 3 and 4: unused", "On-board pull-ups: nominally 10 kΩ"],
        cls="small",
        line_height=20,
    )

    # Primary wiring: Due to shifter.
    s.path([due_pins["3V3"], (410, due_pins["3V3"][1]), (410, lv_points["LV"][1]),
            (lv_points["LV"][0] - 18, lv_points["LV"][1])], cls="wire3")
    s.text(405, lv_points["LV"][1] - 10, "+3V3", cls="net", anchor="end")
    s.path([due_pins["TX1"], (425, due_pins["TX1"][1]), (425, lv_points["LV1"][1]),
            (lv_points["LV1"][0] - 18, lv_points["LV1"][1])], cls="wiretx", marker="arrow-blue")
    s.path([(lv_points["LV2"][0] - 18, lv_points["LV2"][1]), (425, lv_points["LV2"][1]),
            (425, due_pins["RX1"][1]), due_pins["RX1"]], cls="wirerx", marker="arrow-green")
    s.path([due_pins["GND"], (445, due_pins["GND"][1]), (445, lv_points["GND"][1]),
            (lv_points["GND"][0] - 18, lv_points["GND"][1])], cls="ground")

    # Harness connectors.
    j1 = connector(s, 945, 175, "J1  MIDDLE PLUG")
    j2 = connector(s, 1275, 175, "J2  UNUSED END PLUG", end=True)

    # Tesla module block connected to J1.
    mx, my, mw, mh = 945, 545, 270, 150
    s.rect(mx, my, mw, mh, cls="module")
    s.text(mx + mw / 2, my + 34, "TESLA MODULE BMB", cls="block-title", anchor="middle")
    s.text(mx + mw / 2, my + 60, "Original isolated slave board", cls="small", anchor="middle")
    s.multiline(
        mx + mw / 2,
        my + 93,
        ["Plugs into J1", "Cell-tap side stays attached"],
        cls="small",
        line_height=21,
        anchor="middle",
    )
    for x in (985, 1080, 1175):
        s.line(x, 515, x, my, cls="wire")
    s.text(1080, 532, "mated connection", cls="tiny", anchor="middle")

    # Due +5 V header to shifter and connector pins 1/5.
    # Route below U2 to keep the serial nets visually separate.
    s.path([due_pins["+5V"], (390, due_pins["+5V"][1]), (390, 655),
            (885, 655), (885, hv_points["HV"][1]),
            (hv_points["HV"][0] + 18, hv_points["HV"][1])], cls="wire5")
    s.circle(885, hv_points["HV"][1])
    s.text(894, hv_points["HV"][1] - 10, "+5V_BMB", cls="net")
    s.path([(885, hv_points["HV"][1]), (885, j1[1][1]), j1[1]], cls="wire5")
    s.path([(885, j1[5][1]), j1[5]], cls="wire5")
    s.path([(885, j1[1][1]), (910, j1[1][1]), (910, 795), (1240, 795),
            (1240, j2[1][1]), j2[1]], cls="wire5")
    s.path([(1240, j2[5][1]), j2[5]], cls="wire5")

    # Common logic ground rail, sourced from the Due ground header.
    s.path([(445, lv_points["GND"][1]), (445, 875), (890, 875),
            (890, hv_points["GND"][1]), (hv_points["GND"][0] + 18, hv_points["GND"][1])], cls="ground")
    ground_symbol(s, 445, 875)
    s.circle(445, 875)
    s.path([(890, 875), (920, 875), (920, j1[3][1]), j1[3]], cls="ground")
    s.path([j1[8], (1240, j1[8][1]), (1240, 820), (1588, 820),
            (1588, j2[8][1]), j2[8]], cls="ground")
    s.path([(920, j1[3][1]), (920, 840), (1235, 840), (1235, j2[3][1]), j2[3]], cls="ground")
    s.circle(920, j1[3][1])

    # Outgoing TX from shifter to both J1 RX pins.
    tx_start = (hv_points["HV1"][0] + 18, hv_points["HV1"][1])
    s.path([tx_start, (860, tx_start[1]), (860, j1[2][1]), j1[2]], cls="wiretx", marker="arrow-blue")
    s.path([(860, tx_start[1]), (900, tx_start[1]), (900, 135), (1240, 135),
            (1240, j1[7][1]), j1[7]], cls="wiretx", marker="arrow-blue")
    s.circle(860, tx_start[1])
    s.text(835, tx_start[1] - 12, "BMS_TX →", cls="net", anchor="end")

    # J1 TX outputs chain to J2 RX inputs.
    s.path([j1[4], (895, j1[4][1]), (895, 720), (1215, 720),
            (1215, j2[2][1]), j2[2]], cls="wirerx", marker="arrow-green")
    s.path([j1[9], (1230, j1[9][1]), (1230, 120), (1575, 120),
            (1575, j2[7][1]), j2[7]], cls="wirerx", marker="arrow-green")

    # Loopback jumpers at unused J2.
    s.path([j2[2], (1248, j2[2][1]), (1248, j2[4][1]), j2[4]], cls="wirerx")
    s.path([j2[7], (1580, j2[7][1]), (1580, j2[9][1]), j2[9]], cls="wirerx")
    s.text(1410, 475, "LOOPBACK CAP: JP1 = pins 2–4", cls="net", anchor="middle")
    s.text(1410, 497, "JP2 = pins 7–9", cls="net", anchor="middle")

    # Return from J2 TX pins to level shifter HV2.
    rx_end = (hv_points["HV2"][0] + 18, hv_points["HV2"][1])
    s.path([j2[4], (1220, j2[4][1]), (1220, 735), (835, 735),
            (835, rx_end[1]), rx_end], cls="wirerx", marker="arrow-green")
    s.path([j2[9], (1590, j2[9][1]), (1590, 760), (835, 760),
            (835, rx_end[1])], cls="wirerx")
    s.circle(835, rx_end[1])
    s.text(845, rx_end[1] - 12, "← BMS_RX", cls="net")

    # Fault pins: tied by harness but intentionally unused in this base wiring.
    s.path([j1[6], (1255, j1[6][1]), (1255, j2[6][1]), j2[6]], cls="wirefault")
    s.path([j1[10], (1265, j1[10][1]), (1265, j2[10][1]), j2[10]], cls="wirefault")
    # Notes / warnings.
    s.rect(395, 895, 760, 95, cls="warn-box")
    s.multiline(
        415,
        922,
        [
            "BENCH-TEST LIMITATION: U2 is an I²C MOSFET shifter with 10 kΩ pull-ups.",
            "At 612.5 kbaud it may have slow rising edges, especially with the 24-inch harness.",
            "Do not rely on this prototype interface as the only charge/discharge protection.",
        ],
        cls="warning",
        line_height=23,
    )
    s.rect(1180, 840, 365, 150, cls="note-box")
    s.multiline(
        1200,
        868,
        [
            "ASSEMBLY NOTES",
            "• Due +5 V header powers U2 and the BMB.",
            "• Use molded connector cavity numbers.",
            "• Verify every net with power removed.",
            "• J2 +5 V pins remain live: insulate J2.",
            "• This is UART-like serial, not CAN.",
        ],
        cls="note",
        line_height=21,
    )

    s.text(
        55,
        1002,
        "Reference: collin80/TeslaBMS wiring.pdf • Drawing is for the documented 10-pin Model S/X BMB interface; verify harness revision by continuity.",
        cls="footer",
    )
    s.text(1545, 1002, "Rev A • 2026-08-01", cls="footer", anchor="end")
    return s.finish()


def build_production_svg() -> str:
    """Build the table-layout schematic with J1 shown as one mated connector."""
    s = SVG()
    s.rect(18, 18, WIDTH - 36, HEIGHT - 36, cls="sheet", rx=0)
    s.text(55, 65, "Arduino Due to Tesla Model S/X module BMS", cls="title")
    s.text(
        55,
        92,
        "Physical table order • one 6S module • EVTV two-module harness • BMB powered from Due +5 V",
        cls="subtitle",
    )

    # Arduino Due.
    ax, ay, aw, ah = 60, 185, 280, 440
    s.rect(ax, ay, aw, ah, cls="block")
    s.text(ax + aw / 2, ay + 36, "U1  ARDUINO DUE", cls="block-title", anchor="middle")
    s.text(ax + aw / 2, ay + 61, "SAM3X8E • 3.3 V I/O", cls="small", anchor="middle")
    due = {
        "3V3": (ax + aw + 18, ay + 110),
        "+5V": (ax + aw + 18, ay + 170),
        "TX1": (ax + aw + 18, ay + 240),
        "RX1": (ax + aw + 18, ay + 310),
        "GND": (ax + aw + 18, ay + 380),
    }
    due_labels = {
        "3V3": "3V3",
        "+5V": "+5V header",
        "TX1": "D18 / TX1",
        "RX1": "D19 / RX1",
        "GND": "GND",
    }
    for name, (px, py) in due.items():
        s.line(px - 40, py, px, py, cls="pin")
        s.circle(px, py, 3)
        s.text(px - 48, py + 6, due_labels[name], cls="pin-label", anchor="end")
    s.multiline(
        ax + 20,
        ay + ah - 20,
        ["Native USB: firmware + console", "Serial console: 115200 baud"],
        cls="small",
        line_height=18,
    )

    # Level shifter.
    lx, ly, lw, lh = 455, 185, 300, 440
    s.rect(lx, ly, lw, lh, cls="shifter")
    s.text(lx + lw / 2, ly + 36, "U2  LEVEL SHIFTER", cls="block-title", anchor="middle")
    s.text(lx + lw / 2, ly + 61, "HiLetgo BSS138-style board", cls="small", anchor="middle")
    low = {
        "LV": (lx - 18, ly + 110),
        "LV1": (lx - 18, ly + 240),
        "LV2": (lx - 18, ly + 310),
        "GND": (lx - 18, ly + 380),
    }
    high = {
        "HV": (lx + lw + 18, ly + 170),
        "HV1": (lx + lw + 18, ly + 240),
        "HV2": (lx + lw + 18, ly + 310),
        "GND": (lx + lw + 18, ly + 380),
    }
    for name, (px, py) in low.items():
        s.line(px, py, px + 36, py, cls="pin")
        s.circle(px, py, 3)
        s.text(px + 45, py + 6, name, cls="pin-label")
    for name, (px, py) in high.items():
        s.line(px - 36, py, px, py, cls="pin")
        s.circle(px, py, 3)
        s.text(px - 45, py + 6, name, cls="pin-label", anchor="end")
    s.line(lx + 65, low["LV1"][1], lx + lw - 65, low["LV1"][1], cls="wiretx")
    s.line(lx + 65, low["LV2"][1], lx + lw - 65, low["LV2"][1], cls="wirerx")
    s.text(lx + lw / 2, low["LV1"][1] - 10, "CHANNEL 1", cls="tiny", anchor="middle")
    s.text(lx + lw / 2, low["LV2"][1] - 10, "CHANNEL 2", cls="tiny", anchor="middle")
    s.multiline(
        lx + 20,
        ly + lh - 20,
        ["Channels 3 and 4: unused", "On-board pull-ups: nominally 10 kΩ"],
        cls="small",
        line_height=18,
    )

    # Due to shifter wiring.
    s.path([due["3V3"], (398, due["3V3"][1]), (398, low["LV"][1]), low["LV"]], cls="wire3")
    s.path([due["+5V"], (410, due["+5V"][1]), (410, 150), (795, 150),
            (795, high["HV"][1]), high["HV"]], cls="wire5")
    s.path([due["TX1"], low["LV1"]], cls="wiretx", marker="arrow-blue")
    s.path([low["LV2"], due["RX1"]], cls="wirerx", marker="arrow-green")
    s.path([due["GND"], (405, due["GND"][1]), (405, low["GND"][1]), low["GND"]], cls="ground")

    # EVTV harness controller-end breakout.
    hx, hy, hw, hh = 855, 185, 245, 440
    s.rect(hx, hy, hw, hh, cls="connector")
    s.text(hx + hw / 2, hy + 36, "EVTV HARNESS", cls="block-title", anchor="middle")
    s.text(hx + hw / 2, hy + 61, "large controller-end plug", cls="small", anchor="middle")
    harness_ports = {
        "+5V": (hx - 18, high["HV"][1]),
        "TX": (hx - 18, high["HV1"][1]),
        "RX": (hx - 18, high["HV2"][1]),
        "GND": (hx - 18, high["GND"][1]),
    }
    for name, (px, py) in harness_ports.items():
        s.line(px, py, px + 38, py, cls="pin")
        s.circle(px, py, 3)
        label = {"TX": "BMS_TX", "RX": "BMS_RX"}.get(name, name)
        s.text(px + 48, py + 6, label, cls="pin-label")
    s.path([high["HV"], harness_ports["+5V"]], cls="wire5")
    s.path([high["HV1"], harness_ports["TX"]], cls="wiretx", marker="arrow-blue")
    s.path([harness_ports["RX"], high["HV2"]], cls="wirerx", marker="arrow-green")
    s.path([high["GND"], harness_ports["GND"]], cls="ground")

    # Simplified factory-wired cable bundle leaving the harness.
    cable_x = hx + hw
    s.line(cable_x, hy + 115, cable_x + 70, hy + 115, cls="wire")
    s.line(cable_x, hy + 125, cable_x + 70, hy + 125, cls="wire")
    s.line(cable_x, hy + 135, cable_x + 70, hy + 135, cls="wire")
    s.text(cable_x + 35, hy + 102, "factory-wired cable", cls="tiny", anchor="middle")
    s.multiline(
        hx + 20,
        hy + 80,
        [
            "Internal signal path:",
            "BMS_TX → J1/module → J2",
            "loopback → BMS_RX",
            "+5 V and GND feed the BMB",
        ],
        cls="small",
        line_height=23,
    )

    # J2 loopback is the only harness connector requiring user pin wiring.
    jx, jy, jw, jh = 875, 690, 360, 190
    s.rect(jx, jy, jw, jh, cls="loopbox")
    s.text(jx + jw / 2, jy + 30, "J2  UNUSED END PLUG", cls="block-title", anchor="middle")
    s.text(jx + jw / 2, jy + 54, "LOOPBACK CAP — only these two jumpers", cls="small", anchor="middle")
    # Two jumper circuits, drawn as connector cavities.
    for base_y, left_pin, right_pin, jp in (
        (jy + 100, "2", "4", "JP1"),
        (jy + 142, "7", "9", "JP2"),
    ):
        s.circle(jx + 80, base_y, 7, cls="junction")
        s.circle(jx + 280, base_y, 7, cls="junction")
        s.path([(jx + 80, base_y), (jx + 125, base_y), (jx + 125, base_y - 15),
                (jx + 235, base_y - 15), (jx + 235, base_y), (jx + 280, base_y)], cls="wirerx")
        s.text(jx + 58, base_y + 6, f"pin {left_pin}", cls="pin-label", anchor="end")
        s.text(jx + 302, base_y + 6, f"pin {right_pin}", cls="pin-label")
        s.text(jx + jw / 2, base_y - 23, jp, cls="net", anchor="middle")
    s.path([(hx + hw / 2, hy + hh), (hx + hw / 2, jy)], cls="wire")
    s.text(jx + jw / 2, jy + jh - 12, "Other J2 pins remain live — cap and insulate", cls="tiny", anchor="middle")

    # J1 and the Tesla module at the far right, represented as one plug-in action.
    mx, my, mw, mh = 1320, 190, 225, 480
    s.rect(mx, my, mw, mh, cls="module")
    s.text(mx + mw / 2, my + 38, "TESLA 6S MODULE", cls="block-title", anchor="middle")
    s.text(mx + mw / 2, my + 64, "original BMB attached", cls="small", anchor="middle")
    # Module cells as a conventional six-cell stack symbol.
    cell_y = my + 120
    for index in range(6):
        cy = cell_y + index * 43
        s.line(mx + 70, cy, mx + 155, cy, cls="wire")
        s.line(mx + 87, cy - 7, mx + 87, cy + 7, cls="wire")
        s.line(mx + 105, cy - 12, mx + 105, cy + 12, cls="wire")
        s.text(mx + 170, cy + 5, f"cell group {index + 1}", cls="tiny")
    s.text(mx + mw / 2, my + mh - 28, "18–25.2 V module", cls="small", anchor="middle")

    # J1 is one mated connector, deliberately without pin-level wiring.
    p_x, p_y, p_w, p_h = 1235, 330, 105, 190
    s.rect(p_x, p_y, p_w, p_h, cls="connector", rx=3)
    s.text(p_x + p_w / 2, p_y + 32, "J1", cls="block-title", anchor="middle")
    s.text(p_x + p_w / 2, p_y + 56, "MIDDLE", cls="small", anchor="middle")
    s.text(p_x + p_w / 2, p_y + 78, "PLUG", cls="small", anchor="middle")
    for i in range(5):
        py = p_y + 102 + i * 16
        s.circle(p_x + 38, py, 3)
        s.circle(p_x + 67, py, 3)
        s.line(p_x + 38, py, p_x + 67, py, cls="pin")
    s.line(p_x + p_w, p_y + p_h / 2, mx, p_y + p_h / 2, cls="wire")
    s.path([(cable_x + 70, hy + 125), (1195, hy + 125), (1195, p_y + p_h / 2),
            (p_x, p_y + p_h / 2)], cls="wire")
    s.multiline(
        1288,
        560,
        ["Plug J1 directly into", "the module BMB.", "No individual J1 wiring."],
        cls="note",
        line_height=22,
        anchor="middle",
    )

    # Ground symbol and notes.
    s.path([(405, due["GND"][1]), (405, 650)], cls="ground")
    ground_symbol(s, 405, 650)
    s.rect(60, 730, 700, 140, cls="warn-box")
    s.multiline(
        82,
        760,
        [
            "BENCH-TEST LIMITATION",
            "U2 is an I²C MOSFET shifter with 10 kΩ pull-ups. At 612.5 kbaud it may",
            "have slow rising edges, especially with the 24-inch harness. Do not rely",
            "on this prototype interface as the only charge/discharge protection.",
        ],
        cls="warning",
        line_height=25,
    )
    s.rect(60, 895, 1175, 82, cls="note-box")
    s.multiline(
        80,
        922,
        [
            "Power the Due normally through USB or VIN; use its +5 V header as an output here. This is UART-like serial, not CAN.",
            "Before power-up, verify the harness revision and J2 cavity numbers with a continuity meter. No 120 Ω terminator is used.",
        ],
        cls="note",
        line_height=25,
    )
    s.text(
        55,
        1002,
        "Reference: collin80/TeslaBMS wiring.pdf • J1 is intentionally simplified because it is a complete mated harness connection.",
        cls="footer",
    )
    s.text(1545, 1002, "Rev B • 2026-08-01", cls="footer", anchor="end")
    return s.finish()


def build_bench_svg() -> str:
    """Build the direct stock-pigtail bench wiring schematic."""
    s = SVG()
    s.rect(18, 18, WIDTH - 36, HEIGHT - 36, cls="sheet", rx=0)
    s.text(55, 65, "BENCH — Arduino Due to one Tesla module via stock pigtail", cls="title")
    s.text(
        55,
        92,
        "No EVTV harness • no loopback jumpers • original 10-pin BMB connector remains plugged into module",
        cls="subtitle",
    )

    # Arduino Due.
    ax, ay, aw, ah = 55, 175, 280, 455
    s.rect(ax, ay, aw, ah, cls="block")
    s.text(ax + aw / 2, ay + 38, "U1  ARDUINO DUE", cls="block-title", anchor="middle")
    s.text(ax + aw / 2, ay + 64, "powered normally by USB or VIN", cls="small", anchor="middle")
    due = {
        "3V3": (ax + aw + 18, ay + 115),
        "+5V": (ax + aw + 18, ay + 180),
        "TX1": (ax + aw + 18, ay + 255),
        "RX1": (ax + aw + 18, ay + 330),
        "GND": (ax + aw + 18, ay + 405),
    }
    labels = {"3V3": "3V3", "+5V": "+5V header", "TX1": "D18 / TX1",
              "RX1": "D19 / RX1", "GND": "GND"}
    for name, (px, py) in due.items():
        s.line(px - 40, py, px, py, cls="pin")
        s.circle(px, py, 3)
        s.text(px - 48, py + 6, labels[name], cls="pin-label", anchor="end")

    # Existing BSS138 level-shifter board.
    lx, ly, lw, lh = 450, 175, 300, 455
    s.rect(lx, ly, lw, lh, cls="shifter")
    s.text(lx + lw / 2, ly + 38, "U2  LEVEL SHIFTER", cls="block-title", anchor="middle")
    s.text(lx + lw / 2, ly + 64, "HiLetgo BSS138-style board", cls="small", anchor="middle")
    low = {"LV": (lx - 18, due["3V3"][1]), "LV1": (lx - 18, due["TX1"][1]),
           "LV2": (lx - 18, due["RX1"][1]), "GND": (lx - 18, due["GND"][1])}
    high = {"HV": (lx + lw + 18, due["+5V"][1]), "HV1": (lx + lw + 18, due["TX1"][1]),
            "HV2": (lx + lw + 18, due["RX1"][1]), "GND": (lx + lw + 18, due["GND"][1])}
    for name, (px, py) in low.items():
        s.line(px, py, px + 36, py, cls="pin")
        s.circle(px, py, 3)
        s.text(px + 45, py + 6, name, cls="pin-label")
    for name, (px, py) in high.items():
        s.line(px - 36, py, px, py, cls="pin")
        s.circle(px, py, 3)
        s.text(px - 45, py + 6, name, cls="pin-label", anchor="end")
    s.line(lx + 65, low["LV1"][1], lx + lw - 65, low["LV1"][1], cls="wiretx")
    s.line(lx + 65, low["LV2"][1], lx + lw - 65, low["LV2"][1], cls="wirerx")
    s.text(lx + lw / 2, low["LV1"][1] - 10, "CHANNEL 1", cls="tiny", anchor="middle")
    s.text(lx + lw / 2, low["LV2"][1] - 10, "CHANNEL 2", cls="tiny", anchor="middle")
    s.multiline(lx + 22, ly + lh - 30, ["Channels 3 and 4: unused",
                "10 kΩ pull-ups: bench testing only"], cls="small", line_height=18)

    s.path([due["3V3"], low["LV"]], cls="wire3")
    s.path([due["+5V"], (395, due["+5V"][1]), (395, 140), (790, 140),
            (790, high["HV"][1]), high["HV"]], cls="wire5")
    s.path([due["TX1"], low["LV1"]], cls="wiretx", marker="arrow-blue")
    s.path([low["LV2"], due["RX1"]], cls="wirerx", marker="arrow-green")
    s.path([due["GND"], low["GND"]], cls="ground")

    # Stock cut pigtail splice block.  Pin numbers, not left/right orientation,
    # are authoritative because viewing the mating face reverses the connector.
    px, py, pw, ph = 910, 140, 370, 560
    s.rect(px, py, pw, ph, cls="connector")
    s.text(px + pw / 2, py + 35, "STOCK 10-WIRE BMB PIGTAIL", cls="block-title", anchor="middle")
    s.text(px + pw / 2, py + 60, "connector stays plugged in; splice cut wire ends", cls="small", anchor="middle")

    groups = [
        ("+5V_BMB", "pins 1 + 5", "two RED wires", py + 125, "wire5"),
        ("BMB_RX", "pins 2 + 7", "BLUE p2 + YELLOW p7", py + 220, "wiretx"),
        ("BMB_TX", "pins 4 + 9", "BLUE p4 + YELLOW p9", py + 315, "wirerx"),
        ("GND", "pins 3 + 8", "two GREEN wires", py + 410, "ground"),
    ]
    pigtail_ports: dict[str, tuple[int, int]] = {}
    for net, pins, colors, gy, wire_cls in groups:
        port = (px - 18, gy)
        pigtail_ports[net] = port
        s.line(port[0], gy, px + 45, gy, cls=wire_cls)
        s.circle(port[0], gy, 3)
        s.circle(px + 45, gy, 5)
        s.path([(px + 45, gy), (px + 85, gy - 18), (px + 115, gy - 18)], cls=wire_cls)
        s.path([(px + 45, gy), (px + 85, gy + 18), (px + 115, gy + 18)], cls=wire_cls)
        s.text(px + 130, gy - 10, f"{net}: {pins}", cls="net")
        s.text(px + 130, gy + 15, colors, cls="small")

    # Fault wires are not needed for the basic serial bench test.
    fy = py + 495
    s.line(px + 45, fy - 14, px + 115, fy - 14, cls="wirefault")
    s.line(px + 45, fy + 14, px + 115, fy + 14, cls="wirefault")
    s.line(px + 112, fy - 22, px + 122, fy - 6, cls="nc")
    s.line(px + 112, fy + 6, px + 122, fy + 22, cls="nc")
    s.text(px + 130, fy - 5, "FAULT: pins 6 + 10 (GRAY)", cls="net")
    s.text(px + 130, fy + 19, "leave separate; cap and insulate", cls="small")

    # Connections from shifter/power to the four splice bundles.
    s.path([high["HV"], (835, high["HV"][1]), (835, pigtail_ports["+5V_BMB"][1]),
            pigtail_ports["+5V_BMB"]], cls="wire5")
    s.path([high["HV1"], (850, high["HV1"][1]), (850, pigtail_ports["BMB_RX"][1]),
            pigtail_ports["BMB_RX"]], cls="wiretx", marker="arrow-blue")
    s.path([pigtail_ports["BMB_TX"], (865, pigtail_ports["BMB_TX"][1]),
            (865, high["HV2"][1]), high["HV2"]], cls="wirerx", marker="arrow-green")
    s.path([high["GND"], (880, high["GND"][1]), (880, pigtail_ports["GND"][1]),
            pigtail_ports["GND"]], cls="ground")
    s.path([(395, due["GND"][1]), (395, 665)], cls="ground")
    ground_symbol(s, 395, 665)

    # Module shown as one mated load at far right.
    mx, my, mw, mh = 1330, 195, 215, 455
    s.rect(mx, my, mw, mh, cls="module")
    s.text(mx + mw / 2, my + 38, "TESLA 6S MODULE", cls="block-title", anchor="middle")
    s.text(mx + mw / 2, my + 64, "original BMB attached", cls="small", anchor="middle")
    for index in range(6):
        cy = my + 125 + index * 45
        s.line(mx + 45, cy, mx + 130, cy, cls="wire")
        s.line(mx + 62, cy - 7, mx + 62, cy + 7, cls="wire")
        s.line(mx + 80, cy - 12, mx + 80, cy + 12, cls="wire")
        s.text(mx + 142, cy + 5, str(index + 1), cls="tiny")
    s.text(mx + mw / 2, my + mh - 28, "18–25.2 V module", cls="small", anchor="middle")
    s.path([(px + pw, py + ph / 2), (1305, py + ph / 2), (1305, my + mh / 2),
            (mx, my + mh / 2)], cls="wire")
    s.text(1305, my + mh / 2 - 14, "already mated", cls="tiny", anchor="middle")

    # Assembly sequence and cautions.
    s.rect(55, 740, 730, 205, cls="note-box")
    s.multiline(
        78,
        770,
        [
            "BENCH SPLICE CHECKLIST",
            "1. With all power removed, identify every wire by molded connector cavity number.",
            "2. Tie pins 1+5 to Due +5 V; tie pins 3+8 to Due GND.",
            "3. Tie pins 2+7 to shifter HV1 (commands going into BMB).",
            "4. Tie pins 4+9 to shifter HV2 (responses coming out of BMB).",
            "5. Cap pins 6 and 10 separately. Insulate every splice before applying power.",
        ],
        cls="note",
        line_height=28,
    )
    s.rect(820, 740, 725, 205, cls="warn-box")
    s.multiline(
        843,
        770,
        [
            "DO NOT TRUST WIRE COLOR FOR UART DIRECTION",
            "Pins 2 and 4 are both blue; pins 7 and 9 are both yellow. A color-only",
            "splice can connect two outputs together or reverse TX/RX. Confirm cavity",
            "numbers with continuity mode while the module and all power are disconnected.",
            "The BSS138 shifter is marginal at 612.5 kbaud; this is an unloaded bench test.",
        ],
        cls="warning",
        line_height=29,
    )
    s.text(
        55,
        1002,
        "Reference: collin80/TeslaBMS wiring.pdf • UART-like serial, not CAN • no 120 Ω terminator • module terminals can deliver destructive fault current.",
        cls="footer",
    )
    s.text(1545, 1002, "Bench Rev A • 2026-08-01", cls="footer", anchor="end")
    return s.finish()


def build_connector_svg() -> str:
    """Build a continuity-check worksheet for the stock 10-cavity pigtail.

    The project wiring drawing supplies the electrical cavity numbers, but it
    does not define a latch-up physical viewing direction.  Showing both faces
    as explicit mirrors prevents the common mistake of transferring a mating-
    face pinout directly to the wire-entry side.
    """
    s = SVG()
    s.rect(18, 18, WIDTH - 36, HEIGHT - 36, cls="sheet", rx=0)
    s.text(55, 62, "Stock Tesla BMB connector — cavity / continuity worksheet", cls="title")
    s.text(
        55,
        90,
        "Molex 15-97-5101 • 10 cavities, 2 × 5 • opposite faces are horizontal mirrors",
        cls="subtitle",
    )

    pin_info = {
        1: ("+5 V", "RED", "#ef4444", "#ffffff"),
        2: ("BMB RX", "BLUE", "#2563eb", "#ffffff"),
        3: ("GND", "GREEN", "#16a34a", "#ffffff"),
        4: ("BMB TX", "BLUE", "#2563eb", "#ffffff"),
        5: ("+5 V", "RED", "#ef4444", "#ffffff"),
        6: ("FAULT", "GRAY", "#9ca3af", "#111827"),
        7: ("BMB RX", "YELLOW", "#facc15", "#111827"),
        8: ("GND", "GREEN", "#16a34a", "#ffffff"),
        9: ("BMB TX", "YELLOW", "#facc15", "#111827"),
        10: ("FAULT", "GRAY", "#9ca3af", "#111827"),
    }

    def face(x: int, title: str, subtitle: str, rows: tuple[tuple[int, ...], ...]) -> None:
        s.text(x + 315, 142, title, cls="block-title", anchor="middle")
        s.text(x + 315, 166, subtitle, cls="small", anchor="middle")
        s.rect(x, 190, 630, 260, cls="connector", rx=18)
        # Generic polarization/latch cue, deliberately not assigned to a
        # cavity orientation because the source schematic does not establish it.
        s.add(
            f'<path d="M{x + 255},190 L{x + 275},170 L{x + 355},170 '
            f'L{x + 375},190" fill="#e5e7eb" stroke="#374151" stroke-width="2"/>'
        )
        s.text(x + 315, 218, "LATCH / KEY SIDE", cls="tiny", anchor="middle")
        for row_i, row in enumerate(rows):
            cy = 270 + row_i * 110
            for col_i, pin in enumerate(row):
                cx = x + 75 + col_i * 120
                function, color_name, fill, text_fill = pin_info[pin]
                s.add(
                    f'<circle cx="{cx}" cy="{cy}" r="38" fill="{fill}" '
                    'stroke="#111827" stroke-width="2.5"/>'
                )
                s.add(
                    f'<text x="{cx}" y="{cy + 9}" text-anchor="middle" '
                    f'style="font:bold 26px Arial;fill:{text_fill}">{pin}</text>'
                )
                s.text(cx, cy + 58, function, cls="net", anchor="middle")
                s.text(cx, cy + 78, color_name, cls="tiny", anchor="middle")

    # This is the row order used by the TeslaBMS project schematic.  View B is
    # exactly its horizontal mirror, as seen from the opposite connector face.
    face(
        55,
        "VIEW A — REFERENCE FACE",
        "row order from the project wiring drawing",
        ((6, 7, 8, 9, 10), (1, 2, 3, 4, 5)),
    )
    face(
        915,
        "VIEW B — OPPOSITE FACE",
        "horizontal mirror of View A (wire side vs mating side)",
        ((10, 9, 8, 7, 6), (5, 4, 3, 2, 1)),
    )

    s.rect(55, 485, 1490, 105, cls="warn-box")
    s.multiline(
        80,
        515,
        [
            "ORIENTATION CHECK — DO NOT PICK A VIEW FROM THE LATCH ALONE",
            "Find a molded cavity ID (ideally 1, 5, 6, or 10) on your actual housing. Use the view that places that ID at the same corner.",
            "The molded ID is authoritative. The public TeslaBMS wiring drawing gives row numbers, but does not label its physical viewing face.",
        ],
        cls="warning",
        line_height=27,
    )

    s.rect(55, 620, 760, 315, cls="note-box")
    s.multiline(
        80,
        652,
        [
            "SAFE CONTINUITY PROCEDURE",
            "1. Remove Due USB, +5 V, charger, load, and every external connection.",
            "2. Confirm 0 V on the pigtail wires before selecting continuity mode.",
            "3. Unplug the 10-pin communications pigtail from the BMB if accessible.",
            "   Leave the BMB cell-sense connections alone; do not disturb their order.",
            "4. Touch one fine probe to one female terminal; touch the other to cut wires.",
            "5. Label the one wire that beeps P1…P10. Avoid bridging adjacent terminals.",
            "6. Recheck every label from the opposite end before making any splice.",
        ],
        cls="note",
        line_height=33,
    )

    s.rect(845, 620, 700, 315, cls="block")
    s.text(870, 654, "CONTINUITY RECORD", cls="block-title")
    columns = [870, 955, 1090, 1240, 1390]
    headers = ["PIN", "FUNCTION", "FACTORY", "WIRE LABEL", "✓"]
    for x, header in zip(columns, headers):
        s.text(x, 686, header, cls="net")
    rows = [
        ("1 + 5", "+5 V", "RED"),
        ("3 + 8", "GND", "GREEN"),
        ("2 + 7", "BMB RX", "BLUE / YELLOW"),
        ("4 + 9", "BMB TX", "BLUE / YELLOW"),
        ("6, 10", "FAULT", "GRAY; separate"),
    ]
    for index, values in enumerate(rows):
        y = 722 + index * 38
        s.line(865, y + 13, 1520, y + 13, cls="nc")
        for x, value in zip(columns[:3], values):
            s.text(x, y, value, cls="small")
        s.text(1240, y, "________________", cls="small")
        s.add(
            f'<rect x="1392" y="{y - 17}" width="20" height="20" '
            'fill="#ffffff" stroke="#374151" stroke-width="1.5"/>'
        )
    s.multiline(
        870,
        907,
        [
            "If the connector remains plugged into the BMB, internal paths may create",
            "extra or weak beeps. Do not infer a cavity number from resistance alone.",
        ],
        cls="tiny",
        line_height=17,
    )

    s.text(
        55,
        988,
        "Sources: Molex 0015975101 product data (10 circuits, 2 rows) • collin80/TeslaBMS wiring.pdf (electrical cavity mapping). Not to scale.",
        cls="footer",
    )
    s.text(1545, 988, "Connector worksheet Rev A • 2026-08-02", cls="footer", anchor="end")
    s.text(
        55,
        1013,
        "Battery module terminals remain live even when communications power is removed. Keep tools and meter probes away from the module power studs.",
        cls="warning",
    )
    return s.finish()


def find_chrome() -> Path | None:
    candidates = [
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    command = shutil.which("google-chrome") or shutil.which("chromium")
    return Path(command) if command else None


def render(svg_path: Path, svg_text: str) -> tuple[Path, Path]:
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError("Google Chrome or Chromium is required for --render")

    pdf_path = svg_path.with_suffix(".pdf")
    png_path = svg_path.with_suffix(".png")
    page_html = f"""<!doctype html>
<meta charset="utf-8">
<style>
  @page {{ size: 16in 10.5in; margin: 0; }}
  html, body {{ width: 16in; height: 10.5in; margin: 0; overflow: hidden; }}
  svg {{ display: block; width: 16in; height: 10.5in; }}
</style>
{svg_text}
"""
    with tempfile.TemporaryDirectory(prefix="tesla-bms-schematic-") as temp_dir:
        html_path = Path(temp_dir) / "schematic.html"
        html_path.write_text(page_html, encoding="utf-8")
        common = [str(chrome), "--headless=new", "--disable-gpu", "--hide-scrollbars"]
        subprocess.run(
            common + [f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer", html_path.as_uri()],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            common
            + [
                f"--screenshot={png_path}",
                f"--window-size={WIDTH},{HEIGHT}",
                "--force-device-scale-factor=1",
                html_path.as_uri(),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return pdf_path, png_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent,
        help="output directory (default: next to this script)",
    )
    parser.add_argument(
        "--variant",
        choices=("all", "bench", "production", "connector"),
        default="all",
        help="diagram variant to generate (default: all)",
    )
    parser.add_argument("--render", action="store_true", help="also make PDF and PNG with Chrome")
    args = parser.parse_args()

    variants = {
        "bench": ("tesla-bms-bench-stock-pigtail.svg", build_bench_svg),
        "production": ("tesla-bms-production-evtv-harness.svg", build_production_svg),
        "connector": ("tesla-bms-stock-connector-cavity-map.svg", build_connector_svg),
    }
    selected = variants.items() if args.variant == "all" else [(args.variant, variants[args.variant])]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for variant, (filename, builder) in selected:
        svg_text = builder()
        svg_path = (args.output_dir / filename).resolve()
        svg_path.write_text(svg_text, encoding="utf-8")
        print(svg_path)
        if args.render:
            for path in render(svg_path, svg_text):
                print(path)

        # Keep the original filename as a convenient alias for the current
        # bench instructions already open in the user's editor.
        if variant == "bench" and args.variant in ("all", "bench"):
            alias = (args.output_dir / "tesla-bms-single-module.svg").resolve()
            alias.write_text(svg_text, encoding="utf-8")
            print(alias)
            if args.render:
                for path in render(alias, svg_text):
                    print(path)


if __name__ == "__main__":
    main()
