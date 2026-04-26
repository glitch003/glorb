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

## Tube spec

- Flexible 360° silicone neon tube, **22 mm diameter, 5 m long**
- Source (Alibaba): <https://www.alibaba.com/product-detail/Flexible-360-Degree-Black-White-Silicone_1601739508491.html?spm=a2700.prosearch.normal_offer.d_image.1d1d67afJOPjmS&priceId=c2b1047e281c4079a8f678bd0d41239d>

## How many tubes?

Tight-packed shoulder-to-shoulder around the perimeter:

```
tubes = perimeter / tube diameter
      = (2 × 1800 + 2 × 4000) / 22
      = 11 600 / 22
      = 527.27   →   527 tubes
```

Total tube length: **527 × 5 m = 2 635 m** of neon flex.

Pitch = tube diameter + gap. Tubes = ⌊11 600 / pitch⌋. Power columns assume tubes lit at full brightness; existing loads ([../electrical/power-budget.md](../electrical/power-budget.md)) eat ~7.66 kW, so the broom must fit in the remaining **~6.7 kW** of pack headroom (or run off the genny).

| Gap (mm) | Pitch (mm) | Tubes | Total m | Watts @ 14.4 W/m | Watts @ 7.2 W/m | Fits in 6.7 kW headroom? |
| ---: | ---: | ---: | ---: | ---: | ---: | :---: |
| **0 (tight)** | 22 | **527** | 2 635 | 37 944 | 18 972 | ❌ |
| 1 | 23 | 504 | 2 520 | 36 288 | 18 144 | ❌ |
| 2 | 24 | 483 | 2 415 | 34 776 | 17 388 | ❌ |
| 3 | 25 | 464 | 2 320 | 33 408 | 16 704 | ❌ |
| 5 | 27 | 429 | 2 145 | 30 888 | 15 444 | ❌ |
| 8 | 30 | 386 | 1 930 | 27 792 | 13 896 | ❌ |
| 10 | 32 | 362 | 1 810 | 26 064 | 13 032 | ❌ |
| 15 | 37 | 313 | 1 565 | 22 536 | 11 268 | ❌ |
| 20 | 42 | 276 | 1 380 | 19 872 | 9 936 | ❌ |
| 25 | 47 | 246 | 1 230 | 17 712 | 8 856 | ❌ |
| 30 | 52 | 223 | 1 115 | 16 056 | 8 028 | ❌ |
| 40 | 62 | 187 | 935 | 13 464 | 6 732 | ⚠️ borderline (7.2 W/m) |
| 50 | 72 | 161 | 805 | 11 592 | 5 796 | ✅ at 7.2 W/m |
| 78 | 100 | 116 | 580 | 8 352 | 4 176 | ✅ at 7.2 W/m |
| 178 | 200 | 58 | 290 | 4 176 | 2 088 | ✅ even at 14.4 W/m |

> 528 tubes would need 11 616 mm — 16 mm over the perimeter. So 527 is the true cap.

**Reading the table:** at high-density LEDs (14.4 W/m) you basically can't run off the pack — even with a 200 mm gap (58 tubes!) it's still 4.2 kW. With low-density tubes (7.2 W/m, 30 LEDs/m) you get into pack headroom around a **40–50 mm gap (~187–161 tubes)**. Add PWM brightness reduction or partial-animation patterns and you can push the count back up.

## Order math

Tubes ship at a fixed 5 m length, so order by tube count + slack for failures and connectors:

| Plan | Tubes | Notes |
| --- | ---: | --- |
| Tight pack, 0 spares | 527 | minimum |
| Tight pack, +5% spares | **554** | recommended order quantity |
| Tight pack, +10% spares | 580 | safer for desert use |

## ⚠️ Power problem — read before ordering

At standard neon flex density (60 LEDs/m, ~14.4 W/m), 2 635 m of tube draws:

- **2 635 m × 14.4 W/m ≈ 37 950 W (~38 kW)**

The pack ceiling is **14 400 W** (see [../electrical/power-budget.md](../electrical/power-budget.md)) and existing loads already eat ~7 660 W. **There is no scenario where 527 fully-lit tubes run from the existing batteries.**

Mitigation options (combine as needed):

| Option | Effect | Notes |
| --- | --- | --- |
| Lower LED density (e.g. 30 LEDs/m → ~7.2 W/m) | Cuts draw ~half → ~19 kW | Still over budget. Spec available from many sellers. |
| Run at reduced brightness (PWM ~30%) | Cuts draw to ~30% of max → ~11 kW @ 14.4 W/m, ~5.7 kW @ 7.2 W/m | Software/controller side. Free. |
| Animate — only a subset lit at any time | Cuts draw proportional to duty cycle | Chase / wave patterns are on-brand for "broom strokes" anyway |
| Generator runs continuously | Removes pack as bottleneck | We already own a genny — see [../logistics/expenses.md](../logistics/expenses.md) |
| Reduce tube count (with gaps) | 5 mm gaps → 429 tubes / ~31 kW max | Only buys ~20% — not the lever |

**Probably the path:** lower-density tubes (≤30 LEDs/m) + global PWM brightness cap + animated patterns + run off the generator when the broom is fully lit. Need to confirm exact W/m of the SKU before this calc is real.

## Cost ballpark

Silicone neon flex at 22 mm typically runs $5–15 / m delivered.

| Rate | 2 635 m | + 5% spares (2 770 m) |
| --- | ---: | ---: |
| $5/m | $13 175 | $13 850 |
| $10/m | $26 350 | $27 700 |
| $15/m | $39 525 | $41 550 |

Get a quote from the Alibaba seller for the full quantity — they almost always discount at this volume.

## TODOs before ordering

- [ ] Confirm with seller: LEDs/m options, exact W/m, voltage (12 V vs 24 V), cuttable interval
- [ ] Confirm tubes ship at exactly 5 m and ask about pricing breaks at 500+ pieces
- [ ] Decide: addressable (chase patterns, on-brand for broom strokes) vs. solid color
- [ ] Sketch the controller / PSU topology — 527 tubes × 5 m needs serious wire management; likely many smaller PSUs distributed around the perimeter rather than one big one
- [ ] Specify how tubes attach top + bottom (clip rail? grommets through corrugated plastic side panels?)
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
