"""Minimal SLCAN (Lawicel) reader for the Ewert CANdapter.

The CANdapter presents an FTDI virtual COM port at 921600 baud and speaks the
usual Lawicel command set -- the Orion utility's own canbus/CandapterPort
class sends exactly `\\rC\\r`, `V\\r`, `N\\r`, `S<n>\\r` and `\\rO\\r`, which is
what is used here.

Received frames are CR-terminated ASCII:

    t<3-hex id><dlc><data hex>          11-bit
    x<8-hex id><dlc><data hex>          29-bit  (this firmware answers with
                                        lowercase 'x' where the spec says 'T')

This module only ever opens the channel and reads. It never transmits a CAN
frame, so it cannot disturb the bus the two Orions and the chargers share.

Two firmware quirks worth not rediscovering, both checked against the adapter
on 2026-09-02 (version V010403, serial NC3948B2D):

  * `L` (open listen-only) is answered with BELL -- unsupported. Not opening
    listen-only costs nothing here because nothing is ever transmitted.
  * `Z1` (enable receive timestamps) is silently ignored: no ACK, no BELL, and
    frames still arrive with no timestamp field. So arrival times are not
    available, and anything that needs them has to work another way.
"""

BAUD = 921600
ACK = 0x06
NACK = 0x07

# Lawicel bitrate selectors. The Orion utility offers 125/250/500k and stores
# the choice as a combo index; 250k (S5) is what glorb's profile selects.
BITRATES = {10_000: "S0", 20_000: "S1", 50_000: "S2", 100_000: "S3",
            125_000: "S4", 250_000: "S5", 500_000: "S6", 800_000: "S7",
            1_000_000: "S8"}


class SlcanError(RuntimeError):
    pass


def parse_frame(text):
    """Decode one CR-delimited SLCAN line.

    Returns (can_id, data, extended) or None for lines that are not frames
    (status replies, version strings, ACK/NACK bytes).
    """
    if not text:
        return None
    kind = text[0]
    if kind in "tr":
        id_len, extended = 3, False
    elif kind in "TRxX":
        id_len, extended = 8, True
    else:
        return None
    if len(text) < id_len + 2:
        return None
    try:
        can_id = int(text[1:1 + id_len], 16)
        dlc = int(text[1 + id_len], 16)
    except ValueError:
        return None
    if dlc > 8:
        return None
    body = text[2 + id_len:2 + id_len + dlc * 2]
    if len(body) < dlc * 2:
        return None
    try:
        data = bytes.fromhex(body)
    except ValueError:
        return None
    return can_id, data, extended


class SlcanPort:
    """Opens the CANdapter's CAN channel and streams received frames."""

    def __init__(self, serial_factory, bitrate=250_000):
        if bitrate not in BITRATES:
            raise ValueError(f"unsupported CAN bitrate {bitrate}")
        self._open = serial_factory
        self.bitrate = bitrate
        self.ser = None
        self.version = None
        self.serial_number = None
        self._buf = ""

    def close(self):
        if self.ser is None:
            return
        try:
            self.ser.write(b"C\r")
            self.ser.flush()
        except OSError:
            pass
        finally:
            try:
                self.ser.close()
            finally:
                self.ser = None
                self._buf = ""

    def _command(self, text, settle_s=0.25):
        self.ser.reset_input_buffer()
        self.ser.write(text.encode("ascii"))
        self.ser.flush()
        import time
        time.sleep(settle_s)
        return self.ser.read(4096)

    def open(self):
        if self.ser is not None:
            return
        ser = self._open(baudrate=BAUD, timeout=0.2)
        self.ser = ser
        try:
            # Close first: the adapter keeps its channel open across host
            # restarts, and re-opening an open channel is a NACK.
            self._command("\rC\r")
            ver = self._command("V\r")
            self.version = ver.strip().decode("ascii", "replace") or None
            num = self._command("N\r")
            self.serial_number = num.strip().decode("ascii", "replace") or None
            self._command(BITRATES[self.bitrate] + "\r")
            reply = self._command("O\r")
            if NACK in reply:
                raise SlcanError("CANdapter refused to open the channel")
        except Exception:
            self.close()
            raise
        self._buf = ""

    def drain(self):
        """Every complete frame that arrived since the last call."""
        if self.ser is None:
            raise SlcanError("port is not open")
        waiting = self.ser.in_waiting
        chunk = self.ser.read(waiting) if waiting else b""
        if chunk:
            self._buf += chunk.decode("ascii", "replace")
        frames = []
        while "\r" in self._buf:
            line, self._buf = self._buf.split("\r", 1)
            parsed = parse_frame(line.strip("\x06\x07\n "))
            if parsed is not None:
                frames.append(parsed)
        # A stream of bytes with no CR means we are mis-tuned or the adapter
        # is emitting junk; do not let it grow without bound.
        if len(self._buf) > 4096:
            self._buf = ""
        return frames
