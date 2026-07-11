# Driving the data lines — 100 LED tubes

How to run data to **100 × 2.5 m SM16703 tubes** ([led-tubes.md](led-tubes.md), [../broom/DESIGN.md](../broom/DESIGN.md)) without managing 100 separate data runs.

## The problem is small (once you count *pixels*, not tubes)

SM16703 groups **6 physical LEDs per IC → 16 addressable pixels/m per side** ([led-tubes.md](led-tubes.md)). At 2.5 m:

- **40 pixels per tube** (16 px/m × 2.5 m).
- **100 tubes → 4 000 pixels total.**

That's a *small* pixel count for modern pixel controllers. The design driver is **cable management (100 physical tubes)**, not data bandwidth. At WS2811-family timing (800 kHz, ~30 µs/pixel) a 40-px tube refreshes in ~1.2 ms — a whole 500-px output chain still clears well over 60 fps. Bandwidth is a non-issue; grouping tubes onto shared outputs is purely to cut the number of runs.

## Hardware on hand: Chroma-Tech Angio-8

We already drive the (being-replaced) panels with a **Chroma-Tech Angio-8** pixel controller and have **~4 more on hand** (<https://shop.chroma.tech/products/angio-8>). Eight pixel outputs each, Ethernet in, speaks **sACN / E1.31** (also Art-Net). Reusing these means no new controller purchase.

## Topology: 4 Angio-8s, one per side

- **One Angio-8 per side of the car** (4 sides → 4 controllers). Keeps each controller near its tubes, short data runs, clean failure domains (a dead controller = one dark side, not the whole broom).
- ~100 tubes / 4 sides ≈ **25 tubes per controller** across 8 outputs → **~3 tubes/output** (chained).
- Each output chain = 3 tubes × 40 px = **120 px/output** — trivial for the Angio.

### Chaining + serpentine reverse in software

Chain ~3 tubes per output in a **serpentine (boustrophedon)** run: tube 1 top→bottom, tube 2 bottom→top, tube 3 top→bottom. Physically flip alternate tubes so DOUT→DIN hops are short, then **reverse those tubes' pixel order in software** (xLights model: mark alternate strands "reverse", or use a per-strand start-corner) so animations read top-aligned across the whole side.

## Wiring: data + ground only, power injected separately

**Do NOT power the tubes through the Angio outputs.** The Angio's onboard power budget can't feed tube current (100 tubes typical ~125 A @ 24 V — see [../electrical/led-power.md](../electrical/led-power.md)). Run to each tube:

- **DATA** — from the Angio output (through the ~330–470 Ω series resistor at DIN per [led-tubes.md](led-tubes.md)).
- **GND** — Angio ground **and** the 24 V bus ground must be **common** (shared reference is mandatory for the data signal).
- **+24 V** — from the 24 V injection bus, **not** the controller. Single-end injection per tube (24 V allows it — see DESIGN.md), 1000 µF cap at each injection point.

So each tube gets a 2-wire pigtail from the controller side (DATA + GND) and a 2-wire feed from the power bus (+24 V + GND), grounds tied.

## Sequencing: xLights / FPP master over wired Ethernet

- **xLights** to design/sequence; an **FPP** player (RPi) as the show master at the event, output to the 4 Angios over **wired Ethernet** via sACN/E1.31.
- **Wired, not WiFi** — WiFi is unreliable in the dust/RF soup at Black Rock. Small switch, one cable per controller.
- **Model each tube as 40 nodes** in xLights; group the ~3 tubes/output into a strand with alternate strands reversed (above). Lay the 4 side-models into a whole-car layout so patterns can sweep the full perimeter.

## Verification tests before committing (bench, one tube)

1. **SM16703 compatibility on the Angio-8.** The Angio product page doesn't enumerate supported chipsets. SM16703 is WS2811-family single-wire and *usually* works on WS281x-class outputs, but **bench-test one tube on one Angio output**: confirm it lights, **color order is RGB** ([led-tubes.md](led-tubes.md)), and there's no flicker/color corruption at length. If the Angio can't clock SM16703 cleanly, fall back to ESP32 + WLED per zone (E1.31 into the same xLights show).
2. **Confirm the Angio outputs 5 V data logic.** SM16703 wants 5 V logic ([led-tubes.md](led-tubes.md)); the FastLED test rig used a 5 V Trinket/Nano direct. If the Angio drives 3.3 V, add a level shifter at the head of each chain.

## Related

- [led-tubes.md](led-tubes.md) — strip electricals (16 px/m, 5 V data, RGB, resistor/cap)
- [../broom/DESIGN.md](../broom/DESIGN.md) — tube count / layout / power
- [../electrical/led-power.md](../electrical/led-power.md) — 24 V power source (why injection is separate)
- [nano_sm16703_cylon/](nano_sm16703_cylon/) — FastLED SM16703 test sketch
