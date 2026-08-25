# Driving the data lines — 148 LED tubes (open front)

How to run data to **148 × 2.5 m SM16703 tubes** ([led-tubes.md](led-tubes.md), [../broom/DESIGN.md](../broom/DESIGN.md)). Tubes wrap **3 sides** — left (56), rear (24), right (56), back-left (12) — with the **front-left short side open** for the driver's sightline.

**Current design: one data line per tube.** A single [Kulp K128D-B](k128/README.md) drives all 148 tubes through differential receivers — no chaining, no serpentine, no per-tube flipping. See [k128/README.md](k128/README.md) for controller bring-up and [tube-map.md](tube-map.md) for the port/receiver/output map.

> **Superseded:** the five WLED Angio-8 boards with 4-tube chains per data line. What that bought us and what it cost is in [Why we moved off chaining](#why-we-moved-off-chaining) below. Zones A–E, tube labels, 2×4 hangers and busbars are all unchanged — only the data topology changed.

## The pixel count is small; the cable count is the problem

SM16703 groups **6 physical LEDs per IC → 16 addressable pixels/m per side** ([led-tubes.md](led-tubes.md)). At 2.5 m:

- **41 pixels per tube** (measured; nominal 40 = 16 px/m × 2.5 m).
- **148 tubes → 6,068 pixels / 18,204 channels total.**

That is a *small* pixel count for a modern pixel controller. At WS2811-family timing (800 kHz, ~30 µs/pixel) a 41-px tube refreshes in **~1.2 ms** — about 800 fps if it were the only thing on the wire. Bandwidth was never the design driver; **cable management for 148 physical tubes** is.

## Topology: one K128D-B, eleven SRx4 boards, 148 outputs

| | |
|---|---|
| Controller | 1 × Kulp K128D-B (BeagleBone + FPP) |
| RJ45 ports | **11 used of 32** — one per 2×4 hanger board |
| Receivers | **11 × SRx4 v4.00 quad SmartReceiver** (16 outputs each) |
| Tubes | **148**, one per receiver output — 14/board on the sides, 12/board on the back & back-left |
| Busiest port | 574 px, against an 800 px @ 40 fps budget |

Each RJ45 carries 4 differential strings. One SRx4 board = four chained receiver positions in one (output groups A–D of 4), so a whole 2×4's tubes hang off a single cat5 run with nothing chained after it. **Every board's ID dial is `A`, all 4 termination DIPs UP (Only/Last)** — see [tube-map.md](tube-map.md) for the board map and [k128/README.md](k128/README.md#the-receiver-boards-falconkulp-srx4-v400--read-this-first) for the dial/DIP traps.

| Zone | Location | Tubes | Boards (2×4s) | RJ45 ports |
| --- | --- | ---: | --- | --- |
| A | Left-Front | 28 | A1 (L01–L14), A2 (L15–L28) | 1, 2 |
| B | Left-Back | 28 | B1 (L29–L42), B2 (L43–L56) | 3, 4 |
| C | Back | 24 | C1 (B01–B12), C2 (B13–B24) | 5, 6 |
| D | Right-Back | 28 | D1 (R01–R14), D2 (R15–R28) | 7, 8 |
| E | Right-Front | 28 | E1 (R29–R42), E2 (R43–R56) | 9, 10 |
| F | Back-Left | 12 | F1 (F01–F12) | 11 |

> **As-built (2026-08):** zone **F** is a new **12-tube back-left board** (F01–F12) on **port 11**, *left of the ladder*. And boards **B2** and **D1** are hung at **swapped back corners** — B2 (`L43–L56`) at the back-right, D1 (`R01–R14`) at the back-left. Ports/channels are unchanged; only physical location + cat5 length differ. See [tube-map.md](tube-map.md).

21 RJ45 ports stay spare — plenty of room to re-split a zone, or to bring a dead port's tubes up elsewhere by editing `ZONES` in [tube_map.py](tube_map.py) and re-running it.

### Layout — where the boards and tubes sit

```
                 FRONT (OPEN — driver sightline, no tubes)
        front-left ·  ·  ·  ·  ·  ·  ·  ·  · front-right
                  ┌─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐
     LEFT SIDE    │                        │   RIGHT SIDE
     56 tubes     │        [deck]          │   56 tubes
     4 000 mm     │                        │   4 000 mm
   A: A1, A2  ────┤      ┌──────────┐      ├──── E2, E1 :E
   B: B1, B2  ────┤      │  K128D-B │      ├──── D2, D1 :D
                  │      └────┬─────┘      │
                  └───────────┼────────────┘
                     REAR 24 tubes / 1 800 mm
                          C: C1, C2
```

The K128D lives in one box; 11 cat5 runs fan out, one to the SRx4 on each 2×4 hanger board, and each board sits directly above the tubes it drives.

### One board, one 2×4, up to 16 tubes

```
K128D RJ45 port ──cat5──▶ [SRx4 board · dial=A · DIPs UP]   (one board per port, nothing chained)
                             │
                             ├─ group A outs 1-4 ─[330–470Ω]─▶ DIN tubes 1-4  (top)
                             ├─ group B outs 1-4 ─[330–470Ω]─▶ DIN tubes 5-8
                             ├─ group C outs 1-4 ─[330–470Ω]─▶ DIN tubes 9-12
                             └─ group D outs 1-2 ─[330–470Ω]─▶ DIN tubes 13-14  (12-tube boards skip group D)
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
- **One buck per board, 10 for the car.** Each 2×4 carries exactly one SRx4,
  so the buck mounts on the same 2×4 next to it, fed from the 24 V bus that is
  already there.
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

FPP runs on the K128D and takes **DDP unicast (preferred) or E1.31 / sACN** on its bridge input: universes **1–33 × 510 channels** onto FPP channel 1, one flat 16,728-channel space for the whole car. Tube *n* (0-based, in map order) owns channels `n × 123 + 1 … n × 123 + 123`. Every frame ends with a latch (DDP PUSH / E1.31 sync) so fppd outputs at the sender's pace — see [k128/README.md](k128/README.md).

The pattern engine ([glorbleds/](glorbleds/)) runs **on the BeagleBone itself** and sends to localhost, so the show does not depend on Wi-Fi or on a laptop staying awake; clients just open the web UI. See [k128/README.md](k128/README.md#step-4--run-the-show-software-on-the-beaglebone) — including the frame-rate caveat, since the AM3358 is a single 1 GHz core and glorbleds is pure Python.

xLights is no longer in the path. If you ever want sequenced (rather than generative) content, FPP plays FSEQ files natively and xLights can upload straight to it.

## Why we moved off chaining

The Angio build chained 4-tube groups onto shared data lines, which meant:

- **Serpentine wiring** — alternate tubes physically flipped so DOUT→DIN hops stayed short, then reversed again in software.
- **A hang order that had to match the map.** Zone D line 1 went up mirrored and stayed that way, carried as a `REVERSED_LINES` override plus a standing rehang TODO.
- **Chain failure domains** — one bad tube or DOUT killed everything downstream of it.
- **Five controllers** to configure, address, keep on the network and keep spares for.

One data line per tube removes all four. A tube is now an independent, individually addressable 41-px unit: no flips, no reversal, no downstream blast radius, and **the mirrored-D problem simply disappears** — D's tubes are re-patched in the map, not rehung on the car. The cost is 10 SRx4 boards and 10 cat5 runs.
