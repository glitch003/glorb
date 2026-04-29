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

> ⚠️ The pasted spec from the seller reads "12V SM16703" — confirm with seller that the sample shipped is actually 24 V before placing the bulk order. SM16703 is more commonly a 12 V part.

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
| 100 | 116 | 94 | 500 | 96 000 | $3 875 | 14 000 | 15 000 |
| 150 | 77 | 55 | 750 | 144 000 | $5 813 | 21 000 | 22 500 |
| 200 | 58 | 36 | 1 000 | 192 000 | $7 750 | 28 000 | 30 000 |

For comparison, theoretical tight pack (no gap):

| 527 | 22 | 0 | 2 635 | 505 920 | $20 421 | 73 780 | 79 050 |

## Power — managed in software

Full-brightness, full-white numbers look scary (200 strips = 30 kW), but the practical plan is **dim them aggressively in software**. SM16703 is per-pixel PWM, so brightness scaling is free and proportional — 30 % brightness draws 30 % of the wattage. Neon flex at 30 % is still bright as hell.

| Strips | Full bright (white) | @ 50% bright | @ 30% bright | @ 30% bright + chase pattern (~30% lit) |
| ---: | ---: | ---: | ---: | ---: |
| 50 | 7.0–7.5 kW | 3.5–3.75 kW | 2.1–2.25 kW | ~0.7 kW |
| 100 | 14–15 kW | 7.0–7.5 kW | 4.2–4.5 kW | ~1.4 kW |
| 150 | 21–22.5 kW | 10.5–11.25 kW | 6.3–6.75 kW | ~2.0 kW |
| 200 | 28–30 kW | 14–15 kW | 8.4–9.0 kW | ~2.7 kW |

Pack ceiling is **14.4 kW**. Existing loads at peak draw ~10.3 kW (incl. real QSC sub rating of 3.6 kW) leaving ~**4.1 kW peak headroom** ([../electrical/power-budget.md](../electrical/power-budget.md)). For sustained playback at typical music levels the loads are closer to ~5.2 kW, leaving ~**9.2 kW typical headroom**.

**Reading the math against headroom:**

- @ 30% bright + animation: even **200 strips (~2.7 kW)** fits inside peak headroom ✅
- @ 30% bright (no animation, full sweep lit): **150 strips fits typical headroom**, borderline against peak headroom
- @ 50% bright: **50 strips fits comfortably**; 100 strips overruns peak unless the sound system isn't peaking simultaneously
- @ 100% bright: needs the genny for any scale ≥ 50 strips

**Practical plan:** buy generously (150–200 strips), set a global brightness cap in firmware (~30%), use animated chase / wave patterns most of the time (the "broom stroke" aesthetic anyway). Reserve full brightness for short bursts when plugged into the genny.

## Recommendation

**150 strips, +5% spares = order ~158 strips (≈ $6 100).** Reasoning:

- 55 mm gap reads visibly as bristles, not a wall of light — actually broom-shaped
- Real-world animated draw lands ~3–4 kW (genny-easy, even pack-friendly)
- Headroom to grow (can fill in to 200 later if it looks too sparse)
- ~$6k is a defensible spend versus the existing $93k project total

Fallbacks:

- If you want maximum impact and the genny can carry it: **200 strips + 5% spares ≈ $8 100**
- If budget is the constraint: **100 strips + 5% spares ≈ $4 100** (94 mm gap — a bit airy but still reads as bristles in motion)

## Order math

| Plan | Strips | Cost @ $7.75/m |
| --- | ---: | ---: |
| 50 + 5% spares | 53 | $2 054 |
| 100 + 5% spares | 105 | $4 069 |
| **150 + 5% spares (recommended)** | **158** | **$6 123** |
| 200 + 5% spares | 210 | $8 138 |

Ask the Alibaba seller for a volume-discount quote — at 150–200 pieces they almost always come down 10–20% from the listed per-meter price.

## TODOs

- [x] ~~Pick strip type~~ — D22 RGBIC SM16703, sample ordered
- [ ] Evaluate sample on arrival: brightness, diffuser quality, color accuracy, voltage as shipped
- [ ] Confirm with seller the bulk order is **24 V** (the listing template says 12 V — verify before ordering 150+)
- [ ] Get a volume quote at 150–200 strips ($ per meter usually drops 10–20% at this scale)
- [ ] Source the 72 V → 24 V DC-DC converter (sized 5–8 kW for headroom)
- [ ] Sketch the controller / PSU topology — likely 1 ESP32 + WLED per ~10–20 strip zone, sync'd via E1.31
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
