"""24 V side: Tesla modules read through the TeslaBMS Arduino Due.

The firmware in electrical/tesla-batteries/TeslaBMS already has a
machine-parsable snapshot command -- 'i' prints one CSV line per discovered
module between INV-BEGIN and INV-END:

    INV,<addr>,<moduleV>,<c1>..<c6>,<t1>,<t2>,<alerts>,<faults>,<cov>,<cuv>

with the last four in hex. That is used here in preference to scraping the
human 'd' display, which is column-formatted for a terminal and rounds cell
voltages to 2 decimals.

The one thing to be careful about is the port: opening it asserts DTR, which
resets the Due and costs several seconds of boot. So the connection is opened
once and held for the life of the process, and each poll is just another 'i'.
"""

import time

from .soc import estimate_soc

BAUD = 115200
BEGIN = "INV-BEGIN"
END = "INV-END"
BOOT_MARKER = "Started serial interface"
CELLS_PER_MODULE = 6

FAULT_BITS = [
    (0x01, "cell overvoltage"),
    (0x02, "cell undervoltage"),
    (0x04, "CRC error"),
    (0x08, "power-on reset"),
    (0x10, "test fault"),
    (0x20, "registers inconsistent"),
]
ALERT_BITS = [
    (0x01, "over temperature TS1"),
    (0x02, "over temperature TS2"),
    (0x04, "sleep mode active"),
    (0x08, "thermal shutdown"),
    (0x10, "test alert"),
    (0x20, "OTP EEPROM error"),
    (0x40, "group3 regs invalid"),
    (0x80, "address not registered"),
]


def _bits(value, table):
    return [name for bit, name in table if value & bit]


def parse_inventory_line(line):
    """Decode one INV,... line into a module reading."""
    parts = [p.strip() for p in line.strip().split(",")]
    if not parts or parts[0] != "INV":
        raise ValueError(f"not an INV line: {line!r}")
    # INV + addr + moduleV + 6 cells + 2 temps + 4 status words
    expected = 3 + CELLS_PER_MODULE + 2 + 4
    if len(parts) != expected:
        raise ValueError(f"INV line has {len(parts)} fields, expected {expected}")

    addr = int(parts[1])
    voltage = float(parts[2])
    cells = [float(v) for v in parts[3:3 + CELLS_PER_MODULE]]
    t1, t2 = float(parts[9]), float(parts[10])
    alerts, faults, cov, cuv = (int(v, 16) for v in parts[11:15])

    flags = _bits(faults, FAULT_BITS) + _bits(alerts, ALERT_BITS)
    # The firmware reports which cells tripped as a bitmask; naming them saves
    # a trip to the serial console to find out.
    for mask, label in ((cov, "overvoltage"), (cuv, "undervoltage")):
        hit = [str(i + 1) for i in range(CELLS_PER_MODULE) if mask & (1 << i)]
        if hit:
            flags.append(f"{label} on cell {', '.join(hit)}")

    lo, hi = min(cells), max(cells)
    return {
        "addr": addr,
        "voltage": voltage,
        "cells": cells,
        "temps": [t1, t2],
        "cell_min": lo,
        "cell_max": hi,
        "cell_delta_mv": (hi - lo) * 1000.0,
        "soc_estimate": estimate_soc(sum(cells) / len(cells)),
        "alerts": alerts,
        "faults": faults,
        "flags": flags,
    }


def parse_inventory(lines):
    """Decode a whole INV-BEGIN..INV-END block into module readings."""
    modules = []
    for line in lines:
        if line.startswith("INV,"):
            modules.append(parse_inventory_line(line))
    return sorted(modules, key=lambda m: m["addr"])


def summarise(modules):
    """Bank-level figures across every module the BMS found.

    These six modules are the 24 V LED bank and are wired in PARALLEL, so the
    bank sits at one module's voltage -- summing them the way the firmware's
    own printPackSummary() does would report ~146 V for a 24 V bank. The
    firmware has no idea how the modules are wired; this does.

    Module spread is the number that matters here: the bring-up procedure in
    tesla-batteries/README.md wants every module within 0.1 V of the others
    before they are paralleled.
    """
    if not modules:
        return {}
    cells = [c for m in modules for c in m["cells"]]
    temps = [t for m in modules for t in m["temps"]]
    module_v = [m["voltage"] for m in modules]
    lo, hi = min(cells), max(cells)
    average_cell = sum(cells) / len(cells)
    return {
        "voltage": sum(module_v) / len(module_v),
        "module_min": min(module_v),
        "module_max": max(module_v),
        "module_spread_v": max(module_v) - min(module_v),
        # No current sensor on these boards, so this is an open-circuit
        # voltage estimate and is only honest while the bank is resting.
        "soc_estimate": estimate_soc(average_cell),
        "soc_estimate_low": estimate_soc(lo),
        "soc_estimate_high": estimate_soc(hi),
        # What the BMS daisy chain adds up to. Meaningless as a bank voltage,
        # but it is what the serial console prints, so keep it comparable.
        "series_sum_v": sum(module_v),
        "avg_cell": sum(cells) / len(cells),
        "avg_temp": sum(temps) / len(temps),
        "cell_min": lo,
        "cell_max": hi,
        "cell_delta_mv": (hi - lo) * 1000.0,
        "modules": len(modules),
        "faulted": any(m["flags"] for m in modules),
    }


class TeslaBMS:
    """Holds the Due's console open and asks for a snapshot on demand."""

    id = "24v"
    title = "24 V LED bank"
    subtitle = "6x Tesla modules in parallel, TeslaBMS on Arduino Due"

    def __init__(self, serial_factory, boot_wait_s=9.0, reply_timeout_s=15.0):
        self._open = serial_factory
        self.boot_wait_s = boot_wait_s
        self.reply_timeout_s = reply_timeout_s
        self.ser = None

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            finally:
                self.ser = None

    def _connect(self):
        if self.ser is not None:
            return self.ser
        ser = self._open(baudrate=BAUD, timeout=0.5)
        self.ser = ser
        # Opening the port reset the board; let it finish booting and
        # discovering modules before asking anything, or the first poll comes
        # back with a partial module list.
        deadline = time.time() + self.boot_wait_s
        while time.time() < deadline:
            line = ser.readline().decode("ascii", "replace")
            if BOOT_MARKER in line:
                time.sleep(1.0)
                break
        ser.reset_input_buffer()
        return ser

    def poll(self):
        ser = self._connect()
        ser.reset_input_buffer()
        ser.write(b"i\n")
        ser.flush()

        lines, started = [], False
        deadline = time.time() + self.reply_timeout_s
        while time.time() < deadline:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode("ascii", "replace").strip()
            if line == BEGIN:
                started, lines = True, []
                continue
            if line == END:
                if started:
                    break
                continue
            if started:
                lines.append(line)
        else:
            raise TimeoutError("no INV-END from TeslaBMS within "
                               f"{self.reply_timeout_s:.0f}s")

        modules = parse_inventory(lines)
        pack = summarise(modules)
        return self._summarise(modules, pack), [f"i -> {len(lines)} lines"] + lines

    def _summarise(self, modules, pack):
        summary = []
        if pack:
            summary = [
                {"label": "Bank", "value": f"{pack['voltage']:.2f}", "unit": "V"},
                {"label": "SOC (est)", "unit": "%",
                 "value": ("—" if pack["soc_estimate"] is None
                           else f"{pack['soc_estimate']:.0f}")},
                {"label": "Module spread", "unit": "mV",
                 "value": f"{pack['module_spread_v'] * 1000:.0f}"},
                {"label": "Cell spread", "unit": "mV",
                 "value": f"{pack['cell_delta_mv']:.0f}"},
                {"label": "Temp", "value": f"{pack['avg_temp']:.1f}", "unit": "°C"},
            ]

        faults = [f"module {m['addr']}: {f}" for m in modules for f in m["flags"]]
        if not modules:
            state, text = "down", "no modules found"
        elif faults:
            state, text = "fault", "; ".join(faults)
        else:
            state = "ok"
            text = (f"{len(modules)} modules, "
                    f"{pack['module_spread_v'] * 1000:.0f} mV apart")

        notes = []
        if pack.get("soc_estimate") is not None:
            notes.append(
                "SOC is estimated from resting cell voltage: these boards "
                "measure voltage and temperature only, with no current sensor "
                "and so no coulomb counting. It reads low under load and high "
                "on charge. The curve agrees with the Orion's own SOC on the "
                f"72 V pack (same cells) to within a percent. Cells currently "
                f"span {pack['soc_estimate_low']:.0f}-"
                f"{pack['soc_estimate_high']:.0f}%.")
        return {"state": state, "status_text": text, "summary": summary,
                "pack": pack, "modules": modules, "notes": notes}
