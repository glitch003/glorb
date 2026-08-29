# VCU / remote receiver — debug notes (2026-08-28)

Field notes from debugging "remote shows full TX but no RX, drive controllers
beeping" a few days before the burn. Companion to the
[translated chassis manual](manual-en.md). Status at time of writing: **root
cause isolated to the VCU's supply feed being dead; exact break not yet found.**

## What the control chain actually is

Transmitter (FlySky-style, dual power buttons) → 2.4 GHz →
**FS-iA10B receiver** (10-ch, 4.0–6.5 V DC) → plugged into the **VCU control
box** → CAN bus + relay outputs → drive controllers / EPS / EBS.

Inside the VCU box:

- **STM32F103 "Blue Pill"** dev board on a carrier — the brains. Its PWR LED
  runs off the pill's own AMS1117 3.3 V regulator, fed from the 5 V rail.
- Carrier board: **LZX-DB-V3.0** by 康沃瑞智能科技 (Kangworui Intelligent
  Tech). No public documentation exists. Holds ~12 relays (5 V coils), driver
  ICs, a CAN transceiver breakout (purple), and an onboard buck regulator
  (inductor + electrolytics near the top-right) — so the box takes a higher
  supply voltage in (nominally 12 V per the manual) and makes 5 V internally.
- The **FS-iA10B receiver** hangs off the 5 V rail.
- Power enters via a **round 4-pin bulkhead connector** that lands on a white
  Molex-style connector on the carrier. This is the box's only connector;
  4 positions populated.
- The remote's RX bars = telemetry from the FS-iA10B. No RX with full TX,
  standing next to the car = receiver unpowered/dead, not a range problem.

## Findings so far

- **Both VCU boxes (original + never-used spare) are dark on the same
  harness** → the box is not the problem; the supply feeding it is.
- An early "5 V coming in" reading at the white connector did not survive
  better-referenced measurements — treat it as a ghost/floating reading.
- **Ground pin identified**: with the box unplugged, continuity from the Blue
  Pill's `G` pin to the white connector found the ground position
  (read 0.000 Ω — a true short, same as touching probes together).
- **The supply pin does NOT beep to the pill's 5V pin — that's expected.**
  Input goes through a reverse-protection diode + the onboard buck before
  becoming 5 V; continuity can't see through either. (A measured ~11 "Ω"
  between pill-5V and ground is just the 5 V rail's load resistance —
  meaningless for pin mapping.)
- **Autoranging meter gotcha**: check the unit symbol (Ω / kΩ / MΩ) on every
  resistance reading. "0.07" may be 70 Ω or 70 kΩ — which is a signal pin,
  not a ground.
- Likely pinout of the 4 wires (**unconfirmed**): GND, +12 V in, CAN H, CAN L.
- Harness-side voltages with key on: all four pins read ≈0 V (sub-volt noise)
  against the known ground → **the 12 V feed (and/or its path) is dead
  upstream of the connector.**

## Pin-mapping tests (box side, power off)

1. Ground(s): continuity from pill `G` to each pin. True ground ≈ 0.0 Ω.
2. CAN pair: resistance between the two remaining candidates — a terminated
   CAN H↔L pair reads **~120 Ω**. Dead giveaway.
3. Supply pin: meter on **diode mode**, red probe on candidate, black on
   ground → ~0.4–0.7 V one way, OL the other = the input protection diode.
4. Mirror-image warning: pin positions flip left↔right between the two halves
   of a connector. Identify wires by color, not position.

## Where to chase the dead supply

Per the manual's wiring diagram and [batteries.md](../batteries.md), the 12 V
side comes from the 72 V→12 V converter and/or the 13 V aux bank. Follow the
supply wire color from the harness connector back through:

1. **Black-tape splices** in the loom (unwrap, inspect, redo with solder +
   heatshrink) — prime suspect on playa.
2. **Inline fuse holders** — meter the fuse AND the holder contacts.
3. **Key switch / e-stops** in series with the feed — corroded contacts read
   full voltage unloaded and collapse under load.
4. **The DC-DC converter itself** — measure output under load, then input.
   Input live + output dead = replace converter.

Definitive wire test: power off, continuity end-to-end on the one wire
(converter/battery terminal → harness pin), extending a meter lead with spare
wire. Open = broken conductor; ohms instead of ~zero = corroded splice.

Success test: 12–13 V across supply/ground pair at the connector → plug in →
Blue Pill PWR LED + FS-iA10B LED light → transmitter shows RX bars.

## Warnings

- **The Blue Pill's firmware is the vendor's and cannot be re-downloaded.**
  A blank replacement pill will not run the car. If a pill is dead, fix only
  its power path (AMS1117 regulator swap / feed 3.3 V) or get a replacement
  box from the manufacturer (contact in [manual-en.md](manual-en.md)).
- Some red wires in the VCU harness/gland carry **switched 60–69 V traction
  voltage** (drive-controller key-switch and brake lines). Verify before
  touching bare copper; chock the wheels while probing.
- Meter discipline: DC volts mode with red lead in the VΩ jack; continuity /
  resistance / diode tests on dead circuits only; clip black lead to one known
  ground and identify grounds by continuity, not by "it goes to the battery"
  (a 69 V pack terminal is not a reference for the 12 V/5 V control domain,
  and converter outputs may be isolated).
- Drive-controller beep pattern is a fault code — count longs/shorts against
  [manual-en.md § IV](manual-en.md#iv-drive-controller-fault-codes). With the
  VCU dead, expect #0019 (1 long, 9 short: CAN communication fault).
