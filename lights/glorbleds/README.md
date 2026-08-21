# glorbleds

Pure-Python (stdlib only, no pip deps) LED control for Glorb — the giant
glowing broom. Drives 136 vertical LED tubes over DDP (preferred) or
sACN / E1.31, with a browser-based control UI and a 3D mock visualizer so you
can design patterns without the car plugged in. Runs the same on Mac,
Windows, and the BeagleBone itself.

## The car

- Rectangular box: **1800 mm wide (X) × 4000 mm long (Y)**.
- **136 tubes** hang vertically down 3 sides: 56 left + 24 rear + 56 right.
  The front-left corner is left open for the driver.
- Each tube is 2.5 m, **41 px/tube** (measured — one more group than the
  nominal 40) → **5576 pixels / 16,728 channels** total.
- **Every tube has its own data line.** Tubes hang from **10 2×4 boards**,
  each carrying one **SRx4 quad receiver** (14 tubes on the sides, 12 on the
  back) on its own RJ45 port of a single [Kulp K128D-B](../k128/README.md)
  (BeagleBone + FPP). Nothing is chained, so nothing is reversed in software.
- The whole car is **one flat pixel space**: universes **1–33 × 510 ch** into
  FPP's bridge, landing on FPP channel 1. Tube *n* owns channels
  `n × 123 + 1 … n × 123 + 123`.
- Chip **SM16703**, color order **BRG** (measured; datasheets claim RGB —
  FPP reorders on output, everything upstream stays RGB).

Physical wiring, power, and the tube layout map live one level up in
[../](../): `tube-map.json` / `tube-map.md` / `tube-map.pdf` are the source of
truth for which tube is on which port, receiver, output and channel range.

## Layout

```
glorbleds/
  __main__.py      CLI: list / solid / tubes / colorcheck / chase / off / serve
  controller.py    tube-map.json -> receivers; install-time test patterns (Show)
  ddp.py           DDP sender (default transport; PUSH latches each frame)
  e131.py          sACN / E1.31 packet builder + Sender (multicast fallback,
                   sync-packet latch per frame)
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
python3 -m glorbleds serve --host 0.0.0.0 --port 8080 --fps 60
# 60 fps is the default show rate (cap 120). Every pattern is time-based, so
# animation speed never depends on fps — a slow host just drops frames.
# Every pattern renders under 8 ms on a laptop-class CPU (see benchmark.py);
# on Windows use Python 3.11+ for high-resolution sleep timers.

# performance regression checks (stdlib only)
python3 -m glorbleds.benchmark --frames 120 --fps 30
python3 -m glorbleds.benchmark --frames 120 --fps 30 --udp-host 127.0.0.1 --udp-frames 1000
python3 -m unittest discover -s tests -v
```

`--dry-run` builds and prints packets instead of transmitting. The default
transport is **DDP unicast** to the controller from the map (`--host` to
override); if the controller doesn't resolve it falls back to E1.31 multicast
(`--iface` picks the NIC on a multi-homed host, `--protocol` forces one).
Both transports end every frame with a latch (DDP PUSH / E1.31 sync) so fppd
outputs whole frames at *our* pace instead of free-running at 20 fps — the
fix for the post-WLED flicker; see
[../k128/README.md](../k128/README.md#frame-pacing--why-the-first-bring-up-flickered-fixed-2026-08-21).

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
   tube's pixels 0..40. That is exactly the channel order FPP is configured
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
   send to FPP's bridge input (DDP unicast, or E1.31 multicast fallback),
   ending each frame with a latch so fppd outputs it immediately and whole.
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

House rules for smooth motion (2026-08-21 smoothness pass):

- **Animate from `t`, never per-render steps** — stateful simulations
  accumulate real elapsed time (see `Fire`/`Life`), so speed is fps-agnostic.
  `tests/test_patterns.py` enforces this for the decay patterns.
- **Render edges as coverage, not booleans.** A moving shape whose boundary
  is a hard `if` test pops pixel-to-pixel; feather it ~1 pixel with `_cov()`
  (see `DVD`) and it glides.
- **Particles get sub-pixel positions**: split a point's brightness between
  the two pixels it straddles (`matrix`, `meteors`, `fireworks`, `sperm`).
- **Hoist per-frame and per-column work out of the pixel loop.** `perim` is
  constant within a tube, so anything derived only from it can be computed
  136 times instead of 5,576 (`ribbons` got 3.5x faster this way) — but
  `sx` from `_side_unroll` ramps *within* a tube, so it cannot be hoisted.

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
