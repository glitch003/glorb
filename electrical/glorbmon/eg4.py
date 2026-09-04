"""12 V aux packs: EG4 LifePower4 over RS485, 9600 8N1.

These are the "EG4-LL" generation and speak plain **Modbus RTU**, not the
0x7E/0x0D framing used by the 48 V LifePower4 units. Confirmed against all
three of glorb's packs on 2026-09-02: they answer on addresses 1, 2 and 3 at
9600 baud, and the 0x7E protocol gets silence at every baud rate.

    request   <addr> 03 0000 0027 <crc16>      read 39 holding registers
    response  <addr> 03 4E <78 bytes> <crc16>

Modbus CRC-16 (poly 0xA001, init 0xFFFF, appended little-endian), which is a
real checksum that validates -- unlike the 48 V protocol, whose request
checksum was never published.

Register offsets are counted from the start of the whole reply (so the 3-byte
header is included) and follow the community EG4-LL driver at
github.com/tuxntoast/eg4-ll. Two independent cross-checks confirmed them on
the captured replies: the four cell voltages sum to exactly the reported pack
voltage (13.466 V vs 13.46 V), and remaining Ah over total Ah reproduces the
reported SOC exactly (88/400 = 22%, 264/400 = 66%, 168/400 = 42%).

Everything here is a read: function code 0x03 only.
"""

import time

BAUD = 9600
FUNC_READ = 0x03
# Read 39 registers from 0 -- the block holding cells, current, SOC and temps.
READ_BLOCK = b"\x03\x00\x00\x00\x27"
EXPECTED_BYTES = 0x4E
MAX_CELLS = 16

# Offsets into the complete reply.
O_VOLTAGE, O_CURRENT, O_CELLS = 3, 5, 7
O_MOS_TEMP, O_CAP_REMAIN, O_MAX_CHARGE_A = 39, 45, 47
O_SOH, O_SOC = 49, 51
O_STATUS, O_WARNING, O_PROTECTION, O_ERROR = 54, 55, 57, 59
O_CYCLES, O_CAPACITY, O_TEMPS, O_CELL_COUNT = 61, 65, 69, 75


def crc16(data):
    """Modbus CRC-16."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc & 0xFFFF


def build_request(addr):
    if not 0 < addr < 248:
        raise ValueError(f"Modbus address out of range: {addr}")
    body = bytes([addr]) + READ_BLOCK
    return body + crc16(body).to_bytes(2, "little")


def check_crc(frame):
    return crc16(frame[:-2]) == int.from_bytes(frame[-2:], "little")


def parse_status(frame):
    """Decode a reply into a pack reading.

    Raises ValueError on anything malformed so a garbled read is retried
    rather than surfaced as plausible-looking numbers.
    """
    if len(frame) < 5:
        raise ValueError(f"reply too short: {len(frame)} bytes")
    if not check_crc(frame):
        raise ValueError("Modbus CRC mismatch")
    if frame[1] & 0x80:
        raise ValueError(f"Modbus exception {frame[2]:#04x}")
    if frame[1] != FUNC_READ:
        raise ValueError(f"unexpected function {frame[1]:#04x}")
    if frame[2] != EXPECTED_BYTES or len(frame) != frame[2] + 5:
        raise ValueError(f"unexpected payload length {frame[2]}")

    def u16(o):
        return int.from_bytes(frame[o:o + 2], "big")

    def s16(o):
        return int.from_bytes(frame[o:o + 2], "big", signed=True)

    def s8(o):
        return int.from_bytes(frame[o:o + 1], "big", signed=True)

    count = min(u16(O_CELL_COUNT), MAX_CELLS)
    cells = [u16(O_CELLS + i * 2) / 1000.0 for i in range(count)]
    # Sensors 3 and 4 read 0 on these 4-cell packs; only the populated ones
    # are meaningful.
    temps = [t for t in (s8(O_TEMPS + i) for i in range(4)) if t]

    warning = u16(O_WARNING)
    protection = u16(O_PROTECTION)
    error = u16(O_ERROR)
    # The published driver's bit definitions for these words disagree with
    # each other, so rather than invent labels, report that a word is set and
    # let a human open the vendor tool. All three read zero when healthy.
    alarms = []
    for value, name in ((protection, "protection"), (error, "error"),
                        (warning, "warning")):
        if value:
            alarms.append(f"{name} word {value:#06x}")

    reading = {
        "addr": frame[0],
        "online": True,
        "voltage": u16(O_VOLTAGE) / 100.0,
        # Positive is charging; confirmed by remaining-Ah counting upward.
        "current": s16(O_CURRENT) / 100.0,
        "soc": float(u16(O_SOC)),
        "soh": float(u16(O_SOH)),
        "capacity_ah": u16(O_CAP_REMAIN) * 1.0,
        "capacity_full_ah": int.from_bytes(frame[O_CAPACITY:O_CAPACITY + 4],
                                           "big") / 3600 / 1000,
        "cycles": int.from_bytes(frame[O_CYCLES:O_CYCLES + 4], "big"),
        "cells": cells,
        "temps": temps,
        "mos_temp": s16(O_MOS_TEMP),
        "max_charge_a": u16(O_MAX_CHARGE_A),
        "status_hex": f"{frame[O_STATUS]:02X}",
        "alarms": alarms,
    }
    if cells:
        lo, hi = min(cells), max(cells)
        reading["cell_min"] = lo
        reading["cell_max"] = hi
        reading["cell_delta_mv"] = (hi - lo) * 1000.0
    return reading


def read_frame(ser):
    """Read one reply, sized by the Modbus byte-count field."""
    head = ser.read(3)
    if len(head) < 3:
        return None
    if head[1] & 0x80:                      # exception reply: 1 byte + CRC
        return head + ser.read(2)
    frame = head + ser.read(head[2] + 2)
    if len(frame) != head[2] + 5:
        ser.reset_input_buffer()
        raise ValueError(f"truncated reply ({len(frame)} bytes)")
    return frame


class EG4Bus:
    """Polls a chain of EG4 packs on one RS485 bus."""

    id = "12v"
    title = "12 V aux"
    subtitle = "3x EG4 LifePower4 400 Ah in parallel"

    def __init__(self, serial_factory, addresses=(1, 2, 3), gap_s=0.08):
        self._open = serial_factory
        self.addresses = list(addresses)
        self.gap_s = gap_s
        self.ser = None

    def close(self):
        if self.ser is not None:
            try:
                self.ser.close()
            finally:
                self.ser = None

    def _connect(self):
        if self.ser is None:
            self.ser = self._open(baudrate=BAUD, timeout=1.0)
        return self.ser

    def poll(self):
        """One sweep of every configured address.

        A pack that does not answer is reported offline rather than aborting
        the sweep -- with three packs on one bus, one silent unit must not
        hide the other two.
        """
        ser = self._connect()
        packs, raw = [], []
        for addr in self.addresses:
            try:
                ser.reset_input_buffer()
                ser.write(build_request(addr))
                ser.flush()
                frame = read_frame(ser)
                if frame is None:
                    raise ValueError("no reply")
                reading = parse_status(frame)
                raw.append(f"addr {addr} <- {frame.hex()}")
            except (ValueError, OSError) as exc:
                reading = {"addr": addr, "online": False, "error": str(exc)}
                raw.append(f"addr {addr} !! {exc}")
            packs.append(reading)
            time.sleep(self.gap_s)
        return self._summarise(packs), raw

    def _summarise(self, packs):
        live = [p for p in packs if p.get("online")]
        summary = []
        if live:
            # The packs sit in parallel on one 12 V bus: voltage is shared, so
            # average it; current is the total. Bank SOC comes from summed
            # amp-hours rather than averaged percentages, which is the same
            # thing only while every pack is the same size.
            volts = sum(p["voltage"] for p in live) / len(live)
            amps = sum(p["current"] for p in live)
            remaining = sum(p["capacity_ah"] for p in live)
            full = sum(p["capacity_full_ah"] for p in live)
            summary = [
                {"label": "Bus", "value": f"{volts:.2f}", "unit": "V"},
                {"label": "Current", "value": f"{amps:+.1f}", "unit": "A"},
                {"label": "SOC", "unit": "%",
                 "value": f"{(remaining / full * 100) if full else 0:.0f}"},
                {"label": "Remaining", "value": f"{remaining:.0f}", "unit": "Ah"},
            ]
        alarms = [f"pack {p['addr']}: {a}" for p in live for a in p["alarms"]]
        offline = [p["addr"] for p in packs if not p.get("online")]

        if not live:
            state, text = "down", "no packs responding"
        elif alarms:
            state, text = "fault", "; ".join(alarms)
        elif offline:
            state = "warn"
            text = (f"{len(live)} of {len(packs)} responding "
                    f"(silent: {', '.join(str(a) for a in offline)})")
        else:
            state, text = "ok", f"{len(live)} of {len(packs)} responding"

        return {"state": state, "status_text": text, "summary": summary,
                "packs": packs}
