# glorbmon — one dashboard for all three battery systems

Glorb has three independent battery systems, each with its own BMS speaking its
own protocol over its own USB serial adapter. Before this, monitoring meant
alt-tabbing between three vendor programs — BMS_TOOLS, the Arduino IDE serial
monitor, and the Orion BMS 2 utility. `glorbmon` reads all three at once and
serves a single tabbed web page.

It is **read-only**. Each poller sends the minimum its protocol needs to
produce a reading (a status request, or nothing at all for the Orions) and
never writes configuration, clears faults, or commands balancing.

## Running it

```bash
cd electrical
python -m glorbmon serve --host 0.0.0.0
```

Then open <http://localhost:8081/>, or `http://<car IP>:8081/` from a phone.
Double-clicking [start-monitor.bat](../start-monitor.bat) does the same thing.

Requires `pyserial` (`python -m pip install pyserial`); everything else is
stdlib.

**Close the vendor tools first.** Windows gives one process exclusive use of a
COM port, so BMS_TOOLS, the Orion utility and the Arduino serial monitor each
lock out `glorbmon` (and vice versa). A locked port shows up in the UI as
"port is held by another program" rather than as missing hardware, and the
poller keeps retrying, so closing the offending app is enough — no restart.

Other commands:

```bash
python -m glorbmon ports            # what is plugged in, and what it mapped to
python -m glorbmon probe 72v --raw  # poll one system on the terminal
python -m glorbmon serve --log power.csv
```

## Which adapter is which

Ports are matched by USB VID:PID, not COM number, because Windows renumbers
COM ports when things get replugged into different sockets.

| System | What it watches | Adapter | VID:PID | Seen as |
| --- | --- | --- | --- | --- |
| 12 V aux | 3× EG4 LifePower4 400 Ah, parallel (Modbus IDs 1–3) | CH340 USB-RS485 | `1A86:7523` | COM8 |
| 24 V LED bank | 6× Tesla modules, parallel | Arduino Due programming port | `2341:003D` | COM7 |
| 72 V drive pack | 6× Tesla modules, 3s2p | FTDI inside the Ewert CANdapter | `0403:6015` | COM4 |

These are three separate battery sets, not three views of one pack — the
24 V LED bank and the 72 V drive pack are different Tesla modules.

Override with `--port-12v COM9` etc. Passing an empty string (`--port-12v ""`)
disables that system.

## The protocols

### 12 V — EG4 LifePower4 over RS485, 9600 8N1

These are the **EG4-LL** generation and speak plain **Modbus RTU**. That was
settled empirically: sweeping both candidate protocols across 9600/19200/115200
baud and addresses 0x01–0x10, all three packs answered Modbus at 9600 on
addresses 1, 2 and 3, and the 0x7E "LifePower" framing used by the 48 V units
got silence everywhere.

```
request   <addr> 03 0000 0027 <crc16>      read 39 holding registers
response  <addr> 03 4E <78 bytes> <crc16>
```

Modbus CRC-16 (poly `0xA001`, init `0xFFFF`, appended little-endian) — a real
checksum that validates, unlike the 48 V protocol whose request checksum was
never published.

Register offsets are counted from the start of the whole reply (the 3-byte
header included) and follow the community EG4-LL driver at
[tuxntoast/eg4-ll](https://github.com/tuxntoast/eg4-ll):

| Offset | Field | Scale |
| --- | --- | --- |
| 3 | pack voltage | ÷100 V |
| 5 | current (signed) | ÷100 A, **positive = charging** |
| 7 + 2i | cell *i* voltage | ÷1000 V |
| 39 | MOSFET temperature | °C |
| 45 | remaining capacity | Ah |
| 47 | max charge current | A |
| 49, 51 | SOH, SOC | % |
| 54–60 | status, warning, protection, error words | — |
| 61 | cycle count (u32) | — |
| 65 | full capacity (u32) | ÷3600÷1000 Ah |
| 69–72 | temperature sensors (signed bytes) | °C |
| 75 | cell count | — |

Two independent cross-checks confirm the offsets on the captured replies: the
four cell voltages sum to exactly the reported pack voltage (13.466 V vs
13.46 V), and remaining ÷ full capacity reproduces the reported SOC exactly
(88/400 = 22 %, 264/400 = 66 %, 168/400 = 42 %). Sampling repeatedly also shows
offset 5 fluctuating independently per pack while remaining-Ah climbs, which is
what current does and what an SOC-derived field would not.

The warning/protection/error words are surfaced as hex rather than decoded —
the published driver's bit definitions for them contradict each other, and all
three read zero on healthy packs, so any non-zero value is worth a look in the
vendor tool rather than a guessed label.

### 24 V — TeslaBMS on an Arduino Due, 115200 8N1

The firmware in [../tesla-batteries/TeslaBMS](../tesla-batteries/TeslaBMS)
already has a machine-parsable snapshot command. Sending `i` prints one CSV line
per discovered module, framed by `INV-BEGIN` / `INV-END`:

```
INV,<addr>,<moduleV>,<c1>..<c6>,<t1>,<t2>,<alerts>,<faults>,<cov>,<cuv>
```

with the last four fields in hex. `cov`/`cuv` are per-cell bitmasks, so a fault
names the specific cell. This is used in preference to scraping the human `d`
display, which rounds cell voltages to two decimals.

The one hazard is the port itself: opening it asserts DTR, which **resets the
Due** and costs several seconds of boot. So the connection is opened once and
held for the life of the process, and each poll is just another `i`. (Never open
this port at 1200 baud — on a Due that triggers a flash erase.)

**SOC is estimated, not measured.** These boards read voltage and temperature
only — no current sensor, so no coulomb counting and no real state of charge.
[soc.py](soc.py) interpolates an NCA open-circuit-voltage curve instead
(3.0 V empty, 4.2 V full) and the UI labels the result "SOC (est)". Its one
independent check is a good one: the 72 V drive pack is the same Tesla cell
chemistry and carries a real Orion BMS, and the Orion reported 86 % with those
cells at 4.072 V — the curve returns 86.0 % for that voltage. It also lands
where the bring-up doc expects, reading high-80s against a charger programmed
to ~85 %.

The estimate is only honest at rest: under load the cells sag and it reads low,
on charge they are pushed up and it reads high. Nothing here can detect that,
because there is no current measurement on this bank.

**These six modules are wired in parallel**, so the bank sits at one module's
voltage (~24.4 V). The firmware has no idea how they are wired and its
`printPackSummary()` adds all six together, which reports ~146 V for a 24 V
bank; `summarise()` averages instead and keeps the sum as `series_sum_v` for
comparison with the serial console. The number that actually matters during
bring-up is **module spread** — [../tesla-batteries/README.md](../tesla-batteries/README.md)
wants every module within 0.1 V of the others before they are paralleled — so
that is what the tab leads with.

### 72 V — two Orion BMS 2 units, listened to over CAN

The CANdapter is a Lawicel/SLCAN adapter on a 921600 baud virtual COM port; the
Orion utility's own `canbus/CandapterPort` class sends `\rC\r`, `V\r`, `N\r`,
`S<n>\r`, `\rO\r`, and that is what `slcan.py` sends. Glorb's CAN bus runs at
**250 kbit** (the utility stores `DefaultBaudrate=1`, index 1 of
125/250/500 kBit). This firmware answers received extended frames with a
lowercase `x` prefix where the spec says `T`.

`glorbmon` only ever opens the channel and reads — it never transmits a CAN
frame, so it cannot disturb the bus the Orions and the chargers share. (The
CANdapter firmware rejects SLCAN listen-only mode `L`, so the channel is opened
normally; the guarantee comes from never calling a transmit.)

Two message layouts are decoded, both confirmed against the live bus on
2026-09-02:

**`0x6B1`** — one per unit, the two arriving back-to-back every ~300 ms:

| Bytes | Field | Scale |
| --- | --- | --- |
| 0–1 | Pack DCL | 1 A |
| 2–3 | Pack CCL | 1 A |
| 4 | High temperature | 1 °C |
| 5 | Low temperature | 1 °C |
| 7 | checksum | `(sum(b0..b6) + can_id + dlc) & 0xFF` |

The byte→parameter mapping comes from the utility's saved profile
(`master-1.o2bms`, `customMessage[1]`'s `typeMatrix`) resolved through the
parameter table in the utility's own `canbusParameters.xml`. The checksum
passed on 578 of 578 captured frames, which is what pins the layout down.

**`0x1850F3F3`** — the inter-unit parallel-string message, multiplexed on byte
0. Only fields cross-checked against a second source are decoded:

| Mux | Bytes | Field | Confirmed by |
| --- | --- | --- | --- |
| 0 | 1–2 | DC bus voltage (×0.1 V) | 73.3 V is exactly a 3-series Tesla module stack at 4.07 V/cell, so the ×0.1 scale is right |
| 0 | 3 | relay states | — |
| 0 | 4 | **DOD** (×0.5 %) | bytes 4 and 6 sum to exactly 100 % |
| 0 | 6 | **SOC** (×0.5 %) | same complement, and 86 % is what 4.07 V/cell should read |
| 0 | 5 | second SOC estimate (×0.5 %) | tracks a few % below byte 6; not reported as the pack SOC |
| 1 | 1–2 | average current (×0.1 A, signed) | — |
| 1 | 3–4, 5–6 | DCL, CCL | matched `0x6B1`'s 400 A / 65 A |
| 2 | 3, 4 | low, high temperature | matched `0x6B1`'s 17 °C / 19 °C |

The voltage check is a scale sanity check, not a shared-pack measurement: the
Orions watch the drive pack and the TeslaBMS watches the LED bank. They agree
because both are Tesla modules sitting at a similar state of charge.

**Bytes 4 and 6 are easy to swap**, and doing so reports an 86 %-charged pack
as 14 %. The pack is 18 cells in series (3 modules × 6), so 73.3 V is
4.07 V/cell — around 86 % for Tesla NCA, and nothing like 14 %. If the SOC ever
looks implausible against cell voltage again, this complement is the thing to
re-check. Orion keeps both a coulomb-counted and an adaptive SOC; which of the
two byte 5 carries has not been confirmed, so it is kept as a secondary figure.

The remaining bytes have no confirmed meaning and are surfaced as raw hex
rather than guessed at.

## Two things worth fixing on the Orions

Both surface as notes in the 72 V tab:

1. **Both units transmit on the same CAN ID (`0x6B1`).** Nothing in a frame
   says which unit sent it, so `glorbmon` separates them by the order they
   alternate on the bus, cross-checked against each unit's previous reading
   (they sit a few amps of CCL and about a degree apart, and drift far more
   slowly than that). Arrival timestamps would be the honest way to do this,
   but this CANdapter firmware ignores the SLCAN `Z1` command and the frames
   are read out of a buffer, so real arrival times are not available. The
   result is reliable while the two units read differently, but the A/B labels
   could swap if they ever converge. Giving the second unit a different CAN ID
   in its profile would make them reliable.
2. **Neither unit broadcasts `0x6B0`**, even though the saved profile defines
   it — so pack current, instantaneous voltage and SOC are only available from
   the parallel-string message. Enabling `0x6B0` on both units would give
   proper per-string current and voltage instead of one shared bus figure.

## Layout

```
glorbmon/
  ports.py      adapter discovery by USB VID:PID
  eg4.py        12 V EG4 LifePower4 RS485 driver
  teslabms.py   24 V Arduino Due console driver
  slcan.py      CANdapter transport (open + read only)
  orion.py      72 V Orion CAN frame decoding
  hub.py        one thread per system, reconnect, shared snapshot, CSV log
  server.py     HTTP: dashboard, /api/status, /api/stream (SSE), /api/raw
  static/       the dashboard
```

Each system polls in its own thread with its own reconnect backoff, so a pack
that goes quiet, an adapter that gets unplugged, or a vendor tool that grabs a
COM port only takes out that one tab.

`glorbmon` deliberately runs as its own process on port 8081 rather than inside
the LED server on 8080: serial faults, adapter timeouts and reconnect stalls
have no way to reach the LED render loop, and restarting one never interrupts
the other. The two UIs cross-link in their headers.

## Tests

```bash
cd electrical
python -m unittest discover -s tests -v
```

The parser tests run against byte strings captured from glorb's own hardware,
so they encode the real field layouts rather than an idealised reading of the
protocol docs.
