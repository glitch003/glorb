# Handoff — broom LED as-built changes (2026-08)

Captures the physical build changes made since the K128D-B / SRx4 migration, and
the docs/maps updated to match. Author: Jessi. **Heads-up for whoever maintains
[lights/tube_map.py](lights/tube_map.py) / [lights/controllers.md](lights/controllers.md):**
this edits those files — please reconcile on your next pass.

## What changed on the car

1. **11th board added — zone F, 12 new tubes.** A new 2×4 board (`F1`, tubes
   `F01–F12`) with its own SRx4 receiver on **RJ45 port 11**, hung **left of the
   ladder** (back-left). Total is now **148 tubes / 11 boards** (was 136 / 10).
   → 6,068 px / 18,204 channels / 36 universes.
   - ⚠️ *Confirm F's corner:* it was described both as "left of the ladder" and
     "the front section" — the map currently places it **back-left**.

2. **Two boards hung out of map order (physical swap).** The whole 2×4 boards —
   tubes and receiver — are swapped: **B2 (`L43–L56`) hangs at the back-RIGHT**
   and **D1 (`R01–R14`) at the back-LEFT**. The **data map is unchanged**
   (same labels → ports → channels); only the physical location and cat5 length
   move. The layout diagram reflects this; every other board follows the map.

3. **Power trunk legs reassigned by board (the "split at the battery" topology).**
   - **Leg 1 — joins at B1:** A1, A2, B1, B2, C1  (tubes `L01–L56` + `B01–B12`)
   - **Leg 2 — joins at D2:** C2, D1, D2, E1, E2, F1  (tubes `B13–B24` + `R01–R56` + `F01–F12`)
   - ⚠️ Because of the B2/D1 swap, Leg 1 powers B2 (physically back-right) and
     Leg 2 powers D1 (physically back-left) — those two 24 V drops **cross the
     back**. Route them across, or reassign B2↔D1 to the other leg.

(Earlier this session: the free-hang design was adopted — tubes hang loose at the
bottom, male pigtail up, fed only at the top — and receiver/tube wiring notes
were corrected: data-only to SRx4, V/G from the bus bars, receivers powered
5–13 V locally, common ground bonded to the − bus.)

## Files changed

**Modified**
- [lights/tube_map.py](lights/tube_map.py) — added zone F; added `PHYSICAL_SWAP`
  (B2⇄D1) so the diagram places the two boards at their real corners.
- [lights/controllers.md](lights/controllers.md) — 148 tubes / 11 boards / 11
  ports; F table row; as-built swap note.
- [broom/DESIGN.md](broom/DESIGN.md) — 148-tube counts; power note (scale ~+9%).
- [electrical/led-wiring.md](electrical/led-wiring.md) — board-based trunk legs
  + the B2/D1 swap warning; receiver-power (5–13 V) note.
- Regenerated: [lights/tube-map.png/.pdf/.json/.md](lights/tube-map.md).

**New**
- [broom/build-checklist.md](broom/build-checklist.md) — what's left to finish.
- [electrical/bus_bar_map.py](electrical/bus_bar_map.py) +
  [bus-bar-map.svg](electrical/bus-bar-map.svg) /
  [-back.svg](electrical/bus-bar-map-back.svg) / [.md](electrical/bus-bar-map.md)
  / [.pdf](electrical/bus-bar-map.pdf) — per-2×4 power bus-bar map (14-tube side
  + 12-tube back variants).
- [broom/free-hanging-rewire.html](broom/free-hanging-rewire.html) — free-hang
  rewire explainer.
- [lights/build-update-2026-08-08.md](lights/build-update-2026-08-08.md) —
  transcribed field notes.
- IMG_4548.heic — source photo of those notes.

## Still open / to confirm
- F's physical corner ("left of ladder" vs "front section").
- B2/D1 power-leg crossing (above) — accept the cross, or swap legs.
- Power-injection **zone count**: [led-wiring.md](electrical/led-wiring.md) still
  frames "~14 injection zones"; the bus-bar map is now **per-board (11)**.
- [lights/labeling-progress.md](lights/labeling-progress.md) is stale (old Angio
  groups / D-mirror) — not yet updated.
- `tube-map.pdf` regenerates from `tube_map.py`; the older
  [angio-pinout.jpg](lights/angio-pinout.jpg) is superseded (Angio-era).
