# glorbdash — the whole car on one screen

One page, one process, one port: the LED controls and live battery monitoring
for all three packs. Built so that while driving you can work the lights and
watch the batteries without switching screens.

```bash
python -m glorbdash serve --host 0.0.0.0
```

Or double-click [start.bat](../start.bat) in the repo root. Opens on
<http://localhost:8080/>, and on `http://<car ip>:8080/` from a phone.

**Close the vendor tools first** — BMS_TOOLS, the Orion BMS utility and the
Arduino serial monitor. Windows gives one program at a time exclusive use of a
COM port. A locked port shows up as a greyed-out meter, and the poller keeps
retrying, so closing the offending app is enough; no restart needed.

## The screen

```
┌─────────────────────────────────────────────────────┐
│ Glorb    [12 V AUX 38%] [24 V LIGHTS 45%] [72 V 51%]│  <- pinned
├──────────────────────────┬──────────────────────────┤
│                          │  Brightness  ─────●───   │
│   car preview            │  Speed       ───●─────   │
│   (3D / 2D)              │  Density     ──●──────   │
│                          │  Color 1     Color 2     │
│                          │  ─────────────────────   │
│                          │  Pattern  [filter…]      │
│                          │  ┌ scrolls on its own ┐  │
│                          │  │ 52 patterns        │  │
│                          │  └────────────────────┘  │
│                          │  ▸ Emoji                 │
│                          │  ▸ Hardware output       │
└──────────────────────────┴──────────────────────────┘
```

**Battery meters are pinned to the top** and stay there while you scroll. Each
shows the pack's state of charge as a big number, a bar, and a colour:

| Colour | SOC | Meaning |
| --- | --- | --- |
| green | ≥ 50 % | carry on |
| amber | 25–50 % | start thinking about it |
| red | < 25 %, or a BMS fault | deal with it now |
| grey | unknown | the adapter is unplugged, the port is busy, or the reading is stale |

Under each meter is the pack's voltage and current, so you can see at a glance
whether it is charging or being drained. Tapping any meter (or **Battery
detail**) opens the full per-pack, per-module, per-cell breakdown.

The 24 V meter is tagged **EST**, because that bank's BMS boards have no
current sensor — its SOC is inferred from resting cell voltage and reads low
under load and high on charge. Hovering the meter says so. The 12 V and 72 V
figures come from their own BMSes and are measured.

**The controls sit above the pattern list.** There are 52 patterns; as a plain
grid they ran well past the bottom of a phone screen and buried the sliders.
Now the sliders come first and never move, and the pattern grid scrolls inside
its own capped box with a filter box above it — type three letters and press
Enter to jump straight to a pattern. Emoji and hardware settings are collapsed
by default since they are set-once, not set-while-driving.

On a phone the whole thing stacks: meters pinned, then sliders, then patterns,
with the car preview last.

## How it fits together

The two subsystems keep living in their own packages and still run standalone:

- [`lights/glorbleds`](../lights/glorbleds/) — the LED engine, patterns, and
  the car renderer (`app.js`)
- [`electrical/glorbmon`](../electrical/glorbmon/) — the three battery
  protocol drivers and their poller threads

`glorbdash` only composes them. It owns the merged page, the battery meters and
the pattern filter; **`app.js` is served straight out of the lights package**
rather than copied, so the car renderer has exactly one home and cannot drift.
A test asserts that no fork of it appears here, and another asserts the merged
HTML still provides every element `app.js` reaches for — that is the contract
between the two.

```
/                    the merged dashboard        (this package)
/style.css /battery.js /ui.js                    (this package)
/app.js              the car renderer            (lights package)

/layout /state /stream /control                  LED engine
/api/status /api/stream /api/raw                 battery hub
```

Battery polling runs on its own threads inside the hub, which swallows each
poller's failures, so a stuck adapter or an unplugged USB cable cannot reach
the LED render loop. Serial reads release the GIL while they wait, so the
render thread keeps its frame pacing.

## Still available separately

Merging did not remove anything. When you want one subsystem on its own — to
debug a protocol, or to run the lights on a machine with no adapters plugged
in — both still work:

```bash
cd lights      && python -m glorbleds serve --host 0.0.0.0   # port 8080
cd electrical  && python -m glorbmon  serve --host 0.0.0.0   # port 8081
cd electrical  && python -m glorbmon probe 72v --raw         # one system, terminal
```

Don't run a standalone alongside the combined dashboard: they would fight over
the same COM ports and the same 8080.

## Tests

```bash
python -m unittest discover -s tests -v        # from the repo root
```

18 tests covering the merge itself. The subsystems have their own suites
(`lights/tests`, 73 tests; `electrical/tests`, 80 tests).
