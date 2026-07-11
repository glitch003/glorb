# Broom LED tube — power wiring & disconnect

Physical power wiring for the **100 × 2.5 m SM16703 tubes** ([../broom/DESIGN.md](../broom/DESIGN.md)) on the 24 V bus. Data wiring is separate — see [../lights/controllers.md](../lights/controllers.md). Power source (which battery bank) is decided in [led-power.md](led-power.md); this doc assumes a single 24 V feed point at the battery.

## Load & geometry (from DESIGN.md / dimensions.md)

- **Perimeter:** 11.6 m ≈ **38 ft**. Half-perimeter per leg ≈ 5.8 m ≈ **19 ft**.
- **Currents @ 24 V:** idle 42 A · typical chase **125 A** · worst dimmed-solid 138 A · full-white burst **306 A** (firmware-capped).

## Topology — two legs, split at the battery

Run **two trunk pairs from the battery, one clockwise and one counter-clockwise, each covering ~half the perimeter (~19 ft).** Tubes tap the nearest trunk.

```
                far end (least current)
        ┌───────────────·───────────────┐
   leg A│                                 │leg B
        │                                 │
        └──────[BREAKER/DISCONNECT]───────┘
                      │
                 BATTERY +/-  (one spot)
```

Why split beats a single run-around the whole car:
- **Ampacity (the real driver at 24 V):** each leg carries half the current (~62 A typical vs 125 A) → usable **4 AWG** instead of stiff 2/0. Easier to route and terminate.
- **Voltage drop quartered** — half the current over half the distance.
- Far ends (opposite the battery, where the legs stop) carry the least current → naturally balanced.

A full **ring** (run all the way around, tie both ends back to the battery) is marginally better for balance but doubles trunk copper and complicates fusing — not worth it at these margins. Split feed is the sweet spot.

## Disconnect + protection

One **DC circuit breaker with manual switch lever, 150 A, DC-rated ≥32 V**, on the main **+** feed *before* it splits into the two legs. Single part = daytime "kill the LEDs" disconnect **and** wire protection. Kill it → both legs dark.

- A 150 A trip means a runaway **full-white** command (306 A) trips the breaker — a useful hardware backstop, since brightness is firmware-capped to ~30% anyway.
- Want sustained full white? Bump to a **200 A breaker + 2 AWG legs**.

## Wire gauge & voltage drop

**Trunk: 4 AWG per leg** (tinned/marine for BRC dust). Drop over 19 ft legs, split feed:

| Load | Amps/leg | Drop (4 AWG) | % of 24 V |
| --- | ---: | ---: | ---: |
| Typical chase | 62 A | ~0.30 V | 1.2% |
| Worst dimmed-solid | 69 A | ~0.33 V | 1.4% |
| Full-white burst | 153 A | ~0.72 V | 3% |

4 AWG marine ≈ 150 A continuous, so typical draw loafs; full-white burst is at the limit but brief. **6 AWG** is the lighter/cheaper alternative (~0.47 V typical, ~100 A ampacity) — fine typical/dimmed, marginal on full-white bursts.

At 24 V, drop is never the constraint. Even on the 18–25 V Tesla-module bank option ([led-power.md](led-power.md)), the far tube stays ~17.5 V worst case — well above the SM16703's ~10–12 V constant-current dropout.

**Per-tube drops: 18 AWG.** Each tube pulls max ~3 A (full white) / ~1.3 A typical. With zone bus bars every ~1.3 m (below), each drop is short (≤ ~0.7 m).

## Tube connections — tiered trunk + zone bus bars

Don't tap the 4 AWG trunk 100 times. 4 AWG is a big heat-sink (hard to solder) and T-tap/IDC connectors top out around 10–12 AWG. Instead, two tiers:

- **4 AWG trunk stays continuous** along the top rail, two legs (split at battery).
- Every ~10–12 tubes, land the trunk on a **bus bar** — cut the trunk and land both ends on the bar's two main studs, so the bar is an inline node passing the leg current through. **~8–10 bus bars** total, mirroring the ~10 WLED zones / 4 sides.
- Each tube's **18 AWG drop lands on a screw terminal** on the nearest bus bar.

Only ~8–10 lugged bus-bar landings are heavy joints — **no soldering to 4 AWG** — and the 200 tube connections become serviceable **screw terminals**, good for dust/vibration.

**Bus-bar sizing:** near-battery bars pass the full leg current (~69 A sustained worst-dimmed, ~153 A full-white burst) → use **≥150 A rated** bars for those; downstream bars can be lighter. **Fused distribution blocks** per zone are a nice optional upgrade so one zone short doesn't drop the whole leg.

## Routing — top rail (power + data together)

Both the 4 AWG power trunk and the tube data lines run along the top rail:

- Keep each **data wire paired with its own ground return** back to its Angio, all grounds tied common at the controller (shared-ground requirement, [../lights/controllers.md](../lights/controllers.md)).
- Give the data lines a few cm of separation from the high-current trunk over long parallel runs to keep switching noise off the signal. It's DC so coupling is mild; the DIN series resistor + short data pigtail at each tube matter more.

## Feet needed

- **4 AWG trunk:** 2 legs × 19 ft × 2 conductors ≈ 76 ft → buy **50 ft red + 50 ft black** for slack + battery-to-split jumpers.
- **18 AWG drops:** short with zone bus bars (≤ ~0.7 m each) → ~100 tubes × ~1 ft × 2 ≈ 200 ft → **100 ft red + 100 ft black** covers it (less if factory leads reach the bar).

## Order list (BOM)

| # | Item | Qty | Notes |
| --- | --- | ---: | --- |
| 1 | DC circuit breaker, 150 A, manual switch, DC-rated ≥32 V | 1 | Combined disconnect + main protection on the + feed |
| 2 | 4 AWG cable, tinned/marine | 50 ft red + 50 ft black | Two trunk legs |
| 3 | 18 AWG cable, red + black | 100 ft each (adjust) | Per-tube +24 V / GND drops |
| 4 | Ring lugs for 4 AWG + adhesive heatshrink | ~30 lugs | Battery, breaker, split junction, + 2 per bus bar |
| 5 | Bus bars, ≥150 A, multi-terminal (or fused distribution blocks) | ~8–10 | Zone injection nodes; near-battery ones must pass full leg current |
| 6 | Ferrules/spade terminals for 18 AWG | ~220 | Land tube drops on bus-bar screw terminals |
| 7 | 1000 µF, ≥35 V electrolytic caps | 100 (+10 spare) | One per injection point (per controllers.md) |
| 8 | Adhesive cable-tie mounts or P-clips | ~150 | Secure trunk every ~250–300 mm around the rail |
| 9 | Zip ties | 500-pack | General |
| 10 | Common ground bus bar | 1 | Tie LED negative + all Angio grounds + battery negative — **shared ground is mandatory** for the data signal |
| 11 | Inline DC ammeter / shunt, 0–200 A *(optional)* | 1 | Watch real draw, tune the firmware cap |

## Confirm before ordering

1. **Routing DECIDED: top rail**, power trunk + data lines together. Tubes inject at the top end; trunk and bus bars ride the top.
2. **Tube factory lead length** — sets 18 AWG quantity and whether drop wire is needed at all vs. landing factory leads straight on the bus bar.

## Purchasing — Amazon ASINs (verify before reordering)

> ⚠️ ASINs and prices **drift** — listings get discontinued, relisted, or change specs. These were pulled from live `/dp/` URLs on **2026-07-09** but not page-confirmed (Amazon blocked automated fetches). Re-verify before any reorder.

| Item | Product | ASIN | Qty | ~Each |
| --- | --- | --- | ---: | ---: |
| Disconnect/breaker | Blue Sea 7148 150 A switchable, 48 VDC | B00EF0QSH0 | 1 | $45 |
| 4 AWG trunk ⚠️ | TEMCo 25 ft red + 25 ft black (×2 = 50 ft/color) | B00LIB7YTU | 2 | $55 |
| 18 AWG drops | Best Connections 100 ft red + 100 ft black | B01AO0M8TG | 1 | $25 |
| 4 AWG lugs ⚠️ | 4 AWG ring lugs + heatshrink, 10-pk | B01996UWX0 | 3 | $12 |
| Bus bars | Blue Sea 2302 common busbar, 150 A, 20-gang | B000K2NZ3C | 10 | $28 |
| 18 AWG ferrules | TICONN 1200-pc ferrule kit + tool | B09F94TPRV | 1 | $30 |
| Injection caps | 1000 µF 50 V electrolytic, 100-pk | B0F9TK3V21 | 2 | $15 |
| Cable-tie mounts | Pro Tie adhesive+screw bases, 100-pk | B005LTJ4PW | 2 | $12 |
| Zip ties | Southern 94, 8", 500-pk | B075LPQJFK | 1 | $15 |
| Ammeter (optional) | DC 0-200 A meter + shunt | B0GG1TKHSQ | 1 | $18 |

**One-click add-to-cart URL** (click while logged into Amazon; legacy endpoint may skip third-party ASINs — fall back to `amazon.com/dp/ASIN`):

```
https://www.amazon.com/gp/aws/cart/add.html?ASIN.1=B00EF0QSH0&Quantity.1=1&ASIN.2=B00LIB7YTU&Quantity.2=2&ASIN.3=B01AO0M8TG&Quantity.3=1&ASIN.4=B01996UWX0&Quantity.4=3&ASIN.5=B000K2NZ3C&Quantity.5=10&ASIN.6=B09F94TPRV&Quantity.6=1&ASIN.7=B0F9TK3V21&Quantity.7=2&ASIN.8=B005LTJ4PW&Quantity.8=2&ASIN.9=B075LPQJFK&Quantity.9=1&ASIN.10=B0GG1TKHSQ&Quantity.10=1
```

Flags:
- **4 AWG (B00LIB7YTU)** is **bare copper**, not tinned marine — swap for "Ancor 4 AWG 50 ft" if you want tinned for dust/corrosion resistance.
- **Lugs (B01996UWX0)** — lowest-confidence ASIN; confirm 4 AWG / 3/8" ring / heatshrink.
- **Bus bars qty 10** is an estimate: 2302 has 20 gangs → ~10 bars covers 100 tubes' +24 V and ground drops with margin. Doubles as the common ground bar. Adjust to final tubes-per-zone.

## Related

- [led-power.md](led-power.md) — which 24 V bank feeds this (EG4 2s2p vs Tesla module vs DC-DC)
- [../lights/controllers.md](../lights/controllers.md) — data wiring, shared-ground requirement, 1000 µF injection caps
- [../broom/DESIGN.md](../broom/DESIGN.md) — tube count, measured power, perimeter
- [power-budget.md](power-budget.md) — overall cart load budget
