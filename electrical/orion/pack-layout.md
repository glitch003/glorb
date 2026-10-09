# Drive pack layout: which BMS, which switch position, which modules

The 72 V drive battery is six Tesla 6S modules in two stacks of three. Each
stack is one **pack**: three modules in series (18 cell groups, "bricks"),
with its own Orion BMS 2 and its own contactor. The two packs meet at the
**1 / 2 / 1+2 / OFF** selector switch.

| | Pack 1 | Pack 2 |
| --- | --- | --- |
| Physical stack | **Top** three modules | **Bottom** three modules |
| Selector switch position | **1** | **2** |
| Orion BMS 2 | **BMS 1 = master** (OBD2 ECU 0x7E3) | **BMS 2 = slave** (OBD2 ECU 0x7E4, serial L59FA424) |
| Original profile | [profiles/master-master-2026-10-06.o2bms](profiles/master-master-2026-10-06.o2bms) | [profiles/slave-slave-2026-10-06.o2bms](profiles/slave-slave-2026-10-06.o2bms) |
| Charger control | master commands the Elcons over CAN | — |
| Status 2026-10-06 | open taps **3, 5, 7** | open tap **11** |

Confirmed by Chris on 2026-10-08 (top = BMS 1 = master). Label both Orions
and both stacks with this so nobody has to work it out again.

## How the Orion numbers the cells and taps

Each pack is 18 bricks in series. The Orion counts them from the most
negative end: cell 1 is the first brick above pack negative, cell 18 is the
last brick below pack positive. A **tap** is the sense wire on a junction;
tap *n* is the positive side of cell *n* (and the negative side of cell
*n*+1). Tap 0 is pack negative.

```
            pack +  ─── tap 18
  module 3   cells 13-18   taps 12..18
            ──────── tap 12 (module 3 - / module 2 +)
  module 2   cells 7-12    taps 6..12
            ──────── tap 6  (module 2 - / module 1 +)
  module 1   cells 1-6     taps 0..6
            pack -  ─── tap 0
```

"Module 1/2/3" here means the Orion's order up the series string, not the
physical position in the stack and not the `B1`–`B6` label. Fill in the
mapping once it has been read off the car:

| Pack | Orion module (cells) | Physical position in stack | Label (B1–B6) |
| --- | --- | --- | --- |
| 1 (top) | 1 (cells 1–6) | _?_ | _?_ |
| 1 (top) | 2 (cells 7–12) | _?_ | _?_ |
| 1 (top) | 3 (cells 13–18) | _?_ | _?_ |
| 2 (bottom) | 1 (cells 1–6) | _?_ | _?_ |
| 2 (bottom) | 2 (cells 7–12) | _?_ | _?_ |
| 2 (bottom) | 3 (cells 13–18) | _?_ | _?_ |

The Orion tap harness plugs into each module's own tap connector (the
Tesla BMB connector); pinouts are in
[../tesla-batteries/BMS diagrams/](../tesla-batteries/BMS%20diagrams/).

## Where the open taps are (2026-10-06)

| Pack | Tap | Junction | Which module | Symptom in the Orion |
| --- | --- | --- | --- | --- |
| 1 (top) | 3 | between cells 3 and 4 | module 1, between its 3rd and 4th brick | cell 3 reads 3.28 V, cell 4 reads 4.02 V |
| 1 (top) | 5 | between cells 5 and 6 | module 1, between its 5th and 6th brick | cell 5 reads 2.46 V, cell 6 reads 4.90 V |
| 1 (top) | 7 | between cells 7 and 8 | module 2, between its 1st and 2nd brick | cell 7 reads 5.16 V, cell 8 reads 2.24 V |
| 2 (bottom) | 11 | between cells 11 and 12 | module 2, between its 5th and 6th brick | cell 11 reads 3.91 V, cell 12 reads 3.41 V |

In module terms these are junctions 3|4, 5|6, 1|2 and 5|6: all the odd
junctions, which on a Tesla 6S module are the ones on one face. On
2026-10-08 the first module pulled (middle of the top stack) had a badly
corroded underside, so the working theory is corroded sense leads on that
face (see the fault log's "Teardown").

Each pair sums to a normal 7.3–7.4 V, which is how we know these are
measurement wires and not bricks
([../fault-log-2026-10-06.md](../fault-log-2026-10-06.md)). All four are
odd-numbered and all are in the first 12-cell tap group of their unit.

## Baseline: the modules were healthy in August

[../tesla-batteries/battery_log.csv](../tesla-batteries/battery_log.csv)
has every drive module logged on the bench on 2026-08-03, before install
(B1–B6; B7–B12 are the 24 V LED bank):

| Module | Module V | Cells (V) | Spread |
| --- | --- | --- | --- |
| B1 | 21.52 | 3.592–3.610 | 18 mV |
| B2 | 21.55 | 3.609–3.615 | 6 mV |
| B3 | 21.54 | 3.608–3.612 | 4 mV |
| B4 | 21.54 | 3.608–3.613 | 5 mV |
| B5 | 21.55 | 3.609–3.614 | 4 mV |
| B6 | 21.71 | 3.637–3.641 | 3 mV |

So any brick that meters far from its neighbours today would be new damage,
not a pre-existing weak module. The Orion's own readings of the undisputed
cells on 2026-10-06 (3.65–3.70 V, module 3 on both packs within 4 mV) match
that picture.

## Multimeter readings (fill in)

Selector OFF, Orions powered down, tap connectors unplugged (Ewert: never
touch tap wiring with the BMS connected). Adjacent pins on a module's tap
connector span one brick.

| Pack | Cell | At the module (V) | At the Orion connector (V) | Tap continuity | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 (top) | 3 | | | tap 3: | |
| 1 (top) | 4 | | | | |
| 1 (top) | 5 | | | tap 5: | |
| 1 (top) | 6 | | | | |
| 1 (top) | 7 | | | tap 7: | |
| 1 (top) | 8 | | | | |
| 2 (bottom) | 11 | | | tap 11: | |
| 2 (bottom) | 12 | | | | |

Then the other 28 bricks, which should all read 3.65–3.71 V. Full procedure
in the fault log's "Multimeter plan".
