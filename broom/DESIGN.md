# Broom — design doc

Glorb gets converted into a giant glowing broom.

- **Bristles:** flexible 22 mm silicone neon tubes hung vertically around the **full perimeter** of the car, top to bottom. Tubes are 5 m, car is ~12 ft (~3.66 m) tall, so each tube has ~1.34 m of slack that drapes / coils at the bottom — that's the bristle fluff.
- **Handle:** stripper pole mounted on the upper deck.

## Cart geometry

| | mm |
| --- | ---: |
| Width | 1 800 |
| Length | 4 000 |
| Height | ~3 658 (12 ft) |
| **Perimeter** | **11 600** |

## Chosen strip — ORDERED (sample)

> Sample on the way. Final order pending sample evaluation.

**Part:** D22 360° Silicone White Diffuser, RGBIC, double-sided

| Spec | Value |
| --- | --- |
| Diameter | 22 mm |
| Length per roll | 5 m |
| LED chip | SMD 3535 |
| LED density | 96 LEDs/m × 2 sides = **192 LEDs / m** (960 LEDs per 5 m strip) |
| Controller IC | **SM16703** (4-pin) |
| Protocol | Single-wire addressable — same family as WS2811 / WS2812. FastLED: `FastLED.addLeds<SM16703, DATA_PIN, RGB>(...)`. Existing WS2812 experience transfers 1:1. |
| Power | 28–30 W/m (140–150 W per strip at full brightness, full white) |
| Voltage | **24 V** (decision below) |
| Price | $7.75/m → **$38.75 per 5 m strip** |
| Source | <https://www.alibaba.com/product-detail/Flexible-360-Degree-Black-White-Silicone_1601739508491.html?spm=a2700.prosearch.normal_offer.d_image.1d1d67afJOPjmS&priceId=c2b1047e281c4079a8f678bd0d41239d> |

> ✅ **Confirmed 24 V** on the bench sample (2026-06-19). The seller's listing template said "12V" but the shipped strip runs at 24 V as specced.

## Voltage: 24 V

**Why 24 V over 12 V:** the supplier said 12 V strips need power injected at *both ends* of every strip; 24 V allows single-end injection. At 150+ strips that's 300 vs 150 install splice points — decisive on labor alone. Also: half the current, ¼ the I²R losses, thinner feed wire, cooler strips.

**The existing inverter doesn't help here.** The Giandel 4 kW unit is a 12 V DC → 120 V AC inverter ([../electrical/inverter.md](../electrical/inverter.md)) — it feeds the QSC speakers and freezer, not LEDs. LEDs need a separate DC supply path regardless of voltage choice.

**Architecture:** dedicated **24 V DC supply** for LED-only load. Two viable topologies:

| Topology | Pros | Cons |
| --- | --- | --- |
| **72 V pack → DC-DC → 24 V bus** | Direct from pack, no AC conversion, runs without genny | Need a beefy 72 V → 24 V DC-DC (uncommon part, ~$500–1500). Examples: TDK-Lambda industrial, EV-style Eltek/Eaton golf-cart converters. |
| **120 V AC (inverter or genny) → 24 V PSU** | Easy off-the-shelf parts (Mean Well RSP-3000-24, ~$700) | Adds a conversion step (genny → AC → DC, or pack → 12 V → AC → DC), worse efficiency. Forces inverter to share its 4 kW budget with LEDs at peak. |

**Recommendation:** go with the 72 V → 24 V DC-DC route. Avoids loading the existing inverter, runs off pack alone, less to fail. Roughly 5–8 kW of DC-DC capacity for the 200-strip ceiling at typical dimming.

## Layout scenarios

Theoretical max around the 11 600 mm perimeter is **527 strips** tight-packed (touching). At this density and wattage that's ~78 kW — physically can't happen — so the question is how sparse to go. Pitch = 11 600 / N.

| Strips | Pitch (mm) | Gap (mm) | Total m | Total LEDs | Cost @ $7.75/m | Watts @ 28 W/m | Watts @ 30 W/m |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 232 | 210 | 250 | 48 000 | $1 938 | 7 000 | 7 500 |
| 60 | 193 | 171 | 300 | 57 600 | $2 325 | 8 400 | 9 000 |
| 75 | 155 | 133 | 375 | 72 000 | $2 906 | 10 500 | 11 250 |
| 80 | 145 | 123 | 400 | 76 800 | $3 100 | 11 200 | 12 000 |
| 100 | 116 | 94 | 500 | 96 000 | $3 875 | 14 000 | 15 000 |
| 150 | 77 | 55 | 750 | 144 000 | $5 813 | 21 000 | 22 500 |
| 200 | 58 | 36 | 1 000 | 192 000 | $7 750 | 28 000 | 30 000 |

For comparison, theoretical tight pack (no gap):

| 527 | 22 | 0 | 2 635 | 505 920 | $20 421 | 73 780 | 79 050 |

## Power — managed in software

Full-brightness, full-white numbers look scary, but the original plan was to **dim aggressively in software** and lean on chase patterns. The bench data below kills part of that plan: software dimming **cannot get you below the idle floor** (~20 W/tube), no matter how few pixels are lit. That floor — not brightness — is now the dominant constraint, and it's what's pushing the count down toward 50.

> ⚠️ An earlier theoretical table here claimed a "30% bright + chase (~30% lit)" column reaching ~0.7 kW for 50 tubes. **That was wrong and physically impossible** — 50 tubes idle is already 1.0 kW, so nothing in software gets below that. Deleted; use the measured numbers below.

### Bench measurements — MEASURED (2026-06-19)

One 5 m sample tube, 24 V, full white, inline DC meter. Brightness swept in firmware:

| Brightness | W / tube | W/m | LED portion (W, minus idle) |
| ---: | ---: | ---: | ---: |
| idle (all black) | **20** | 4.0 | 0 |
| 4% | 27 | 5.4 | 7 |
| 10% | 36 | 7.2 | 16 |
| 20% | 51 | 10.2 | 31 |
| 30% | 66 | 13.2 | 46 |
| 100% | 147 | 29.4 | 127 |

Full white lands at **147 W/tube (29.4 W/m)** — bang on the 28–30 W/m spec. ✅

**The surprise is the 20 W idle floor.** That's ~6.5× my pre-bench estimate (had guessed 0.3–1 W/m; it's 4 W/m). The SM16703 ICs draw it whenever the strip is powered, *regardless of brightness* — commanding pixels black does NOT remove it. It's a fixed floor under every scenario:

Idle floor and the two measured-brightness points scaled by tube count. The chase column is **derived**, not measured (idle floor + 30%-bright LED portion × ~30% of pixels lit) — it respects the floor, unlike the deleted theoretical table:

| Tubes | Idle floor alone (measured) | 30% white, all lit (measured) | 30% bright + ~30% chase (derived) | 100% white (measured) |
| ---: | ---: | ---: | ---: | ---: |
| 50  | 1.0 kW | 3.3 kW | ~1.7 kW | 7.35 kW |
| 60  | 1.2 kW | 4.0 kW | ~2.0 kW | 8.82 kW |
| 75  | 1.5 kW | 4.95 kW | ~2.5 kW | 11.03 kW |
| 80  | 1.6 kW | 5.28 kW | ~2.7 kW | 11.76 kW |
| 100 | **2.0 kW** | 6.6 kW | ~3.4 kW | 14.7 kW |
| 150 | **3.0 kW** | 9.9 kW | ~5.1 kW | 22.05 kW |
| 200 | **4.0 kW** | 13.2 kW | ~6.8 kW | 29.4 kW |

Implications against headroom (peak ~4.1 kW / typical ~9.2 kW):

- **Dimming is NOT proportional** — the 20 W floor doesn't scale. 30% brightness draws ~45% of full white, not 30%, because of the floor. And no software trick gets below the floor: N tubes × 20 W is the hard minimum any time the bus is hot.
- **60 tubes is the safe sweet spot.** It's the largest count that stays under peak headroom (4.1 kW) even in the worst dimmed-but-solid case (30% white all lit = 3.96 kW). Idle 1.2 kW, 30%+chase ~2.0 kW — easy.
- **75–80 tubes** are viable and look fuller (133 / 123 mm gaps): 30%+chase fits peak (2.5 / 2.7 kW), but 30%-white-all-lit (4.95 / 5.28 kW) overruns *peak* — fine in *typical* headroom, just don't run a full-white solid sweep while the sound system peaks.
- **100 tubes** idle (2.0 kW) is livable but 30%-white-all-lit (6.6 kW) already overruns peak; only fits typical headroom, no margin for the sound system peaking.
- **150+ tubes** burns 3–4 kW doing *nothing* — eats most/all peak headroom before lighting a pixel. Off the table without the genny.
- **Cut the 24 V bus per zone with contactors when parked** — still worth it, but at 60–80 tubes the idle floor (1.2–1.6 kW) is survivable even if you forget.

Pack ceiling is **14.4 kW**. Existing loads at peak draw ~10.3 kW (incl. real QSC sub rating of 3.6 kW) leaving ~**4.1 kW peak headroom** ([../electrical/power-budget.md](../electrical/power-budget.md)). For sustained playback at typical music levels the loads are closer to ~5.2 kW, leaving ~**9.2 kW typical headroom**.

**Reading the math against headroom (measured):**

- **Idle floor is the binding constraint, not brightness.** N × 20 W is unavoidable whenever the bus is hot: 50→1.0, 60→1.2, 75→1.5, 80→1.6, 100→2.0 kW.
- @ 30% bright + chase (normal operating mode): **50–80 tubes (1.7–2.7 kW)** all fit peak headroom comfortably; **100 tubes (~3.4 kW)** fits with little margin; **150+ overruns peak**.
- @ 30% bright, full sweep lit (worst dimmed case): **50 (3.3) and 60 (3.96 kW)** stay under peak headroom; **75 (4.95) and 80 (5.28 kW)** overrun peak but fit typical (9.2 kW); 100 (6.6 kW) needs typical and no sound peaking.
- @ 100% bright: needs the genny at any scale ≥ 50 tubes.

**Practical plan:** **60 tubes**, global brightness cap ~30% in firmware, animated chase / wave patterns (the "broom stroke" aesthetic anyway), and **per-zone 24 V bus cutoff** so the idle floor isn't burning while parked. Reserve full brightness for short bursts on the genny.

## Recommendation

**60 tubes, +5% spares = order ~63 tubes (≈ $2 440).** Reasoning (revised after the 2026-06-19 bench + 60/75/80 layout study):

- **60 is the largest count that survives the idle floor *and* worst dimmed case.** 30%-white-all-lit lands at 3.96 kW, just under the 4.1 kW peak headroom — so even a solid full-perimeter sweep during a bass peak stays in budget. Idle is only 1.2 kW.
- The realistic 30%+chase draw (~2.0 kW) leaves comfortable margin — pack-friendly, no genny for normal operation.
- 193 mm pitch / 171 mm gap reads clearly as bristles in motion — noticeably fuller than 50's airy 210 mm gap.
- ~$2.4k is an easy spend; savings vs. the old 150-tube plan go toward bus-cutoff contactors and the DC-DC.

Fallbacks:

- Want more density and willing to enforce a firmware cap that forbids full-white-solid during sound peaks: **75–80 tubes (≈ $3.1–3.3k)** — gaps of 123–133 mm look great, 30%+chase fits peak, only the full-white-solid case dips into typical-only headroom.
- Minimum / most budget-conscious: **50 tubes (≈ $2 050)** — airier but safe.
- 100+ tubes need dedicated LED power (bigger DC-DC + genny budget); 150–200 are **off the table** on the current pack budget.

## Order math

| Plan | Tubes | Cost @ $7.75/m | Idle floor |
| --- | ---: | ---: | ---: |
| 50 + 5% spares | 53 | $2 054 | 1.0 kW |
| **60 + 5% spares (recommended)** | **63** | **$2 441** | **1.2 kW** |
| 75 + 5% spares | 79 | $3 061 | 1.5 kW |
| 80 + 5% spares | 84 | $3 255 | 1.6 kW |
| 100 + 5% spares | 105 | $4 069 | 2.0 kW |
| 150 + 5% spares | 158 | $6 123 | 3.0 kW |
| 200 + 5% spares | 210 | $8 138 | 4.0 kW |

Ask the Alibaba seller for a volume-discount quote even at ~60 pieces — they often still come down 10% from the listed per-meter price.

## TODOs

- [x] ~~Pick strip type~~ — D22 RGBIC SM16703, sample ordered
- [ ] Evaluate sample on arrival: brightness, diffuser quality, color accuracy, voltage as shipped
- [x] ~~Bench-measure sample power~~ — done 2026-06-19: 20 W/tube idle, 147 W full white, sweep recorded in [Bench measurements](#bench-measurements--measured-2026-06-19)
- [ ] Design per-zone 24 V bus cutoff (contactors) — idle floor is 2–4 kW at 100–200 tubes, too much to leave parked
- [x] ~~Confirm 24 V~~ — bench-confirmed 24 V on sample (2026-06-19); still worth restating to seller on the bulk PO
- [ ] Get a volume quote at ~60 tubes ($ per meter often still drops ~10%)
- [ ] Source the 72 V → 24 V DC-DC converter — size ~2.5 kW for 60 tubes (idle 1.2 kW + 30%+chase ~2.0 kW, with margin); was over-spec'd at 5–8 kW when 200 tubes was on the table
- [ ] Sketch the controller / PSU topology — likely 1 ESP32 + WLED per ~10 tube zone, sync'd via E1.31
- [ ] Specify how strips attach top + bottom (clip rail? grommets through corrugated plastic side panels?)
- [ ] Stripper pole: source, mount plan, how it ties into the upper deck structurally

## Open questions

- Bristles end at ground level or above? (Driveability + scraping at Black Rock concerns)
- Any color zoning around the perimeter (all white = broom-like; rainbow / chase = party-like)?
- Does the pole itself glow too? (Would tie the silhouette together visually.)

## Related

- [../dimensions.md](../dimensions.md) — cart dimensions source
- [../electrical/power-budget.md](../electrical/power-budget.md) — current 12 V load budget (the constraint)
- [../lights/leds.md](../lights/leds.md) — existing LED panel install (for comparison)
- [../lights/twisty-lights.md](../lights/twisty-lights.md) — twisty light coil math (similar density tradeoffs)
