# Broom LED power source

How to power the 24 V LED bus for the broom bristles (**136 × 2.5 m tubes**, [../broom/DESIGN.md](../broom/DESIGN.md)) and, tied to it, whether to swap the 12 V inverter for 24 V.

> ✅ **SETTLED 2026-07-24: dedicated LED bank = 6× Tesla Model S modules in parallel (6p).** Each module is internally 6s → the pack is **6s6p, ~24 V nominal (18–25 V range), ~31.8 kWh**. This is **option D** below, scaled from one module to six for runtime. No DC-DC, no 2s2p EG4 string. Details under [Battery topology → D](#battery-topology--four-options) and [Recommendation](#recommendation).

## What we actually have (correcting the "3× 12 V batteries" assumption)

The cart does **not** run on a bank of 12 V batteries. Per [batteries.md](batteries.md):

- **Main pack:** Tesla modules, **3s2p = 72 V nominal, ~30 kWh.** This is the primary energy store (drivetrain + everything, via converters).
- **Aux pack:** **3× EG4 LifePower4 12 V 400 Ah (~4.8 kWh each → ~14.4 kWh)** from the original 2022 build (confirmed 2026-07-02), repurposed as a 12 V supply. Currently feeds the 12 V loads (RPi, dashboard, lighting controllers) **and** the 12 V input of the 4 kW Giandel inverter. A **72 V → 12 V converter** also feeds this 12 V bus from the main pack.

> **A 2s2p 24 V bank needs 4 batteries** — you have 3, so **source one more matched EG4** (same model/age/capacity). Three batteries can't make a balanced 2s2p; don't mix a 24 V string with an odd battery.

## LED load (136 × 2.5 m, from DESIGN.md)

| State | Per tube | 136 tubes | Amps @ 24 V |
| --- | ---: | ---: | ---: |
| Idle floor | 10 W | 1.36 kW | 57 A |
| Typical chase | ~30 W | ~4.08 kW | 170 A |
| 30% white, all lit | 33 W | 4.49 kW | 187 A |
| 100% white solid | 73.5 W | ~10.0 kW | 417 A |

Plan around **~4.1 kW / ~170 A typical**, with a firmware cap keeping full-white-solid to short bursts.

## The 24 V inverter swap — recommended regardless

Swapping the 12 V Giandel for a **24 V inverter is a clear win** and independent of the LED battery decision:

- The current 12 V inverter pulls **~370 A at 4 kW** ([inverter.md](inverter.md), flagged as "heavy bus current, watch the wiring"). At 24 V the same 4 kW is **~185 A** — half the current, ¼ the I²R loss, thinner/cooler cabling.
- It lets the inverter share the **same 24 V bank** as the LEDs, so there's one house-power voltage instead of two.

Do this. The only cost is buying a comparable 24 V pure-sine inverter and re-terminating the DC feed.

## Battery topology — four options

**A. Your plan: 2s2p aux bank (4× 12 V EG4 → 24 V), LEDs + 24 V inverter off it.**
- Simple, cheap, no DC-DC to buy. Batteries deliver the peaky sound + LED current natively.
- ~19 kWh (4× 4.8 kWh). But if it powers **both** LEDs (~3 kW) and the sound inverter (~2.9 kW typical), combined ~6 kW → **only ~3 h runtime** before recharge. Likely too short for a full night on its own.
- ⚠️ **Gating item: confirm the EG4 LifePower4 12 V units are rated for 2S (24 V) series use.** Many 12 V LiFePO4 with internal BMS are; some are not. Check the manual before wiring anything in series.
- Match batteries within each series pair (same age/SoC/capacity); consider an active balancer across the series junction.
- The existing **12 V loads (RPi, dashboard, controllers) lose their supply** — add a small 24 V → 12 V buck, or keep one battery as a 12 V tap.
- Charging changes: the 72 V → 12 V converter no longer matches a 24 V bank.

**B. DESIGN.md's plan: 72 V → 24 V DC-DC off the Tesla main pack.**
- One master pack (~30 kWh) backs everything — best runtime, one thing to charge.
- ⚠️ A DC-DC sized to carry the **inverter + LED peak (7–11 kW)** is a big, expensive part (~$1–2k+). DC-DCs handle peaks worse than batteries. Overkill if it must cover inverter surge.

**C. Hybrid (recommended): 2s2p aux bank buffers peaks, small 72 V → 24 V DC-DC trickle-charges it from the main pack.**
- LEDs **and** the 24 V inverter run straight off the 24 V aux bank → batteries handle peaky loads well (no giant converter needed).
- A **modest ~2–3 kW** 72 V → 24 V DC-DC feeds the bank at its *average* draw, so runtime is backed by the 30 kWh Tesla pack, not just the ~19 kWh aux bank. Bank = buffer, main pack = tank.
- Cheaper converter than B, far longer runtime than A. Best of both.
- Same caveats as A: confirm 2S rating, rehome the 12 V loads, match/balance the series pairs.

**D. Tesla Model S modules as a dedicated 24 V LED bank (6s, 18–25 V). ✅ CHOSEN — 6 modules in parallel (6p).**
- A single Model S module is **6s74p** (444 × 18650 cells) → **~25 V full, ~22 V nominal, ~18 V empty**. That range sits inside the tubes' SM16703P **5–24 V** spec, and — critically — **the tubes stay at full brightness across the whole discharge** (see below). No sag, no fade as the module drains.
- **Chosen build: 6 modules in parallel → 6s6p, ~24 V nominal, ~31.8 kWh (~1 390 Ah).** Big native cell bank → handles peaky LED current (and a 24 V inverter, if shared) with no DC-DC.
- **Runtime:** LEDs alone at ~4.08 kW typical → **~7.8 h**. Sharing the bank with a ~2.9 kW 24 V inverter (~7 kW combined) → **~4.5 h**. Comfortably covers a night; recharge between.
- ⚠️ **Top-end edge:** 25 V full charge is over the 24 V *recommended* input, but under the SM16703P's **26 V OUT withstand**; the chip's RD-fed VDD clamp protects the logic rail. Fine, but bench-check one tube at 25 V before committing.
- ⚠️ Needs its **own BMS/charger** (Tesla-module cell-tap board like the main pack's EV Stealth setup) and doesn't share the EG4 charging path.
- ✅ **Separate pack — confirmed.** These 6 are dedicated to the LEDs, independent of the 3s2p/72 V main drivetrain pack.
- **Sourcing (via Henri): 18 modules total.** 6 read **~22 V (healthy)** → these form the 6p LED bank. The other **12 read ~19 V and are untested** — set aside for future testing before any use (see TODO); ~19 V may mean deep-discharged or degraded, so don't assume they're bank-ready.
- Rehome the 12 V loads on a 24 V → 12 V buck, same as A/C.

### Why low voltage doesn't dim them (the SM16703P is constant-current)

The tube driver ([../lights/controllers.md](../lights/controllers.md), [../lights/led-tubes.md](../lights/led-tubes.md)) is a **constant-current** IC — **17 mA/channel**, held flat regardless of supply (SM16703P datasheet). Brightness is set by that regulated current, **not** supply voltage, so 18 V and 24 V look identical. The tubes hold full brightness until the supply falls below **dropout**, then dim abruptly.

Dropout is set by the green/blue string (highest Vf, ~3.0–3.2 V each) plus the constant-current knee (VDS ≈ 0.9 V). For a 24 V strip = **6 LEDs/IC = 2 per color channel in series**:

```
Vmin ≈ 2 × 3.2 V (green string) + ~2.5 V (series resistor) + 0.9 V (knee) ≈ ~10 V
```

So full regulated brightness down to **~10–12 V** — the 18 V module floor has **~6–8 V of headroom**.

Consequences worth noting:
- **Same amps, fewer watts at low V.** Supply current ≈ channel current (series path), so the ~125 A typical figure holds at 18 V, but power drops (18 V × same A ≈ 2.25 kW vs 3 kW at 24 V). Wire sizing unchanged; less energy burned in the strips' series resistors.
- ⚠️ **Verify the internal series count.** ~10 V dropout assumes **2 LEDs/channel**. If a batch instead wires a long single series string (e.g. 6 green ≈ 19 V), dropout jumps to ~20 V and 18 V would fail. Bench test: one tube on a supply, full white, sweep 24 V → 18 V — **current holds flat = good**; current sags = note the real floor. Also confirm along-the-tube copper drop still leaves margin at 18 V.

## Recommendation — SETTLED (option D)

**Dedicated LED bank: 6× Tesla Model S modules in parallel (6s6p, ~24 V, ~31.8 kWh).** Options A/B/C (EG4 2s2p, DC-DC, hybrid) are superseded and kept below for reference only.

1. **Swap to a 24 V inverter** — still a strict improvement, and it can share this same 24 V bank. (Combined LED + inverter runtime ~4.5 h; LED-only ~7.8 h.)
2. **Build the 6p Tesla bank** with its own BMS/charger (cell-tap boards like the main pack's EV Stealth setup). Confirm the 6 modules are additional to the 72 V main pack.
3. **Bench-test one tube 24 V → 18 V** (current holds flat = good) and **at 25 V full-charge** before committing — confirms the constant-current dropout margin and top-end withstand.
4. Rehome the 12 V loads on a small 24 V → 12 V buck.
5. **Test the 12 spare modules reading ~19 V** (of Henri's 18) — check per-cell voltages, capacity, and whether they recover on a balance charge. If healthy, they're a big reserve (could extend the bank or become a second pack); if degraded, plan around the 6 good ones only.

## Related

- [led-wiring.md](led-wiring.md) — physical power wiring, disconnect, wire gauge & order list for the tube bus
- [batteries.md](batteries.md) · [inverter.md](inverter.md) · [power-budget.md](power-budget.md)
- [../broom/DESIGN.md](../broom/DESIGN.md) — LED count / power tables
- [../lights/led-tubes.md](../lights/led-tubes.md) · [../lights/controllers.md](../lights/controllers.md) — SM16703P driver (constant-current, 5–24 V)
