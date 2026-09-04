"""Command line for the combined glorb dashboard.

    python -m glorbdash serve --host 0.0.0.0
"""

import argparse
import sys

from . import server
from glorbleds.controller import load_map
from glorbmon import hub as hub_mod


def cmd_serve(args):
    gmap = load_map()
    monitor = hub_mod.build(
        {"12v": args.port_12v, "24v": args.port_24v, "72v": args.port_72v},
        log_path=args.log)
    server.run(gmap, monitor, host=args.host, port=args.port, fps=args.fps,
               fpp_brightness=args.fpp_brightness, dither=args.dither,
               subpixel=args.subpixel)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="glorbdash",
        description="Glorb dashboard: LED control and battery monitoring "
                    "on one page.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="run the dashboard")
    p.add_argument("--host", default="127.0.0.1",
                   help="bind address (0.0.0.0 to reach it from a phone)")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--fps", type=float, default=60.0)
    p.add_argument("--fpp-brightness", type=float, default=30.0)
    p.add_argument("--subpixel", type=float, default=1 / 3)
    p.add_argument("--dither", action="store_true")
    p.add_argument("--log", help="append battery readings to this CSV file")
    p.add_argument("--port-12v", help="COM port for the EG4 RS485 chain")
    p.add_argument("--port-24v", help="COM port for the TeslaBMS Due")
    p.add_argument("--port-72v", help="COM port for the CANdapter")
    p.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
