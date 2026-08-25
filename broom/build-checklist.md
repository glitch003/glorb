# Glorb broom — build checklist

What's left to finish the broom LED build. Status **2026-08-22**, after the
Angio-8 → **K128D-B + SRx4** migration. Sources: [../lights/README.md](../lights/README.md),
[../lights/k128/README.md](../lights/k128/README.md),
[../lights/labeling-progress.md](../lights/labeling-progress.md),
[../electrical/led-wiring.md](../electrical/led-wiring.md), [DESIGN.md](DESIGN.md).

## Controller — K128D-B (mostly done)
- [x] Board up on FPP 9.5.3 at `192.168.8.124`, zone C configured, E1.31 path verified — 2026-08-21
- [ ] Make `192.168.8.124` a **DHCP reservation** on the glorb router
- [ ] Set FPP **HostName → `glorb-k128`** (then update `CONTROLLER` in [tube_map.py](../lights/tube_map.py))
- [ ] Fix the **clock** (NTP, or the cape RTC — currently reporting ~2000)

## Receivers & data — the big remaining job (all zones)
- [ ] **Mount the 11 SRx4 boards**, one per 2×4. Mount **A, B & F** receivers (A & B on the 2nd-floor railings / old Angio magnet spots; **F1** is the new front-right board on **port 11**)
- [ ] Every board: **ID dial = `A`** (never `0` = dumb passthrough/flicker), all **termination DIPs UP** (Only/Last)
- [ ] **Power each receiver** from a 12 V buck off the 24 V bus (one per board) — **never 24 V**
- [ ] **Re-patch every zone to one-data-line-per-tube**: each tube's DIN on its own output through the 330–470 Ω resistor, **DIN at the top**, use **D + G** (leave **V** unconnected). Remove the old chain jumpers; **keep** power jumpers. (Zone D's mirror is now just re-patched in the map — no rehang.)
- [ ] **Push FPP config** per zone as they come online: `fpp_setup.py --only-zone <Z> --brightness 30` (30% ceiling on the car)
- [ ] Bench-confirm **SM16703 clocks clean + 5 V data logic** on the SRx4 (`colorcheck` / `tubes` / `chase`)

## Tube hang (zones A, B & the new F not yet up)
- [ ] **Hang zone A** (L01–L28), the **zone B** remainder, and the **new zone F** (F01–F12, 12 new tubes, front-right corner) — C, D, E already hung & powered
- [ ] **Power injection every other tube** (inject tube 1, skip 2, inject 3…); crimp fork terminals to the busbar
- [ ] **Label the remaining tubes** (zones A, B, F) with board / group / output per [../lights/tube-map.md](../lights/tube-map.md)

## Power wiring (bus bars + trunk)
- [ ] Build the **+/− bus bars per 2×4** (11 boards) — see [../electrical/bus-bar-map.md](../electrical/bus-bar-map.md) (14-tube side / 12-tube back)
- [ ] **Trunk legs (2026-08):** Leg 1 (joins at **B1**) → A1, A2, B1, B2, C1 · Leg 2 (joins at **D2**) → C2, D1, D2, E1, E2, F1. Each leg stays on its own side — [led-wiring.md](../electrical/led-wiring.md)
- [ ] **Bond every SRx4 / K128D ground to the − bus** (common ground — the lone data wire has no reference otherwise)
- [ ] **Reorder consumables for 148 tubes**: 250 A breaker (not 150), +25 ft each 4 AWG color, busbars/caps for 11 boards, +1 buck (board F1), +18/2 roll, ring-lugs ([led-wiring.md](../electrical/led-wiring.md#reorder-for-136-tubes))
- [ ] **Cut the 20 AWG data extensions** to length — needs the receiver-mount decision first
- [ ] **Per-zone 24 V bus cutoff** (contactors) for parking (idle floor ~1.4 kW)

## Handle / structure
- [ ] **Stripper-pole handle**: source, mount, structural tie-in to the upper deck
- [ ] Decide: do the **bristles reach the ground** or stop above? (driveability / scraping at BRC)

## Open design questions
- [ ] **Color zoning** around the perimeter (all-white broom vs. chase/rainbow party)?
- [ ] Does the **pole glow** too?

## Housekeeping
- [ ] Update [labeling-progress.md](../lights/labeling-progress.md) — still describes the old Angio GPIO / D-mirror / 16-12 split
- [ ] Move the **glorb wifi router** to the inverter in the belly of the car for the burn

## Broader project (non-LED)
- [ ] **Generators:** get ≥1 of the 3 repaired and running for the playa
- [ ] **Trailer:** upgrade to 7000 lb payload (current 5000 lb is short of the ~3960 lb build)
- [ ] **Tasks:** sniff CAN bus & limit to 5 mph · pocketable remote · decoration hooks ([../logistics/tasks.md](../logistics/tasks.md))
