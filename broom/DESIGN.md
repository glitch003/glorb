# Broom — design doc

Glorb gets converted into a giant glowing broom.

- **Bristles:** flexible 22 mm silicone neon tubes hung vertically around the **full perimeter** of the car. **Tube length 2.5 m, 100 tubes ORDERED** (2026-07-02).
  - **Length validated on the car (2026-07-01):** 2.5 m matches the existing side panels — **99 in ≈ 2 515 mm** — which are already the perfect size and mount without dragging. Hang the tubes to span the same vertical zone as the panels; the panels prove 2.5 m fits, so the earlier deck-vs-roof drag question is moot.
- **Handle:** stripper pole mounted on the upper deck.

## Cart geometry

| | mm |
| --- | ---: |
| Width | 1 800 |
| Length | 4 000 |
| Height | ~3 658 (12 ft) |
| **Perimeter** | **11 600** |

## Chosen strip — ORDERED

> Sample evaluated (2026-06-19, 24 V confirmed). **Bulk order placed 2026-07-02: 100 tubes @ 2.5 m (50× 5 m rolls).**

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

**Architecture:** the 24 V source is now being planned alongside a **12 V → 24 V inverter swap** (the ~370 A 12 V inverter bus is halved at 24 V). Leading option is a **2s2p 24 V bank from the EG4 aux batteries** feeding both LEDs and the new 24 V inverter, buffered/topped by a small 72 V → 24 V DC-DC off the Tesla main pack. Full analysis, battery-count caveat, and 2S-rating gate: **[../electrical/led-power.md](../electrical/led-power.md).**

## Layout scenarios

Theoretical max around the 11 600 mm perimeter is **527 strips** tight-packed (touching). At this density and wattage that's ~78 kW — physically can't happen — so the question is how sparse to go. Pitch = 11 600 / N.

Tube length is **2.5 m**, **100 tubes ordered** (116 mm pitch, 94 mm gap). All figures below scale with that length:

| Strips | Pitch (mm) | Gap (mm) | Total m (@2.5 m) | Total LEDs | Cost @ $19.38/tube | W full-white @ 28 W/m | @ 30 W/m |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 50 | 232 | 210 | 125 | 24 000 | $969 | 3 500 | 3 750 |
| 60 | 193 | 171 | 150 | 28 800 | $1 163 | 4 200 | 4 500 |
| 75 | 155 | 133 | 188 | 36 000 | $1 453 | 5 250 | 5 625 |
| 80 | 145 | 123 | 200 | 38 400 | $1 550 | 5 600 | 6 000 |
| **100** | **116** | **94** | **250** | **48 000** | **$1 938** | **7 000** | **7 500** |
| 150 | 77 | 55 | 375 | 72 000 | $2 906 | 10 500 | 11 250 |
| 200 | 58 | 36 | 500 | 96 000 | $3 875 | 14 000 | 15 000 |

For comparison, theoretical tight pack (no gap):

| 527 | 22 | 0 | 1 318 | 252 960 | $10 211 | 36 890 | 39 525 |

> **Total strip meterage (= N × 2.5 m) drives both cost and power.** The ordered **100 × 2.5 m = 250 m** has the same power/cost profile as a hypothetical 50 × 5 m plan (also 250 m), spread at 116 mm pitch. Sourcing: the strip ships in 5 m rolls — cut to 2.5 m (2 tubes/roll, no offcut) — 100 tubes = 50 rolls.

## Power — managed in software

Full-brightness, full-white numbers look scary, but the plan is to **dim aggressively in software** and lean on chase patterns. Software dimming **cannot get you below the idle floor** (10 W/tube at 2.5 m — see scaling note below), no matter how few pixels are lit. At the ordered 100 tubes the idle floor is 1.0 kW; the binding question is now the **power source** (own 24 V bank vs. shared pack — see below), not the tube count.

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

> **Bench data is from a 5 m sample; tubes are now 2.5 m.** Per-tube power for the all-pixel states scales by length (× 0.5): **idle 10 W**, 30% white 33 W, **full white 73.5 W**, at 480 LEDs/tube. (W/m figures are unchanged — they're length-independent.)

**Real animated-pattern draw (measured 2026-06-19):** running the Larson scanner ([../lights/nano_sm16703_cylon/](../lights/nano_sm16703_cylon/)) at **full brightness (255)** draws only **37–45 W/tube on the 5 m sample** — because a sweep pattern only lights a few pixels (+ short fade tail) at any instant, the lit-pixel count dominates, not the brightness cap. On a 2.5 m tube the idle portion drops to 10 W but the lit comet barely shrinks, so the typical figure does **not** scale by a clean 0.5×. **Planning figure: ~30 W/tube for typical pattern playback at 2.5 m** (conservative). This is the number to budget against day-to-day, not the all-lit cases below.

**The idle floor (10 W/tube at 2.5 m) still doesn't scale with brightness.** The SM16703 ICs draw it whenever the strip is powered, *regardless of brightness* — commanding pixels black does NOT remove it. It's a fixed floor under every scenario (4 W/m × 2.5 m):

Idle floor, the typical-pattern figure, and the all-lit cases by tube count — **all scaled to 2.5 m tubes**. Typical (~30 W/tube) is the real day-to-day number; the chase column is **derived** (idle floor + 30%-bright LED portion × ~30% lit); the all-lit columns are worst cases:

| Tubes | Idle floor | Typical pattern @ ~30 W/tube | 30% bright + ~30% chase (derived) | 30% white, all lit | 100% white |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 50  | 0.50 kW | 1.50 kW | ~0.85 kW | 1.65 kW | 3.68 kW |
| 60  | 0.60 kW | 1.80 kW | ~1.01 kW | 1.98 kW | 4.41 kW |
| 75  | 0.75 kW | 2.25 kW | ~1.27 kW | 2.48 kW | 5.51 kW |
| 80  | 0.80 kW | 2.40 kW | ~1.35 kW | 2.64 kW | 5.88 kW |
| **100** | **1.00 kW** | **3.00 kW** | **~1.69 kW** | **3.30 kW** | **7.35 kW** |
| 150 | 1.50 kW | 4.50 kW | ~2.54 kW | 4.95 kW | 11.03 kW |
| 200 | 2.00 kW | 6.00 kW | ~3.38 kW | 6.60 kW | 14.70 kW |

> Note the pattern: a 2.5 m tube at count N draws exactly what a 5 m tube drew at count 0.5 N. So **the ordered 100 × 2.5 m ≡ 50 × 5 m** on every power column.

Implications against headroom (peak ~4.1 kW / typical ~9.2 kW — but see the power-source note: LEDs may get their **own** 24 V bank, off this shared budget entirely):

- **Dimming is NOT proportional** — the 10 W floor doesn't scale. 30% brightness still draws ~45% of full white, not 30%. N × 10 W is the hard minimum any time the bus is hot.
- **Typical-pattern draw is ~30 W/tube** at 2.5 m → **100 tubes ≈ 3.0 kW** day-to-day. This is the figure to plan against.
- **100 tubes (ordered) is comfortable.** Idle 1.0 kW, typical 3.0 kW, worst dimmed-solid (30%-white-all-lit) 3.3 kW — all under the 4.1 kW shared peak headroom. Only **100% white solid (7.35 kW)** exceeds peak; it fits *typical* headroom (9.2 kW) for short bursts, or run it on the genny.
- **If LEDs get a dedicated 24 V battery bank** (the plan under discussion), none of this competes with the inverter/drivetrain budget — the shared headroom above stops being the constraint and the LED bank's own capacity/runtime becomes the limit instead.
- **Per-zone 24 V bus cutoff with contactors when parked** — idle is 1.0 kW at 100 tubes; worth cutting so it isn't draining a bank overnight.

Pack ceiling is **14.4 kW**. Existing loads at peak draw ~10.3 kW (incl. real QSC sub rating of 3.6 kW) leaving ~**4.1 kW peak headroom** ([../electrical/power-budget.md](../electrical/power-budget.md)). For sustained playback at typical music levels the loads are closer to ~5.2 kW, leaving ~**9.2 kW typical headroom**.

**Reading the math against shared headroom (2.5 m tubes, if LEDs share the pack):**

- **Idle floor:** N × 10 W: 100→1.0, 150→1.5, 200→2.0 kW.
- @ 30% bright + chase (normal operating mode): every count up to **200 (~3.4 kW)** fits peak headroom.
- @ 30% bright, full sweep lit (worst dimmed case): **100 (3.3 kW)** stays under peak; **150 (4.95 kW)** overruns peak, fits typical; **200 (6.6 kW)** typical only.
- @ 100% bright: **100 (7.35 kW)** fits typical headroom for short bursts; **150+ needs the genny**.

**Practical plan:** **100 tubes @ 2.5 m (ORDERED)**, global brightness cap ~30% in firmware, animated chase / wave patterns (the "broom stroke" aesthetic anyway), and **per-zone 24 V bus cutoff** when parked. Reserve full white for short bursts. If LEDs get their own 24 V bank (see Power source), the shared-headroom limits above don't apply — bank runtime does.

## Recommendation — SETTLED

**100 tubes @ 2.5 m — ORDERED 2026-07-02 (≈ $1 940, 50 rolls cut 2-per).**

- Idle 1.0 kW, typical chase ~3.0 kW, worst dimmed-solid 3.3 kW — all under the 4.1 kW shared peak headroom. Only 100%-white-solid (7.35 kW) needs typical headroom or the genny; cap it in firmware.
- 116 mm pitch / 94 mm gap — a solid, clearly-bristled look.
- Install load: ~100 hangs, ~10 WLED zones, 100 single-end 24 V injection points. Budget the labor.

## Order math

| Plan | Tubes | Cost @ $19.38/tube | Idle floor |
| --- | ---: | ---: | ---: |
| 50 | 50 | $969 | 0.50 kW |
| 75 | 75 | $1 453 | 0.75 kW |
| **100 (ORDERED)** | **100** | **$1 938** | **1.00 kW** |
| 150 | 150 | $2 906 | 1.50 kW |
| 200 | 200 | $3 875 | 2.00 kW |

(5 m rolls cut 2 × 2.5 m each = no offcut; 100 tubes = 50 rolls. Ask the seller for a volume quote at 50 rolls / 250 m.)

## TODOs

- [x] ~~Pick strip type~~ — D22 RGBIC SM16703, sample ordered
- [ ] Evaluate sample on arrival: brightness, diffuser quality, color accuracy, voltage as shipped
- [x] ~~Bench-measure sample power~~ — done 2026-06-19: 20 W/tube idle, 147 W full white, sweep recorded in [Bench measurements](#bench-measurements--measured-2026-06-19)
- [x] ~~Confirm hang point~~ — validated on car 2026-07-01: tubes span the same zone as the existing 99 in (≈2.5 m) side panels, which fit without dragging.
- [ ] Design per-zone 24 V bus cutoff (contactors) — idle floor is 1.0 kW at 100 tubes; worth cutting when parked
- [x] ~~Confirm 24 V~~ — bench-confirmed 24 V on sample (2026-06-19); still worth restating to seller on the bulk PO
- [ ] Get a volume quote at 50 rolls / 250 m ($ per meter often still drops ~10%)
- [ ] **Decide LED power source** — dedicated 24 V bank (2s2p of the 12 V EG4 aux batteries) + 24 V inverter swap, vs. 72 V → 24 V DC-DC off the Tesla main pack. See [../electrical/led-power.md](../electrical/led-power.md).
- [x] ~~Sketch the controller topology~~ — settled: 4 Chroma-Tech Angio-8s (one per side, ~3 tubes/output, serpentine reverse in software), data+ground only with separate 24 V injection, xLights/FPP master over wired Ethernet (sACN). See [../lights/controllers.md](../lights/controllers.md).
- [ ] **Bench-test SM16703 on an Angio-8 output** — the Angio spec page doesn't list chipsets. Wire one tube to one output: confirm it lights, RGB color order, no flicker at length, and that the Angio drives 5 V data logic. Fall back to ESP32 + WLED per zone if it can't clock SM16703. See [../lights/controllers.md](../lights/controllers.md).
- [ ] Specify how strips attach top + bottom (clip rail? grommets through corrugated plastic side panels?)
- [ ] Stripper pole: source, mount plan, how it ties into the upper deck structurally

## Open questions

- **Tube length + hang RESOLVED: 2.5 m, 100 tubes ordered (2026-07-02).** Length matches the existing 99 in (≈2.5 m) side panels, validated on the car 2026-07-01 — tubes span the same zone, no drag. Power = 50% of the 5 m figures (idle 10 W, full white 73.5 W per tube).
- Bristles end at ground level or above? (Driveability + scraping at Black Rock concerns)
- Any color zoning around the perimeter (all white = broom-like; rainbow / chase = party-like)?
- Does the pole itself glow too? (Would tie the silhouette together visually.)

## Related

- [../dimensions.md](../dimensions.md) — cart dimensions source
- [../electrical/power-budget.md](../electrical/power-budget.md) — current 12 V load budget (the constraint)
- [../lights/leds.md](../lights/leds.md) — existing LED panel install (for comparison)
- [../lights/twisty-lights.md](../lights/twisty-lights.md) — twisty light coil math (similar density tradeoffs)
