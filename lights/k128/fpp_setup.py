#!/usr/bin/env python3
"""Configure the Kulp K128D-B (BeagleBone + FPP) from tube-map.json.

Pushes two things over FPP's HTTP API:

  1. **E1.31 bridge input** (`ci-universes.json`) — the universes glorbleds
     sends: universes 1..32 x 510 channels, landing on FPP channel 1.
  2. **BBB Strings channel outputs** (`co-bbbStrings.json`) — one pixel
     string per tube: 40 px, Forward, RGB, start channel from the map, on
     the right RJ45 port / receiver / output.

Then restarts fppd.

This script is **read-modify-write**: it GETs the board's current config and
only replaces the fields it owns, so whatever the cape's EEPROM reports
(`type`, `subType`, `outputCount`) is preserved rather than guessed.

Usage (from lights/):
  python3 k128/fpp_setup.py --host 192.168.8.x --dry-run   # print, send nothing
  python3 k128/fpp_setup.py --host 192.168.8.x
  python3 k128/fpp_setup.py --host 192.168.8.x --brightness 100   # show mode
  python3 k128/fpp_setup.py --host 192.168.8.x --only-zone C      # subset

Brightness: FPP's per-string brightness is a HARD CEILING on what the tubes
can draw and defaults to 5% here for bench work. glorbleds has its own
brightness that MULTIPLIES with this one -- see README.md ("Brightness: who
owns it") before changing either.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

MAP = Path(__file__).resolve().parent.parent / "tube-map.json"

# FPP API (verified against FalconChristmas/fpp www/api/index.php):
#   GET/POST /api/channel/output/co-bbbStrings   -> co-bbbStrings.json
#   GET/POST /api/channel/output/universeInputs  -> ci-universes.json
#   GET      /api/system/fppd/restart
OUT_KEY = "co-bbbStrings"
IN_KEY = "universeInputs"

# E1.31 input type in ci-universes.json: 0 = multicast, 1 = unicast.
# glorbleds sends multicast by default (no device IP needed).
E131_MULTICAST = 0

# FPP smart-receiver chain positions map to these keys on the same port.
CHAIN_KEYS = {"A": "virtualStrings", "B": "virtualStringsB",
              "C": "virtualStringsC", "D": "virtualStringsD",
              "E": "virtualStringsE", "F": "virtualStringsF"}

# differentialType in co-bbbStrings.json (from PixelString.cpp):
#   0        = standard (dumb) differential receiver
#   1..3     = v1 smart receivers, count = value
#   4..9     = v2 smart receivers, count = value - 3
V2_SMART_BASE = 3

OUTPUTS_PER_RJ45 = 4      # a K128D RJ45 carries 4 differential strings
TUBES_PER_RECEIVER = 4    # pixel outputs on a differential receiver
CHAIN_LETTERS = "ABCDEF"

# The BBB string cape output block. FPP 9.x reports the K128D-B as
# "BBShiftString"; older images used "BBB48String". Match both.
CAPE_TYPES = ("BBShiftString", "BBB48String")
DEFAULT_PROTOCOL = "ws2811"


def _is_cape(block: dict) -> bool:
    t = str(block.get("type", ""))
    return t in CAPE_TYPES or t.startswith("BBB") or t.startswith("BBShift")


def fpp_get(host: str, path: str, timeout: float = 10.0,
            missing_ok: bool = False):
    """GET an FPP API path. With missing_ok, a 404 returns {} instead of
    raising -- ci-universes.json does not exist until it is first written."""
    url = f"http://{host}/api/{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        if missing_ok and e.code == 404:
            return {}
        raise


def fpp_post(host: str, path: str, payload, timeout: float = 30.0):
    url = f"http://{host}/api/{path}"
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def port_number(rj45_port: int, output: int) -> int:
    """Map (RJ45 port, receiver output) -> FPP portNumber (0-based).

    Each RJ45 on the K128D carries 4 differential strings, so RJ45 port p
    owns portNumbers (p-1)*4 .. (p-1)*4+3. A chained smart receiver taps its
    own slice of the SAME string, which is why the chain position selects the
    virtualStrings<letter> key rather than a different portNumber.

    NOTE: confirm this against the board's own BBB Strings page on first
    light -- it is the one part of the mapping inferred from the FPP source
    and Kulp's port math rather than read off a K128D manual (there isn't
    one published). `--verify` prints what the board reports.
    """
    return (rj45_port - 1) * OUTPUTS_PER_RJ45 + (output - 1)


def build_input_universes(data: dict, current: dict, desc: str) -> dict:
    """E1.31 bridge input: one line covering every universe glorbleds sends.

    The starting universe goes in **`id`**, not `universe`. fppd reads
    `u["id"]` (src/e131bridge.cpp: `int universe = u["id"].asInt();`) and then
    allocates `universeCount` universes from there, advancing startChannel by
    channelCount each. Writing only `universe` leaves `id` defaulting to 0, so
    FPP silently allocates universes 0..N-1 and every channel lands one
    universe (510 ch) early -- which is exactly the bug this hit on first
    light. `universe` is mirrored alongside it for the web UI's benefit.
    """
    c = data["controller"]
    entry = {
        "active": 1,
        "description": desc,
        "startChannel": c["start_channel"],
        "type": E131_MULTICAST,
        "id": c["start_universe"],
        "universe": c["start_universe"],
        "universeCount": c["universe_count"],
        "channelCount": c["universe_size"],
        "address": "",
        "priority": 0,
        "monitor": 0,
    }
    out = json.loads(json.dumps(current)) if current else {}
    inputs = out.get("channelInputs") or []
    universes_block = next(
        (b for b in inputs if b.get("type") == "universes"), None)
    if universes_block is None:
        universes_block = {"type": "universes", "enabled": 1, "universes": []}
        inputs.append(universes_block)
    universes_block["enabled"] = 1
    universes_block["universes"] = [entry]
    out["channelInputs"] = inputs
    return out


def bench_relocate(data: dict, port: int, first_label: str,
                   count: int) -> list[dict]:
    """Put a contiguous run of `count` tubes starting at `first_label` onto ONE
    RJ45 port's receiver chain, for bench testing.

    The as-built map already puts each 2x4 board's whole run on its own port,
    so this is only for driving an arbitrary run from a different jack on the
    bench (e.g. 5:L43:14 put board B2's tubes on port 5 during the 2026-08
    bench) -- it packs them A/B/C/... x4 outputs on the given port.

    Each tube KEEPS its real start_channel, so glorbleds patterns address them
    exactly as they will on the car -- only the physical port/receiver/output
    is relocated.
    """
    tubes = data["tubes"]
    idx = next((i for i, t in enumerate(tubes)
                if t["label"].upper() == first_label.upper()), None)
    if idx is None:
        raise SystemExit(f"error: no tube labelled {first_label!r} in the map")
    run = tubes[idx:idx + count]
    if len(run) < count:
        raise SystemExit(
            f"error: only {len(run)} tubes from {first_label} to the end of "
            f"the map, asked for {count}")
    need = -(-count // TUBES_PER_RECEIVER)
    if need > len(CHAIN_LETTERS):
        raise SystemExit(
            f"error: {count} tubes needs {need} chained receivers, max is "
            f"{len(CHAIN_LETTERS)}")
    out = []
    for i, t in enumerate(run):
        t = dict(t)
        t["port"] = port
        # recompute the jack silkscreen for the NEW port, or it keeps the
        # label of the port the tube was planned on
        t["port_silkscreen"] = (f"{(port - 1) * OUTPUTS_PER_RJ45 + 1}-"
                                f"{port * OUTPUTS_PER_RJ45}")
        t["chain_pos"] = i // TUBES_PER_RECEIVER + 1
        t["chain_letter"] = CHAIN_LETTERS[i // TUBES_PER_RECEIVER]
        t["output"] = i % TUBES_PER_RECEIVER + 1
        out.append(t)
    return out


def build_string_outputs(data: dict, current: dict, brightness: int,
                         gamma: str, zones: set | None,
                         bench: list[dict] | None = None) -> tuple[dict, int]:
    """One virtual string per tube, on its port/receiver/output."""
    tubes = bench if bench is not None else [
        t for t in data["tubes"]
        if zones is None or t["zone"] in zones]
    color_order = data["meta"]["color_order"]

    # chain length per RJ45 port -> differentialType for its 4 strings.
    # Only ports we're actually populating: with --only-zone, declaring a
    # smart-receiver chain on an empty port would have FPP sending config
    # packets down a cable with nothing on it.
    chain_len = {}
    for t in tubes:
        chain_len[t["port"]] = max(chain_len.get(t["port"], 0),
                                   t["chain_pos"])

    # portNumber -> {chain key: [virtual strings]}
    by_port: dict[int, dict[str, list]] = {}
    for t in tubes:
        pn = port_number(t["port"], t["output"])
        key = CHAIN_KEYS[t["chain_letter"]]
        by_port.setdefault(pn, {}).setdefault(key, []).append({
            "description": f"{t['label']} (R{t['receiver']}"
                           f"{t['chain_letter']} out{t['output']})",
            "startChannel": t["start_channel"],
            "pixelCount": t["pixels"],
            "groupCount": 0,
            "reverse": 1 if t["direction"] == "reverse" else 0,
            "colorOrder": color_order,
            "nullNodes": 0,
            "endNulls": 0,
            "zigZag": 0,
            "brightness": brightness,
            "gamma": gamma,
        })

    out = json.loads(json.dumps(current)) if current else {}
    cos = out.get("channelOutputs") or []
    cape = next((c for c in cos if _is_cape(c)), None)
    if cape is None:
        raise SystemExit(
            "error: the board reports no BBB string cape in co-bbbStrings.json.\n"
            "Enable the cape once in the FPP UI (Input/Output Setup -> Channel\n"
            "Outputs -> BBB Strings -> 'Enable BBB String Cape', pick the K128D\n"
            "cape type, Save) so its type/subType/outputCount are set, then\n"
            "re-run this script.")

    cape["enabled"] = 1
    cape["startChannel"] = 1
    cape["channelCount"] = -1

    n_ports = int(cape.get("outputCount") or 0)
    if not n_ports:
        n_ports = max(by_port) + 1
        cape["outputCount"] = n_ports
    highest = max(by_port) + 1
    if highest > n_ports:
        raise SystemExit(
            f"error: the map needs FPP portNumber {highest - 1} but the cape "
            f"reports only {n_ports} outputs.\nCheck FIRST_RJ45_PORT / ZONES "
            f"in tube_map.py, or --verify to see what the board reports.")

    # Rebuild every port so a re-run can't leave stale strings behind, but
    # start from whatever the board already had for that port so fields we
    # don't own (protocol, pixelTiming, ...) survive untouched.
    existing = {int(o["portNumber"]): o for o in cape.get("outputs", [])
                if "portNumber" in o}
    outputs = []
    for pn in range(n_ports):
        entry = dict(existing.get(pn, {}))
        entry["portNumber"] = pn
        entry.setdefault("protocol", DEFAULT_PROTOCOL)
        rj45 = pn // OUTPUTS_PER_RJ45 + 1
        n_recv = chain_len.get(rj45, 0)
        if n_recv > 1:
            entry["differentialType"] = V2_SMART_BASE + n_recv
        elif n_recv == 1:
            entry["differentialType"] = 0
        for key in CHAIN_KEYS.values():
            entry[key] = by_port.get(pn, {}).get(key, [])
        outputs.append(entry)
    cape["outputs"] = outputs
    if cape not in cos:
        cos.append(cape)
    out["channelOutputs"] = cos
    return out, len(tubes)


def main(argv=None) -> int:
    data = json.loads(MAP.read_text())
    c = data["controller"]

    p = argparse.ArgumentParser(prog="fpp_setup")
    p.add_argument("--host", default=c["ip"] or c["hostname"],
                   help="FPP address (default from tube-map.json)")
    p.add_argument("--brightness", type=int, default=5,
                   help="FPP per-string brightness %%, a HARD power ceiling "
                        "(default 5 for bench work; 100 for show)")
    p.add_argument("--gamma", default="1.0",
                   help="FPP per-string gamma (default 1.0: glorbleds "
                        "previews linear values, so keep the wire linear)")
    p.add_argument("--only-zone", action="append", metavar="Z",
                   help="limit outputs to zone(s) A-E (repeatable); other "
                        "ports are cleared")
    p.add_argument("--bench", metavar="PORT:TUBE:COUNT",
                   help="bench test: put COUNT tubes starting at TUBE onto "
                        "one RJ45 PORT's receiver chain, e.g. 5:L43:14. "
                        "Channels stay canonical; only the physical "
                        "port/receiver/output moves. Clears all other ports.")
    p.add_argument("--source", default="glorb",
                   help="description written on the E1.31 input line")
    p.add_argument("--dry-run", action="store_true",
                   help="print the configs, send nothing")
    p.add_argument("--verify", action="store_true",
                   help="just report what the board currently has")
    p.add_argument("--no-restart", action="store_true",
                   help="skip the fppd restart")
    args = p.parse_args(argv)

    if not 0 <= args.brightness <= 100:
        p.error("--brightness must be 0..100")
    bench = None
    if args.bench:
        try:
            bport, blabel, bcount = args.bench.split(":")
            bport, bcount = int(bport), int(bcount)
        except ValueError:
            p.error("--bench must look like PORT:TUBE:COUNT, e.g. 5:L43:14")
        if args.only_zone:
            p.error("--bench and --only-zone are mutually exclusive")
        bench = bench_relocate(data, bport, blabel, bcount)

    zones = ({z.upper() for z in args.only_zone} if args.only_zone else None)
    if zones:
        known = {z["name"] for z in data["zones"]}
        bad = zones - known
        if bad:
            p.error(f"unknown zone(s): {', '.join(sorted(bad))}")

    host = args.host
    try:
        cur_out = fpp_get(host, f"channel/output/{OUT_KEY}")
        cur_in = fpp_get(host, f"channel/output/{IN_KEY}",
                         missing_ok=True)
    except (urllib.error.URLError, OSError) as e:
        print(f"error: cannot reach FPP at {host}: {e}", file=sys.stderr)
        print("Is the board powered, imaged with FPP, and on this network? "
              "See k128/README.md.", file=sys.stderr)
        return 1

    if args.verify:
        cape = next((x for x in cur_out.get("channelOutputs", [])
                     if _is_cape(x)), None)
        try:
            info = fpp_get(host, "system/info")
        except OSError:
            info = {}
        print(f"host          {host}")
        print(f"FPP version   {info.get('Version', '?')} "
              f"({info.get('Platform', '?')} {info.get('Variant', '')})")
        print(f"hostname      {info.get('HostName', '?')}")
        if cape is None:
            print("BBB cape      NONE configured — enable it in the FPP UI first")
        else:
            print(f"BBB cape      type={cape.get('type')} "
                  f"subType={cape.get('subType')} "
                  f"outputCount={cape.get('outputCount')} "
                  f"enabled={cape.get('enabled')}")
            used = sum(1 for o in cape.get("outputs", [])
                       for k in CHAIN_KEYS.values() for _ in o.get(k, []))
            print(f"strings set   {used}")
        ins = [u for b in cur_in.get("channelInputs", [])
               if b.get("type") == "universes" for u in b.get("universes", [])]
        print(f"E1.31 inputs  {len(ins)} line(s)")
        for u in ins:
            print(f"  univ {u.get('id', u.get('universe'))}"
                  f"+{u.get('universeCount')} x {u.get('channelCount')} ch "
                  f"-> FPP ch {u.get('startChannel')} "
                  f"(active={u.get('active')}, type={u.get('type')})")
        return 0

    new_in = build_input_universes(data, cur_in, args.source)
    new_out, n_strings = build_string_outputs(
        data, cur_out, args.brightness, args.gamma, zones, bench)

    if bench:
        scope = (f"BENCH port {bench[0]['port']} "
                 f"(jack {bench[0]['port_silkscreen']}) "
                 f"{bench[0]['label']}..{bench[-1]['label']}")
    else:
        scope = f"zones {','.join(sorted(zones))}" if zones else "all zones"
    print(f"{c['model']} @ {host}")
    print(f"  input   universes {c['start_universe']}"
          f"-{c['universes'][-1]} x {c['universe_size']} ch -> FPP ch 1")
    print(f"  outputs {n_strings} strings ({scope}), "
          f"{data['meta']['pixels_per_tube']} px each, "
          f"{data['meta']['color_order']}, Forward, "
          f"brightness {args.brightness}%, gamma {args.gamma}")

    if bench:
        print("  wiring:")
        for t in bench:
            print(f"    recv {t['chain_letter']} out{t['output']} -> "
                  f"{t['label']}  (ch {t['start_channel']})")

    if args.dry_run:
        print("\n--- ci-universes.json ---")
        print(json.dumps(new_in, indent=2))
        print("\n--- co-bbbStrings.json ---")
        print(json.dumps(new_out, indent=2))
        print("\n[dry-run] nothing sent.")
        return 0

    if args.brightness > 20:
        print(f"\n  ! brightness {args.brightness}% — at full white 136 tubes "
              f"draw ~170 A @ 24 V.\n    Make sure you are on the real "
              f"batteries, not a bench supply.")

    fpp_post(host, f"channel/output/{IN_KEY}", new_in)
    print("  wrote ci-universes.json")
    fpp_post(host, f"channel/output/{OUT_KEY}", new_out)
    print("  wrote co-bbbStrings.json")

    if args.no_restart:
        print("  (skipped fppd restart — config is not live yet)")
        return 0
    try:
        fpp_get(host, "system/fppd/restart", timeout=60.0)
        print("  restarted fppd")
    except (urllib.error.URLError, OSError) as e:
        print(f"  warning: restart request failed ({e}); "
              f"restart fppd from the FPP UI", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
