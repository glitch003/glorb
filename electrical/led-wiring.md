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
- **18 AWG drops:** at 116 mm tube pitch ([../broom/DESIGN.md](../broom/DESIGN.md)) the ~6 in factory leads reach the 2–3 tubes nearest each bar directly; the rest need short drops of a few inches to ~0.4 m. Summed across ~10 zones ≈ 30 m total → buy **50 ft red + 50 ft black**. (Densifying to a terminal block every ~3 tubes would let factory leads land direct and drop this to near zero.)

## Zone plan — 14 zones × ~10 tubes (136 tubes, open front)

> ⚠️ **Updated 2026-07-24: tube count went 100 → 136 (open-front U-run).** This changes the injection-zone count and means some consumables ordered for 100 tubes are now short — see **[Reorder for 136 tubes](#reorder-for-136-tubes)** below.

Split feed, two legs. **14 injection zones of ~10 tubes each** (136 / 10 ≈ 14). Per zone, one **+24 V bar** (tapped off the red 4 AWG trunk) and one **ground bar** (tapped off the black trunk) — single-node bars can't mix polarity, so they come in +/− pairs. 14 zones × 2 = **28 bars**. At ~10 tubes/zone (~0.72 m span at the 72 mm pitch) the ~6 in factory leads reach the nearest tubes; the rest take short drops. Near-battery bars pass full leg current, so all bars are 150 A rated.

### Reorder for 136 tubes

The 2026-07-16 order was sized for 100 tubes / 10 zones. Going to 136 tubes / 14 zones, these come up short:

| Item | Have | Need (136) | Reorder |
| --- | ---: | ---: | --- |
| Busbars | 22 (11 two-packs) | 28 | **+3 Ampper 2-packs** (→ 28 + 2 spare) |
| Injection caps | 100 (4× 25-pk) | 136 | **+2 Innfeeltech 25-pks** (→ 150, ~14 spare) |
| 18 AWG drops | 50 ft/color | ~68 ft/color | **+1 more 50 ft 18/2** roll |
| 4 AWG ring lugs | 30 | ~60 (2 per bar × 28 = 56 + battery/breaker/split) | **+3–4 TKDMR 10-pks** — recount against final bar count |
| Fork terminals | 400 | 272 | ✅ enough |

Everything else (breaker, 4 AWG trunk, heatshrink, cable-tie mounts, ammeter) is unaffected.

## Ordered — 2026-07-16 (Amazon, total $624.96)

> Placed 2026-07-16. Everything cross-checked against the zone plan before ordering. Re-verify listings before any reorder — ASINs/prices drift.

| # | Item | Product | Qty | ~Each | Covers |
| --- | --- | --- | ---: | ---: | --- |
| 1 | Disconnect/breaker | Bolipoeq 150 A DC breaker, 12–48 V, IP67, manual reset — 2-pack | 1 | $18.99 | Combined disconnect + main protection on the + feed (spare in the 2-pack) |
| 2 | 4 AWG trunk | TEMCo 50 ft black + 50 ft red, USA pure copper welding cable | 1 | $168.32 | Two trunk legs. Bare copper (not tinned) — accepted |
| 3 | 18 AWG drops | 18/2 bonded 2-conductor, 50 ft, tinned stranded | 1 | $15.50 | Per-tube +24 V / GND drops = 50 ft red + 50 ft black |
| 4 | 4 AWG ring lugs | TKDMR 4 AWG 1/4"/M6 ring lugs + heatshrink, 10-pk | 3 | $7.99 | 30 lugs — battery, breaker, split, + trunk landings on M6 studs |
| 5 | Bus bars | Ampper 150 A marine busbar, 3× M6 studs + 10× #8 screws, w/ cover, red+black 2-pack | 11 | $23.19 | 22 bars = 10 +/− zone pairs + 2 spare. M6 studs = trunk pass-through; #8 screws = tube drops |
| 6 | 18 AWG fork terminals | Teansic 200-pc #8 insulated fork, 22–16 AWG (100 red + 100 black) | 2 | $9.99 | 400 forks for ~200 tube drops. Match the #8 busbar screws — **not ferrules** (bars are screw-down) |
| 7 | Injection caps | Innfeeltech 1000 µF 50 V radial electrolytic, 25-pk | 4 | $6.49 | 100 caps, one per tube. Across +24 V/GND at each tube; polarity matters |
| 8 | Cap heatshrink | NeoWire 3/4" (19.1 mm) 3:1 dual-wall adhesive-lined, 29 ft | 1 | $30.99 | Sleeve + strain-relief over each soldered cap |
| 9 | Cable-tie mounts | 140-pk 3/4" adhesive+screw cable-tie bases (**includes zip ties**) | 1 | $9.99 | Secure trunk every ~250–300 mm around the rail |
| 10 | Ammeter / shunt | CGELE DC monitor meter + shunt, 0–300 A | 1 | $21.59 | On the main before the split — watch real draw, tune firmware cap |

Notes / decisions baked in:
- **Routing: top rail** — power trunk + data lines together; tubes inject at the top end.
- **4 AWG is bare copper, not tinned** — accepted the corrosion trade for cost; keep an eye on the lugged joints for playa oxidation.
- **Caps mount at each tube**, soldered across +24 V / GND, sleeved in the 3:1 adhesive heatshrink. Long lead (+) → +24 V, stripe (−) → GND.
- **Fork terminals, not ferrules** — busbars are screw-down (single-node), so #8 forks land under the screws.
- **Ground:** the black-trunk bars are the distributed common ground; tie them, all Angio grounds, and battery negative together — **shared ground is mandatory** for the data signal.

## Related

- [led-power.md](led-power.md) — which 24 V bank feeds this (EG4 2s2p vs Tesla module vs DC-DC)
- [../lights/controllers.md](../lights/controllers.md) — data wiring, shared-ground requirement, 1000 µF injection caps
- [../broom/DESIGN.md](../broom/DESIGN.md) — tube count, measured power, perimeter
- [power-budget.md](power-budget.md) — overall cart load budget
