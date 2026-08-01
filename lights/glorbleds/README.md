# glorbleds

Pure-Python (stdlib only, no pip deps) LED control for Glorb — the giant
glowing broom. Drives 136 vertical LED tubes over sACN / E1.31, with a
browser-based control UI and a 3D mock visualizer so you can design patterns
without the car plugged in. Runs the same on Mac and Windows.

## The car

- Rectangular box: **1800 mm wide (X) × 4000 mm long (Y)**.
- **136 tubes** hang vertically down 3 sides: 56 left + 24 rear + 56 right.
  The front-left corner is left open for the driver.
- Each tube is 2.5 m, **40 px/tube** → **5440 pixels** total.
- Tubes are grouped **4 per group → 34 groups**; each Angio chains 3–4 groups
  per data line (2 lines/board) and owns one E1.31 pixel space packed
  **170 px/universe** from its start universe (WLED "Multi" mode).
- Chip **SM16703**, color order **RGB** (see [../led-tubes.md](../led-tubes.md)).

Physical wiring, power, and the tube layout map live one level up in
[../](../): `tube-map.json` / `tube-map.md` / `tube-map.pdf` are the source of
truth for which tube is on which Angio controller line and universe.

## Layout

```
glorbleds/
  __main__.py      CLI: list / solid / tubes / colorcheck / chase / off / serve
  controller.py    tube-map.json -> groups; install-time test patterns (Show)
  e131.py          minimal sACN / E1.31 packet builder + UDP Sender
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
# install-time hardware tests (send straight to the Angios)
python3 -m glorbleds list                      # print the group map
python3 -m glorbleds colorcheck G15            # verify RGB color order
python3 -m glorbleds tubes G15                 # each tube a distinct color
python3 -m glorbleds chase G15                 # comet down the chain
python3 -m glorbleds solid all --color 255,80,0
python3 -m glorbleds off all
python3 -m glorbleds solid C --color 0,0,255 --host 10.0.0.51    # unicast one Angio

# the web control UI + 3D mock visualizer
python3 -m glorbleds serve                     # http://127.0.0.1:8080
python3 -m glorbleds serve --host 0.0.0.0 --port 8080 --fps 30
```

`--dry-run` builds and prints packets instead of transmitting. `--brightness`
defaults to `0.05` (5%) as a safety margin; the Angio boards output realtime
data at full range (force-max-brightness on) now that the tubes run off the
main batteries, so what you send is what the tubes show. Multicast is the default (no device
IPs needed); pass `--host` to unicast, `--iface` to pick the NIC on a
multi-homed host.

## How the pipeline fits together

1. **`CarModel`** ([webui/model.py](webui/model.py)) flattens `tube-map.json`
   into a per-pixel model in **canonical order**: groups in map order, each
   group's tubes in order, each tube's pixels 0..39. Because that order is
   contiguous per Angio, an Angio's pixel space is just a flat slice of the
   frame buffer. For each pixel it precomputes attributes patterns read:
   - `side` — `'L'`/`'B'`/`'R'`
   - `along` — 0..1 down the tube (0 = top, 1 = bottom)
   - `perim` — 0..1 around the perimeter of the whole car
   - `tube_of` — index into `tubes`
2. **Patterns** ([webui/patterns.py](webui/patterns.py)) fill a canonical-order
   RGB `bytearray` at **full range** (0..255). They never apply brightness.
3. **`Engine`** ([webui/engine.py](webui/engine.py)) runs the loop at `fps`:
   render → scale by brightness via a 256-entry LUT (`buf.translate(lut)`, one
   C call) → broadcast to browsers (SSE, base64) and, if hardware is enabled,
   split into per-Angio slices packed 170 px/universe and send over E1.31.
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

Registered in `NAMES` order (from [webui/patterns.py](webui/patterns.py)):

| name | what it does |
|------|--------------|
| `solid` | fill everything with color1 |
| `rainbow` | hue sweep around the perimeter |
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
