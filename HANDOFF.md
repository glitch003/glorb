# Handoff — broom LED as-built changes (2026-08)

Captures the physical build changes made since the K128D-B / SRx4 migration, and
the docs/maps updated to match. Author: Jessi. **Heads-up for whoever maintains
[lights/tube_map.py](lights/tube_map.py) / [lights/controllers.md](lights/controllers.md):**
this edits those files — please reconcile on your next pass.

## What changed on the car

1. **11th board added — zone F, 12 new tubes.** A new 2×4 board (`F1`, tubes
   `F01–F12`) with its own SRx4 receiver on **RJ45 port 11**, hung at the
   **front-right corner**. Total is now **148 tubes / 11 boards** (was 136 / 10)
   → 6,068 px / 18,204 channels / 36 universes.

2. **All boards hang in map order.** (An earlier back-corner B2/D1 swap was
   considered and then reverted — the layout diagram is back to the original
   order, with F1 added at the front-right.)

3. **Power trunk legs assigned by board** (the "split at the battery" topology):
   - **Leg 1 — joins at B1:** A1, A2, B1, B2, C1  (tubes `L01–L56` + `B01–B12`)
   - **Leg 2 — joins at D2:** C2, D1, D2, E1, E2, F1  (tubes `B13–B24` + `R01–R56` + `F01–F12`)
   - Each leg stays on its own side of the car — no crossing drops.

(Earlier this session: the free-hang design was adopted — tubes hang loose at the
bottom, male pigtail up, fed only at the top — and receiver/tube wiring notes
were corrected: data-only to SRx4, V/G from the bus bars, receivers powered
5–13 V locally, common ground bonded to the − bus.)

## Files changed

**Modified**
- [lights/tube_map.py](lights/tube_map.py) — added zone F (front-right, port 11);
  `PHYSICAL_SWAP` mechanism left empty (boards drawn in map order).
- [lights/controllers.md](lights/controllers.md) — 148 tubes / 11 boards / 11
  ports; F table row (Front-Right).
- [broom/DESIGN.md](broom/DESIGN.md) — 148-tube counts; power note (scale ~+9%).
- [electrical/led-wiring.md](electrical/led-wiring.md) — board-based trunk legs
  (Leg 1 @ B1, Leg 2 @ D2); receiver-power (5–13 V) note.
- Regenerated: [lights/tube-map.png/.pdf/.json/.md](lights/tube-map.md).

**New**
- [broom/build-checklist.md](broom/build-checklist.md) — what's left to finish.
- [electrical/bus_bar_map.py](electrical/bus_bar_map.py) +
  [bus-bar-map.svg](electrical/bus-bar-map.svg) /
  [-back.svg](electrical/bus-bar-map-back.svg) / [.md](electrical/bus-bar-map.md)
  / [.pdf](electrical/bus-bar-map.pdf) — per-2×4 power bus-bar map (14-tube side
  + 12-tube back variants; F1 uses the 12-tube variant).
- [electrical/power_map.py](electrical/power_map.py) +
  [power-map.svg](electrical/power-map.svg) — how the 24 V power is connected
  (bank → breaker → two legs → per-board bus bars → tubes).
- [broom/free-hanging-rewire.html](broom/free-hanging-rewire.html) — free-hang
  rewire explainer.
- [lights/build-update-2026-08-08.md](lights/build-update-2026-08-08.md) —
  transcribed field notes.
- IMG_4548.heic — source photo of those notes.

## Still open / to confirm
- Power-injection **zone count**: [led-wiring.md](electrical/led-wiring.md) still
  frames "~14 injection zones"; the bus-bar map is now **per-board (11)**.
- [lights/labeling-progress.md](lights/labeling-progress.md) is stale (old Angio
  groups / D-mirror) — not yet updated.
- `tube-map.pdf` regenerates from `tube_map.py`; the older
  [angio-pinout.jpg](lights/angio-pinout.jpg) is superseded (Angio-era).
