"""Ask the two Orion BMS 2 units questions over OBD2, through the CANdapter.

The Orion answers ISO 15765 (OBD2 over CAN) requests addressed to its OBD2
ECU ID (profile field `obd2EcuId`: 0x7E3 on the master, 0x7E4 on the slave),
replying on ECU ID + 8. Three things are useful:

    mode 03 / 07 / 0A    stored / pending / permanent diagnostic trouble codes
    mode 22, PID F0xx    one BMS parameter; xx is the parameter ID from the
                         utility's canbusParameters.xml (F00D = pack voltage)
    mode 22, PID F1nn    cell voltages, 12 per block (F100 = cells 1-12,
                         F101 = 13-24); F3nn open-cell voltages, F2nn
                         resistances (MSB = balancing)

Replies longer than 7 bytes come as ISO-TP multi-frame: a first frame
(0x1L LL ...) that must be answered with a flow-control frame (30 00 00)
before the consecutive frames (0x2n ...) follow. The units time out if the
flow control is more than about a second late, so it is sent as soon as the
first frame is seen.

Everything here was checked against glorb's two units on 2026-10-06; the
request/response layout follows Ewert's OBD2 PID list (orionbms_obd2_pids.pdf,
2018-08-27) and the worked example in the utility's help.

Run `python -m glorbmon.obd2` with the Orion utility closed (it holds the
CANdapter's COM port) to dump both units to CSV.
"""

import argparse
import csv
import datetime
import sys
import time
from collections import Counter
from functools import partial

from . import ports, slcan

ECUS = {"master": 0x7E3, "slave": 0x7E4}

# Modes 03/07/0A reply with 4x/count/DTC pairs; the first byte of each pair
# carries the letter in its top two bits.
DTC_LETTERS = "PCBU"

# Parameter ID -> (name, scale, signed). Mode 22 PID F0xx returns parameter
# xx; the table is the TX parameter list in the utility's canbusParameters.xml
# cross-checked against Ewert's OBD2 PID list.
PARAMETERS = {
    0x04: ("Relay State", 1, False), 0x06: ("Max Cell Number", 1, False),
    0x07: ("Populated Cells", 1, False), 0x09: ("Failsafe Statuses", 1, False),
    0x0A: ("Pack CCL (A)", 1, False), 0x0B: ("Pack DCL (A)", 1, False),
    0x0C: ("Pack Current (A)", 0.1, True), 0x0D: ("Pack Inst. Voltage (V)", 0.1, False),
    0x0E: ("Pack Open Voltage (V)", 0.1, False), 0x0F: ("Pack SOC (%)", 0.5, False),
    0x10: ("Pack Amphours (Ah)", 0.1, False), 0x11: ("Pack Resistance (mOhm)", 0.01, False),
    0x12: ("Pack DOD (%)", 0.5, False), 0x13: ("Pack Health (%)", 1, False),
    0x14: ("Pack Summed Voltage (V)", 0.01, False), 0x15: ("Pack Abs. Current (A)", 0.1, False),
    0x16: ("Maximum Pack Voltage (V)", 0.1, False), 0x17: ("Minimum Pack Voltage (V)", 0.1, False),
    0x18: ("Total Pack Cycles", 1, False), 0x19: ("Current Limits Status", 1, False),
    0x1A: ("Pack CCL (kW)", 0.1, False), 0x1B: ("Pack DCL (kW)", 0.1, False),
    0x1C: ("Maximum Pack DCL (A)", 1, False), 0x1D: ("Maximum Pack CCL (A)", 1, False),
    0x1E: ("Simulated SOC", 0.5, False), 0x1F: ("Simulated Mode", 1, False),
    0x20: ("Simulated Req. Mode", 1, False), 0x21: ("DTC Flags #1", 1, False),
    0x22: ("DTC Flags #2", 1, False), 0x27: ("Average Current (A)", 0.1, True),
    0x28: ("High Temperature (C)", 1, False), 0x29: ("Low Temperature (C)", 1, False),
    0x2A: ("Average Temperature (C)", 1, False), 0x2B: ("Fan Speed", 1, False),
    0x2C: ("Req. Fan Speed", 1, False), 0x2D: ("Internal Temperature (C)", 1, False),
    0x2E: ("High Thermistor ID", 1, False), 0x2F: ("Low Thermistor ID", 1, False),
    0x30: ("J1772 Plug State", 1, False), 0x31: ("J1772 AC Current Limit (A)", 1, False),
    0x32: ("Low Cell Voltage (V)", 0.0001, False), 0x33: ("High Cell Voltage (V)", 0.0001, False),
    0x34: ("Avg. Cell Voltage (V)", 0.0001, False), 0x35: ("Low Opencell Voltage (V)", 0.0001, False),
    0x36: ("High Opencell Voltage (V)", 0.0001, False), 0x37: ("Avg. Opencell Voltage (V)", 0.0001, False),
    0x38: ("Low Cell Resistance (mOhm)", 0.01, False), 0x39: ("High Cell Resistance (mOhm)", 0.01, False),
    0x3A: ("Avg. Cell Resistance (mOhm)", 0.01, False), 0x3B: ("Maximum Cell Voltage (V)", 0.0001, False),
    0x3C: ("Minimum Cell Voltage (V)", 0.0001, False), 0x3D: ("High Cell Voltage ID", 1, False),
    0x3E: ("Low Cell Voltage ID", 1, False), 0x3F: ("High Opencell ID", 1, False),
    0x40: ("Low Opencell ID", 1, False), 0x41: ("High Intres ID", 1, False),
    0x42: ("Low Intres ID", 1, False), 0x43: ("Adaptive Amphours (Ah)", 0.1, False),
    0x44: ("Adaptive Total Capacity (Ah)", 0.1, False), 0x45: ("Adaptive SOC (%)", 0.5, False),
    0x46: ("Input Supply Voltage (V)", 0.1, False), 0x47: ("Current ADC1", 1, False),
    0x48: ("Current ADC2", 1, False), 0x49: ("Fan Voltage (V)", 0.01, False),
    0x4A: ("Isolation ADC", 1, False), 0x4B: ("Shortest Wave (V)", 0.001, False),
    0x4C: ("Isolation Clipping (V)", 0.001, False), 0x4D: ("Isolation Threshold (V)", 0.001, False),
    0x52: ("J1772 AC Power Limit (W)", 1, False), 0x53: ("J1772 AC Voltage (V)", 0.1, False),
    0x58: ("Intake Temperature (C)", 1, False), 0x59: ("Vehicle Speed (KPH)", 1, False),
    0x5A: ("Parallel Relay States", 1, False), 0x5B: ("Parallel SOC (%)", 0.5, False),
    0x5C: ("Parallel DCL (A)", 1, False), 0x5D: ("Parallel CCL (A)", 1, False),
    0x5E: ("Parallel Avg Current (A)", 0.1, True), 0x5F: ("Parallel DC Bus Voltage (V)", 0.1, False),
    0x60: ("Parallel Target Max DC PackV (V)", 0.01, False),
    0x61: ("Parallel Target Min DC PackV (V)", 0.01, False),
    0x62: ("Parallel Low Temperature (C)", 1, False), 0x63: ("Parallel High Temperature (C)", 1, False),
    0x64: ("Parallel Active Strings", 1, False), 0x65: ("Parallel Unit Type", 1, False),
    0x76: ("Float Charge Voltage (V)", 0.1, False), 0x77: ("Precharge Circuit State", 1, False),
    0x80: ("Application DC Bus Voltage", 0.1, False), 0x82: ("Pack kW Power", 0.1, False),
}

# DTC Flags #1 / #2 bit meanings, from the utility's help (bms_param_dtc_status_*).
DTC_FLAGS_1 = ["P0A07", "P0A08", "P0A09", "P0A0A", "P0A0B", "P0A0C", "P0A0E", "P0A10"]
DTC_FLAGS_2 = ["P0A1F", "P0A12", "P0A80", "P0AFA", "P0A04", "P0AC0", "P0A0D", "P0A0F",
               "P0A02", "P0A81", "P0A9C", "U0100", "P0560", "P0AA6", "P0A05", "P0A06"]

# Parallel Unit Type values seen on glorb's units.
UNIT_TYPES = {0: "single unit", 1: "master", 2: "slave"}

SUMMARY_FIELDS = ("Pack Inst. Voltage", "Pack Summed Voltage", "Pack SOC", "Pack DCL", "Pack CCL",
                  "Low Cell Voltage", "High Cell Voltage", "Low Cell Voltage ID", "High Cell Voltage ID",
                  "Low Opencell ID", "High Opencell ID", "Failsafe Statuses", "Relay State")


def decode_dtcs(payload):
    """Decode a mode 03/07/0A reply (0x43/0x47/0x4A, count, pairs) to codes."""
    if not payload or payload[0] not in (0x43, 0x47, 0x4A):
        return None
    codes = []
    for i in range(payload[1]):
        hi, lo = payload[2 + 2 * i], payload[3 + 2 * i]
        codes.append("%s%d%X%X%X" % (DTC_LETTERS[hi >> 6], (hi >> 4) & 3, hi & 0xF, lo >> 4, lo & 0xF))
    return codes


def decode_flags(value, names):
    return [name for bit, name in enumerate(names) if value & (1 << bit)]


def decode_parameter(pid_lo, payload):
    """(name, value) for a mode 22 F0xx reply payload (bytes after the PID)."""
    if pid_lo not in PARAMETERS or len(payload) not in (1, 2, 4):
        return "parameter %d" % pid_lo if pid_lo not in PARAMETERS else PARAMETERS[pid_lo][0], payload.hex()
    name, scale, signed = PARAMETERS[pid_lo]
    n = int.from_bytes(payload, "big", signed=signed)
    return name, (round(n * scale, 4) if scale != 1 else n)


def decode_cell_block(payload):
    """16-bit big-endian values from a F1nn/F2nn/F3nn reply payload."""
    return [int.from_bytes(payload[2 * i:2 * i + 2], "big") for i in range(len(payload) // 2)]


class IsoTp:
    """Reassemble one ISO-TP reply. feed() returns the payload once complete."""

    def __init__(self):
        self.buf = None
        self.total = None
        self.need_flow_control = False

    def feed(self, data):
        pci = data[0] >> 4
        if pci == 0:
            return bytes(data[1:1 + (data[0] & 0xF)])
        if pci == 1:
            self.total = ((data[0] & 0xF) << 8) | data[1]
            self.buf = bytearray(data[2:])
            self.need_flow_control = True
        elif pci == 2 and self.buf is not None:
            self.buf += data[1:]
        if self.buf is not None and len(self.buf) >= self.total:
            return bytes(self.buf[:self.total])
        return None


class Obd2Client:
    def __init__(self, port):
        self.port = port

    def request(self, ecu, payload, timeout=0.4):
        resp = ecu + 8
        self.port.drain()
        self.port.send(ecu, bytes([len(payload)]) + bytes(payload))
        asm = IsoTp()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for can_id, data, extended in self.port.drain():
                if extended or can_id != resp:
                    continue
                done = asm.feed(data)
                if asm.need_flow_control:
                    asm.need_flow_control = False
                    self.port.send(ecu, bytes([0x30, 0x00, 0x00]))
                    deadline = time.monotonic() + 2.0
                if done is not None:
                    return done
            time.sleep(0.003)
        return None

    def dtcs(self, ecu, mode=0x03):
        return decode_dtcs(self.request(ecu, [mode]))

    def parameter(self, ecu, pid_lo):
        reply = self.request(ecu, [0x22, 0xF0, pid_lo])
        if not reply or reply[0] != 0x62:
            return None
        return reply[3:]

    def cell_block(self, ecu, pid_hi, block):
        reply = self.request(ecu, [0x22, pid_hi, block])
        if not reply or reply[0] != 0x62:
            return None
        return decode_cell_block(reply[3:])

    def cells(self, ecu, count):
        blocks = (count + 11) // 12
        volts, opens, res = [], [], []
        for b in range(blocks):
            volts += self.cell_block(ecu, 0xF1, b) or []
            opens += self.cell_block(ecu, 0xF3, b) or []
            res += self.cell_block(ecu, 0xF2, b) or []
        rows = []
        for i in range(count):
            r = res[i] if i < len(res) else 0
            rows.append({
                "cell": i + 1,
                "inst_voltage_V": round(volts[i] * 1e-4, 4) if i < len(volts) else None,
                "open_cell_voltage_V": round(opens[i] * 1e-4, 4) if i < len(opens) else None,
                "resistance_mOhm": round((r & 0x7FFF) * 0.01, 2),
                "balancing": int(bool(r & 0x8000)),
            })
        return rows


def snapshot(client, ecu, cells_per_module=6):
    """Everything worth keeping from one unit, as (summary rows, cell rows)."""
    rows = []
    for mode, label in ((0x03, "stored DTCs"), (0x07, "pending DTCs"), (0x0A, "permanent DTCs")):
        reply = client.request(ecu, [mode])
        rows.append(("mode %02X" % mode, label, reply.hex() if reply else "",
                     " ".join(decode_dtcs(reply) or [])))
    populated = 0
    for pid_lo in range(0x100):
        payload = client.parameter(ecu, pid_lo)
        if payload is None:
            continue
        name, value = decode_parameter(pid_lo, payload)
        rows.append(("F0%02X" % pid_lo, name, payload.hex(), value))
        if pid_lo == 0x07:
            populated = value
        elif pid_lo == 0x21:
            rows.append(("F021.bits", "DTC Flags #1 decoded", "", " ".join(decode_flags(value, DTC_FLAGS_1))))
        elif pid_lo == 0x22:
            rows.append(("F022.bits", "DTC Flags #2 decoded", "", " ".join(decode_flags(value, DTC_FLAGS_2))))
        elif pid_lo == 0x65:
            rows.append(("F065.name", "Parallel Unit Type decoded", "", UNIT_TYPES.get(value, "?")))
    cell_rows = client.cells(ecu, populated) if populated else []
    for row in cell_rows:
        row["tesla_module"] = (row["cell"] - 1) // cells_per_module + 1
    return rows, cell_rows


def print_summary(unit, rows, cell_rows, cells_per_module=6):
    print("=== %s" % unit)
    for pid, name, raw, value in rows:
        if (pid.startswith("mode") or pid.endswith(".bits") or pid.endswith(".name")
                or name.split(" (")[0] in SUMMARY_FIELDS):
            print("  %-9s %-32s %s" % (pid, name, value))
    for m in range(0, len(cell_rows), cells_per_module):
        seg = [r["inst_voltage_V"] for r in cell_rows[m:m + cells_per_module]]
        print("  module %d cells %2d-%2d: %s  sum=%.2f spread=%.3f" % (
            m // cells_per_module + 1, m + 1, m + len(seg),
            " ".join("%.3f" % v for v in seg), sum(seg), max(seg) - min(seg)))


def write_csvs(out_dir, unit, ecu, stamp, rows, cell_rows):
    with open("%s/obd2-%s.csv" % (out_dir, unit), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# Orion BMS 2 OBD2 snapshot, unit=%s, ecu=0x%03X, captured %s" % (unit, ecu, stamp)])
        w.writerow(["pid", "name", "raw_hex", "value"])
        w.writerows(rows)
    if cell_rows:
        with open("%s/cells-%s.csv" % (out_dir, unit), "w", newline="") as f:
            f.write("# Orion BMS 2 per-cell readings via OBD2 PIDs F1nn/F3nn/F2nn, unit=%s, ecu=0x%03X, captured %s\n"
                    % (unit, ecu, stamp))
            w = csv.DictWriter(f, fieldnames=["cell", "tesla_module", "inst_voltage_V",
                                              "open_cell_voltage_V", "resistance_mOhm", "balancing"])
            w.writeheader()
            w.writerows(cell_rows)


def capture_bus(port, seconds, out_dir, stamp):
    port.drain()
    t0 = time.monotonic()
    frames = []
    while time.monotonic() - t0 < seconds:
        for can_id, data, extended in port.drain():
            frames.append((round(time.monotonic() - t0, 3),
                           "%08X" % can_id if extended else "%03X" % can_id, data.hex()))
        time.sleep(0.02)
    with open("%s/bus-capture.csv" % out_dir, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# %g s of raw CAN traffic through the CANdapter, captured %s" % (seconds, stamp)])
        w.writerow(["t_s", "can_id", "data_hex"])
        w.writerows(frames)
    print("bus capture: %d frames %s" % (len(frames), dict(Counter(c for _, c, _ in frames))))


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Dump DTCs, parameters and cell voltages from the Orions over OBD2.")
    parser.add_argument("--port", help="CANdapter COM port (default: auto-detect by USB id)")
    parser.add_argument("--out", default=".", help="directory for the CSV files")
    parser.add_argument("--units", default="master,slave", help="comma list of units to query")
    parser.add_argument("--capture", type=float, default=10.0,
                        help="seconds of raw bus traffic to record afterwards (0 to skip)")
    args = parser.parse_args(argv)

    device = args.port or ports.discover().get("72v")
    if not device:
        print("no CANdapter found; pass --port", file=sys.stderr)
        return 2
    import serial
    port = slcan.SlcanPort(partial(serial.Serial, device, write_timeout=1.0))
    port.open()
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    try:
        client = Obd2Client(port)
        for unit in args.units.split(","):
            unit = unit.strip()
            ecu = ECUS[unit]
            rows, cell_rows = snapshot(client, ecu)
            write_csvs(args.out, unit, ecu, stamp, rows, cell_rows)
            print_summary(unit, rows, cell_rows)
        if args.capture > 0:
            capture_bus(port, args.capture, args.out, stamp)
    finally:
        port.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
