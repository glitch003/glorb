# Orion BMS 2 — the two drive-pack BMS units

The 72 V drive battery is **two Tesla-module packs**, each with its own
**Orion BMS 2** and its own contactor, joined on the DC side through a
**1 / 2 / 1+2 / OFF** pack selector switch. This folder holds the saved Orion
profiles and the notes on how the two units are linked, what happens when one
of them faults, and how to run on a single pack.

Related: [../batteries.md](../batteries.md) (pack overview),
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

### Dashboard side effect

Once the good unit is standalone it stops sending the parallel-string
message, and glorbmon currently takes pack voltage, current and SOC **only**
from that message (`0x1850F3F3`). The 72 V tab keeps the `0x6B1` limits and
temperatures but loses voltage/SOC. The proper fix is the one the glorbmon
README already recommends: enable the `0x6B0` broadcast in the profile so
each unit reports its own voltage, current and SOC. Until then, read the pack
from the utility's Live Text Data.

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

- **Which physical pack is the master.** The profiles saved on 2026-10-05
  were named `master-01` and `slave-2`, which suggests master = switch
  position 1 and slave = position 2. Confirm on the car and label both
  Orions. The ex-slave is serial **L59FA424** (firmware 3.6.3).
- **Exact label of the role setting.** Confirmed so far: the option chosen
  on the Addon Settings tab is called **Single Unit**. Record the label of
  the selector itself and the other option names when next in the utility.
  In the saved profiles the role appears to live in `parallelStringSettings`
  (4 on the master, 8 on the slave); the Single Unit value is unknown
  because the modified profile was not saved — save it as
  `slave-single-<date>.o2bms` next time (see [profiles/README.md](profiles/README.md)).
- **The "good" pack has its own fault.** On the first limp-mode attempt the
  ex-slave raised **P0A04 Open Wiring Fault on tap 11** (cells 11/12 reading
  3.91 / 3.41 V, the classic open-tap pair). Analysis and verdict in
  [../fault-log-2026-10-06.md](../fault-log-2026-10-06.md). Check the DTC
  history to see whether it predates the role change.
- Whether the faulted (bad) pack's fault was a cell-voltage fault, a
  weak-cell fault, or something else. Export the freeze frame from the DTC
  tab before clearing it.
- **How the DC link is precharged.** The Orion profiles contain no precharge
  settings and the freeze frame shows *Precharge State 0*, so precharge (if
  any) is outside the BMS. Find it before anyone jumpers a contactor coil.

## Sources

- [Orion U0100 External Communication Fault](https://www.orionbms.com/faultcodes/DTC%20U0100%20-%20External%20Communication%20Fault.pdf)
  — subcode 50 and the Voltage Failsafe behaviour.
- [Orion utility manual: Connecting Multiple BMS Units](https://www.orionbms.com/manuals/utility/param_addon_series.html)
  — the Addon Settings role selector.
- [Orion: Strings, Parallel Cells, and Parallel Strings](https://www.orionbms.com/manuals/pdf/parallel_strings.pdf)
  — Ewert's topology guidance and the cascading-shutdown warning.
- [Orion BMS 2 Operation Manual](https://www.orionbms.com/manuals/pdf/orionbms2_operational_manual.pdf),
  [Wiring & Installation Manual](https://www.orionbms.com/manuals/pdf/orionbms2_wiring_manual.pdf),
  [Using the Orion BMS with Tesla Battery Modules](https://www.orionbms.com/manuals/pdf/tesla_modules.pdf).
