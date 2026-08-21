# Kulp K128D-B — controller bring-up

The K128D-B is the single LED controller for the whole broom: a **BeagleBone
Black/Green + a Kulp cape** running **FPP (Falcon Player)**, driving
**136 tubes on 136 individual data lines** through differential receivers.
It replaces the five WLED Angio-8 boards and the chained-tube topology.

- Product page: <https://kulplights.com/product/k128d-b/>
- Wiring and receiver layout: [../controllers.md](../controllers.md)
- Which tube is on which port/receiver/output: [../tube-map.md](../tube-map.md)
- Closest published manual (same conventions, fewer ports):
  [K16A-B manual](https://kulplights.com/manuals/K16A-B-Manual.pdf) —
  there is no K128D manual published.

## What the board is

| | |
|---|---|
| Ports | 32 RJ45 differential, **4 strings each = 128 strings** |
| Per port | 800 px @ 40 fps, **shared across every receiver chained on it** |
| Receivers | 1 standard differential receiver, **or up to 6 chained v2 SmartReceivers**, 4 pixel outputs each, ≤250 ft of cat5 to the last one |
| Also on board | 2 RS485 outputs (DMX/Renard/LOR/PixelNet), RTC, temp sensors, OLED header, 4 buttons, DAC, optional Si4713 FM header |
| Power | **External 5 V, ≥4 A (20 W)**, into the screw terminals. This is separate from the tubes' 24 V. |
| Software | FPP 6.1 or newer on a microSD card |

We use **10 of the 32 ports** — two per zone A–E, 3–4 receivers chained on
each. That is 34 receivers × 4 outputs = 136 tubes, and the busiest port
carries 640 px, well inside the 800 px budget.

## Step 1 — Wi-Fi needs a USB adapter

**The BeagleBone Black and Green have no onboard Wi-Fi.** Kulp only sells the
cape with Black or Green premounted, and the K16A-B manual is explicit: *"The
K16A-B requires a BeagleBone Black or BeagleBone Green (not the wireless
version)."* So joining the glorb network needs one of:

1. **USB Wi-Fi adapter** (what the manual recommends) — **Edimax Nano**, and
   **2.4 GHz only**: *"It is not recommended to use a 5 GHz Wireless network
   as the transmission distance is less than the 2.4 GHz and not all devices
   support 5 GHz."* Some 5 GHz cards have outright driver problems.
2. **Wired Ethernet to the glorb router** — the BeagleBone has a 10/100
   Ethernet port. This is the better answer for the car: cat5 from the
   BeagleBone to the router is one more cable in a box that is already full
   of cables, and it removes Wi-Fi from the show data path entirely. Dust and
   RF at Black Rock are unkind to 2.4 GHz.

**Recommendation: run it wired, and treat Wi-Fi as the way you get a laptop
or phone onto the same network to reach the web UI.** Clients hit the web app
over Wi-Fi; the controller stays on copper.

### Configuring the network

Once the board boots with an FPP image on the SD card, reach it at
<http://fpp.local/> — or via **USB tethering** with a mini-USB cable, which
works with no network at all and is the fastest way to tell whether it is
booting FPP. The tether address depends on your machine:
**`192.168.6.2` from a Mac or Linux, `192.168.7.2` from Windows.** Use the IP,
not the hostname. If nothing answers, try a different USB cable — charge-only
cables are a known cause.

Then **Status/Control → Network**:

- **Wired:** click `eth0`, choose **Static** (recommended) or DHCP. If static,
  netmask `255.255.255.0`, gateway `192.168.8.1`.
- **Wi-Fi:** set *WIFI Drivers: External*, click `wlan0`, enter the glorb
  **WPA SSID** and **Pre Shared Key**, click **Update Interface**.
- **If you use both `wlan0` and `eth0`, leave the `eth0` gateway blank** —
  two default routes will break name resolution.
- **Host & DNS:** set HostName to **`glorb-k128`** so it answers at
  <http://glorb-k128.local/>. Put that in `CONTROLLER["hostname"]` in
  [../tube_map.py](../tube_map.py) if you change it.
- Do **not** press *Restart Network* until every interface is filled in —
  then press it once and click *Yes*.

Give the board a **DHCP reservation** on the glorb router and record the IP in
`CONTROLLER["ip"]` in [../tube_map.py](../tube_map.py), then re-run
`python3 tube_map.py`. Everything downstream picks it up.

> **Status 2026-08-21: the board is up at `192.168.8.124`** — FPP **9.5.3**,
> BeagleBone Black, cape auto-detected as **K128D-B v1.1**, 128 outputs
> enabled. Zone C is configured and the E1.31 path is verified end to end
> (32/32 universes received, 0 errors). Make that IP a **DHCP reservation**;
> FPP's HostName is still the default `FPP`.
>
> Two things bit us during bring-up, both worth remembering:
>
> - **Not enough power.** The first symptom of an undersized 5 V supply was
>   simply no boot. It needs **≥4 A**; 5 A is comfortable.
> - **Ethernet in the router's WAN port.** This gave a perfectly good link
>   (both LEDs, green flashing) and a **`169.254.x.x` link-local address on
>   the OLED**, which means DHCP failed — the board never appeared in the
>   router's client list. A router only serves DHCP on its **LAN** side. Kulp
>   lists this exact trap in the K16A-B manual. If you see `169.254.*` on the
>   OLED, check which port the cable is in before anything else.

## Step 2 — Push the config

On FPP 9.5 the cape is **auto-detected from its EEPROM** — `capeInfo` reports
`K128D-B` and the BBB String cape comes up already enabled with
`outputCount: 128`, so there is nothing to enable by hand. (If you ever see
`fpp_setup.py` complain that no cape is configured, that is the fallback path:
**Input/Output Setup → Channel Outputs → BBB Strings → *Enable BBB String
Cape*, pick the K128D cape type, Save**, then re-run.)

Then let the map drive everything else:

```bash
cd lights
python3 k128/fpp_setup.py --host glorb-k128.local --verify     # what's there now
python3 k128/fpp_setup.py --host glorb-k128.local --dry-run    # what we'd write
python3 k128/fpp_setup.py --host glorb-k128.local              # write + restart fppd
```

[fpp_setup.py](fpp_setup.py) reads [../tube-map.json](../tube-map.json) and writes:

- **`ci-universes.json`** — E1.31 bridge input, universes **1–32 × 510 ch**
  landing on FPP channel 1, multicast, which is exactly what glorbleds sends.
- **`co-bbbStrings.json`** — 136 pixel strings: 40 px, **Forward**, **RGB**,
  start channel `n × 120 + 1`, on the port/receiver/output from the map, with
  `differentialType` set per port for the smart-receiver chain length.

It is read-modify-write: it preserves whatever the cape reports for `type`,
`subType`, `outputCount`, and each output's `protocol` / `pixelTiming`, instead
of guessing them. (On FPP 9.5 the cape type is **`BBShiftString`**, not the
older `BBB48String`.)

> **Gotcha, found the hard way on first light.** In `ci-universes.json` the
> starting universe goes in **`id`**, *not* `universe` — fppd reads
> `u["id"]` (`src/e131bridge.cpp`). Write only `universe` and `id` defaults to
> **0**, so FPP silently allocates universes `0..31` instead of `1..32`: every
> channel lands one universe (510 ch) early and the last universe is dropped
> entirely. Nothing errors — it just renders wrong. There is a regression test
> for this in [../tests/test_e131.py](../tests/test_e131.py).

### Verifying the data path without any tubes

`GET /api/channel/input/stats` counts received packets per universe, which
proves the whole path independently of wiring:

```bash
curl -s -X DELETE http://<ip>/api/channel/input/stats     # zero the counters
python3 -m glorbleds --brightness 1.0 solid C --color 0,0,255
curl -s http://<ip>/api/channel/input/stats               # expect 32 universes, 0 errors
```

Each entry's `id` is the universe number and `startChannel` is where FPP maps
it — universe 1 must show `startChannel: 1`. If universe 1 shows `511`, you
have the `id` bug above. A burst of `errors` with each run is normal when you
invoke the CLI repeatedly: every process starts a fresh sender whose sequence
numbers restart at 1, which FPP counts as a sequence error. A long-running
`serve` keeps one sender and stays clean.

### Finding the right jack

**The board silkscreens each RJ45 with the *string range* it owns, not a port
number.** Port 1 is the jack marked `1-4`, port 5 is `17-20`. Jacks run
**right-to-left, bottom-to-top in columns of four**, so the rightmost column
is strings 1–16, the next 17–32, and so on. All ten ports we use live in the
three rightmost columns:

| Zone | Ports | Jacks |
|---|---|---|
| A Left-Front | 1, 2 | `1-4`, `5-8` |
| B Left-Back | 3, 4 | `9-12`, `13-16` |
| C Back | 5, 6 | `17-20`, `21-24` |
| D Right-Back | 7, 8 | `25-28`, `29-32` |
| E Right-Front | 9, 10 | `33-36`, `37-40` |

That silkscreen also **confirms the one part of the mapping that was inferred**
rather than documented (there is no published K128D manual): port *p* owns
strings `4p-3 … 4p`, i.e. `portNumber` `(p-1)×4 … (p-1)×4+3`, which is exactly
what `port_number()` in [fpp_setup.py](fpp_setup.py) computes. What remains
unproven until tubes light is only that a **chained** smart receiver taps the
same string via the `virtualStringsB…F` keys — `tubes R15` in step 3 below is
the test for that.

## Brightness: who owns it

There are **two** brightness controls and they **multiply**. Set 5% in both
and you get 0.25% — near-black. Pick an owner:

| | FPP per-string brightness | glorbleds brightness |
|---|---|---|
| Where | `fpp_setup.py --brightness` | web UI slider / `--brightness` |
| Scope | hard ceiling, per string, in the controller | show dimmer, whole car |
| Survives a rogue full-white frame? | **yes** | no |

- **Bench / bring-up (now):** FPP at **5%** (the `fpp_setup.py` default) and
  glorbleds at **100%**. The 5% is then a real power ceiling that no pattern,
  slider or stray sACN source can exceed — which is the point when you are on
  a 200 W supply.
- **Show, on the real batteries:** FPP at **100%**
  (`--brightness 100`) and glorbleds owns the dimmer. Full range on the wire,
  one slider to ride.

The old WLED boards used the same single-owner rule (*force-max-brightness on,
server owns brightness*); FPP's per-string brightness is the equivalent knob.

### Your 200 W bench supply

A tube is 28–30 W/m over 2.5 m, so **~70–75 W per tube at full white**:

| Brightness | W per tube | Tubes on 200 W (24 V, 8.3 A) |
|---:|---:|---:|
| 100% | ~72 | **2.7** |
| 25% | ~18 | ~11 |
| **5%** | **~3.6** | **~55** |

So at full white the bench supply cannot even light **three** tubes, and a set
of 4 would try to pull ~290 W. At 5% a 4-tube receiver draws ~14 W. Do not
raise brightness on the bench supply — raise it once the tubes are on the
battery bus.

## The receiver boards: Falcon/Kulp SRx4 v4.00 — READ THIS FIRST

The bench (and likely the car) uses **SRx4 v4.00 "SmartReceiver × 4"**
boards: one board = **four chained receiver positions in one** (output
groups `ID`, `ID+1`, `ID+2`, `ID+3`, 16 outputs total), with protocol
auto-detect (v1/v2). Three switches on the board decide everything, and two
of them cost us a full day of "flicker" debugging on 2026-08-21:

- **ID Selection rotary (0–F): position `0` is DUMB PASSTHROUGH MODE, and
  it ships from the factory set to 0.** In dumb mode the board forwards the
  *entire* multi-segment smart stream to every tube; the tubes re-latch at
  each 0.15 ms segment gap and strobe through all four segments every frame.
  The symptom is a dim, flickering ghost of whatever is on *other* tubes
  (the bouncing-DVD ghost), fluorescent-style flicker on static content, and
  corrupted pixels at tube bottoms. **The first board in a chain goes at
  `A`** (positions A–D for its four groups), the second at `E`, etc. The
  board reads the dial at power-up — power-cycle after changing it.
- **Termination DIP block ("Middle RCVR" / "Only-Last RCVR"): all four
  switches to "Only/Last"** when the board is the only or last receiver on
  the cat5; "Middle" only for a board with another receiver chained after
  it.
- **Two `Data` RJ45s** — in from the controller, out to the next chained
  board.

FPP-side setting for one SRx4: `differentialType: 7` (v2 smart receivers ×
4), which is what [fpp_setup.py](fpp_setup.py) writes. We tested the v1 (3)
and FalconV5 (13) framings against this board during the debug: v1 renders
garbage and **v5 sprays full-brightness config packets onto the tubes,
bypassing the brightness cap — don't.**

### Color order: the tubes are BRG, not RGB

Measured on the real tubes: sent red showed blue, sent blue showed green —
the strips are wired **BRG** despite SM16703 datasheets claiming RGB.
`meta.color_order` in tube-map.json is now `BRG`; FPP reorders on output and
everything upstream (patterns, preview, CLI) stays RGB. If colors are ever
wrong again, `colorcheck` + fix `color_order` in
[../tube_map.py](../tube_map.py), regenerate, re-run fpp_setup — don't
touch the engine.

## Step 3 — Bench test: board + one receiver + tubes

1. **Power the cape** from its own 5 V ≥4 A supply (screw terminals). The
   BeagleBone can be fed from the cape via the jumper; the cape cannot be fed
   from the BeagleBone.
2. **Power the receiver** — it needs its own **5–13 V** (12 V from a buck off
   the 24 V bus is what we're building), and it is *not* powered over the
   cat5. **Never give it 24 V**; that kills the board. Only **one** of its two
   lug sets needs feeding — they're the same rail — but **check the silkscreen,
   V and G may be swapped end to end.** See
   [../controllers.md](../controllers.md#powering-the-receiver-boards).
3. **Cat5** from the RJ45 jack silkscreened **`17-20`** — that is **port 5**,
   zone C, receiver R15 = tubes `B01`–`B04` (see
   [../tube-map.md](../tube-map.md)). Set the receiver's rotary/DIP address
   for **v2 smart, position A** if it is a SmartReceiver; leave a standard
   receiver alone.
4. **Tubes** on receiver outputs 1–4: land **D and G** on each tube (D through
   the 330–470 Ω resistor at DIN), **leave V unconnected**. DIN at the **top**
   of every tube. No chaining, no flipping.
5. **24 V + shared ground.** The tube ground and the receiver ground must be
   **common** — the data signal has no reference otherwise, and the per-tube
   **G** connection in step 4 is what gives you that. 1000 µF across
   +24 V/GND at each injection point.
6. **Config:** `python3 k128/fpp_setup.py --host <ip> --only-zone C` so only
   zone C's ports are populated while you bench.
7. **Light it** from `lights/`:

```bash
python3 -m glorbleds list                     # confirm R15 = B01-B04
python3 -m glorbleds --brightness 1.0 colorcheck R15   # R/G/B/W - verify RGB order
python3 -m glorbleds --brightness 1.0 tubes R15        # out1=red out2=green out3=blue out4=white
python3 -m glorbleds --brightness 1.0 chase R15        # comet: confirms 40 px and top-to-bottom
python3 -m glorbleds off all
```

`--brightness 1.0` is safe here **only because FPP is capped at 5%**. Check
that assumption with `--verify` before you type it.

### What each test proves

| Test | Passes if | Fails → |
|---|---|---|
| `colorcheck` | printed color matches the tubes | wrong `colorOrder`; these tubes measured **BRG** (see above) |
| `tubes` | out1 red, out2 green, out3 blue, out4 white | receiver outputs patched in the wrong order, or `port_number()` mapping is wrong |
| `chase` | one comet crosses all 4 tubes top→bottom, no gaps | wrong `pixelCount`/`startChannel`, or a tube hung upside down |
| — | no flicker or color corruption at length | SM16703 clocking on the differential receiver; check the 5 V data logic and the series resistor |

Two hardware facts still worth confirming with real tubes, carried over from
the Angio bench notes: that the receiver clocks **SM16703** cleanly, and that
it drives **5 V** data logic (SM16703 wants 5 V; a 3.3 V driver needs a level
shifter at the head of each run).

## Step 4 — Where the pattern engine runs

**Decided 2026-08-21: the engine runs on the glorb Windows laptop, and the
K128D is a dumb E1.31 receiver.** This is the same shape as the Angio build,
which the laptop already ran successfully for a season.

Running it *on* the BeagleBone was tried and rejected — benchmarked on the real
board it is **30–90x too slow**, with only 13 of 50 patterns fitting at 30 fps
and 16 unable to reach 10 fps. Numbers and method:
[../glorbleds/PERFORMANCE_AUDIT.md](../glorbleds/PERFORMANCE_AUDIT.md#beaglebone-measurements-2026-08-21).

```bash
cd lights
./start.sh                    # binds 0.0.0.0:8080 so a phone can reach it
```

glorbleds talks to the board over **DDP unicast** (UDP 4048, no FPP config
needed) when the controller resolves, falling back to E1.31 multicast with a
per-frame sync packet otherwise. Clients just open `http://<laptop-ip>:8080`.

### Frame pacing — why the first bring-up flickered (fixed 2026-08-21)

The move from WLED to FPP brought visible flicker/judder on moving patterns
(the bouncing-DVD kind) that the Angio boards never showed. It was **not**
packet loss (30.03 fps per universe, 0 errors over 30 s), not the smart
receivers, and not quantisation — it was **fppd's bridge-mode output clock**:

- WLED applies E1.31 packets to the LEDs as they arrive — the *sender* paces
  the LEDs.
- fppd only writes bridge data into channel memory; the LEDs are latched by a
  free-running **50 ms timer** (`E131BridgingInterval`, i.e. **20 fps**),
  fully unsynchronised with the sender (`src/channeloutputthread.cpp`).

Against a 30 fps stream that latch beats at ~10 Hz (frames alternately
dropped and doubled) and regularly lands mid-way through the 32-packet frame
burst — a torn frame. That is the "flickery before the logo comes in"
weirdness. An earlier attempt blamed quantisation and added dithering; the
temporal variant strobed at 7.5 Hz and made it worse (it is now opt-in,
spatial-only, and off by default).

The fix is in the sender, and it makes the K128D a truly dumb receiver:
**every frame now ends with a latch signal** that makes fppd output the
completed frame immediately (`ForceChannelOutputNow()`), so glorbleds paces
the LEDs exactly as WLED did:

- **DDP (default):** the frame's last packet carries the **PUSH flag**
  (`glorbleds/ddp.py`). Unicast, ~12 packets/frame instead of 32, and no
  multicast/IGMP in the show path.
- **E1.31 fallback:** a 49-byte **universe-sync packet** after the data
  (`Sender.send_pixels` in `glorbleds/e131.py`) — same latch, still
  multicast, no controller IP needed.

Leave `E131BridgingInterval` at its 50 ms default: it is now only the idle
fallback, and it must stay *slower* than the send rate so the free-run timer
never fires (and never races a frame burst) while frames are flowing.

The trade-off is that the laptop has to stay awake and on the glorb network for
the show. If that ever becomes the weak link, the two escape hatches are a
**Pi 4/5** running the same code, or **pre-rendering to FSEQ** and letting FPP
play it from the SD card with no host at all.

### Brightness, in this arrangement

FPP owns the hard ceiling and glorbleds owns the dimmer, and **they multiply**
— leaving both at 5% gives 0.25% and looks black. On the bench that means
glorbleds at **1.0** and FPP at **5%**:

```bash
curl -X POST http://127.0.0.1:8080/control \
  -H 'Content-Type: application/json' -d '{"brightness":1.0}'
```

See [Brightness: who owns it](#brightness-who-owns-it).
