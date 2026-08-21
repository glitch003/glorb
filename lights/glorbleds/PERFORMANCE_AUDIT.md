# glorbleds performance and visual audit

Audit date: 2026-08-01. Target map: 136 tubes × 40 RGB pixels = 5,440 pixels.
All measurements below were made with CPython 3.11 on **a laptop**. They are
repeatable with:

> **Measured on the real BeagleBone 2026-08-21 — see
> [the section below](#beaglebone-measurements-2026-08-21). Verdict: the engine
> cannot run on the K128D.** It is 30–90× slower than this laptop, not the
> 5–10× estimated. The laptop numbers in this document remain valid for a
> laptop or Pi host.
>
> The wire/universe figures were also measured against 34 universes; the flat
> single-controller map now sends 32.

```bash
cd lights
python3 -m unittest discover -s tests -v
python3 -m glorbleds.benchmark --frames 120 --fps 30
python3 -m glorbleds.benchmark --frames 120 --fps 60
python3 -m glorbleds.benchmark --frames 120 --fps 30 \
  --udp-host 127.0.0.1 --udp-frames 1000
```

## Executive result

The 30 FPS default has ample host and wired-network headroom. The slowest
pattern (`disco`) averaged 7.69 ms and had a 7.85 ms p95 render time against a
33.33 ms frame budget. A loopback UDP run that built and sent 34,000 real E1.31
packets measured 0.411 ms/frame mean and 0.424 ms/frame p95 for snapshotting,
physical-order conversion, packet building, and the complete 34-packet burst.
Rendering plus measured output work therefore remains far below the
30 FPS budget on the audit host.

Do **not** raise the production default to 60 FPS without a controller/LED bench
test. **This ceiling changed for the better:** with one data line per tube the
longest output is now a single 40-px tube, which serializes in about 1.2 ms at
the usual ~30 microseconds/pixel wire rate, instead of the 640-px / 19.2 ms
chains the Angio build ran. The per-port budget is Kulp's 800 px at 40 fps,
shared across a port's receiver chain, and our busiest port carries 640 px.
The output wire is no longer the limiting factor — **host CPU is**, especially
on the BeagleBone.

## Frame and wire budget

- Canonical frame: 16,320 RGB bytes.
- One flat controller span: 5,440 px / 170 px = **32 E1.31 universes/frame**
  (was 34 across five Angio spans).
- E1.31 data packet: 638-byte UDP payload (full 512-channel DMX payload).
- UDP payload/frame: **21,692 bytes**.
- At 30 FPS: **5.206 Mbit/s UDP payload**, about 5.745 Mbit/s including rough
  Ethernet + IPv4/UDP framing.
- At 60 FPS: **10.412 Mbit/s UDP payload** before link framing.
- Measured localhost snapshot, physical-order conversion, packet build, and
  kernel send cost for a complete 34-packet frame: **0.411 ms mean, 0.424 ms
  p95, 0.520 ms max** over 1,000 frames.
- Wired 100 Mbit/s Ethernet has abundant bandwidth. Multicast avoids having to
  duplicate all data per controller.

The sender emits each frame's universes in ascending, contiguous order.
Every universe has an independent monotonically wrapping E1.31 sequence number.
Packet lengths, vectors, property counts, CID width, universe range, splitting,
and sequence behavior now have regression tests.

### Universe synchronization caveat

The sender does not emit E1.31 synchronization packets. The measured 34-packet
burst is under 0.5 ms, much shorter than the ~19.2 ms longest LED-output shift,
so ordinary buffered controllers should receive the next frame before output.
Whether FPP latches a multi-universe span atomically before the PRUs shift it
out is still a hardware fact, not something a host-only test can prove. Test a
hard black/white vertical edge moving across universe boundaries. If a camera
shows tearing, confirm FPP's synchronization behaviour before adding
sync-universe packets; unsupported synchronization can be worse than the
sub-millisecond unsynchronized burst. Sending to localhost on the BeagleBone
makes the burst faster still.

## Buffering and concurrency

A second mutable render buffer is not needed:

1. A single engine thread renders into a private `bytearray`.
2. Brightness scaling uses `bytearray.translate`, which returns a new immutable
   `bytes` snapshot.
3. Browser subscribers receive that immutable snapshot.
4. Serpentine conversion and optional color reordering also return independent
   byte snapshots before packetization.

That is already safe snapshot/double-buffer behavior: neither the browser nor
the UDP sender can observe a half-rendered frame.

The audit did find three real pipeline issues and fixes them:

- **Preview backlog:** a slow SSE client previously kept a two-frame FIFO and
  dropped the newest frame when full. It now has a one-frame latest-value
  mailbox; stale preview data is replaced rather than displayed later.
- **Catch-up bursts:** after an overrun, the frame loop previously replayed
  missed deadlines back-to-back with zero sleep, producing packet bursts and
  animation jumps. It now skips elapsed frame slots, keeps the next future
  monotonic deadline, and reports cumulative `dropped_frames` in `/state`.
- **Socket lifecycle race:** changing hardware settings or stopping could close
  a sender while the engine was transmitting a frame. Sender refresh/close and
  frame transmission are serialized; start is idempotent and stop joins the
  worker before closing resources.

## Pattern timing and performance

`fire`, `sparkle`, `confetti`, and `storm` used per-render decay/update rates.
Changing `--fps` therefore changed their real-time speed and a dropped frame
changed their dynamics. Their updates are now normalized to a 30 Hz reference
simulation. `fire` uses a capped fixed-step accumulator; the other three scale
decay and event rates by elapsed time. Tests compare one second at 30 and 60 FPS.

All registered patterns were also rendered into both a zeroed frame and a
poison-filled frame. Every result matched, proving that pattern switching cannot
leak stale pixels from the previous effect.

Performance classes below are default-parameter means from the 30 FPS audit:
`trivial` < 1 ms, `light` 1–3 ms, `medium` 3–6 ms, `heavy` 6–9 ms.

| Pattern | Cost | Visual audit |
|---|---:|---|
| rainbow | medium | Excellent broad, continuous color bands; very legible on all three sides. |
| aurora | light | Strong ambient curtain with good vertical shaping and layered shimmer. |
| fire | light | Convincing independent flames; fixed-step timing now stays consistent across FPS. |
| plasma | medium | Rich smooth motion and color; one of the better full-surface effects. |
| snake | light | Clear rainbow path; reads best at medium/high density from a side view. |
| meteors | trivial | Crisp diagonal heads/tails and excellent negative space. |
| storm | trivial | Dramatic full-tube ambience/lightning; visually strong, but use with strobe sensitivity in mind. |
| stripes | light | Very crisp diagonal geometry and high contrast; excellent on the U-shaped surface. |
| cubes | medium | Recognizable but intentionally sparse/aliased at 136×40; best above the 5% safety brightness. |
| breathe | trivial | Excellent slow ambient look and essentially free to render. |
| rainbreathe | trivial | Excellent ambient rainbow wash; essentially free. |
| wave | light | Smooth, coherent rolling bands; reliable crowd-scale effect. |
| comet | light | A bright vertical curtain circling the perimeter; clean, though less comet-like from head-on. |
| rain | trivial | Individual falling drops are crisp and spatially easy to read. |
| sparkle | light | Good glints over a dim base; elapsed-time fix prevents FPS-dependent decay. |
| confetti | light | Good colorful pops; elapsed-time fix prevents FPS-dependent decay. |
| broomstroke | light | Strong horizontal sweep down all bristles; simple and highly legible. |
| pacman | light | Dots read clearly; characters are only ~7 tube columns wide and look best at higher safe brightness/density. |
| fireworks | trivial | Attractive sparse bursts; low density may look quiet between launches. |
| matrix | trivial | Excellent match for vertical tubes; bright heads and flickering tails read clearly. |
| disco | heavy (7.69 ms) | Energetic facet/glint effect and still only ~23% of the 30 FPS budget. |
| ekg | light | Recognizable trace with useful thickness control; good perimeter sweep. |
| dvd | trivial | Logo is compact but recognizable; higher density improves long-distance readability. |
| dvd penis | light | Multiple compact sprites remain affordable; silhouettes are clearest at moderate density. |
| police | trivial | Extremely legible red/blue motion; strobing warrants sensitivity caution. |
| butthole | light | Radial wrinkles survive the grid reasonably well; stronger as a close/medium-distance gag. |
| boobs | light | Shaded paired forms are legible at medium density; motion adds readability. |
| penis | light | Tall vertical geometry suits the tubes and reads clearly. |
| twerk | light | Alternating motion helps the paired silhouette read on the sparse grid. |
| poop | medium | Detailed but within budget; pile reads better than tiny flies/stink accents at distance. |
| ufo | light | Saucer and beam are clear; the tiny abductee is a close-view detail. |
| eyes | light | Strong white sclera/iris contrast; one of the best character patterns. |
| sperm | trivial | Motion and bright heads read well; tails are intentionally one-pixel sparse. |
| lava | medium (5.61 ms) | Smooth, high-quality metaballs; second-heaviest effect but ample 30 FPS headroom. |
| hypno | light | High-contrast spirals are clear and compelling; caution for photosensitive viewers. |
| solid | trivial | Correct uniform diagnostic/ambient fill. |
| emoji | content-dependent | Full-color source is good; readability depends on rasterized emoji and bouncer count. |
| broom | light | The actual broom sprite is identifiable and on-theme; side transitions are smooth. |
| mapping | light | Purpose-built diagnostic is clear: head direction and per-group tube colors are unambiguous. |
| off | trivial | Correctly overwrites the entire frame with black. |

## Hardware acceptance checklist

Host-only tests cannot certify the final optical result. Before show deployment:

1. Use wired Ethernet and capture traffic while running `mapping`, `stripes`,
   and a one-column black/white edge at 30 FPS.
2. Film at high shutter speed across each universe boundary; look for
   horizontal/vertical frame tears rather than relying only on the eye.
3. Confirm FPP accepts all 32 configured universes and latches a complete span
   before shifting its outputs.
4. Measure actual output refresh at the port level; do not assume the
   controller's network receive FPS equals LED shift FPS.
4b. **Re-run the whole benchmark on the BeagleBone**, not the laptop, and set
   the show frame rate from those numbers.
5. Run 30–60 minutes on `disco`, `lava`, `plasma`, and `fire`; confirm the UI
   stays at ~30 FPS and `dropped_frames` remains stable.
6. Verify multicast routing/NIC selection on the production host and repeat with
   the production Ethernet switch.
7. Start at the 5% safety brightness. Raise current only after power, thermal,
   and voltage-drop checks; preview attractiveness is not a reason to skip the
   electrical limits.

## BeagleBone measurements (2026-08-21)

Measured on the actual K128D-B host, not estimated: **BeagleBone Black, single
ARMv7 core (AM3358 Cortex-A8), 481 MB RAM, Python 3.11.2, FPP 9.5.3**, via
`python3 -m glorbleds.benchmark` run on the board itself.

**Conclusion: do not run the pattern engine on the BeagleBone.** Run it on a
laptop or a Raspberry Pi and treat the K128D as a pure E1.31 output device, or
pre-render to FSEQ and let FPP play it.

### Why

- **The engine is 30–90x slower here than on the laptop.** `disco` 7.69 ms ->
  **272 ms**. `lava` 5.61 ms -> **178 ms**. `voronoi` -> **667 ms**.
- **E1.31 output alone costs 7.95 ms/frame** (p95 9.0, max 10.3) sending 32
  universes to localhost — **24% of a 30 fps budget before rendering a single
  pixel.**
- The run was fully CPU-bound on one core (`user` 2m23s of `real` 2m25s), and
  `fppd` already takes ~5% idle and needs headroom to feed the PRUs. The web
  UI's SSE broadcast (base64 per frame per client) is *not* in these numbers
  and would come out of the same core.

### What would actually fit

Render room = frame budget minus 7.95 ms of output:

| Target | Frame budget | Render room | Patterns that fit |
|---|---:|---:|---:|
| 30 fps | 33.3 ms | 25.4 ms | **13 / 50** |
| 20 fps | 50.0 ms | 42.0 ms | 16 / 50 |
| 15 fps | 66.7 ms | 58.7 ms | 25 / 50 |
| 10 fps | 100.0 ms | 92.0 ms | 32 / 50 |
| 5 fps | 200.0 ms | 192.0 ms | 42 / 50 |

Sixteen patterns cannot clear 10 fps even given the *entire* frame, including
most of the best-looking ones — their hard ceilings on this CPU:

| pattern | ms | max fps |
|---|---:|---:|
| voronoi | 666.7 | 1.50 |
| ribbons | 659.0 | 1.52 |
| supernova | 483.9 | 2.07 |
| collider | 360.7 | 2.77 |
| scrub | 343.8 | 2.91 |
| reaction | 284.8 | 3.51 |
| disco | 272.4 | 3.67 |
| lasers | 199.6 | 5.01 |
| lava | 178.3 | 5.61 |
| poop | 174.1 | 5.74 |
| plasma | 168.9 | 5.92 |
| cubes | 154.7 | 6.46 |
| rainbow | 118.9 | 8.41 |
| life | 107.4 | 9.31 |
| broomstroke | 103.8 | 9.64 |
| boobs | 101.0 | 9.90 |

Cheap enough to run anywhere (<10 ms on the board): `meteors`, `breathe`,
`rainbreathe`, `fireworks`, `matrix`, `solid`, `emoji`, `rain`, `sperm`,
`storm`, `dvd`, `off`.

### Options

1. **glorbleds on a Pi 4/5 on the car**, E1.31 over a short cat5 to the K128D.
   Keeps every pattern and the live web UI, no laptop at showtime. Closest to
   the original intent.
2. **glorbleds on the laptop** — works today, zero further work, but the
   laptop has to stay awake and on the network.
3. **Pre-render to FSEQ**, let FPP play it from the SD card at near-zero CPU.
   Full pattern fidelity and no extra host at all, but control becomes
   "pick a sequence" rather than live sliders.
4. **A curated subset at 15 fps on the BeagleBone** — possible, but it gives up
   over half the library and leaves no CPU margin. Not recommended.

Reproduce with:

```bash
ssh fpp@<board> 'cd /home/fpp/media/glorb/lights && \
  python3 -m glorbleds.benchmark --frames 20 --fps 30'
ssh fpp@<board> 'cd /home/fpp/media/glorb/lights && \
  python3 -m glorbleds.benchmark --frames 3 --fps 30 \
    --udp-host 127.0.0.1 --udp-frames 150'
```
