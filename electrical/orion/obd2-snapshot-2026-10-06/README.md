# OBD2 snapshot of both Orions, 2026-10-06 ~22:35 MDT

Taken with `python -m glorbmon.obd2` (see
[../../glorbmon/README.md](../../glorbmon/README.md)) right after Chris
re-uploaded the original profiles to both units, with the car parked in the
garage, selector off, nothing charging. Both units were in Voltage Failsafe
(DCL and CCL 0, relays open) with codes present; nothing was cleared.

| File | What |
| --- | --- |
| `obd2-master.csv` | master (ECU 0x7E3, switch position 1): stored/pending/permanent DTCs, every mode-22 parameter F000–F0FF that answered, decoded |
| `obd2-slave.csv` | the same for the slave (ECU 0x7E4, serial L59FA424, switch position 2) |
| `cells-master.csv` | master: 18 cell voltages, open-cell voltages, resistances, balancing flags (PIDs F100/F101, F300/F301, F200/F201) |
| `cells-slave.csv` | the same for the slave |
| `bus-capture.csv` | 10 s of raw bus traffic afterwards (`0x6B1` from both units and the parallel-string `0x1850F3F3`, i.e. the units are linked again) |

Headline: see [../../fault-log-2026-10-06.md](../../fault-log-2026-10-06.md).
Both packs show open-tap pairs (adjacent cells reading high/low and summing
to normal): taps 3, 5 and 7 on the master's pack, tap 11 on the slave's.
