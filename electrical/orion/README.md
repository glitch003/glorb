# Orion BMS 2 — the two drive-pack BMS units

The 72 V drive battery is **two Tesla-module packs**, each with its own
**Orion BMS 2** and its own contactor, joined on the DC side through a
**1 / 2 / 1+2 / OFF** pack selector switch. This folder holds the saved Orion
profiles and the notes on how the two units are linked, what happens when one
of them faults, and how to run on a single pack.

> **Status 2026-10-06 (late):** both units are back on their original
> profiles and linked, and both are faulted with open cell taps: taps 3, 5
> and 7 on the master's pack (switch position 1), tap 11 on the slave's
> (position 2). The "bad pack" looks like a wiring problem, not bad modules.
> **Do not charge** until the taps are fixed and both units read 18 clean
> cells. Data and the multimeter plan:
> [../fault-log-2026-10-06.md](../fault-log-2026-10-06.md).

Related: [pack-layout.md](pack-layout.md) (which BMS / switch position /
stack / module / tap is which),
[../batteries.md](../batteries.md) (pack overview),
[../glorbmon/README.md](../glorbmon/README.md) (what the Orions broadcast on
CAN and how the dashboard decodes it),
[../fault-log-2026-10-06.md](../fault-log-2026-10-06.md) (the trailer
incident that prompted these notes).

## How the two units are linked

Both Orions sit on the same **250 kbit CAN bus** (shared with the Elcon
chargers and the CANdapter). They run Ewert's **parallel-string** mode: one
unit is configured as the **master** and the other as the **slave**, and they
exchange a multiplexed extended-ID frame, `0x1850F3F3`, carrying bus voltage,
SOC/DOD, relay state, current and limits. That frame is what
[glorbmon](../glorbmon/) decodes for the 72 V tab. The original profiles are
saved under [profiles/](profiles/) — the master's is the one glorbmon's README
calls `master-1.o2bms`.

The link is a **profile setting, not wiring**. It lives on the **Addon
Settings** tab of the Orion BMS 2 Utility, in the multi-unit role selector
(Master / Master-Slave / Slave / Single Unit). Ewert ships parallel-string
support as custom firmware and does not publish a manual page for it, so the
exact wording on our units may differ slightly from the series-mode page
linked below.

## What happens when one pack faults

Ewert's U0100 fault document defines **subcode 50**: "CANBUS communications
with the Master BMS has been lost (CANBUS parallel string communication)".
A unit that raises it enters **Voltage Failsafe Mode**, which ramps its charge
and discharge current limits to zero and then drops its relays. Consequences:

- If the **master's pack** faults for a cell reason, the master stops acting
  as a healthy partner, the **slave raises U0100** and drops its contactor
  too. **Both packs go dead, including the good one.**
- Powering down, unplugging, or disconnecting the faulted unit does **not**
  free the other one. The survivor still sees a missing partner and faults.
- The only way to run the healthy pack alone is to **reconfigure its Orion
  as a standalone unit** (below).

## Single-pack limp mode

Use this when one pack is out of service and the car has to move on the other.

1. **Isolate the bad pack at the selector switch.** Put the switch on the
   good pack only (1 or 2), **not 1+2**. On 1+2 you are relying on the bad
   pack's contactor staying open to keep two packs at different voltages
   apart. If that contactor ever closes (cleared fault, welded contact, or
   someone pressing buttons), the result is an inrush between a healthy pack
   and one with cells far out of balance. Selecting the good pack alone gives
   the same drive capability with the bad pack physically out of the circuit.
2. **Connect the utility to the good pack's Orion.** Close glorbmon first
   (it holds the CANdapter's COM port), plug in the CANdapter, open the Orion
   BMS 2 Utility and connect. Read the **Diagnostic Trouble Codes** tab and
   confirm the fault on this unit is U0100 (lost partner), not a cell,
   thermistor or current-sensor fault on this pack. If it is a real fault on
   this pack, stop: this pack is not the good one.
3. **Back up the profile.** Download the profile from the unit and save it
   under [profiles/](profiles/) with the date, before changing anything.
   Profiles may be password-locked; the password is noted in
   [../batteries.md](../batteries.md).
4. **Set the unit to Single Unit.** Addon Settings tab → multi-unit role →
   *Single Unit* (standalone). Upload the profile to the BMS.
5. **Power-cycle the unit** on its 12 V side so the new role takes effect,
   reconnect, and **clear its fault codes**.
6. **Verify before moving.** On the Live Text Data tab check *Relay Status*
   shows the discharge relay on, and *Current Limit Status* is not reporting
   a limit reason. Check the pack's cell spread while you are there.
   Re-read the DTC tab too: the first attempt stalled on a **P0A04 open
   tap** on the good pack that had been masked by the U0100 (see
   [../fault-log-2026-10-06.md](../fault-log-2026-10-06.md)). P0A04 is a
   Voltage Failsafe fault in its own right, so the relay stays off until the
   tap is fixed and the code stays clear.
7. **Save the modified profile** too, with a name that says what it is (see
   the naming convention in [profiles/README.md](profiles/README.md)), so
   there is a record of exactly what the unit is running.
   (On 2026-10-05 this step was skipped and the single-unit profile is not
   on record; do it before closing the utility.)
8. Drive. Keep it short and gentle: one pack has half the capacity and the
   DCL of a single string, and the dashboard will be partly blind (below).

### Emergency only: masking an open tap by unpopulating cells

Learned on 2026-10-06. If the unit refuses to close its relay because of a
**P0A04 open-wire fault** and you cannot get at the harness, there is one
software route: in the cell population table (Cell Settings tab) **uncheck
the cell on each side of the open tap**, upload, clear codes. Ewert's P0A04
document says an unpopulated cell listed under "open wire" does not set a
code, and on our unit that was enough for the discharge relay to close.
Clearing codes alone does nothing: the fault re-sets immediately. No profile
setting disables the open-wire test, relay polarity cannot be inverted on the
contactor-capable outputs, and the Voltage Failsafe overrides every relay and
discharge setting.

This is a bypass of the BMS for those bricks, not a fix:

- The unit stops watching the unchecked bricks entirely: no over/under
  voltage cutoff, no balancing, no weak-cell detection.
- **Never charge a pack with cells unpopulated.** The master commands the
  Elcon chargers, so keep them off.
- Pack voltage, SOC and Ah readouts become wrong (fewer cells summed).
- Save the modified profile so the record shows which cells were unchecked,
  and re-populate them as soon as the tap is fixed.

Unpopulating cells that are genuinely bad (as was done on the master to get
off the trailer) is the same mechanism with higher stakes: the invisible
bricks are the ones most likely to go out of range. Creep speed, shortest
possible distance, no charging.

### Dashboard side effect

Once the good unit is standalone it stops sending the parallel-string
message, and glorbmon currently takes pack voltage, current and SOC **only**
from that message (`0x1850F3F3`). The 72 V tab keeps the `0x6B1` limits and
temperatures but loses voltage/SOC. The proper fix is the one the glorbmon
README already recommends: enable the `0x6B0` broadcast in the profile so
each unit reports its own voltage, current and SOC. Until then, read the pack
from the utility's Live Text Data.

## Reading the units over OBD2 (no utility needed)

Each Orion answers OBD2-over-CAN requests on its ECU ID (profile
`obd2EcuId`: **0x7E3 master, 0x7E4 slave**; replies on ID + 8). That gives
trouble codes and every live parameter, including all cell voltages, through
the CANdapter without the utility and without changing anything on the units:

```bash
cd electrical
python -m glorbmon.obd2 --out orion/obd2-snapshot-<date>
```

(Close the Orion utility and glorbmon first; they hold the COM port.) It
writes `obd2-<unit>.csv` (DTCs via modes 03/07/0A, every mode-22 parameter
`F000–F0FF`, decoded), `cells-<unit>.csv` (18 cell voltages, open-cell
voltages and resistances via PIDs `F100/F101`, `F300/F301`, `F200/F201`) and
a short raw bus capture. Details in
[../glorbmon/README.md](../glorbmon/README.md). What it does not give you is
freeze frames or when a code first set; those are only on the utility's DTC
tab, so export them there before clearing codes.

Useful facts learned from the replies:

- `Parallel Unit Type` (PID F065) is **1 = master, 2 = slave, 0 = Single
  Unit**: the multi-unit role, readable live.
- `DTC Flags #2` (PID F022) bit 0x10 is P0A04, 0x04 P0A80, 0x40 P0A0D,
  0x800 U0100 (bit map in the utility help, `bms_param_dtc_status_2`).
- Open-wire sub-codes are not in the OBD2 DTC list, but the high/low cell
  IDs (PIDs F03D/F03E) and the per-cell table show the open tap directly.

## Relay outputs and contactors

What is known from the manuals and the profiles; the physical count on the
car is still to be confirmed.

- Each Orion BMS 2 has **four contactor-capable outputs**: Charge Enable
  (Main I/O pin 8), Discharge Enable (pin 7), Charger Safety (pin 6) and
  Multi-Purpose Enable (pin 26). All eight on/off outputs are **open-drain
  low-side drivers**: they pull the coil's return to ground when on and float
  when off. The four above are rated 500 mA and may drive approved
  economiser contactors directly, **at most two contactors per BMS**; more
  need a relay in between (wiring manual pp. 26–31). MPO1–4 are 175 mA
  signal-level outputs.
- Polarity: MPO1–4 can be inverted in software, but still turn off on a
  critical fault. The Multi-Purpose Enable pin "cannot be inverted" by design.
  The Voltage Failsafe switches all primary enable outputs off regardless of
  relay settings.
- In both saved profiles `relaysPopulated` = 102 (four bits set; Ewert does
  not publish the mapping) and `mpoFunction` = 10, which in the utility
  manual's Multi-Purpose Output list is **Contactor Enable Output** ("active
  as long as there are no critical fault codes present"), the function Ewert
  suggests for a system-level contactor. So **three contactors per pack**
  (discharge, charge/charger, system) is plausible; one of them would have to
  be relay-driven.
- The drive chassis wiring diagram
  ([../drive/manual-en.md](../drive/manual-en.md), "Wiring and pairing")
  shows both drive controllers wired straight to the traction battery with
  **no contactors and no precharge resistor**. Every contactor on the car came
  with the Orion install, and no drawing of that install exists yet. The
  controllers report a "capacitor-board low voltage" fault code, so they do
  have DC-link capacitors; unless there is a precharge resistor in the
  contactor box, each close is a hard close.
- **To count them without opening the car:** with a relay closed, read the
  output statuses on Live Text Data (Discharge-Enable, Charge-Enable,
  Charger-Safety, Multi-Purpose Enable); each active one drives something.
  Power-cycle once and count the clunks.

## Re-linking the packs

When the bad pack is rebuilt (modules replaced, voltages matched):

1. Bring both packs to the **same voltage** before paralleling them on the
   switch. Mismatched strings mean inrush through the contactors.
2. Upload the saved **original** master and slave profiles from
   [profiles/](profiles/) to their respective units, or set the roles back by
   hand on the Addon Settings tab.
3. Power-cycle both, clear codes on both, confirm `0x1850F3F3` is back on the
   bus (glorbmon's 72 V tab shows voltage/SOC again, or Live CANBUS Traffic in
   the utility).

Whether to keep the link at all is worth a think at that point. Ewert's own
parallel-strings guidance is one BMS per string with each contactor driven by
its own BMS, and the cascading shutdown we hit is a known cost of coupling
them. The upside of the link is coordinated limits and a shared SOC.

## Things still to confirm on the car

- ~~Master ↔ switch mapping~~ **Confirmed:** position 1 = top stack = BMS 1
  = master; position 2 = bottom stack = BMS 2 = slave (L59FA424). See
  [pack-layout.md](pack-layout.md). Still to do: label both Orions and both
  stacks, and fill in which `B1`–`B6` module sits where.
- **Why four odd-numbered taps (3, 5, 7 on pack 1; 11 on pack 2) read open
  at once.** Meter plan in
  [../fault-log-2026-10-06.md](../fault-log-2026-10-06.md). Record what the
  bricks measure directly and where the breaks are.
- **Exact label of the role setting** on the Addon Settings tab (the option
  chosen was **Single Unit**). In the profile the role is
  `parallelStringSettings` (4 master, 8 slave); live it is PID F065.
- Freeze frames for the master's three codes and the slave's P0A04: export
  from the DTC tab before clearing.
- **How many contactors there are and how the DC link is precharged.** See
  "Relay outputs and contactors".

## Sources

- [Orion U0100 External Communication Fault](https://www.orionbms.com/faultcodes/DTC%20U0100%20-%20External%20Communication%20Fault.pdf)
  — subcode 50 and the Voltage Failsafe behaviour.
- [Orion utility manual: Connecting Multiple BMS Units](https://www.orionbms.com/manuals/utility/param_addon_series.html)
  — the Addon Settings role selector.
- [Orion: Strings, Parallel Cells, and Parallel Strings](https://www.orionbms.com/manuals/pdf/parallel_strings.pdf)
  — Ewert's topology guidance and the cascading-shutdown warning.
- [Orion P0A04 Open Wiring Fault](https://www.orionbms.com/faultcodes/DTC%20P0A04%20-%20Open%20Wiring%20Fault.pdf)
  — detection method, the high/low adjacent-cell signature, the note that
  unpopulated cells in the open-wire list set no code, diagnostic steps.
- [Orion Failsafe Mode Descriptions](https://www.orionbms.com/faultcodes/Failsafe%20Chart.pdf)
  — Voltage Failsafe behaviour and which DTCs trigger it.
- [Orion BMS OBD2 PID list](https://www.orionbms.com/downloads/misc/orionbms_obd2_pids.pdf)
  (2018-08-27) — mode 22 PIDs including per-cell voltage blocks.
- Orion utility manual pages:
  [Cell Population Settings](https://www.orionbms.com/manuals/utility/param_cell_population_settings.html),
  [Discharge Enable Relay](https://www.orionbms.com/manuals/utility/profile_discharge_enable_relay.html),
  [Multi-Purpose Output Function](https://www.orionbms.com/manuals/utility/param_multipurpose_output_function.html),
  [Invert Multi-Purpose Output Polarity](https://www.orionbms.com/manuals/utility/param_invert_mpo_polarity.html).
- [Orion BMS 2 Operation Manual](https://www.orionbms.com/manuals/pdf/orionbms2_operational_manual.pdf),
  [Wiring & Installation Manual](https://www.orionbms.com/manuals/pdf/orionbms2_wiring_manual.pdf),
  [Using the Orion BMS with Tesla Battery Modules](https://www.orionbms.com/manuals/pdf/tesla_modules.pdf).
