# Tesla Batteries

_Status as of 2026-08-05: batteries still on the pile, ~10% charge, not yet installed._

Pack layout: [Pack diagrams/pack_diagram.png](Pack%20diagrams/pack_diagram.png)

## Modules in use

- 6× Tesla 6S modules labeled **B7–B12** (top of the battery pile).
- Nominal ~24V per module, ~230Ah pack after paralleling.

## Remaining work to install

### Cables & busbars

- Cables **1a, 1b, 2, 3a, 3b** are already made — in the cardboard box labeled **"tesla battery hookups"** (located **underneath the Tesla batteries on the shelf / in the pile**).
- Remaining cables still need to be made. Materials are in the same box:
  - AWG 2/0 wire
  - 3/8" lugs
- The **master big switch** is also in that box.
- **Pack parallel busbars** and **distribution busbars** (both 300A) arrived in the mail 2026-08-05 — still need to be brought to glorb.
- **EVA foam** arrived in the mail 2026-08-05 — still need to be brought to glorb.

### Physical install

- Stack the 6 modules as **2 groups of 3 high**, with **EVA foam mats between each module**.
- Put something underneath the stacks on the car floor — plywood or EVA foam.
- Secure the stacks in the car so they don't bounce around while driving.

### BMS bring-up (before paralleling)

The [TeslaBMS](TeslaBMS/) Arduino Due firmware is already flashed. The Arduino is sitting on the battery pile, wired to B7–B12.

1. Plug USB into the **right USB port on the Due** (with the USB ports facing you).
2. Open the Arduino IDE serial monitor at **115200 baud**.
3. You should see a startup message.
4. Type `d` and hit enter — voltages for all 6 modules print every 3 seconds.
5. Goal: get all modules **within 0.1V of each other** before paralleling.

**Note on module numbering:** the TeslaBMS firmware has no knowledge of the battery labels. Module **#1** is just the first one in the chain on the harness, module **#6** is the last. The physical batteries are labeled **B7–B12**, but the BMS does not know about that — you'll need to map them in your head (B7 = module #1 for example, so try to install and hook them up in order, B7 first, then B8, etc.).

BMS wiring reference: [BMS diagrams/](BMS%20diagrams/)

### Charging

- Meanwell charger is programmed to **24V** (~85% SoC) at **40A**.
- Charge individual modules to match voltages, then parallel and top up together.
- ~230Ah pack, 40A charge → **~5.75 hours per module from empty**.
- Modules are at ~10% right now, so plan on a long charge session.
- **Goal: batteries installed, paralleled, and fully charged before the burn.**

## Reference

- Inventory: [battery_inventory.py](battery_inventory.py), [battery_log.csv](battery_log.csv)
- Pack diagram source: [Pack diagrams/pack_diagram.py](Pack%20diagrams/pack_diagram.py)
- BMS schematic notes: [BMS diagrams/tesla-bms-schematic.md](BMS%20diagrams/tesla-bms-schematic.md)
