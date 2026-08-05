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
    """Build the table-layout schematic for a fully-populated 6-port EVTV harness."""
    s = SVG()
    s.rect(18, 18, WIDTH - 36, HEIGHT - 36, cls="sheet", rx=0)
    s.text(55, 65, "Arduino Due to Tesla Model S/X module BMS", cls="title")
    s.text(
        55,
        92,
        "EVTV 6-port production harness • all six 6S modules pre-connected • BMB chain powered from Due +5 V",
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

    # EVTV harness controller-end plug — the single connector the user wires to.
    hx, hy, hw, hh = 855, 185, 260, 440
    s.rect(hx, hy, hw, hh, cls="loopbox")
    s.text(hx + hw / 2, hy + 36, "EVTV HARNESS", cls="block-title", anchor="middle")
    s.text(hx + hw / 2, hy + 61, "controller-end plug", cls="small", anchor="middle")
    s.text(hx + hw / 2, hy + 82, "(the only user-wired connector)", cls="tiny", anchor="middle")
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
    s.multiline(
        hx + 18,
        hy + 200,
        [
            "Factory-terminated harness:",
            "carries +5V / TX / RX / GND",
            "and daisy-chains all six",
            "module BMBs internally.",
            "No jumpers, no loopback cap.",
        ],
        cls="small",
        line_height=22,
    )

    # Factory-terminated cable trunk leaving the harness toward the modules.
    cable_x = hx + hw
    trunk_y = hy + hh / 2
    for dy in (-8, 0, 8):
        s.line(cable_x, trunk_y + dy, cable_x + 90, trunk_y + dy, cls="wire")
    s.text(cable_x + 45, trunk_y - 20, "factory trunk", cls="tiny", anchor="middle")

    # Six modules stacked at the right, each hanging off the shared trunk.
    mx, mw, mh = 1250, 300, 60
    module_gap = 12
    top_y = 155
    trunk_top = top_y + mh / 2
    trunk_bottom = top_y + 5 * (mh + module_gap) + mh / 2
    tap_x = cable_x + 90
    # Vertical trunk running past all six module taps.
    s.line(tap_x, trunk_top, tap_x, trunk_bottom, cls="wire")
    s.circle(tap_x, trunk_y)
    for index in range(6):
        my = top_y + index * (mh + module_gap)
        s.rect(mx, my, mw, mh, cls="module")
        s.text(mx + 18, my + 24, f"MODULE {index + 1}", cls="block-title")
        s.text(mx + 18, my + 46, "6S • original BMB attached", cls="small")
        # Connector puck between trunk tap and the module.
        conn_x = mx - 60
        conn_y = my + mh / 2
        s.rect(conn_x - 22, conn_y - 14, 44, 28, cls="connector", rx=4)
        s.text(conn_x, conn_y + 5, f"P{index + 1}", cls="pin-label", anchor="middle")
        s.line(conn_x + 22, conn_y, mx, conn_y, cls="wire")
        s.line(tap_x, conn_y, conn_x - 22, conn_y, cls="wire")
        s.circle(tap_x, conn_y)

    # Ground symbol and notes.
    s.path([(405, due["GND"][1]), (405, 650)], cls="ground")
    ground_symbol(s, 405, 650)
    s.rect(60, 730, 780, 140, cls="warn-box")
    s.multiline(
        82,
        760,
        [
            "BENCH-TEST LIMITATION",
            "U2 is an I²C MOSFET shifter with 10 kΩ pull-ups. At 612.5 kbaud it may",
            "have slow rising edges over the harness run. Do not rely on this prototype",
            "interface as the only charge/discharge protection.",
        ],
        cls="warning",
        line_height=25,
    )
    s.rect(60, 895, 1485, 82, cls="note-box")
    s.multiline(
        80,
        922,
        [
            "Power the Due normally through USB or VIN; use its +5 V header as an output here. This is UART-like serial, not CAN.",
            "The 6-port EVTV harness terminates the BMB daisy chain internally — only the four controller-end wires (+5V / TX / RX / GND) need attention.",
        ],
        cls="note",
        line_height=25,
    )
    s.text(
        55,
        1002,
        "Reference: collin80/TeslaBMS wiring.pdf • Fully-populated harness — no loopback cap, no J1/J2 breakout, no user pin-level splices.",
        cls="footer",
    )
    s.text(1545, 1002, "Rev C • 2026-08-04", cls="footer", anchor="end")
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


def build_harness_plug_svg() -> str:
    """Pin map for the 12-position Molex controller-end plug of the EVTV harness."""
    s = SVG()
    s.rect(18, 18, WIDTH - 36, HEIGHT - 36, cls="sheet", rx=0)
    s.text(55, 62, "EVTV Tesla BMS harness — controller-end plug pinout", cls="title")
    s.text(
        55,
        90,
        "Molex 12-position housing • signals derived from EVTV ESP32 BMS Controller Manual v2.18 (pp. 39, 42)",
        cls="subtitle",
    )

    # (pin, signal, wire color from EVTV two-module + extension diagrams,
    #  fill for the swatch, text color, whether the pin is used).
    pin_info = {
        1:  ("FAULT",  "GRAY",         "#9ca3af", "#111827", True),
        2:  ("N.C.",   "—",            "#f3f4f6", "#6b7280", False),
        3:  ("RX",     "YELLOW",       "#facc15", "#111827", True),
        4:  ("N.C.",   "—",            "#f3f4f6", "#6b7280", False),
        5:  ("TX",     "BLUE",         "#2563eb", "#ffffff", True),
        6:  ("N.C.",   "—",            "#f3f4f6", "#6b7280", False),
        7:  ("N.C.",   "—",            "#f3f4f6", "#6b7280", False),
        8:  ("GND",    "GREEN (bank 2)","#16a34a","#ffffff", True),
        9:  ("GND",    "GREEN",        "#16a34a", "#ffffff", True),
        10: ("+5 V",   "RED",          "#ef4444", "#ffffff", True),
        11: ("+5 V",   "RED (bank 2)", "#ef4444", "#ffffff", True),
        12: ("N.C.",   "—",            "#f3f4f6", "#6b7280", False),
    }

    # Plug drawing — 2 rows × 6 columns, viewed from the wire-entry side.
    plug_x, plug_y, plug_w, plug_h = 120, 165, 900, 320
    s.rect(plug_x, plug_y, plug_w, plug_h, cls="connector", rx=14)
    s.text(plug_x + plug_w / 2, plug_y - 12, "12-position Molex plug — view LOOKING INTO the harness plug (battery-side end)", cls="small", anchor="middle")
    # Latch cue on top edge (indicative only).
    s.add(
        f'<path d="M{plug_x + plug_w/2 - 60},{plug_y} L{plug_x + plug_w/2 - 40},{plug_y - 22} '
        f'L{plug_x + plug_w/2 + 40},{plug_y - 22} L{plug_x + plug_w/2 + 60},{plug_y} Z" '
        'fill="#e5e7eb" stroke="#374151" stroke-width="2"/>'
    )
    s.text(plug_x + plug_w / 2, plug_y - 30, "LATCH", cls="tiny", anchor="middle")

    # Pin cavity layout: row 1 = pins 1..6, row 2 = pins 7..12.
    col_x = [plug_x + 95 + i * 142 for i in range(6)]
    row_y = [plug_y + 100, plug_y + 225]
    for row_i, pin_start in enumerate((1, 7)):
        for col_i in range(6):
            pin = pin_start + col_i
            cx = col_x[col_i]
            cy = row_y[row_i]
            signal, color_name, fill, text_fill, used = pin_info[pin]
            border = "#111827" if used else "#9ca3af"
            width = "3" if used else "1.8"
            s.add(
                f'<circle cx="{cx}" cy="{cy}" r="44" fill="{fill}" '
                f'stroke="{border}" stroke-width="{width}"/>'
            )
            s.add(
                f'<text x="{cx}" y="{cy + 10}" text-anchor="middle" '
                f'style="font:bold 30px Arial;fill:{text_fill}">{pin}</text>'
            )
            label_cls = "net" if used else "tiny"
            s.text(cx, cy + 68, signal, cls=label_cls, anchor="middle")
            s.text(cx, cy + 88, color_name, cls="tiny", anchor="middle")

    # Orientation note.
    s.rect(120, 510, 900, 80, cls="warn-box")
    s.multiline(
        140,
        538,
        [
            "VIEW: LOOKING INTO the harness plug — the end that connects to the batteries.",
            "Verified with a continuity meter against a real EVTV harness.",
            "The mating controller-side plug is the horizontal mirror of this view.",
        ],
        cls="warning",
        line_height=22,
    )

    # Wiring table for the Due + level shifter.
    s.rect(120, 605, 700, 335, cls="block")
    s.text(140, 640, "HOW TO WIRE THE ARDUINO DUE", cls="block-title")
    columns_x = [140, 260, 440, 640]
    headers = ["PIN", "SIGNAL", "CONNECT TO", "WIRE"]
    for x, header in zip(columns_x, headers):
        s.text(x, 673, header, cls="net")
    rows = [
        ("10", "+5 V",  "Due +5V header",        "RED"),
        ("11", "+5 V",  "same +5V rail (jumper to pin 10)", "RED"),
        ("9",  "GND",   "Due GND",               "GREEN"),
        ("8",  "GND",   "same GND rail (jumper to pin 9)",  "GREEN"),
        ("5",  "TX",    "U2 shifter HV1 (from Due TX1)", "BLUE"),
        ("3",  "RX",    "U2 shifter HV2 (to Due RX1)",   "YELLOW"),
        ("1",  "FAULT", "leave unconnected (or to a Due input, optional)", "GRAY"),
    ]
    for index, values in enumerate(rows):
        y = 705 + index * 33
        s.line(130, y + 11, 810, y + 11, cls="nc")
        for x, value in zip(columns_x, values):
            s.text(x, y, value, cls="small")

    # Signal note box.
    s.rect(840, 605, 705, 335, cls="note-box")
    s.multiline(
        862,
        640,
        [
            "SIGNAL NOTES",
            "• TX (pin 5) is data OUT of the controller — drives the BMB chain input.",
            "• RX (pin 3) is data IN to the controller — response from the BMB chain.",
            "• Pins 10/11 are both +5 V and pins 8/9 are both GND; tie them together at",
            "  the Due end. Bank 2 is only populated on ≥4-port harnesses, but bridging",
            "  is harmless on a 2-port harness (pins 8 and 11 are simply unused there).",
            "• FAULT (pin 1) is a loop that opens if any BMB trips. Optional to monitor.",
            "• NC pins (2, 4, 6, 7, 12) carry no signal in EVTV's harness wiring.",
            "• This is a 6-port fully-connected harness build — no J2 loopback needed.",
            "• The harness plug itself is a Molex 12-position housing. Verify the exact",
            "  Molex family (Mini-Fit Jr style) against your parts before ordering mating",
            "  pins or a spare housing.",
        ],
        cls="note",
        line_height=25,
    )

    s.text(
        55,
        988,
        "Sources: EVTV ESP32 BMS Controller Assembly v2.18 (Aug 2021), pp. 37–42 • Two-Module and Four-Module Extension wiring diagrams.",
        cls="footer",
    )
    s.text(1545, 988, "Harness pinout Rev B • 2026-08-04", cls="footer", anchor="end")
    s.text(
        55,
        1013,
        "Battery module terminals remain live even when the communications harness is unpowered. Keep tools away from the module power studs.",
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
        choices=("all", "bench", "production", "connector", "harness-plug"),
        default="all",
        help="diagram variant to generate (default: all)",
    )
    parser.add_argument("--render", action="store_true", help="also make PDF and PNG with Chrome")
    args = parser.parse_args()

    variants = {
        "bench": ("tesla-bms-bench-stock-pigtail.svg", build_bench_svg),
        "production": ("tesla-bms-production-evtv-harness.svg", build_production_svg),
        "connector": ("tesla-bms-stock-connector-cavity-map.svg", build_connector_svg),
        "harness-plug": ("tesla-bms-evtv-harness-plug-pinout.svg", build_harness_plug_svg),
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
