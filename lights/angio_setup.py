#!/usr/bin/env python3
"""Configure a WLED Angio board uniformly from tube-map.json.

Applies the standard glorb settings for a zone (A-E):
  - LED outputs: output 1 = line 1, output 2 = line 2; lengths/starts and
    GPIO pins from the map (WS281x, RGB). Pins are per-board (ANGIO_PINS
    in tube_map.py): default 13/12, D is plugged 12/13.
  - E1.31 realtime: Multi RGB, start universe from the map, port 5568,
    multicast on, force-max-brightness ON (server owns brightness)
  - Boot defaults: preset 1 (Rain effect / Party palette), ON at 5%
    brightness (bri 13) -- so a board that boots without wifi/packets shows
    something pretty but can't accidentally burn real power
  - Name/mDNS: glorb-wled-<zone lowercase>
  - ABL power limit 30000 mA

Then reboots the board (cfg changes don't fully apply live) and verifies.

Usage (from lights/):
  python3 angio_setup.py D                     # IP from tube-map.json
  python3 angio_setup.py E --ip 192.168.8.123  # IP not in the map yet
  python3 angio_setup.py D --pins 16,17        # non-standard ports
  python3 angio_setup.py D --dry-run           # print cfg, send nothing
"""

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

MAP = Path(__file__).parent / "tube-map.json"
BOOT_BRI = 13          # ~5% of 255
BOOT_PRESET = 1
BOOT_FX = "Rain"       # resolved to ids by name from the board's own lists
BOOT_PAL = "Party"
MAX_POWER_MA = 30000
LED_TYPE = 22          # WS281x
COLOR_ORDER = 1        # WLED enum: 0=GRB, 1=RGB (SM16703 tubes are RGB)
E131_PORT = 5568
DMX_MODE_MULTI_RGB = 4


def http_json(url, payload=None, timeout=8):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json"} if data else {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def build_cfg(angio, pins):
    ins = []
    for line, pin in zip(angio["lines"], pins):
        ins.append({
            "start": line["start_px"], "len": line["pixels"], "pin": [pin],
            "order": COLOR_ORDER, "rev": False, "skip": 0, "type": LED_TYPE,
            "ref": False, "rgbwm": 0, "freq": 0,
        })
    name = f"glorb-wled-{angio['name'].lower()}"
    return {
        "id": {"mdns": name, "name": name},
        "hw": {"led": {"total": angio["pixels"], "maxpwr": MAX_POWER_MA,
                       "ins": ins}},
        "if": {"live": {"en": True, "port": E131_PORT, "mc": True,
                        "maxbri": True,
                        "dmx": {"uni": angio["start_universe"],
                                "mode": DMX_MODE_MULTI_RGB, "addr": 1}}},
        "def": {"ps": BOOT_PRESET, "on": True, "bri": BOOT_BRI},
    }


def resolve_boot_ids(ip):
    """Look up effect/palette ids by name on the board (ids are stable in
    WLED but resolving by name survives any list differences)."""
    effects = http_json(f"http://{ip}/json/eff")
    palettes = http_json(f"http://{ip}/json/pal")
    try:
        return effects.index(BOOT_FX), palettes.index(BOOT_PAL)
    except ValueError:
        sys.exit(f"error: board doesn't have effect {BOOT_FX!r} or "
                 f"palette {BOOT_PAL!r}")


def save_boot_preset(ip, fx, pal):
    state = {
        "on": True, "bri": BOOT_BRI, "mainseg": 0,
        "seg": [{"id": 0, "fx": fx, "pal": pal}],
        "psave": BOOT_PRESET, "n": f"{BOOT_FX} / {BOOT_PAL}",
        "ib": True, "sb": True,   # store brightness + segment bounds
    }
    r = http_json(f"http://{ip}/json/state", state)
    if not r.get("success"):
        sys.exit(f"error: preset save failed: {r}")


def verify(ip, angio, pins, fx, pal):
    cfg = http_json(f"http://{ip}/json/cfg")
    led, live, dflt = cfg["hw"]["led"], cfg["if"]["live"], cfg["def"]
    problems = []

    def chk(what, got, want):
        if got != want:
            problems.append(f"{what}: got {got!r}, want {want!r}")

    chk("total px", led["total"], angio["pixels"])
    chk("n outputs", len(led["ins"]), len(angio["lines"]))
    for i, (line, pin) in enumerate(zip(angio["lines"], pins), start=1):
        out = led["ins"][i - 1]
        chk(f"out{i} start", out["start"], line["start_px"])
        chk(f"out{i} len", out["len"], line["pixels"])
        chk(f"out{i} pin", out["pin"], [pin])
        chk(f"out{i} color order", out["order"], COLOR_ORDER)
    chk("e131 enabled", live["en"], True)
    chk("e131 port", live["port"], E131_PORT)
    chk("multicast", live["mc"], True)
    chk("maxbri", live["maxbri"], True)
    chk("start universe", live["dmx"]["uni"], angio["start_universe"])
    chk("dmx mode", live["dmx"]["mode"], DMX_MODE_MULTI_RGB)
    chk("boot preset", dflt["ps"], BOOT_PRESET)
    chk("boot bri", dflt["bri"], BOOT_BRI)
    presets = http_json(f"http://{ip}/presets.json")
    ps = presets.get(str(BOOT_PRESET), {})
    seg0 = (ps.get("seg") or [{}])[0]
    chk("preset fx", seg0.get("fx"), fx)
    chk("preset palette", seg0.get("pal"), pal)
    chk("preset bri", ps.get("bri"), BOOT_BRI)
    return problems


def main(argv=None):
    p = argparse.ArgumentParser(prog="angio_setup")
    p.add_argument("zone", help="Angio zone letter (A-E)")
    p.add_argument("--ip", help="board IP (default: 'ip' field in tube-map.json)")
    p.add_argument("--pins", help="override GPIO for line 1,line 2 "
                   "(default: per-line 'pin' field in the map)")
    p.add_argument("--map", default=MAP)
    p.add_argument("--dry-run", action="store_true",
                   help="print the cfg payload, don't send")
    args = p.parse_args(argv)

    gmap = json.loads(Path(args.map).read_text())
    zone = args.zone.upper()
    angio = next((a for a in gmap["angios"] if a["name"] == zone), None)
    if angio is None:
        names = ", ".join(a["name"] for a in gmap["angios"])
        sys.exit(f"error: no zone {zone!r} in map (have {names})")

    ip = args.ip or angio.get("ip")
    if not ip:
        sys.exit(f"error: zone {zone} has no IP in the map; pass --ip "
                 f"(and add it to ANGIO_IPS in tube_map.py + re-run it)")
    if args.pins:
        pins = tuple(int(x) for x in args.pins.split(","))
        if len(pins) != len(angio["lines"]):
            sys.exit(f"error: {zone} has {len(angio['lines'])} lines, "
                     f"got {len(pins)} pins")
    else:
        pins = tuple(line["pin"] for line in angio["lines"])

    cfg = build_cfg(angio, pins)
    lines_desc = ", ".join(
        f"out{i} = {ln['pixels']} px @ {ln['start_px']} pin {pin}"
        for i, (ln, pin) in enumerate(zip(angio["lines"], pins), start=1))
    print(f"{zone} ({angio['location']}) @ {ip}: {lines_desc}, "
          f"start universe {angio['start_universe']}, boot bri {BOOT_BRI}, "
          f"boot preset {BOOT_PRESET} = {BOOT_FX} / {BOOT_PAL}")
    if args.dry_run:
        print(json.dumps(cfg, indent=2))
        return 0

    r = http_json(f"http://{ip}/json/cfg", cfg)
    if not r.get("success"):
        sys.exit(f"error: cfg POST failed: {r}")
    print("cfg accepted; rebooting (cfg doesn't fully apply live)...")
    try:
        http_json(f"http://{ip}/json/state", {"rb": True})
    except OSError:
        pass  # board often drops the connection mid-reboot

    for _ in range(30):
        time.sleep(2)
        try:
            info = http_json(f"http://{ip}/json/info", timeout=3)
            break
        except OSError:
            continue
    else:
        sys.exit("error: board didn't come back after reboot")
    print(f"back up: {info.get('name')} (WLED {info.get('ver')}, "
          f"{info['leds']['count']} px)")

    # Save the boot preset after the reboot: WLED writes presets.json to
    # flash asynchronously, so a psave immediately before a reboot is lost.
    fx, pal = resolve_boot_ids(ip)
    save_boot_preset(ip, fx, pal)
    print(f"saved preset {BOOT_PRESET}: {BOOT_FX} (fx {fx}) / "
          f"{BOOT_PAL} (pal {pal})")
    time.sleep(3)   # let the preset hit flash before reading it back

    problems = verify(ip, angio, pins, fx, pal)
    if problems:
        print("VERIFY FAILED:")
        for pr in problems:
            print(f"  - {pr}")
        return 1
    print(f"verified OK. Test with:\n"
          f"  python3 -m glorbleds --host {ip} tubes G{angio['groups'][0]}\n"
          f"  python3 -m glorbleds --host {ip} off {zone}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
