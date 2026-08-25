# Broom LED tube — power wiring & disconnect

Physical power wiring for the **136 × 2.5 m SM16703 tubes** ([../broom/DESIGN.md](../broom/DESIGN.md)) on the 24 V bus. Data wiring is separate — see [../lights/controllers.md](../lights/controllers.md). Power source (which battery bank) is decided in [led-power.md](led-power.md); this doc assumes a single 24 V feed point at the battery.

## Load & geometry (from DESIGN.md / dimensions.md)

- **Perimeter (open-front U):** 11.6 m ≈ **38 ft**. Sides ~4 m each (L01–L56, R01–R56), back ~1.7 m (B01–B24).
- **Currents @ 24 V, 136 tubes** ([led-power.md](led-power.md)): idle 57 A · typical chase **170 A** · 30%-white all-lit 187 A · full-white solid **417 A** (firmware-capped to bursts).

## Topology — split at the battery, both legs share the riser

> ✏️ **Re-routed 2026-07-28.** Batteries are in the **bottom of the car**; all trunk runs use the **existing wire coverings**: up the **middle-right pole** (riser), **across the ceiling** middle-right → middle-left, along **both ceiling sides**, and across the **back-right portion only** of the back.

Split into two trunk pairs at the breaker (bottom, at the battery), run **both pairs up the riser together**, then part ways at the ceiling. **Leg assignment is by 2×4 board (updated 2026-08):**

- **Leg 1 — joins at board B1** (left side + back-left): powers **A1, A2, B1, B2, C1** — tubes `L01–L56` + `B01–B12`.
- **Leg 2 — joins at board D2** (right side + back-right + front-right F): powers **C2, D1, D2, E1, E2, F1** — tubes `B13–B24` + `R01–R56` + `F01–F12`.

> Each leg stays on its own side of the car — no crossing drops. Leg 2 also feeds the new **F1** front-right board (`F01–F12`).

```
 front-left ◄──── left leg ────► back-left      (left ceiling covering)
                    ▲
                    │  ceiling crossing (mid)
                    ▼
 front-right ◄─── right leg ───► back-right ─► mid-back bar ─► B24…B01
                    ▲                          (back-right covering; B01–B12
                    │  riser: middle-right      on long uncovered drops)
                    │  pole, both pairs
           [BREAKER/DISCONNECT]
                    │
              BATTERY +/-  (bottom of car)
```

Why still split at the battery even though both legs share the riser: each pair carries **~85 A typical instead of 170 A**, so the trunk stays **4 AWG** instead of one stiff 2/0 run, and a fault on one leg doesn't dark the whole car.

**Run lengths (estimates — verify on the car):** riser ~8 ft, ceiling crossing ~6 ft, half-side ~6.5 ft, back-right covering ~3 ft. Longest branch (left leg backward, or right leg to mid-back) ≈ **20 ft one-way**.

## Disconnect + protection

One **DC circuit breaker with manual switch lever, 250 A, DC-rated ≥32 V**, at the battery (bottom of car) on the main **+** feed *before* it splits into the two legs — location confirmed 2026-07-28. Single part = daytime "kill the LEDs" disconnect **and** wire protection. Kill it → both legs dark.

- ⚠️ **The originally-ordered 150 A breaker is undersized for 136 tubes** — typical chase is now 170 A and would trip it. **Reorder at 250 A** (170 A typical = 68% of rating, no nuisance trips; a runaway full-white command at 417 A still trips it — a useful hardware backstop, since brightness is firmware-capped anyway).
- Want sustained full white? That's 417 A — needs a bigger breaker **and** 2/0-class legs; not planned.

## Wire gauge & voltage drop

**Trunk: 4 AWG per leg** (tinned/marine for BRC dust). Drop for the ~20 ft worst branch (riser + crossing carry the full leg current with no taps; the ceiling section tapers as tubes tap off):

| Load | Amps/leg | Drop (4 AWG, worst branch) | % of 24 V |
| --- | ---: | ---: | ---: |
| Typical chase | 85 A | ~0.7 V | 3% |
| 30%-white all-lit | 94 A | ~0.8 V | 3.3% |
| Full-white burst | 208 A | ~1.7 V | 7% |

4 AWG marine ≈ 150 A continuous: 94 A sustained loafs; the 208 A full-white burst is **over** continuous rating and relies on the firmware cap keeping it brief. If sustained full-white ever becomes a requirement, bump legs to **2 AWG**. (6 AWG is no longer a viable lighter alternative at these currents.)

At 24 V, drop is still not the constraint. Even on the 18–25 V Tesla 6p bank ([led-power.md](led-power.md)), the far tube stays ~16 V worst case — well above the SM16703's ~10–12 V constant-current dropout.

**Per-tube drops: 18 AWG.** Each tube pulls max ~3 A (full white) / ~1.3 A typical. With zone bus bars every ~1.3 m (below), each drop is short (≤ ~0.7 m).

## Tube connections — tiered trunk + zone bus bars

Don't tap the 4 AWG trunk 100 times. 4 AWG is a big heat-sink (hard to solder) and T-tap/IDC connectors top out around 10–12 AWG. Instead, two tiers:

- **4 AWG trunk stays continuous** along the ceiling coverings, two legs (split at battery).
- Every ~10–12 tubes, land the trunk on a **bus bar** — cut the trunk and land both ends on the bar's two main studs, so the bar is an inline node passing the leg current through. **~8–10 bus bars** total, mirroring the ~10 WLED zones / 4 sides.
- Each tube's **18 AWG drop lands on a screw terminal** on the nearest bus bar.

Only ~8–10 lugged bus-bar landings are heavy joints — **no soldering to 4 AWG** — and the 200 tube connections become serviceable **screw terminals**, good for dust/vibration.

**Bus-bar sizing:** near-battery bars pass the full leg current (~69 A sustained worst-dimmed, ~153 A full-white burst) → use **≥150 A rated** bars for those; downstream bars can be lighter. **Fused distribution blocks** per zone are a nice optional upgrade so one zone short doesn't drop the whole leg.

## Routing — existing coverings (power + data together)

Both the 4 AWG power trunk and the tube data lines share the coverings (riser, ceiling crossing, ceiling sides, back-right):

- Run **only the data wire** to each tube — V/G come from the bus bars — as a **20 AWG extension** butt-spliced (marine) to the tube's female pigtail, back to the nearest **SRx4**. The tube's ground reference is the − bus, so **bond every SRx4 / K128D-B ground to the − bus** (shared-ground requirement, [../lights/controllers.md](../lights/controllers.md)).
- **Power the receivers locally, never at 24 V.** Each SRx4 takes **5–13 V** on its power lugs (use a 12 V buck off the 24 V bus, one per 2×4 board) — the cat5 from the K128D carries data only. On the 3-pin receiver outputs use **D + G**; leave **V unconnected** (landing V on a 24 V tube back-feeds the board). See [../lights/controllers.md](../lights/controllers.md).
- Give the data lines a few cm of separation from the high-current trunk over long parallel runs to keep switching noise off the signal. It's DC so coupling is mild; the DIN series resistor + short data pigtail at each tube matter more.

## Feet needed

- **4 AWG trunk:** right leg ≈ 24 ft/conductor (riser 8 + fwd 6.5 + back 6.5 + back-right 3), left leg ≈ 26.5 ft/conductor (riser 8 + crossing 6 + fwd 6.5 + back 6.5) → **~50 ft per color before slack or battery jumpers**. The 50 ft red + 50 ft black on hand has **zero slack** — reorder **+25 ft each color** (see [Reorder](#reorder-for-136-tubes)).
- **18 AWG drops:** at 116 mm tube pitch ([../broom/DESIGN.md](../broom/DESIGN.md)) the ~6 in factory leads reach the 2–3 tubes nearest each bar directly; the rest need short drops of a few inches to ~0.4 m. Summed across ~10 zones ≈ 30 m total → buy **50 ft red + 50 ft black**. (Densifying to a terminal block every ~3 tubes would let factory leads land direct and drop this to near zero.)

## Zone plan — 14 zones × ~10 tubes (136 tubes, open front)

> ⚠️ **Updated 2026-07-24: tube count went 100 → 136 (open-front U-run).** This changes the injection-zone count and means some consumables ordered for 100 tubes are now short — see **[Reorder for 136 tubes](#reorder-for-136-tubes)** below.

Split feed, two legs. **14 injection zones of ~10 tubes each** (136 / 10 ≈ 14). Per zone, one **+24 V bar** (tapped off the red 4 AWG trunk) and one **ground bar** (tapped off the black trunk) — single-node bars can't mix polarity, so they come in +/− pairs. 14 zones × 2 = **28 bars**. At ~10 tubes/zone (~0.72 m span at the 72 mm pitch) the ~6 in factory leads reach the nearest tubes; the rest take short drops. Bars nearest the riser pass full leg current, so all bars are 150 A rated.

**Mid-back zone is the exception:** the trunk ends at the mid-back +/− bar pair (end of the back-right covering), which feeds all 24 back tubes — B13–B24 normally, B01–B12 on longer uncovered 18 AWG drops up to ~0.9 m.

### Reorder for 136 tubes

The 2026-07-16 order was sized for 100 tubes / 10 zones. Going to 136 tubes / 14 zones, these come up short:

| Item | Have | Need (136) | Reorder |
| --- | ---: | ---: | --- |
| Main breaker | 150 A (2-pack) | **250 A** (170 A typical would trip 150 A) | **1× 250 A DC breaker**, manual lever, ≥32 V DC |
| 4 AWG trunk | 50 ft/color | ~50 ft/color + slack/jumpers (new riser route) | **+25 ft red + 25 ft black** |
| Busbars | 22 (11 two-packs) | 28 | **+3 Ampper 2-packs** (→ 28 + 2 spare) |
| Injection caps | 100 (4× 25-pk) | 136 | **+2 Innfeeltech 25-pks** (→ 150, ~14 spare) |
| 18 AWG drops | 50 ft/color | ~68 ft/color | **+1 more 50 ft 18/2** roll |
| 4 AWG ring lugs | 30 | ~60 (2 per bar × 28 = 56 + battery/breaker/split) | **+3–4 TKDMR 10-pks** — recount against final bar count |
| Fork terminals | 400 | 272 | ✅ enough |

Everything else (heatshrink, cable-tie mounts, ammeter) is unaffected.

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
- ~~**Routing: top rail**~~ — superseded 2026-07-28 by the covering route (riser up middle-right pole → ceiling); power trunk + data lines still run together, tubes still inject at the top end.
- **4 AWG is bare copper, not tinned** — accepted the corrosion trade for cost; keep an eye on the lugged joints for playa oxidation.
- **Caps mount at each tube**, soldered across +24 V / GND, sleeved in the 3:1 adhesive heatshrink. Long lead (+) → +24 V, stripe (−) → GND.
- **Fork terminals, not ferrules** — busbars are screw-down (single-node), so #8 forks land under the screws.
- **Ground:** the black-trunk bars are the distributed common ground; tie them, all **SRx4 / K128D-B** grounds, and battery negative together — **shared ground is mandatory** for the data signal (only data runs to each tube; its return reference is the − bus).

## Related

- [led-power.md](led-power.md) — which 24 V bank feeds this (EG4 2s2p vs Tesla module vs DC-DC)
- [../lights/controllers.md](../lights/controllers.md) — data wiring, shared-ground requirement, 1000 µF injection caps
- [../broom/DESIGN.md](../broom/DESIGN.md) — tube count, measured power, perimeter
- [power-budget.md](power-budget.md) — overall cart load budget
