# Tube labeling progress

Tracks which groups have their 4 tubes **labeled (both ends)** and **grouped up**. See [tube-map.md](tube-map.md) for the full map; this file is hand-maintained.

**Progress: 24 / 34 groups** (96 / 136 tubes) — last updated 2026-07-26

## A — Left-Front
- [ ] G1 · L01–L04
- [ ] G2 · L05–L08
- [ ] G3 · L09–L12
- [ ] G4 · L13–L16
- [ ] G5 · L17–L20
- [ ] G6 · L21–L24
- [ ] G7 · L25–L28

## B — Left-Back
- [ ] G8 · L29–L32
- [ ] G9 · L33–L36
- [ ] G10 · L37–L40
- [x] G11 · L41–L44
- [x] G12 · L45–L48
- [x] G13 · L49–L52
- [x] G14 · L53–L56

## C — Back ✅ complete
- [x] G15 · B01–B04
- [x] G16 · B05–B08
- [x] G17 · B09–B12
- [x] G18 · B13–B16
- [x] G19 · B17–B20
- [x] G20 · B21–B24

## D — Right-Back ✅ complete

> ⚠️ **HARDWARE TODO:** D was hung as **two 14-tube lines** (not the planned
> 16/12), with line 1 (D1, GPIO 12) **mirrored** — injected at R14 (middle
> of the section), running right-to-left to R01. Line 2 (D2, GPIO 13) is
> injected at R15, running to R28. The map (`REVERSED_LINES` + D's custom
> line spec in [tube_map.py](tube_map.py)) reflects the as-built order
> below — group sizes are uneven (G24 = 2 tubes, G27 = 6) and the group
> flags on D's tubes no longer match their electrical group.
> **Rehang D1 left-to-right and restore the 16/12 split, then revert
> tube_map.py** (G21 · R01–R04 … G27 · R25–R28).

- [x] G21 · R14–R11 (mirrored)
- [x] G22 · R10–R07 (mirrored)
- [x] G23 · R06–R03 (mirrored)
- [x] G24 · R02–R01 (mirrored, 2 tubes)
- [x] G25 · R15–R18
- [x] G26 · R19–R22
- [x] G27 · R23–R28 (6 tubes)

## E — Right-Front ✅ complete
- [x] G28 · R29–R32
- [x] G29 · R33–R36
- [x] G30 · R37–R40
- [x] G31 · R41–R44
- [x] G32 · R45–R48
- [x] G33 · R49–R52
- [x] G34 · R53–R56
