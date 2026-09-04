"""Command line for the glorb power monitor.

    python -m glorbmon serve --host 0.0.0.0
    python -m glorbmon ports
    python -m glorbmon probe 72v
"""

import argparse
import json
import sys
import time

from . import hub as hub_mod
from . import ports as ports_mod
from . import server


def _overrides(args):
    return {"12v": args.port_12v, "24v": args.port_24v, "72v": args.port_72v}


def cmd_ports(args):
    print("serial ports present:")
    for entry in ports_mod.describe():
        print(f"  {entry['device']:<6} {entry['vid_pid']}  "
              f"{entry['description']}")
    resolved = ports_mod.resolve(_overrides(args))
    print("\nassigned:")
    for system in ("12v", "24v", "72v"):
        print(f"  {system:>4}  {resolved.get(system, '-- not found --')}")
    return 0


def cmd_probe(args):
    resolved = ports_mod.resolve(_overrides(args))
    device = resolved.get(args.system)
    if device is None:
        print(f"no adapter found for {args.system}", file=sys.stderr)
        return 1
    driver = hub_mod.build_driver(args.system, device)
    print(f"probing {args.system} on {device} ... Ctrl-C to stop")
    try:
        while True:
            try:
                payload, raw = driver.poll()
                print(json.dumps(payload, indent=2, default=str))
                if args.raw:
                    for line in raw:
                        print(f"  | {line}")
            except Exception as exc:                # noqa: BLE001
                print(f"  !! {hub_mod.explain(exc)}", file=sys.stderr)
            if args.once:
                return 0
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        driver.close()


def cmd_serve(args):
    monitor = hub_mod.build(_overrides(args), log_path=args.log)
    if not monitor.devices:
        print("warning: no known battery adapters found. The UI will still "
              "start; plug an adapter in and restart.", file=sys.stderr)
    server.run(monitor, host=args.host, port=args.port)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="glorbmon", description="Unified monitoring for glorb's 12 V, "
                                     "24 V and 72 V battery systems.")
    parser.add_argument("--port-12v", help="COM port for the EG4 RS485 chain")
    parser.add_argument("--port-24v", help="COM port for the TeslaBMS Due")
    parser.add_argument("--port-72v", help="COM port for the CANdapter")
    sub = parser.add_subparsers(dest="command", required=True)

    p_serve = sub.add_parser("serve", help="run the web dashboard")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8081)
    p_serve.add_argument("--log", help="append readings to this CSV file")
    p_serve.set_defaults(func=cmd_serve)

    p_ports = sub.add_parser("ports", help="list serial ports and assignments")
    p_ports.set_defaults(func=cmd_ports)

    p_probe = sub.add_parser("probe", help="poll one system on the terminal")
    p_probe.add_argument("system", choices=["12v", "24v", "72v"])
    p_probe.add_argument("--once", action="store_true")
    p_probe.add_argument("--raw", action="store_true",
                         help="also print the raw protocol lines")
    p_probe.add_argument("--interval", type=float, default=2.0)
    p_probe.set_defaults(func=cmd_probe)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
