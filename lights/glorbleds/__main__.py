"""CLI: light one group (or an Angio / all) for install-time testing.

Examples (run from the lights/ dir):
  python3 -m glorbleds list
  python3 -m glorbleds colorcheck G15          # verify color order
  python3 -m glorbleds tubes G15               # each tube a distinct color
  python3 -m glorbleds chase G15               # comet down the chain
  python3 -m glorbleds solid G15 --color 255,80,0
  python3 -m glorbleds off all
  python3 -m glorbleds solid A3 --color 0,0,255 --host 10.0.0.51
"""

import argparse
import sys

from .controller import Show, load_map, normalize_group
from .e131 import Sender, iface_for

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
        return show.all_groups()
    if t.startswith("A") and t[1:].isdigit():
        return show.groups_for_angio(t)
    return [show.group(t)]


def main(argv=None):
    p = argparse.ArgumentParser(prog="glorbleds")
    p.add_argument("--map", help="path to tube-map.json")
    p.add_argument("--brightness", type=float, default=0.3,
                   help="0..1 global scale (default 0.3, matches firmware cap)")
    p.add_argument("--color-order", default="RGB")
    p.add_argument("--host", help="unicast to this IP (default: multicast)")
    p.add_argument("--iface", help="local IP of the NIC facing the Angios "
                   "(for multicast on multi-homed hosts)")
    p.add_argument("--source", default="glorb", help="sACN source name")
    p.add_argument("--dry-run", action="store_true",
                   help="build+print packets, don't transmit")

    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="print the group map")
    srv = sub.add_parser("serve", help="launch the web control UI + mock viz")
    srv.add_argument("--host", dest="serve_host", default="127.0.0.1",
                     help="bind address (0.0.0.0 to reach from another machine)")
    srv.add_argument("--port", type=int, default=8080)
    srv.add_argument("--fps", type=float, default=30.0)
    sp = sub.add_parser("solid", help="fill target with one color")
    sp.add_argument("target"); sp.add_argument("--color", type=parse_color,
                                               default=(255, 255, 255))
    sub.add_parser("tubes", help="each tube a distinct color").add_argument("target")
    sub.add_parser("colorcheck", help="cycle R/G/B/W to verify color order").add_argument("target")
    cp = sub.add_parser("chase", help="comet down the chain")
    cp.add_argument("target"); cp.add_argument("--color", type=parse_color,
                                               default=(255, 255, 255))
    cp.add_argument("--fps", type=float, default=40.0)
    sub.add_parser("off", help="blank target").add_argument("target")

    args = p.parse_args(argv)
    gmap = load_map(args.map) if args.map else load_map()

    if args.cmd == "serve":
        from .webui.server import run
        run(gmap, host=args.serve_host, port=args.port, fps=args.fps)
        return 0

    if args.cmd == "list":
        m = gmap["meta"]
        print(f"{m['total_tubes']} tubes, {m['total_groups']} groups, "
              f"{m['pixels_per_tube']} px/tube, order {m['color_order']}")
        for g in gmap["groups"]:
            print(f"  G{g['group']:<2} {g['angio']} p{g['port']}  "
                  f"{g['tubes'][0]}-{g['tubes'][-1]}  univ {g['universe']}")
        return 0

    iface = args.iface
    if not iface and not args.host:
        probe = next((a.get("ip") for a in gmap.get("angios", [])
                      if a.get("ip")), None)
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
        print(f"error: '{args.cmd}' runs on a single group, not "
              f"'{args.target}' ({len(targets)} groups)", file=sys.stderr)
        return 1

    try:
        if args.cmd == "solid":
            for g in targets:
                show.solid(g["group"], args.color)
            print(f"solid {args.color} on {len(targets)} group(s).")
        elif args.cmd == "tubes":
            for g in targets:
                show.per_tube(g["group"])
            print(f"per-tube colors on {len(targets)} group(s).")
        elif args.cmd == "off":
            for g in targets:
                show.off(g["group"])
            print(f"off: {len(targets)} group(s).")
        elif args.cmd == "colorcheck":
            show.colorcheck(targets[0]["group"])
        elif args.cmd == "chase":
            show.chase(targets[0]["group"], fps=args.fps, rgb=args.color)
    finally:
        sender.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
