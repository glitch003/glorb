# glorbleds

Pure-Python (stdlib only, no pip deps) LED control for Glorb — the giant
glowing broom. Drives 136 vertical LED tubes over sACN / E1.31, with a
browser-based control UI and a 3D mock visualizer so you can design patterns
without the car plugged in. Runs the same on Mac, Windows, and the
BeagleBone itself.

## The car

- Rectangular box: **1800 mm wide (X) × 4000 mm long (Y)**.
- **136 tubes** hang vertically down 3 sides: 56 left + 24 rear + 56 right.
  The front-left corner is left open for the driver.
- Each tube is 2.5 m, **40 px/tube** → **5440 pixels / 16,320 channels** total.
- **Every tube has its own data line.** Tubes are grouped **4 per receiver →
  34 receivers** on 10 RJ45 ports of a single [Kulp K128D-B](../k128/README.md)
  (BeagleBone + FPP). Nothing is chained, so nothing is reversed in software.
- The whole car is **one flat pixel space**: universes **1–32 × 510 ch** into
  FPP's E1.31 bridge, landing on FPP channel 1. Tube *n* owns channels
  `n × 120 + 1 … n × 120 + 120`.
- Chip **SM16703**, color order **RGB** (see [../led-tubes.md](../led-tubes.md)).

Physical wiring, power, and the tube layout map live one level up in
[../](../): `tube-map.json` / `tube-map.md` / `tube-map.pdf` are the source of
truth for which tube is on which port, receiver, output and channel range.

## Layout

```
glorbleds/
  __main__.py      CLI: list / solid / tubes / colorcheck / chase / off / serve
  controller.py    tube-map.json -> receivers; install-time test patterns (Show)
  e131.py          minimal sACN / E1.31 packet builder + UDP Sender
  benchmark.py     repeatable per-pattern + E1.31 bandwidth benchmark
  PERFORMANCE_AUDIT.md  measured architecture, wire, FPS, and visual audit
  webui/
    server.py      stdlib HTTP server: static UI + SSE frame stream + control POST
    engine.py      animation loop -> browser viz + (optional) hardware
    model.py       flattens tube-map into a per-pixel model (CarModel)
    patterns.py    the pattern library (see below)
    svg_sprite.py  pure-Python SVG -> alpha-mask rasterizer (for sprite patterns)
    static/        index.html + app.js (Canvas viz) + style.css
```

## Running

From the `lights/` directory:

```bash
# install-time hardware tests (send straight to the K128D)
# targets: R15 (receiver), A-E (zone), all
python3 -m glorbleds list                      # print the receiver map
python3 -m glorbleds colorcheck R15            # verify RGB color order
python3 -m glorbleds tubes R15                 # each of its 4 tubes a distinct color
python3 -m glorbleds chase R15                 # comet across its 4 tubes
python3 -m glorbleds solid all --color 255,80,0
python3 -m glorbleds off all
python3 -m glorbleds solid C --color 0,0,255 --host 192.168.8.51   # unicast

# the web control UI + 3D mock visualizer
python3 -m glorbleds serve                     # http://127.0.0.1:8080
python3 -m glorbleds serve --host 0.0.0.0 --port 8080 --fps 30
# Engine output is capped at 60 FPS. 30 is the show rate; re-measure on the
# BeagleBone before trusting it there (see PERFORMANCE_AUDIT.md).

# performance regression checks (stdlib only)
python3 -m glorbleds.benchmark --frames 120 --fps 30
python3 -m glorbleds.benchmark --frames 120 --fps 30 --udp-host 127.0.0.1 --udp-frames 1000
python3 -m unittest discover -s tests -v
```

`--dry-run` builds and prints packets instead of transmitting. Multicast is
the default (no device IP needed); pass `--host` to unicast, `--iface` to pick
the NIC on a multi-homed host.

**`--brightness` defaults to `0.05` (5%) and multiplies with FPP's own
per-string brightness.** Set both to 5% and you get 0.25% — near black. FPP's
is the hard power ceiling; this one is the show dimmer. Pick one owner before
touching either: [../k128/README.md](../k128/README.md#brightness-who-owns-it).

See [PERFORMANCE_AUDIT.md](PERFORMANCE_AUDIT.md) for measured frame/network
budgets, buffering rationale, the per-pattern visual review, and the remaining
K128D hardware acceptance checks.

## How the pipeline fits together

1. **`CarModel`** ([webui/model.py](webui/model.py)) flattens `tube-map.json`
   into a per-pixel model in **canonical order**: tubes in map order, each
   tube's pixels 0..39. That is exactly the channel order FPP is configured
   against, so hardware output is one flat span of the frame buffer. For each
   pixel it precomputes attributes patterns read:
   - `side` — `'L'`/`'B'`/`'R'`
   - `along` — 0..1 down the tube (0 = top, 1 = bottom)
   - `perim` — 0..1 around the perimeter of the whole car
   - `tube_of` — index into `tubes`
2. **Patterns** ([webui/patterns.py](webui/patterns.py)) fill a canonical-order
   RGB `bytearray` at **full range** (0..255). They never apply brightness.
3. **`Engine`** ([webui/engine.py](webui/engine.py)) runs the loop at `fps`:
   render → scale by brightness via a 256-entry LUT (`buf.translate(lut)`, one
   C call) → broadcast to browsers (SSE, base64) and, if hardware is enabled,
   split into 510-channel universes and send over E1.31 to FPP's bridge input.
4. **`server.py`** serves the static UI, streams frames over Server-Sent
   Events (`/stream`), and takes control updates via `POST /control`.
5. **`app.js`** in the browser draws the frame two ways: a **3D car** (drag to
   orbit, hand-rolled perspective projection, depth-based alpha) and a **2D
   flat** unrolled sheet (additive `lighter` blend).

### Important: where brightness happens

Brightness is applied **server-side**, before the frame ever reaches the
browser. At 30% brightness, a white pixel (255) becomes ~76 before it's sent.
So both the hardware and the browser see already-dimmed values — the preview
stays faithful to what the LEDs actually output.

### Display-only gamma (preview realism)

Real LEDs *emit* light and the eye is gamma-curved, so a linearly-scaled value
looks too dark on a monitor — dimmed white reads as grey in the preview even
though the LEDs would look bright white. To fix the *look* without touching the
data, `app.js` runs each pixel through a **display-only gamma LUT**
(`255 · (i/255)^(1/2.2)`) right before drawing. This boosts mid-tones for the
preview only; the hardware still receives the true linear values from the
engine. If preview colors ever look off but hardware looks right, this LUT is
the reason.

## Patterns

Selected built-ins from [webui/patterns.py](webui/patterns.py) (the control UI
always shows the complete live registry):

| name | what it does |
|------|--------------|
| `solid` | fill everything with color1 |
| `rainbow` | hue sweep around the perimeter |
| `scrub` | a giant brushing stroke swishing front-to-back and reversing |
| `ribbons` | intertwined neon strands that flare where they braid together |
| `voronoi` | living stained-glass cells that drift and exchange neighbors |
| `life` | Conway's Game of Life with age color, ghost trails, and fresh seeds |
| `reaction` | evolving reaction-diffusion alien coral and labyrinths |
| `breakout` | a self-playing brick-breaking game with impact sparks |
| `invaders` | an autonomous Space Invaders battle with animated formations and crossfire |
| `supernova` | overlapping stellar shockwaves blooming across the car |
| `lasers` | sweeping two-color laser fans with white-hot intersections |
| `collider` | moving filaments whose intersections emit reactive shockwaves |
| `snake` | rainbow snake along the boustrophedon path |
| `brooms` | broom-stroke motif repeated around the car |
| `pacman` | Pac-Man chomps a row of dots top→bottom, a ghost chasing on his tail |
| `comet` | single comet with a fading tail |
| `wave` | sine wave down the tubes |
| `broomstroke` | sweeping broom stroke |
| `sides` | color each side (L/B/R) independently |
| `plasma` | classic plasma field |
| `fire` | heat palette flames rising up the tubes |
| `rain` | falling droplets |
| `confetti` | random colored sparks |
| `sparkle` | twinkle |
| `broom` | **sprite**: the broom vector swept around the car (auto-loaded, see below) |
| `off` | blank |

Controls exposed in the UI: **pattern**, **brightness**, **speed** (0..1),
**density** (0..1), and **color1 / color2**.

### Adding a pattern

Subclass `Pattern`, set a `name`, implement `render(self, m, p, t, buf)`, and
add an instance to the `_BASE` list at the bottom of `patterns.py`:

- `m` — the `CarModel` (use `m.perim`, `m.along`, `m.side`, `m.total_pixels`).
- `p` — params dict: `p["speed"]`, `p["density"]`, `p["color1"]`, `p["color2"]`.
- `t` — seconds since start (float), for animation.
- `buf` — canonical-order RGB `bytearray` to fill. The byte index for tube
  `ti`, pixel `j` is `(ti * px_per_tube + j) * 3`.

Render full-range (0..255); the engine applies brightness. A common trick is
the **boustrophedon path**: run across a perimeter row, drop down one step, run
back the other way — a snake that spirals top→bottom over the unrolled sheet.
`snake` and `pacman` both use it.

### Sprite patterns (SVG → light)

Drop a monochrome SVG into [../vectors/](../vectors/) and it auto-registers as a
pattern named after the file (e.g. `broom.svg` → `broom`). At startup,
`svg_sprite.load_sprite()` rasterizes the SVG **server-side** (pure Python, no
deps) into a low-res alpha mask, and the `Sprite` pattern stamps that mask onto
the car surface and sweeps it around, tinting color1→color2.

`svg_sprite.py` parses path commands `M/L/H/V/C/S/Q/T/Z/A` (absolute +
relative, with reflected-control tracking for `S`/`T`; arcs approximated by a
line), flattens beziers, then fills with the **nonzero-winding rule** and 2×
supersampling to produce the coverage mask. It reads the `viewBox` (falling
back to the path bounding box) to preserve aspect ratio. Because it runs
server-side, sprites reach the real hardware too, not just the preview.
