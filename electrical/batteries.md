# Batteries

Firmware password: `QTHN6666`

## Current setup (post 2023-05 swap)

**Main pack:** Tesla modules — 6 modules wired **3s2p** for **72 V nominal**.

| | Value |
| --- | --- |
| Configuration | 3 series × 2 parallel = 6 modules |
| Pack voltage | 72 V nominal |
| Module weight | ~60 lb each → **360 lb total** |
| Pack capacity | ~30 kWh (rough — depends on exact Tesla module variant) |
| Cost (May 2023) | $4 800 total — see [../logistics/expenses.md](../logistics/expenses.md) |
| BMS | EV Stealth cell-tap boards (custom Tesla-module BMS) + balance charger |
| Charger | 2× Elcon UHF 6.6 kW CANbus (HK-LF-108-60), 90–265 VAC in, ~32 A each at 240 V — see [chargers.md](chargers.md) |
| Bench measurement | 2023-05-02 with 3s Tesla modules — see [power-measurements.md](power-measurements.md) |

The Tesla pack delivers far more current than the previous EG4 pack — the practical power bottleneck on the cart is now the [4 kW Giandel inverter](inverter.md) and the 72 V → 12 V converter for aux loads, not the cells.

**Aux pack:** **3× EG4 LifePower4 12 V 400 Ah** batteries (~4.8 kWh each → ~14.4 kWh) kept from the original 2022 build, repurposed as auxiliary 12 V supply (~300 lb total per [../logistics/weight.md](../logistics/weight.md)). Powers 12 V loads (RPi, dashboard, lighting controllers, the 4 kW inverter input bus). Count confirmed 2026-07-02 (original build had 6; 3 remain).

## Compartment (in)

| Width | Length | Height |
| --- | --- | --- |
| 40 | 70.87 | 17.72 |

This was sized for the EG4 12V 400Ah footprint (17.4 × 18.5 × 6.1 in, 2 wide × 3 long × 1 tall). The Tesla modules fit in a custom cage built by Anthony in May 2023 ([../logistics/expenses.md](../logistics/expenses.md): "Anthony / Battery cage work").

## Operating constants

- Car speed: 5 mph
- Range model: 600 Wh / mile
- Pack capacity ~30 kWh → theoretical range ~50 miles, drive time ~10 h @ 5 mph

## Original 2022 plan (superseded)

The cart shipped in 2022 with **EG4 LifePower4 12 V 400 Ah** as the main pack — 6 batteries in series for 72 V, $9 000, 654 lb. Replaced by Tesla modules in May 2023 because Tesla cells are lighter, cheaper used, and deliver much higher continuous current. The remaining EG4s became the aux pack.

The EG4 24 V 200 Ah variant (3 in series, $4 500, 327 lb) was also evaluated in 2022 but not chosen.
