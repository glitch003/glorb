#!/usr/bin/env python3
"""Measure how many addressable pixels a tube really has.

Symptom this exists for: the last stretch of each tube shows a different
colour (white, or white blended with the tube's colour). SM16703 defaults ON
with no data, so a white tail means those trailing ICs are never addressed —
the tube has MORE pixels than we are driving.

How it works: drives ONE tube with a deliberately large pixel count, painting
it green with every 10th pixel red. Then:

  * If the white tail is gone, we are now driving at least as many pixels as
    the tube physically has.
  * Count the red marks. Each one is 10 pixels, so `marks * 10` is the pixel
    count, plus however far the green runs past the last mark.

Wires up port/receiver/output A/out1 only; every other string is cleared, so
nothing else lights while you count.

Usage (from lights/):
  python3 k128/measure_pixels.py --host 192.168.8.124 --port 5
  python3 k128/measure_pixels.py --host 192.168.8.124 --port 5 --pixels 128
  python3 k128/measure_pixels.py --host 192.168.8.124 --port 5 --off
"""

import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

import fpp_setup as F
from glorbleds.e131 import Sender, iface_for, resolve_controller, send_span

MARK_EVERY = 10
BASE = (0, 255, 0)      # green body
MARK = (255, 0, 0)      # red every MARK_EVERY-th pixel


def configure(host, port, pixels, brightness, gamma):
    """One string on port/recvA/out1, startChannel 1, `pixels` long."""
    cur = F.fpp_get(host, f"channel/output/{F.OUT_KEY}")
    cape = next((c for c in cur.get("channelOutputs", []) if F._is_cape(c)),
                None)
    if cape is None:
        raise SystemExit("error: no BBB string cape reported by the board")
    n_ports = int(cape.get("outputCount") or 128)
    existing = {int(o["portNumber"]): o for o in cape.get("outputs", [])
                if "portNumber" in o}
    target = F.port_number(port, 1)

    outputs = []
    for pn in range(n_ports):
        entry = dict(existing.get(pn, {}))
        entry["portNumber"] = pn
        entry.setdefault("protocol", F.DEFAULT_PROTOCOL)
        # single dumb/standard receiver: no smart chain config needed for one
        # board at position A, and it keeps the test as simple as possible
        entry["differentialType"] = 0
        for key in F.CHAIN_KEYS.values():
            entry[key] = []
        if pn == target:
            entry["virtualStrings"] = [{
                "description": f"pixel-count ruler ({pixels}px)",
                "startChannel": 1,
                "pixelCount": pixels,
                "groupCount": 0,
                "reverse": 0,
                "colorOrder": "RGB",
                "nullNodes": 0,
                "endNulls": 0,
                "zigZag": 0,
                "brightness": brightness,
                "gamma": gamma,
            }]
        outputs.append(entry)

    cape["enabled"] = 1
    cape["startChannel"] = 1
    cape["channelCount"] = -1
    cape["outputs"] = outputs
    F.fpp_post(host, f"channel/output/{F.OUT_KEY}", cur)
    F.fpp_get(host, "system/fppd/restart", timeout=60.0)
    return target


def main(argv=None):
    data = json.loads((HERE.parent / "tube-map.json").read_text())
    c = data["controller"]

    p = argparse.ArgumentParser(prog="measure_pixels")
    p.add_argument("--host", default=c["ip"] or c["hostname"])
    p.add_argument("--port", type=int, default=5,
                   help="RJ45 port number (5 = jack 17-20)")
    p.add_argument("--pixels", type=int, default=96,
                   help="how many pixels to drive (default 96)")
    p.add_argument("--brightness", type=int, default=5)
    p.add_argument("--gamma", default="1.0")
    p.add_argument("--fps", type=float, default=10.0)
    p.add_argument("--off", action="store_true",
                   help="just blank and exit")
    args = p.parse_args(argv)

    jack = f"{(args.port - 1) * 4 + 1}-{args.port * 4}"
    total_ch = args.pixels * 3

    if args.off:
        sender = Sender(iface=iface_for(args.host))
        send_span(sender, c["start_universe"], bytes(total_ch))
        sender.close()
        print("blanked.")
        return 0

    pn = configure(args.host, args.port, args.pixels,
                   args.brightness, args.gamma)
    print(f"driving {args.pixels} px on port {args.port} (jack {jack}), "
          f"portNumber {pn}, receiver A output 1, at {args.brightness}%")
    time.sleep(6)   # let fppd come back up

    frame = bytearray()
    for i in range(args.pixels):
        frame += bytes(MARK if (i + 1) % MARK_EVERY == 0 else BASE)

    marks = args.pixels // MARK_EVERY
    print(f"pattern: GREEN body, RED every {MARK_EVERY}th pixel "
          f"({marks} red marks over {args.pixels} px)\n")
    print("What to look for on that ONE tube:")
    print("  * white tail GONE  -> we are driving >= the tube's real length")
    print("  * white tail still there -> re-run with a bigger --pixels")
    print(f"  * count the RED marks: each is {MARK_EVERY} px. "
          f"marks x {MARK_EVERY} = pixel count")
    print("    (plus any green running past the last mark)\n")

    iface = iface_for(args.host)
    sender = Sender(iface=iface, source_name="glorb-ruler")
    payload = bytes(frame)
    period = 1.0 / args.fps
    print(f"holding at {args.fps:g} fps (multicast, iface {iface}). "
          f"Ctrl-C to stop.")
    try:
        while True:
            send_span(sender, c["start_universe"], payload)
            time.sleep(period)
    except KeyboardInterrupt:
        send_span(sender, c["start_universe"], bytes(total_ch))
        print("blanked, stopped.")
    finally:
        sender.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
