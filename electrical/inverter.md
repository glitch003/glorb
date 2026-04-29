# Inverter

**Giandel 4000 W pure sine wave inverter — 12 V DC → 120 V AC.**

- Source: <https://www.amazon.com/dp/B08Q7VQ2S4>
- Pure sine wave, THD < 3 %, 90 % efficiency
- 4 × AC outlets + 1 × USB (5 V / 2.4 A)
- LCD remote with 36 ft cable
- Pre-charge function (limits inrush at startup)

## Specs

| | Value |
| --- | --- |
| Rated power | 4 000 W |
| Peak power | 8 000 W |
| Input voltage (DC) | 9.8 – 16 V |
| Output voltage (AC) | 110 – 125 V |
| Output waveform | Pure sine |
| THD | < 3 % |
| Efficiency | 90 % |
| Internal fuses | 16 × 30 A |
| Battery cables | 3 pairs × 2 ft (pure copper) |
| Remote | LCD, 36 ft cable |

## What it powers

This is the only path to 120 VAC on the cart. AC loads route through here:

- QSC K12.2 tops (×2) — 2 000 W each rated, ~⅓ typical
- QSC KS118 sub — 3 600 W rated, ~⅓ typical
- Freezer — 400 W
- Anything else with a wall plug

## Capacity sanity check

At rated **4 000 W AC out**:

- AC loads sum (peak nameplate): 4 000 + 3 600 + 400 = **8 000 W** — exceeds rated, fits in 8 kW peak window
- AC loads sum (typical playback): ~1 300 + 1 200 + 400 = **~2 900 W** — comfortable
- DC input current at 4 kW AC, 12 V, 90 %: **~370 A** — heavy bus current, watch the wiring

> If the broom build pushes the audio loud at the same time as the freezer cycles on, peak draw can briefly hit the 8 kW peak limit. Typical playback is well within rated.

## Related

- [power-budget.md](power-budget.md) — AC loads and how they sum against this inverter
- [batteries.md](batteries.md) — 12 V bus that feeds the inverter input
- [../sound/setup.md](../sound/setup.md) — biggest AC consumer
