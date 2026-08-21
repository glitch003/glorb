# Driving the data lines — 136 LED tubes (open front)

How to run data to **136 × 2.5 m SM16703 tubes** ([led-tubes.md](led-tubes.md), [../broom/DESIGN.md](../broom/DESIGN.md)). Tubes wrap **3 sides** — left (56), rear (24), right (56) — with the **front-left short side open** for the driver's sightline.

**Current design: one data line per tube.** A single [Kulp K128D-B](k128/README.md) drives all 136 tubes through differential receivers — no chaining, no serpentine, no per-tube flipping. See [k128/README.md](k128/README.md) for controller bring-up and [tube-map.md](tube-map.md) for the port/receiver/output map.

> **Superseded:** the five WLED Angio-8 boards with 4-tube chains per data line. What that bought us and what it cost is in [Why we moved off chaining](#why-we-moved-off-chaining) below. Zones A–E, tube labels, 2×4 hangers and busbars are all unchanged — only the data topology changed.

## The pixel count is small; the cable count is the problem

SM16703 groups **6 physical LEDs per IC → 16 addressable pixels/m per side** ([led-tubes.md](led-tubes.md)). At 2.5 m:

- **40 pixels per tube** (16 px/m × 2.5 m).
- **136 tubes → 5,440 pixels / 16,320 channels total.**

That is a *small* pixel count for a modern pixel controller. At WS2811-family timing (800 kHz, ~30 µs/pixel) a 40-px tube refreshes in **~1.2 ms** — about 830 fps if it were the only thing on the wire. Bandwidth was never the design driver; **cable management for 136 physical tubes** is.

## Topology: one K128D-B, 34 receivers, 136 outputs

| | |
|---|---|
| Controller | 1 × Kulp K128D-B (BeagleBone + FPP) |
| RJ45 ports | **10 used of 32** — two per zone |
| Receivers | **34**, 4 pixel outputs each |
| Tubes | **136**, one per receiver output |
| Busiest port | 640 px, against an 800 px @ 40 fps budget |

Each RJ45 carries 4 differential strings and can feed either one standard differential receiver or **up to 6 chained v2 SmartReceivers**, with up to 250 ft of cat5 to the last one. We chain 3–4 receivers per port, two ports per zone:

| Zone | Location | Tubes | Receivers | RJ45 ports |
| --- | --- | ---: | --- | --- |
| A | Left-Front | 28 | R1–R7 | 1 (4 recv), 2 (3 recv) |
| B | Left-Back | 28 | R8–R14 | 3 (4 recv), 4 (3 recv) |
| C | Back | 24 | R15–R20 | 5 (3 recv), 6 (3 recv) |
| D | Right-Back | 28 | R21–R27 | 7 (4 recv), 8 (3 recv) |
| E | Right-Front | 28 | R28–R34 | 9 (4 recv), 10 (3 recv) |

22 RJ45 ports stay spare — plenty of room to re-split a zone, or to bring a dead port's tubes up elsewhere by editing `ZONES` in [tube_map.py](tube_map.py) and re-running it.

### Layout — where the receivers and tubes sit

```
                 FRONT (OPEN — driver sightline, no tubes)
        front-left ·  ·  ·  ·  ·  ·  ·  ·  · front-right
                  ┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐
     LEFT SIDE    │                        │   RIGHT SIDE
     56 tubes     │        [deck]          │   56 tubes
     4 000 mm     │                        │   4 000 mm
   A: R1–R7   ────┤      ┌──────────┐      ├──── R28–R34 :E
   B: R8–R14  ────┤      │  K128D-B │      ├──── R21–R27 :D
                  │      └────┬─────┘      │
                  └───────────┼────────────┘
                     REAR 24 tubes / 1 800 mm
                          C: R15–R20
```

The K128D lives in one box; 10 cat5 runs fan out to the receiver clusters, and each receiver sits close to the 4 tubes it drives.

### One receiver, four tubes

```
K128D RJ45 port ──cat5──▶ [recv A] ──cat5──▶ [recv B] ──▶ …   (≤6 v2 smart, ≤250 ft to the last)
                             │
                             ├─out1─[330–470Ω]─▶ DIN tube 1 (top)
                             ├─out2─[330–470Ω]─▶ DIN tube 2 (top)
                             ├─out3─[330–470Ω]─▶ DIN tube 3 (top)
                             └─out4─[330–470Ω]─▶ DIN tube 4 (top)
```

**Every tube takes data at its top end.** Because nothing is chained, every string is *Forward* in FPP, no tube is reversed in software, and a tube can be swapped without disturbing its neighbours.

## Powering the receiver boards

> ⚠️ **Never feed a receiver 24 V.** Falcon differential receivers — standard and
> v2 smart alike — take **5–13 V DC** on their power lugs. The 24 V tube bus is
> right there and tapping it will destroy the board.

Each receiver **must be locally powered**. It is not powered over the cat5 from
the K128D — the cat5 carries differential data only. An unpowered receiver puts
out nothing, which looks exactly like a dead data line.

- **Don't run 5 V across the car.** Voltage drop at low voltage over those
  distances is brutal, and a sagging receiver rail gives marginal data edges —
  a miserable thing to debug. Put a **buck converter at each receiver cluster**,
  fed from the 24 V bus that is already in every zone.
- **One buck per RJ45 port, 10 for the car** — not 34. The 3–4 receivers on a
  port are physically adjacent, and each board has power lugs at **both ends**
  which are the **same rail in parallel**, so feed the first board's near lugs
  and **daisy-chain out of its far lugs** to the next one.
- **12 V (as built) or 5 V** — both are inside the 5–13 V window. At 5 V the
  data outputs are certain to be **5 V logic**, which is what SM16703 wants
  ([led-tubes.md](led-tubes.md)). At 12 V they should still be 5 V logic from
  the board's onboard regulator (that is why the input accepts a range) —
  **put a meter on one output driving a pattern to confirm it.** Note the `V`
  passthrough on the output ports is then 12 V, so keeping `V` unconnected
  matters even more.
- Current draw is tiny when the receiver is only doing data — logic and line
  drivers, tens of mA. The 30 A rating on those lugs is for boards that pass
  pixel power through to their output ports, which ours do not.

> ⚠️ **Check the silkscreen at both ends before applying power: V and G may be
> swapped side to side.** Kulp documents exactly this on the K16A-B's own power
> connector — *"orientation of Voltage and Ground is different for each side."*
> Verify with a continuity meter first: G-to-G and V-to-V across the two ends
> should both beep (same rail, so either set works). If V-to-V is open but
> V-to-G beeps, the silkscreen is flipped, not a second rail.

## Wiring: data + ground only, power injected separately

**Do NOT power the tubes through the receiver outputs.** 136 tubes at full white is ~170 A @ 24 V (see [../electrical/led-power.md](../electrical/led-power.md)) — orders of magnitude past what a receiver can pass. Run to each tube:

Receiver output ports are 3-pin **G / D / V**. Use **two of the three**:

- **D (DATA)** — from the receiver output, through the ~330–470 Ω series resistor at DIN ([led-tubes.md](led-tubes.md)).
- **G (GND)** — **always connect this.** It is the data signal's return path, and it is what ties the receiver ground common with the 24 V bus ground. Skipping it is the single most common cause of dead or flickering pixels: data with no shared reference has nothing to swing against.
- **V** — **leave unconnected.** V is the passthrough of the receiver's own 5 V input; the tubes take +24 V from the injection bus instead. Landing V on a 24 V tube would back-feed 5 V into the 24 V rail.
- **+24 V** — from the 24 V injection bus, **not** the receiver. Injection is unchanged from the Angio build: every 2 tubes (tube 1 and tube 3 of each group of 4), 1000 µF cap at each injection point.

```
PER-TUBE HOOKUP (two separate systems meet at the tube)

  recv out ─[330–470Ω]──▶ DIN ┐
                              │   ┌──────────────┐
  (data side)  recv GND ──────┼──▶│  LED TUBE    │
                              │   │  DIN  +  GND │
  ──────────────────────────  │   └───┬──────┬───┘
  (power side, from busbars)   │      │      │
     +24V bar ──── fork ───────┼──────┘      │
                               │             │
     1000µF cap across +24V/GND (at the tap) │
                                             │
     GND bar ──── fork ──────────────────────┘
        │
        └──▶ tied common with receiver GND  ← MANDATORY for the data signal
```

Power wiring (busbars, trunk, injection zones) lives in [../electrical/led-wiring.md](../electrical/led-wiring.md); this doc owns only DATA + the shared-ground requirement.

## Control path

FPP runs on the K128D and takes **E1.31 / sACN** on its bridge input: universes **1–32 × 510 channels** onto FPP channel 1, one flat 16,320-channel space for the whole car. Tube *n* (0-based, in map order) owns channels `n × 120 + 1 … n × 120 + 120`.

The pattern engine ([glorbleds/](glorbleds/)) runs **on the BeagleBone itself** and sends to localhost, so the show does not depend on Wi-Fi or on a laptop staying awake; clients just open the web UI. See [k128/README.md](k128/README.md#step-4--run-the-show-software-on-the-beaglebone) — including the frame-rate caveat, since the AM3358 is a single 1 GHz core and glorbleds is pure Python.

xLights is no longer in the path. If you ever want sequenced (rather than generative) content, FPP plays FSEQ files natively and xLights can upload straight to it.

## Why we moved off chaining

The Angio build chained 4-tube groups onto shared data lines, which meant:

- **Serpentine wiring** — alternate tubes physically flipped so DOUT→DIN hops stayed short, then reversed again in software.
- **A hang order that had to match the map.** Zone D line 1 went up mirrored and stayed that way, carried as a `REVERSED_LINES` override plus a standing rehang TODO.
- **Chain failure domains** — one bad tube or DOUT killed everything downstream of it.
- **Five controllers** to configure, address, keep on the network and keep spares for.

One data line per tube removes all four. A tube is now an independent, individually addressable 40-px unit: no flips, no reversal, no downstream blast radius, and **the mirrored-D problem simply disappears** — D's tubes are re-patched in the map, not rehung on the car. The cost is 34 receiver boards and 10 cat5 runs.
