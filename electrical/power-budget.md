# Power budget

## Source

> The 14 400 W "max watts" below was the 2022 EG4 pack's continuous ceiling (6 × 12 V × 200 A). After the May 2023 Tesla module swap ([batteries.md](batteries.md)) the cells themselves can deliver substantially more, so the practical pack ceiling is now set by the **4 kW [Giandel inverter](inverter.md)** for AC loads and the 72 V → 12 V converter for DC aux. The 14.4 kW figure is kept here as a working budget number for headroom calcs across legacy docs — actual pack-cell limit is higher.

| Batteries max current (A) | Battery count | Max watts |
| ---: | ---: | ---: |
| 200 | 6 | 14 400 |

## Loads — peak (worst-case for sizing)

AC loads (marked 🔌) route through the [Giandel 4 kW inverter](inverter.md). DC loads tap the 12 V bus directly.

| Thing | Bus | Watts each | Count | Total W | Amps @ 12 V |
| --- | :---: | ---: | ---: | ---: | ---: |
| LEDs (existing panels) | DC | 72 | 30 | 2 160 | 180 |
| QSC K12.2 tops | 🔌 | 2 000 | 2 | 4 000 | 333.33 |
| QSC KS118 sub | 🔌 | 3 600 | 1 | 3 600 | 300.00 |
| Other lights | DC | 100 | 1 | 100 | 8.33 |
| Freezer | 🔌 | 400 | 1 | 400 | 33.33 |
| **Total (peak)** | | | | **10 260** | **855** |

**AC subtotal (through inverter):** 8 000 W rated peak — at the inverter's 8 kW peak ceiling. The 4 kW *rated* output is exceeded if QSC sub + tops + freezer all peak together. Typical playback (~⅓ rated) lands ~2.9 kW, well within rated.

Peak headroom: 14 400 − 10 260 = **4 140 W** spare against the 200 A pack ceiling.

> Subwoofer was previously listed at 1 000 W on the spreadsheet; the actual QSC KS118 rating is **3 600 W peak program** ([sound/setup.md](../sound/setup.md)). Updated to match nameplate.

## Loads — typical playback (realistic for sustained pack draw / range)

QSC speakers' rated power is peak program, not what they actually consume during normal music playback. Field-typical sustained draw is ~⅓ of rated:

| Thing | Typical W | Notes |
| --- | ---: | --- |
| LEDs (existing panels) | 2 160 | Same — LEDs run at rated draw when on |
| QSC K12.2 tops (×2) | ~1 300 | ~⅓ of peak per speaker |
| QSC KS118 sub | ~1 200 | ~⅓ of peak |
| Other lights | 100 | |
| Freezer | 400 | Compressor cycles — average lower |
| **Typical total** | **~5 200** | |

Typical headroom: 14 400 − 5 200 ≈ **9 200 W** for sustained operation. This is the right number for range / runtime planning; the 4 140 W peak headroom is the right number for breaker and inverter sizing.
