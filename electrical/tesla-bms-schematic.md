# Tesla BMS single-module schematic

Generated files:

- `tesla-bms-bench-stock-pigtail.*` — direct stock-pigtail bench wiring
- `tesla-bms-production-evtv-harness.*` — EVTV harness installation layout
- `tesla-bms-stock-connector-cavity-map.*` — mirrored connector-face diagrams and continuity worksheet
- `tesla-bms-single-module.*` — alias of the current bench diagram
- `tesla_bms_schematic.py` — dependency-free SVG generator and renderer

Regenerate all outputs from the repository root:

```sh
python3 electrical/tesla_bms_schematic.py --render
```

Generate only one version with `--variant bench`, `--variant production`, or
`--variant connector`.
The SVG generator uses only the Python standard library. The optional PDF and
PNG rendering step uses Google Chrome or Chromium in headless mode.

## Scope

Both drawings cover one original 10-pin Tesla Model S/X 6S module BMS slave,
an Arduino Due using `Serial1`, and the HiLetgo BSS138-style four-channel level
shifter. The Due's `+5V` power-header pin powers the level shifter's high side
and the single BMB.

The bench drawing uses the original connector that remains plugged into the
BMB with its factory wires cut as a pigtail. The duplicate power, ground, RX,
and TX wires are spliced by connector cavity number. No EVTV harness or
loopback jumper is used.

The production-layout drawing uses the EVTV two-module harness. The module is
plugged into its middle connector and a two-jumper loopback cap closes the
unused end connector.

The connector worksheet shows the cavity matrix from both opposing faces. The
two views are horizontal mirrors. Match a molded cavity ID on the actual
housing before choosing a view; the source wiring schematic does not identify
its physical viewing face from the latch alone. Use continuity only with all
external power removed, preferably with the 10-pin communications pigtail
unplugged from the BMB. Do not disturb the BMB cell-sense connections.

The drawing follows the intended left-to-right table layout. J1 and the Tesla
module are at the far right, and J1 is represented as one complete mated
connection rather than ten separately wired pins. J2 retains pin-level detail
because its `2–4` and `7–9` loopback jumpers must be assembled by the user.

The BSS138 board is shown because it is the hardware currently on hand. Its
10 kΩ pull-ups can produce marginal rise times at the Tesla bus's 612.5 kbaud,
so it is suitable for cautious unloaded bench testing, not as the sole battery
protection interface. Verify the actual harness revision and every connector
cavity with a continuity meter before applying power.
