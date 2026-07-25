# Driving the data lines — 136 LED tubes (open front)

How to run data to **136 × 2.5 m SM16703 tubes** ([led-tubes.md](led-tubes.md), [../broom/DESIGN.md](../broom/DESIGN.md)) without managing 136 separate data runs. Tubes wrap **3 sides** — left (56), rear (24), right (56) — with the **front-left short side open** for the driver's sightline.

## The problem is small (once you count *pixels*, not tubes)

SM16703 groups **6 physical LEDs per IC → 16 addressable pixels/m per side** ([led-tubes.md](led-tubes.md)). At 2.5 m:

- **40 pixels per tube** (16 px/m × 2.5 m).
- **136 tubes → 5 440 pixels total.**

That's a *small* pixel count for modern pixel controllers. The design driver is **cable management (136 physical tubes)**, not data bandwidth. At WS2811-family timing (800 kHz, ~30 µs/pixel) a 40-px tube refreshes in ~1.2 ms — even a 7-tube / 280-px output chain clears in ~8.4 ms (~119 fps). Bandwidth is a non-issue; grouping tubes onto shared outputs is purely to cut the number of runs.

## Hardware on hand: Chroma-Tech Angio-8

We already drive the (being-replaced) panels with a **Chroma-Tech Angio-8** pixel controller and have **~4 more on hand** (<https://shop.chroma.tech/products/angio-8>). Eight pixel outputs each, Ethernet in, speaks **sACN / E1.31** (also Art-Net). Reusing these means no new controller purchase.

## Topology: 3 Angio-8s (one per lit side) + 1 spare

The open front leaves **3 lit sides**, so one Angio-8 sits on each. Keeps every controller near its tubes, short data runs, and clean failure domains (a dead controller = one dark side, not the whole broom). The 4th Angio is a **hot spare** — carry it pre-configured to swap in on failure, or press it into service to halve the long-side chains if you want more redundancy.

| Angio | Side | Tubes | Outputs used | Tubes/output | Px/output |
| --- | --- | ---: | ---: | ---: | ---: |
| A | Left (4 000 mm) | 56 | 8 | 7 | 280 |
| B | Right (4 000 mm) | 56 | 8 | 7 | 280 |
| C | Rear (1 800 mm) | 24 | 8 | 3 | 120 |
| D | — | *spare* | — | — | — |

280 px/output is trivial for the Angio (~119 fps). If you'd rather run shorter chains, split a long side across Angio C's spare outputs or bring D online (e.g. 4 tubes/output everywhere).

### Layout — where the Angios and tubes sit

```
                 FRONT (OPEN — driver sightline, no tubes)
        front-left ·  ·  ·  ·  ·  ·  ·  ·  · front-right
                  ┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐
                  │                        │
     LEFT SIDE    │                        │   RIGHT SIDE
     56 tubes     │        [deck]          │   56 tubes
     4 000 mm     │                        │   4 000 mm
    ┌─────────┐   │                        │   ┌─────────┐
    │ Angio A │───┤                        ├───│ Angio B │
    └─────────┘   │                        │   └─────────┘
                  └────────────────────────┘
                     REAR 24 tubes / 1 800 mm
                        ┌─────────┐
                        │ Angio C │   (Angio D = spare, carried)
                        └─────────┘
```

### Chaining + serpentine reverse in software

Chain the per-output tubes in a **serpentine (boustrophedon)** run: tube 1 top→bottom, tube 2 bottom→top, tube 3 top→bottom, … Physically flip alternate tubes so DOUT→DIN hops are short, then **reverse those tubes' pixel order in software** (xLights model: mark alternate strands "reverse", or use a per-strand start-corner) so animations read top-aligned across the whole side.

```
DATA TOPOLOGY (per side; Left shown — 7 tubes/output × 8 = 56)

  FPP player (RPi, show master)
     │  wired Ethernet — sACN / E1.31
  [ small Ethernet switch ]
     ├── Angio A (LEFT)  ── out1..out8, 7 tubes each
     ├── Angio B (RIGHT) ── out1..out8, 7 tubes each
     ├── Angio C (REAR)  ── out1..out8, 3 tubes each
     └── Angio D (SPARE)

  One output chain (serpentine):
  out ─[330–470Ω]─▶ DIN[T1] top→bot ─DOUT─▶ DIN[T2] bot→top ─▶ DIN[T3] top→bot ─▶ … (7 tubes)
       DATA + GND only          (flip alternate tubes; reverse in xLights)
```

## Wiring: data + ground only, power injected separately

**Do NOT power the tubes through the Angio outputs.** The Angio's onboard power budget can't feed tube current (136 tubes typical ~170 A @ 24 V — see [../electrical/led-power.md](../electrical/led-power.md)). Run to each tube:

- **DATA** — from the Angio output (through the ~330–470 Ω series resistor at DIN per [led-tubes.md](led-tubes.md)).
- **GND** — Angio ground **and** the 24 V bus ground must be **common** (shared reference is mandatory for the data signal).
- **+24 V** — from the 24 V injection bus, **not** the controller. Single-end injection per tube (24 V allows it — see DESIGN.md), 1000 µF cap at each injection point.

So each tube gets a 2-wire pigtail from the controller side (DATA + GND) and a 2-wire feed from the power bus (+24 V + GND), grounds tied:

```
PER-TUBE HOOKUP (two separate systems meet at the tube)

  Angio out ─[330–470Ω]──▶ DIN ┐
                               │   ┌──────────────┐
  (data side)   Angio GND ─────┼──▶│  LED TUBE    │
                               │   │  DIN  +  GND  │
  ───────────────────────────  │   └───┬──────┬───┘
  (power side, from busbars)    │      │      │
     +24V bar ──── fork ────────┼──────┘      │
                                │             │
     1000µF cap across +24V/GND (at the tap)  │
                                              │
     GND bar ──── fork ───────────────────────┘
        │
        └──▶ tied common with Angio GND  ← MANDATORY for the data signal
```

Power wiring (busbars, trunk, injection zones) lives in [../electrical/led-wiring.md](../electrical/led-wiring.md); this doc owns only DATA + the shared-ground requirement.

## Sequencing: xLights / FPP master over wired Ethernet

- **xLights** to design/sequence; an **FPP** player (RPi) as the show master at the event, output to the 4 Angios over **wired Ethernet** via sACN/E1.31.
- **Wired, not WiFi** — WiFi is unreliable in the dust/RF soup at Black Rock. Small switch, one cable per controller.
- **Model each tube as 40 nodes** in xLights; group the per-output tubes (7 on the long sides, 3 on the rear) into a strand with alternate strands reversed (above). Lay the 3 side-models into a whole-car layout (front open) so patterns sweep the U from front-left, around the rear, to front-right.

## Verification tests before committing (bench, one tube)

1. **SM16703 compatibility on the Angio-8.** The Angio product page doesn't enumerate supported chipsets. SM16703 is WS2811-family single-wire and *usually* works on WS281x-class outputs, but **bench-test one tube on one Angio output**: confirm it lights, **color order is RGB** ([led-tubes.md](led-tubes.md)), and there's no flicker/color corruption at length. If the Angio can't clock SM16703 cleanly, fall back to ESP32 + WLED per zone (E1.31 into the same xLights show).
2. **Confirm the Angio outputs 5 V data logic.** SM16703 wants 5 V logic ([led-tubes.md](led-tubes.md)); the FastLED test rig used a 5 V Trinket/Nano direct. If the Angio drives 3.3 V, add a level shifter at the head of each chain.

## Related

- [led-tubes.md](led-tubes.md) — strip electricals (16 px/m, 5 V data, RGB, resistor/cap)
- [../broom/DESIGN.md](../broom/DESIGN.md) — tube count / layout / power
- [../electrical/led-power.md](../electrical/led-power.md) — 24 V power source (why injection is separate)
- [nano_sm16703_cylon/](nano_sm16703_cylon/) — FastLED SM16703 test sketch
