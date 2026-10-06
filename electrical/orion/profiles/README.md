# Orion BMS 2 profiles

Saved `.o2bms` profiles for the two drive-pack Orions, downloaded with the
Orion BMS 2 Utility (connect to the unit → download profile → save).

**Put the files in this folder.** Never overwrite an older profile: every
download is a new file with a date, so the history of what each unit was
running is in git.

## Naming

```
<unit>-<role>-<YYYY-MM-DD>.o2bms
```

- `<unit>` is which Orion it came from: `master` / `slave` as originally
  configured, or `pack1` / `pack2` once the units are mapped to the selector
  switch positions and labelled on the car.
- `<role>` is the multi-unit role the profile sets: `master`, `slave`, or
  `single` (standalone).
- The date is the download date.
- An optional `-<note>` suffix for profiles that are deliberately abnormal,
  e.g. `slave-single-2026-10-06-cells11-12-unpopulated.o2bms`. Never upload
  one of these thinking it is an original.

Examples: `master-master-2026-10-06.o2bms` (the original linked master),
`slave-single-2026-10-06.o2bms` (the good pack's unit after the single-pack
change).

## What to keep

| Profile | Why |
| --- | --- |
| Original master and slave, as linked | Restoring the two-pack configuration when the bad pack is rebuilt |
| Each unit's profile after any change | A record of what was uploaded and when |

The profile that glorbmon's README refers to as `master-1.o2bms` is the
original linked master. Its `customMessage[1]` entry is how the `0x6B1` byte
layout was pinned down, so keep it even after the units are re-profiled.

## Saved profiles

| File | Unit | Role | Downloaded | Notes |
| --- | --- | --- | --- | --- |
| `master-master-2026-10-06.o2bms` | master (provisionally switch position 1) | master | 2026-10-05 22:55 MDT | Original linked master. Carries the Elcon charger frames (`customMessages[11..14]`) and `customFlags`. OBD-II ECU ID 0x7E3. |
| `slave-slave-2026-10-06.o2bms` | slave, serial L59FA424 (provisionally position 2) | slave | 2026-10-05 22:54 MDT | Original linked slave. OBD-II ECU ID 0x7E4. Byte-identical to the utility's autosave from that session. |
| `slave-single-2026-10-06-cells11-12-unpopulated.o2bms` | slave | single | _not yet saved_ | **What the ex-slave is running now**: Single Unit, cells 11 and 12 unpopulated to mask the tap-11 P0A04. Save it before changing anything. |
| `master-<role>-2026-10-06-badcells-unpopulated.o2bms` | master | master or single, unknown | _not yet saved_ | **What the master is running now**: out-of-line cells unpopulated to drive off the trailer. Save it before changing anything; it is the only record of which cells were unchecked. |

The files are dated 2026-10-06 to match the fault log and the incident; the
downloads themselves happened late on 2026-10-05 local time.

## Reading one without the utility

The utility stores the custom CAN message table (`customMessage[n]`,
`typeMatrix`) and the CAN baud index (`DefaultBaudrate`, 0/1/2 = 125/250/500
kbit) in the profile. If you need to compare two profiles, a text diff is the
quickest way to see what changed.

Fields identified so far by diffing the two originals (see
[../../fault-log-2026-10-06.md](../../fault-log-2026-10-06.md) for the full
table):

- `parallelStringSettings` — 4 on the master, 8 on the slave; looks like the
  multi-unit role. `parallelStrings` is 1 on both.
- `obd2EcuId` — 2019 (0x7E3) master, 2020 (0x7E4) slave.
- `populationTable` (18 × `populated` = true) and `totalCells` (18) — the
  cell population; identical on both units.
- `totalAmphours` 23000 = 230 Ah; `relaysPopulated` 102.
- The master alone has `customFlags` and `customMessages[11..14]`
  (0x1806E7F4 / E5F4 / E9F4 Elcon command frames, 0x18FF50E5 Elcon status).
- `profileStr` is a hex blob that mirrors the settings above; ignore it when
  diffing (`diff a b | grep -v '<string>0'`).

The profiles do not contain the unit's serial number or the firmware
password.
