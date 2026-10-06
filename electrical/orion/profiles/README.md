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

## Reading one without the utility

The utility stores the custom CAN message table (`customMessage[n]`,
`typeMatrix`) and the CAN baud index (`DefaultBaudrate`, 0/1/2 = 125/250/500
kbit) in the profile. If you need to compare two profiles, a text diff is the
quickest way to see what changed.
