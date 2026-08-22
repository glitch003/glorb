# Power draw & battery runtime

Measured 2026-08-21 on the real car with the back zones live (C1 + C2 =
**24 tubes**), running the **plasma** pattern, current read at the Tesla
module output (~22 V bus, everything — receivers *and* the K128's 5 V
converter — on that bus).

## The measurements

| glorb app slider | true brightness on the wire (FPP ceiling 30%) | current (24 tubes) |
|---:|---:|---:|
| 100% | 30% | 25 A |
| 50%  | 15% | 19 A |
| 5%   | 1.5% | 13 A |

## The model

The three points sit on a straight line (linear-brightness LUT → linear
current, as expected). Least-squares fit for the 24-tube back section:

```
I_back(b) ≈ 12.4 A  +  12.6 A × b        b = app slider, 0..1
```

Check: b=0.5 → 18.7 A (measured 19 A). Good.

The **12.4 A baseline** is what the section burns with the LEDs barely
lit: pixel-IC quiescent draw, the per-board buck converters, and the
BBB/K128 (the BBB is a rounding error, well under 1 A on this bus). It's
dominated by per-tube costs, so it scales with tube count.

Scale by 136/24 = 5.67 for the full car:

```
I_car(b) ≈ 70 A  +  72 A × b             (plasma, at ~22 V)
```

So the full car at slider 100% ≈ **142 A ≈ 3.1 kW** — right in line with
the earlier per-tube estimate (~22 W/tube at the 30% ceiling).

## Runtime on 6 × Tesla modules

Each module: 6S, ~22.2 V nominal, 230 Ah (~5.1 kWh). Six in parallel on
the 22 V bus = **1380 Ah / ~30.6 kWh**. Using **90% usable** (don't run
lithium to the floor, and the low-end sag is wasted anyway) →
**1242 Ah** for the show.

`runtime = 1242 Ah / I_car(b)`

| app slider | full-car current | power | runtime (LEDs only) |
|---:|---:|---:|---:|
| 5%   | 74 A  | 1.6 kW | **16.8 h** |
| 25%  | 88 A  | 1.9 kW | **14.1 h** |
| **40% (default)** | **99 A** | **2.2 kW** | **12.6 h** |
| 50%  | 106 A | 2.3 kW | **11.7 h** |
| 75%  | 124 A | 2.7 kW | **10.0 h** |
| 100% | 142 A | 3.1 kW | **8.8 h** |

Per single module, divide by 6 (e.g. one module runs the full car at 40%
for about 2.1 h).

## What the numbers are telling us

- **The baseline is the story.** ~70 A (~1.5 kW) flows before brightness
  does anything. Going from 100% → 5% brightness only doubles-ish your
  runtime (8.8 h → 16.8 h); most of the budget is burned just having the
  system *on*. If you need to stretch the battery, **cut power to the
  boards** (the `off` pattern still pays the full baseline).
- **Brightness is a weak lever below ~50%.** Dropping the default from
  40% to 25% buys only ~1.5 h. Run it at a brightness that looks good.
- The baseline number is worth a follow-up measurement: read the current
  with the `off` pattern (and again with data unplugged) to split "pixel
  quiescent" from "pattern floor" — plasma at 1.5% still lights every
  pixel dimly, so the true all-off floor may be lower than the fit's
  intercept.

## Caveats

- **Pattern-dependent.** Plasma averages roughly half-coverage color.
  Full-frame white at slider 100% is the worst case — expect roughly
  `70 A + ~140 A ≈ 210 A / 4.6 kW` (~6 h). Sparse patterns (comet,
  sparkle, rain) will beat the table.
- These are LED-only numbers. Driving the car, sound, or anything else
  on the same modules comes out of the same 1242 Ah.
- Currents were read at ~22 V nominal. As the pack sags toward ~19.5 V
  the converters pull proportionally more amps for the same light —
  the *energy* (kWh) math still holds, so the runtime table is fine.
- The 136-tube scaling assumes the sides behave like the back
  (same tubes, same W/tube). Re-check the fit once a side zone is up:
  measure plasma at 5/50/100% again and the slope should be ~5.67× the
  back-only numbers.
