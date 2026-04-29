# Sound system

DJ rig: laptop / DJ controller → mixer → powered sub → tops. All gear is self-amplified pro PA — no external amps.

## Signal chain

```
Pioneer XDJ-XZ ──(2× XLR-F → TRS-M, 3 ft)──▶ Mackie Mix8 (Ch 3 & 4)
                                                  │
                                                  ▼ TRS-M L/R
                                       (2× TRS-M → XLR-M, 10 ft)
                                                  │
                                                  ▼
                                       QSC KS118 Sub (XLR in)
                                                  │
                                                  ▼ XLR-F crossover (bottom) out
                                       (2× XLR-F → TRS-M, 20 ft)
                                                  │
                                                  ▼
                                       2× QSC K12.2 (XLR/TRS in)
```

The sub does the crossover internally — its low-pass output drives the sub, its high-pass XLR output feeds the tops.

## Components

| Device | Inputs | Outputs | Rated power | Mounting | Notes |
| --- | --- | --- | ---: | --- | --- |
| [QSC K12.2](https://www.qsc.com/solutions-products/loudspeakers/portable/powered/portable-pa/k2-series/k122/) (×2) | XLR or TRS male | — | 2 000 W ea | K12.2 Yoke Mount Kit | Tops |
| [QSC KS118 Sub](https://www.sweetwater.com/store/detail/KS118--qsc-ks118-3600w-18-inch-powered-subwoofer) | XLR/TRS male from Mackie | XLR Female crossover (bottom) → K12.2s | 3 600 W | — | 18" powered sub |
| [Mackie Mix8](https://mackie.com/en/products/mixers/mix-series/mix8.html) | XLR/TRS male for XDJ | TRS male L/R to sub | (low) | — | 8-channel mixer |
| [Pioneer XDJ-XZ](https://www.pioneerdj.com/en-us/product/all-in-one-system/xdj-xz/white/overview/) | (none for now) | Master 1 → Mackie Ch 3 & 4 | (low) | — | All-in-one DJ controller |

**Total rated AC power:** ~7 600 W peak (4 000 W tops + 3 600 W sub). Mixer + DJ controller draw is negligible (<100 W combined).

> "Rated power" on QSC speakers is *peak program* — sustained typical-listening draw is more like 1/3 to 1/4 of that. The 7.6 kW number is the worst-case for sizing breakers and inverter output, not what the system actually pulls during normal playback.

## Cables

All cables are on hand (✅).

| Cable | Type | Length | Qty | Run |
| --- | --- | --- | ---: | --- |
| [Pro Co BPBQXF-3](#) | XLR-F → TRS-M | 3 ft | 2 | XDJ-XZ → Mackie |
| [Pro Co BPBQXM-10](#) | TRS-M → XLR-M | 10 ft | 2 | Mackie → Sub |
| [Pro Co BPBQXF-20](#) | XLR-F → TRS-M | 20 ft | 2 | Sub crossover out → K12.2 tops |
| Hosa PWC-415 | IEC C13 power | 15 ft | — | K12.2 power |
| Provided power cables | IEC C13 | — | — | Sub, Mackie, XDJ |

## Mounting

- K12.2 tops: **K12.2 Yoke Mount Kit** (have)
- Sub: not yet specified
- Mixer / XDJ: not yet specified

## References

- [QSC hookup diagrams (PDF)](https://www.qsc.com/resource-files/productresources/spk/kw/q_spk_kw_hookupdrawings.pdf)
- [How to set up the speakers (Reddit thread)](https://www.reddit.com/r/DJs/comments/1yfb7q/comment/cfk0fg4/?utm_source=share&utm_medium=web2x&context=3)

## Related

- [../electrical/power-budget.md](../electrical/power-budget.md) — sound system load against the 14.4 kW pack ceiling
