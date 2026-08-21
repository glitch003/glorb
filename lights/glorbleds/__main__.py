"""CLI: light one receiver (or a zone / all) for install-time testing.

A receiver drives 4 tubes, one per output. Targets are `R7` (receiver),
`A`-`E` (zone), or `all`.

Examples (run from the lights/ dir):
  python3 -m glorbleds list
  python3 -m glorbleds colorcheck R15          # verify color order
  python3 -m glorbleds tubes R15               # each tube a distinct color
  python3 -m glorbleds chase R15               # comet across its 4 tubes
  python3 -m glorbleds solid R15 --color 255,80,0
  python3 -m glorbleds off all
  python3 -m glorbleds solid C --color 0,0,255 --host 10.0.0.51
"""

import argparse
import sys

from .controller import Show, load_map, normalize_receiver
from .e131 import Sender, iface_for, resolve_controller

NAMED = {
    "red": (255, 0, 0), "green": (0, 255, 0), "blue": (0, 0, 255),
    "white": (255, 255, 255), "off": (0, 0, 0), "black": (0, 0, 0),
    "orange": (255, 90, 0), "purple": (160, 0, 255),
}


def parse_color(s: str):
    s = s.strip().lower()
    if s in NAMED:
        return NAMED[s]
    parts = s.split(",")
    if len(parts) == 3:
        return tuple(max(0, min(255, int(p))) for p in parts)
    raise argparse.ArgumentTypeError(f"bad color {s!r} (use r,g,b or a name)")


class DrySender:
    """Stand-in sender: prints instead of transmitting (for --dry-run)."""
    def send(self, universe, dmx):
        nonzero = sum(1 for b in dmx if b)
        print(f"  [dry] univ {universe}: {len(dmx)} ch, {nonzero} lit, "
              f"head={tuple(dmx[:6])}")

    def close(self):
        pass


def resolve_targets(show: Show, target: str):
    t = target.upper()
    if t == "ALL":
        return show.all_receivers()
    if len(t) == 1 and t in "ABCDE":
        return show.receivers_for_zone(t)
    return [show.receiver(t)]


def main(argv=None):
    p = argparse.ArgumentParser(prog="glorbleds")
    p.add_argument("--map", help="path to tube-map.json")
    p.add_argument("--brightness", type=float, default=0.05,
                   help="0..1 global scale, applied on top of FPP's "
                        "per-string brightness (default 5%% for bench safety)")
    p.add_argument("--color-order", default="RGB")
    p.add_argument("--host", help="unicast to this IP (default: multicast)")
    p.add_argument("--iface", help="local IP of the NIC facing the K128D "
                   "(for multicast on multi-homed hosts)")
    p.add_argument("--source", default="glorb", help="sACN source name")
    p.add_argument("--dry-run", action="store_true",
                   help="build+print packets, don't transmit")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print the receiver map")
    srv = sub.add_parser("serve", help="launch the web control UI + mock viz")
    srv.add_argument("--host", dest="serve_host", default="127.0.0.1",
                     help="bind address (0.0.0.0 to reach from another machine)")
    srv.add_argument("--port", type=int, default=8080)
    srv.add_argument("--fps", type=float, default=30.0)
    srv.add_argument("--fpp-brightness", type=float, default=10.0,
                     help="FPP's per-string brightness %%, so the temporal "
                          "dither can match the step size FPP quantises to "
                          "(default 10; use 100 when FPP is passthrough)")
    srv.add_argument("--no-dither", action="store_true",
                     help="disable temporal dithering on the hardware path")
    sp = sub.add_parser("solid", help="fill target with one color")
    sp.add_argument("target"); sp.add_argument("--color", type=parse_color,
                                               default=(255, 255, 255))
    sub.add_parser("tubes", help="each tube a distinct color").add_argument("target")
    sub.add_parser("colorcheck", help="cycle R/G/B/W to verify color order").add_argument("target")
    cp = sub.add_parser("chase", help="comet across the 4 tubes")
    cp.add_argument("target"); cp.add_argument("--color", type=parse_color,
                                               default=(255, 255, 255))
    cp.add_argument("--fps", type=float, default=40.0)
    sub.add_parser("off", help="blank target").add_argument("target")

    args = p.parse_args(argv)
    gmap = load_map(args.map) if args.map else load_map()

    if args.cmd == "serve":
        from .webui.server import run
        run(gmap, host=args.serve_host, port=args.port, fps=args.fps,
            fpp_brightness=args.fpp_brightness, dither=not args.no_dither)
        return 0

    if args.cmd == "list":
        m, c = gmap["meta"], gmap["controller"]
        print(f"{m['total_tubes']} tubes, {m['total_receivers']} receivers, "
              f"{m['pixels_per_tube']} px/tube, order {m['color_order']}")
        print(f"{c['model']} @ {c['ip'] or c['hostname']}: "
              f"{c['rj45_ports_used']}/{c['rj45_ports_total']} RJ45 ports, "
              f"universes {c['universes'][0]}-{c['universes'][-1]} "
              f"x {c['universe_size']} ch")
        for r in gmap["receivers"]:
            print(f"  R{r['id']:<2} {r['zone']} port {r['port']}"
                  f"{r['chain_letter']}  "
                  f"{r['tubes'][0]}-{r['tubes'][-1]}  "
                  f"ch {r['start_channel']}-{r['end_channel']}")
        return 0

    iface = args.iface
    if not iface and not args.host:
        probe = resolve_controller(gmap.get("controller", {}))
        iface = iface_for(probe) if probe else None
    sender = DrySender() if args.dry_run else Sender(
        host=args.host, iface=iface, source_name=args.source)
    show = Show(sender, gmap, brightness=args.brightness,
                color_order=args.color_order)

    try:
        targets = resolve_targets(show, args.target)
    except KeyError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    animated = args.cmd in ("colorcheck", "chase")
    if animated and len(targets) != 1:
        print(f"error: '{args.cmd}' runs on a single receiver, not "
              f"'{args.target}' ({len(targets)} receivers)", file=sys.stderr)
        return 1

    try:
        if args.cmd == "solid":
            for r in targets:
                show.solid(r["id"], args.color)
            print(f"solid {args.color} on {len(targets)} receiver(s).")
        elif args.cmd == "tubes":
            for r in targets:
                show.per_tube(r["id"])
            print(f"per-tube colors on {len(targets)} receiver(s).")
        elif args.cmd == "off":
            for r in targets:
                show.off(r["id"])
            print(f"off: {len(targets)} receiver(s).")
        elif args.cmd == "colorcheck":
            show.colorcheck(targets[0]["id"])
        elif args.cmd == "chase":
            show.chase(targets[0]["id"], fps=args.fps, rgb=args.color)
    finally:
        sender.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
