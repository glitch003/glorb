"""72 V main pack: two Orion BMS 2 units, listened to over CAN.

Both units broadcast continuously, so nothing is ever transmitted at them.
Two message layouts are decoded, and both were confirmed against the live bus
on 2026-09-02:

0x6B1 (11-bit, one per unit, in a back-to-back pair every ~300 ms)
    b0:1  Pack DCL          A        b2:3  Pack CCL          A
    b4    High Temperature  degC     b5    Low Temperature   degC
    b7    checksum = (sum(b0..b6) + can_id + dlc) & 0xFF

    The byte->parameter mapping comes from the utility's saved profile
    (master-1.o2bms customMessage[1] typeMatrix) resolved through the
    parameter table in the utility's own canbusParameters.xml. The checksum
    passed on 578 of 578 captured frames, which is what pins the layout down.

0x1850F3F3 (29-bit) is the inter-unit parallel-string message, multiplexed on
byte 0. Only the fields cross-checked against another source are decoded:

    mux 0  b1:2  DC bus voltage  x0.1 V   -- 73.3 V is exactly a 3-series
                                            Tesla module stack at the
                                            4.07 V/cell the pack is sitting
                                            at, confirming the scale
           b3    relay states
           b4    DOD             x0.5 %   -- b4 and b6 sum to exactly 100%,
           b6    SOC             x0.5 %      which is Orion's DOD/SOC pair
           b5    second SOC estimate x0.5 %
    mux 1  b1:2  average current x0.1 A (signed)
           b3:4  DCL  A   b5:6  CCL  A    -- matched 0x6B1's 400 A / 65 A
    mux 2  b3    low temp degC   b4  high temp degC
                                          -- matched 0x6B1's 17 C / 19 C

Getting b4 and b6 the wrong way round reads 86%-charged as 14%, so the
complement is worth re-checking if these ever look implausible against cell
voltage. b5 tracks a few percent below b6; Orion keeps both a coulomb-counted
and an adaptive SOC, and which of the two this is has not been confirmed, so
it is reported as a secondary figure rather than as the pack's SOC.

The remaining bytes of mux 2 have no confirmed meaning and are exposed as raw
hex rather than guessed at.
"""

import time

CAN_ID_STATUS = 0x6B1        # per-unit DCL/CCL/temperatures
CAN_ID_PARALLEL = 0x1850F3F3  # inter-unit parallel-string message

# A unit that has not been heard from for this long is reported as lost.
UNIT_TIMEOUT_S = 3.0

RELAY_BITS = [
    (0x01, "discharge"),
    (0x02, "charge"),
    (0x04, "charger safety"),
    (0x08, "precharge"),
]

NOTES = [
    "Both Orions broadcast on the same CAN ID (0x6B1), so nothing in a frame "
    "says which unit sent it. They are separated by the order they alternate "
    "on the bus, cross-checked against each unit's previous reading. That "
    "works while their readings differ, but if the two ever converge the A/B "
    "labels could swap. Giving the second unit a different CAN ID in its "
    "profile would make them reliable.",
    "Neither unit is broadcasting 0x6B0, so pack current, instantaneous "
    "voltage and SOC come from the parallel-string message instead.",
]


def checksum_ok(can_id, data):
    """Orion's CAN checksum: sum of the payload plus the ID plus the length."""
    if len(data) != 8:
        return False
    return (sum(data[:7]) + can_id + len(data)) & 0xFF == data[7]


def _i16(data, i):
    return int.from_bytes(data[i:i + 2], "big", signed=True)


def _u16(data, i):
    return int.from_bytes(data[i:i + 2], "big")


_COMPARE_FIELDS = ("dcl_a", "ccl_a", "temp_high_c", "temp_low_c")


def _distance(a, b):
    """How unlike two 0x6B1 readings are, for telling the units apart."""
    return sum(abs(a[f] - b[f]) for f in _COMPARE_FIELDS)


def parse_status(data):
    """Decode one 0x6B1 frame into a single unit's limits and temperatures."""
    if len(data) != 8:
        raise ValueError(f"0x6B1 needs 8 bytes, got {len(data)}")
    return {
        "dcl_a": _u16(data, 0),
        "ccl_a": _u16(data, 2),
        "temp_high_c": data[4],
        "temp_low_c": data[5],
    }


def parse_parallel(data):
    """Decode one 0x1850F3F3 frame; returns only the fields its mux carries."""
    if len(data) != 8:
        raise ValueError(f"0x1850F3F3 needs 8 bytes, got {len(data)}")
    mux = data[0]
    if mux == 0:
        return {
            "bus_voltage": _u16(data, 1) / 10.0,
            "relay_state": data[3],
            "relays": [n for bit, n in RELAY_BITS if data[3] & bit],
            # b4 and b6 always sum to exactly 100%, which is Orion's
            # DOD/SOC pair -- so b6 is the state of charge and b4 is the
            # depth of discharge, not the other way round.
            "dod": data[4] * 0.5,
            "soc_alt": data[5] * 0.5,
            "soc": data[6] * 0.5,
        }
    if mux == 1:
        return {
            "avg_current": _i16(data, 1) / 10.0,
            "dcl_a": _u16(data, 3),
            "ccl_a": _u16(data, 5),
        }
    if mux == 2:
        return {
            "temp_low_c": data[3],
            "temp_high_c": data[4],
            "mux2_head": data[1:3].hex(),
            "mux2_tail": data[5:7].hex(),
        }
    return {}


class OrionBus:
    """Accumulates the state both Orions broadcast onto the CAN bus."""

    id = "72v"
    title = "72 V drive pack"
    subtitle = "2x Orion BMS 2 via CANdapter"

    def __init__(self, port, expected_units=2, settle_s=0.7):
        self.port = port
        self.expected_units = expected_units
        self.settle_s = settle_s
        self._units = {}          # burst position -> latest reading
        self._pack = {}
        self._pack_seen = 0.0
        self._last_slot = None
        self._counts = {}
        self._recent = []
        self._bad_checksums = 0
        self._other_ids = {}

    def close(self):
        self.port.close()

    def poll(self):
        self.port.open()
        self._consume(self.port.drain())
        # Right after opening there is nothing buffered yet: the status pair
        # only repeats every ~300 ms and the parallel message cycles through
        # three multiplexed layouts. Wait for a full round the first time so
        # the first reading is complete rather than half a bus.
        deadline = time.time() + self.settle_s
        while not self._round_complete() and time.time() < deadline:
            time.sleep(0.05)
            self._consume(self.port.drain())
        self._recent = self._recent[-200:]
        return self._summarise(time.time()), list(self._recent[-40:])

    def _round_complete(self):
        """Have we heard from every unit and seen all three parallel muxes?"""
        return (len(self._units) >= self.expected_units
                and "bus_voltage" in self._pack      # mux 0
                and "avg_current" in self._pack      # mux 1
                and "temp_low_c" in self._pack)      # mux 2

    def _consume(self, frames):
        for can_id, data, extended in frames:
            now = time.time()
            self._recent.append(
                f"{'x' if extended else 't'}{can_id:X} {data.hex().upper()}")
            if can_id == CAN_ID_STATUS and not extended:
                self._on_status(can_id, data, now)
            elif can_id == CAN_ID_PARALLEL and extended:
                self._pack.update(parse_parallel(data))
                self._pack_seen = now
            else:
                self._other_ids[can_id] = self._other_ids.get(can_id, 0) + 1

    def _on_status(self, can_id, data, now):
        if not checksum_ok(can_id, data):
            self._bad_checksums += 1
            return
        reading = parse_status(data)
        index = self._assign_slot(reading)
        reading["name"] = f"Orion {chr(ord('A') + index)}"
        reading["seen"] = now
        self._counts[index] = self._counts.get(index, 0) + 1
        reading["frames"] = self._counts[index]
        self._units[index] = reading

    def _assign_slot(self, reading):
        """Decide which unit a 0x6B1 frame came from.

        Both units transmit on the same CAN ID, so there is nothing in the
        frame that identifies the sender. What they do reliably is alternate
        on the bus, so the next frame belongs to the next unit round-robin.

        That alone is not enough: arrival timestamps are lost because frames
        are read out of a buffer (and this CANdapter firmware ignores the
        SLCAN Z1 timestamp command), so a single missed frame would flip the
        phase permanently. The round-robin guess is therefore checked against
        content -- the units sit a few amps of CCL and about a degree apart
        and drift far more slowly than that, so the closest previous reading
        wins. When the two readings are identical there is nothing to tell
        apart and the round-robin order stands.
        """
        count = self.expected_units
        slot = 0 if self._last_slot is None else (self._last_slot + 1) % count
        if len(self._units) >= count:
            best = min(self._units, key=lambda i: _distance(reading,
                                                            self._units[i]))
            if _distance(reading, self._units[best]) < \
                    _distance(reading, self._units[slot]):
                slot = best
        self._last_slot = slot
        return slot

    def _summarise(self, now):
        units = []
        for index in sorted(self._units):
            unit = dict(self._units[index])
            unit["age_s"] = round(now - unit.pop("seen"), 2)
            unit["online"] = unit["age_s"] <= UNIT_TIMEOUT_S
            units.append(unit)
        live = [u for u in units if u["online"]]

        pack = dict(self._pack)
        pack_fresh = self._pack_seen and (now - self._pack_seen) <= UNIT_TIMEOUT_S
        if not pack_fresh:
            pack = {}

        summary = []
        if pack.get("bus_voltage") is not None:
            summary.append({"label": "Bus", "unit": "V",
                            "value": f"{pack['bus_voltage']:.1f}"})
        if pack.get("avg_current") is not None:
            summary.append({"label": "Current", "unit": "A",
                            "value": f"{pack['avg_current']:+.1f}"})
        if pack.get("soc") is not None:
            summary.append({"label": "SOC", "unit": "%",
                            "value": f"{pack['soc']:.0f}"})
        if live:
            summary.append({"label": "Temp", "unit": "°C",
                            "value": f"{max(u['temp_high_c'] for u in live)}"})

        if not live:
            state, text = "down", "no Orion traffic on the bus"
        elif len(live) < self.expected_units:
            state = "warn"
            text = (f"{len(live)} of {self.expected_units} units transmitting")
        else:
            state, text = "ok", f"{len(live)} units on CAN"

        notes = list(NOTES)
        if self._bad_checksums:
            notes.append(f"{self._bad_checksums} frames failed the Orion "
                         "checksum and were discarded.")
        if self._other_ids:
            seen = ", ".join(f"0x{i:X} ({n})"
                             for i, n in sorted(self._other_ids.items())[:6])
            notes.append(f"Other CAN IDs seen on the bus: {seen}.")

        return {"state": state, "status_text": text, "summary": summary,
                "pack": pack, "units": units, "notes": notes}
