#!/usr/bin/env python3
"""Continuously light a contiguous run of tubes with a repeating 4-color
sequence, to verify a bench-wired receiver chain.

Pairs with `fpp_setup.py --bench PORT:TUBE:COUNT`. Each tube gets one of
RED / GREEN / BLUE / WHITE cycling in map order, so reading the colors off the
tubes tells you three things at once:

  * the tubes light at all (data path + receiver power + shared ground)
  * output order within a receiver (out1..out4)
  * receiver order along the smart-receiver chain (A, B, C, ...)

A correct chain reads R G B W  R G B W  R G B W  R G, in physical order.

FPP expires bridge data after a few seconds, so this holds the frame open
until Ctrl-C rather than sending once.

Usage (from lights/):
  python3 k128/bench_tubes.py L43 14
  python3 k128/bench_tubes.py L43 14 --host 192.168.8.124   # unicast
  python3 k128/bench_tubes.py L43 14 --solid 0,0,255        # one color instead
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from glorbleds.e131 import Sender, iface_for, resolve_controller, send_span

MAP = Path(__file__).resolve().parent.parent / "tube-map.json"

CYCLE = [("RED", (255, 0, 0)), ("GREEN", (0, 255, 0)),
         ("BLUE", (0, 0, 255)), ("WHITE", (255, 255, 255))]


def parse_color(s):
    parts = s.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("--solid wants r,g,b")
    return tuple(max(0, min(255, int(p))) for p in parts)


def main(argv=None):
    p = argparse.ArgumentParser(prog="bench_tubes")
    p.add_argument("first", help="first tube label, e.g. L43")
    p.add_argument("count", type=int, help="how many tubes")
    p.add_argument("--host", help="unicast target (default: multicast)")
    p.add_argument("--iface", help="local IP of the NIC facing the controller")
    p.add_argument("--solid", type=parse_color,
                   help="one color on every tube instead of the 4-color cycle")
    p.add_argument("--fps", type=float, default=10.0,
                   help="resend rate; just has to beat FPP's bridge timeout")
    args = p.parse_args(argv)

    data = json.loads(MAP.read_text())
    tubes = data["tubes"]
    ppt = data["meta"]["pixels_per_tube"]
    total = data["meta"]["total_pixels"]
    start_universe = data["controller"]["start_universe"]

    idx = next((i for i, t in enumerate(tubes)
                if t["label"].upper() == args.first.upper()), None)
    if idx is None:
        print(f"error: no tube labelled {args.first!r}", file=sys.stderr)
        return 1
    run = tubes[idx:idx + args.count]
    if len(run) < args.count:
        print(f"error: only {len(run)} tubes from {args.first} onward",
              file=sys.stderr)
        return 1

    # Whole-car frame, black except the run under test.
    frame = bytearray(total * 3)
    print(f"{len(run)} tubes from {run[0]['label']} to {run[-1]['label']}:")
    for i, t in enumerate(run):
        if args.solid:
            name, rgb = "SOLID", args.solid
        else:
            name, rgb = CYCLE[i % len(CYCLE)]
        off = t["start_channel"] - 1
        frame[off:off + ppt * 3] = bytes(rgb) * ppt
        print(f"  {i + 1:>2}. {t['label']}  recv "
              f"{'ABCDEF'[i // 4]} out{i % 4 + 1}  ->  {name}")

    iface = args.iface
    if not iface and not args.host:
        probe = resolve_controller(data.get("controller", {}))
        iface = iface_for(probe) if probe else None
    sender = Sender(host=args.host, iface=iface, source_name="glorb-bench")
    payload = bytes(frame)
    period = 1.0 / args.fps
    print(f"\nholding frame at {args.fps:g} fps "
          f"({'unicast ' + args.host if args.host else 'multicast'}"
          f"{', iface ' + iface if iface else ''}). Ctrl-C to stop.")
    try:
        while True:
            send_span(sender, start_universe, payload)
            time.sleep(period)
    except KeyboardInterrupt:
        send_span(sender, start_universe, bytes(total * 3))
        print("blanked, stopped.")
    finally:
        if sender.dropped_packets:
            print(f"note: {sender.dropped_packets} packets dropped")
        sender.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
