#!/usr/bin/env python3
"""Tesla module battery inventory logger.

Workflow: hook up a module to the Due running TeslaBMS, write an ID on the
battery (B1..B6), then run:

    python3 battery_inventory.py log --id B1

The tool samples cell voltages/temps via the 'i' console command, grabs a
register-dump fingerprint via 'x' (the bq76PL536A has no serial number, so
this is best-effort), assesses health, and appends to battery_log.csv.

    python3 battery_inventory.py report

prints everything logged so far plus a parallel-compatibility check.

Requires: pip install pyserial
"""

import argparse
import csv
import glob
import hashlib
import os
import statistics
import sys
import time
from datetime import datetime, timezone

try:
    import serial
except ImportError:
    serial = None

LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "battery_log.csv")

CSV_FIELDS = [
    "timestamp", "battery_id", "fingerprint", "module_addr", "samples",
    "module_v", "cell1_v", "cell2_v", "cell3_v", "cell4_v", "cell5_v", "cell6_v",
    "cell_delta_mv", "temp1_c", "temp2_c",
    "alerts", "faults", "cov", "cuv", "health", "notes",
]

# thresholds for a resting (no load/charge) Tesla Model S module cell
CELL_MIN_OK = 3.00      # below this: over-discharged, suspect
CELL_MIN_DEAD = 2.50    # below this: likely damaged
CELL_MAX_OK = 4.20      # above this: overcharged
DELTA_WARN_MV = 25.0    # resting imbalance worth noting
DELTA_BAD_MV = 100.0    # serious imbalance / weak cell group
TEMP_SENSOR_DISAGREE_C = 8.0

# module-voltage spread guidance for paralleling
PARALLEL_OK_V = 0.10
PARALLEL_PRECHARGE_V = 0.50


def find_port(explicit):
    if explicit:
        return explicit
    patterns = ["/dev/cu.usbmodem*", "/dev/ttyACM*", "/dev/ttyUSB*"]
    candidates = [p for pat in patterns for p in sorted(glob.glob(pat))]
    if not candidates:
        sys.exit("No serial port found. Plug in the Due or pass --port.")
    if len(candidates) > 1:
        print(f"Multiple ports found, using {candidates[0]} (override with --port): {candidates}")
    return candidates[0]


def read_lines_until(ser, end_marker, timeout=10.0):
    """Collect decoded lines until end_marker or timeout."""
    lines = []
    deadline = time.time() + timeout
    while time.time() < deadline:
        raw = ser.readline()
        if not raw:
            continue
        line = raw.decode("ascii", errors="replace").strip()
        if line:
            lines.append(line)
        if line == end_marker:
            return lines
    return lines


def parse_inv_lines(lines):
    """Return {module_addr: dict} from INV,... lines."""
    out = {}
    for line in lines:
        if not line.startswith("INV,"):
            continue
        parts = line.split(",")
        if len(parts) != 15:
            continue
        try:
            addr = int(parts[1])
            out[addr] = {
                "module_v": float(parts[2]),
                "cells": [float(x) for x in parts[3:9]],
                "temps": [float(parts[9]), float(parts[10])],
                "alerts": int(parts[11], 16),
                "faults": int(parts[12], 16),
                "cov": int(parts[13], 16),
                "cuv": int(parts[14], 16),
            }
        except ValueError:
            continue
    return out


def get_fingerprint(ser):
    ser.reset_input_buffer()
    ser.write(b"x\n")
    lines = read_lines_until(ser, "REGS-END", timeout=15.0)
    blobs = {}
    for line in lines:
        if not line.startswith("REGS,"):
            continue
        parts = line.split(",")
        if len(parts) != 4 or parts[3] == "ERR":
            continue
        blobs.setdefault(int(parts[1]), []).append((int(parts[2], 16), parts[3]))
    fps = {}
    for addr, chunks in blobs.items():
        data = "".join(hexstr for _, hexstr in sorted(chunks))
        fps[addr] = hashlib.sha1(data.encode()).hexdigest()[:12]
    return fps


def sample_inventory(ser, n_samples, interval=1.2):
    """Take n snapshots; return {addr: list of snapshot dicts}."""
    all_samples = {}
    for i in range(n_samples):
        ser.reset_input_buffer()
        ser.write(b"i\n")
        lines = read_lines_until(ser, "INV-END", timeout=10.0)
        snap = parse_inv_lines(lines)
        if not snap:
            print(f"  sample {i + 1}/{n_samples}: no data (retrying)")
            time.sleep(interval)
            ser.write(b"i\n")
            snap = parse_inv_lines(read_lines_until(ser, "INV-END", timeout=10.0))
        for addr, d in snap.items():
            all_samples.setdefault(addr, []).append(d)
        got = ", ".join(
            f"module {a}: {d['module_v']:.3f}V" for a, d in sorted(snap.items())
        ) or "nothing"
        print(f"  sample {i + 1}/{n_samples}: {got}")
        if i < n_samples - 1:
            time.sleep(interval)
    return all_samples


def average_samples(samples):
    """Average a list of snapshot dicts into one."""
    n = len(samples)
    avg = {
        "module_v": sum(s["module_v"] for s in samples) / n,
        "cells": [sum(s["cells"][i] for s in samples) / n for i in range(6)],
        "temps": [sum(s["temps"][i] for s in samples) / n for i in range(2)],
        # status flags: OR them so a transient fault isn't averaged away
        "alerts": 0, "faults": 0, "cov": 0, "cuv": 0,
    }
    for s in samples:
        avg["alerts"] |= s["alerts"]
        avg["faults"] |= s["faults"]
        avg["cov"] |= s["cov"]
        avg["cuv"] |= s["cuv"]
    if n >= 3:
        avg["noise_mv"] = max(
            statistics.pstdev([s["cells"][i] for s in samples]) * 1000.0
            for i in range(6)
        )
    return avg


def assess_health(avg):
    """Return (verdict, [issue strings])."""
    issues = []
    cells = avg["cells"]
    delta_mv = (max(cells) - min(cells)) * 1000.0
    for i, v in enumerate(cells):
        if v < CELL_MIN_DEAD:
            issues.append(f"cell {i + 1} at {v:.3f}V: over-discharged, likely damaged")
        elif v < CELL_MIN_OK:
            issues.append(f"cell {i + 1} at {v:.3f}V: low, suspect")
        elif v > CELL_MAX_OK:
            issues.append(f"cell {i + 1} at {v:.3f}V: overcharged")
    if delta_mv > DELTA_BAD_MV:
        issues.append(f"cell delta {delta_mv:.0f}mV: serious imbalance / weak group")
    elif delta_mv > DELTA_WARN_MV:
        issues.append(f"cell delta {delta_mv:.0f}mV: imbalanced, balance before use")
    if abs(avg["temps"][0] - avg["temps"][1]) > TEMP_SENSOR_DISAGREE_C:
        issues.append(
            f"temp sensors disagree ({avg['temps'][0]:.1f}C vs {avg['temps'][1]:.1f}C)"
        )
    if avg["faults"]:
        issues.append(f"BMB fault register nonzero (0x{avg['faults']:02X})")
    if avg["cov"] or avg["cuv"]:
        issues.append(f"COV/CUV latched (COV=0x{avg['cov']:02X} CUV=0x{avg['cuv']:02X})")

    if any("damaged" in s or "serious" in s or "overcharged" in s for s in issues):
        verdict = "BAD"
    elif issues:
        verdict = "WARN"
    else:
        verdict = "OK"
    return verdict, issues, delta_mv


def cmd_log(args):
    if serial is None:
        sys.exit("pyserial not installed: pip3 install pyserial")
    battery_id = args.id or input("Battery ID written on the module (e.g. B1): ").strip()
    if not battery_id:
        sys.exit("Need a battery ID.")

    port = find_port(args.port)
    print(f"Opening {port} (the Due resets on connect, waiting for boot)...")
    with serial.Serial(port, 115200, timeout=1.0) as ser:
        # sketch has delay(4000) + module enumeration on boot
        time.sleep(7.0)
        ser.reset_input_buffer()

        print("Reading board fingerprint...")
        fps = get_fingerprint(ser)

        print(f"Taking {args.samples} samples...")
        all_samples = sample_inventory(ser, args.samples)

    if not all_samples:
        sys.exit(
            "No modules responded. Check wiring / that the firmware has the "
            "'i' command (reflash TeslaBMS.ino)."
        )

    file_exists = os.path.exists(LOG_PATH)
    rows_written = []
    with open(LOG_PATH, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if not file_exists:
            writer.writeheader()
        multi = len(all_samples) > 1
        for addr, samples in sorted(all_samples.items()):
            avg = average_samples(samples)
            verdict, issues, delta_mv = assess_health(avg)
            label = f"{battery_id}-m{addr}" if multi else battery_id
            row = {
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "battery_id": label,
                "fingerprint": fps.get(addr, ""),
                "module_addr": addr,
                "samples": len(samples),
                "module_v": f"{avg['module_v']:.4f}",
                **{f"cell{i + 1}_v": f"{avg['cells'][i]:.4f}" for i in range(6)},
                "cell_delta_mv": f"{delta_mv:.1f}",
                "temp1_c": f"{avg['temps'][0]:.1f}",
                "temp2_c": f"{avg['temps'][1]:.1f}",
                "alerts": f"0x{avg['alerts']:02X}",
                "faults": f"0x{avg['faults']:02X}",
                "cov": f"0x{avg['cov']:02X}",
                "cuv": f"0x{avg['cuv']:02X}",
                "health": verdict,
                "notes": args.notes or "",
            }
            writer.writerow(row)
            rows_written.append((label, avg, verdict, issues, fps.get(addr, "")))

    for label, avg, verdict, issues, fp in rows_written:
        print(f"\n=== {label} ===")
        print(f"  Module voltage: {avg['module_v']:.3f}V")
        print("  Cells: " + "  ".join(f"{v:.3f}" for v in avg["cells"]))
        delta_mv = (max(avg["cells"]) - min(avg["cells"])) * 1000.0
        print(f"  Cell delta: {delta_mv:.1f}mV")
        print(f"  Temps: {avg['temps'][0]:.1f}C / {avg['temps'][1]:.1f}C")
        if "noise_mv" in avg:
            print(f"  Sample noise (stdev): {avg['noise_mv']:.1f}mV")
        if fp:
            print(f"  Board fingerprint: {fp}")
        print(f"  Health: {verdict}")
        for issue in issues:
            print(f"    - {issue}")
    print(f"\nLogged to {LOG_PATH}")
    print("Run 'battery_inventory.py report' to compare all batteries.")


def load_log():
    if not os.path.exists(LOG_PATH):
        sys.exit(f"No log yet at {LOG_PATH} — log some batteries first.")
    with open(LOG_PATH, newline="") as f:
        return list(csv.DictReader(f))


def cmd_report(_args):
    rows = load_log()
    latest = {}
    history = {}
    for r in rows:
        latest[r["battery_id"]] = r
        history.setdefault(r["battery_id"], []).append(r)

    print(f"{'ID':<8}{'ModuleV':>9}{'Delta mV':>10}{'MinCell':>9}{'MaxCell':>9}"
          f"{'Temp C':>8}  {'Health':<7}{'Fingerprint':<14}{'Last logged'}")
    print("-" * 92)
    for bid in sorted(latest, key=lambda b: float(latest[b]["module_v"]), reverse=True):
        r = latest[bid]
        cells = [float(r[f"cell{i + 1}_v"]) for i in range(6)]
        temp = (float(r["temp1_c"]) + float(r["temp2_c"])) / 2.0
        print(f"{bid:<8}{float(r['module_v']):>9.3f}{float(r['cell_delta_mv']):>10.1f}"
              f"{min(cells):>9.3f}{max(cells):>9.3f}{temp:>8.1f}  "
              f"{r['health']:<7}{r['fingerprint']:<14}{r['timestamp']}")

    # self-discharge drift for batteries with multiple snapshots
    drift_lines = []
    for bid, hist in history.items():
        if len(hist) < 2:
            continue
        first, last = hist[0], hist[-1]
        t0 = datetime.fromisoformat(first["timestamp"].replace("Z", "+00:00"))
        t1 = datetime.fromisoformat(last["timestamp"].replace("Z", "+00:00"))
        days = (t1 - t0).total_seconds() / 86400.0
        if days < 0.5:
            continue
        dv = (float(last["module_v"]) - float(first["module_v"])) * 1000.0 / days
        drift_lines.append(f"  {bid}: {dv:+.1f} mV/day module drift over {days:.1f} days")
    if drift_lines:
        print("\nSelf-discharge (re-log batteries after a week of rest to populate):")
        for line in drift_lines:
            print(line)

    fps = {bid: latest[bid]["fingerprint"] for bid in latest if latest[bid]["fingerprint"]}
    if len(fps) >= 2:
        unique = len(set(fps.values()))
        if unique == len(fps):
            print("\nFingerprints are unique across boards — usable as hardware IDs.")
        else:
            print("\nFingerprints are NOT unique across boards — rely on your written labels.")

    healthy = {b: r for b, r in latest.items() if r["health"] != "BAD"}
    if len(healthy) >= 2:
        volts = {b: float(r["module_v"]) for b, r in healthy.items()}
        spread = max(volts.values()) - min(volts.values())
        hi = max(volts, key=volts.get)
        lo = min(volts, key=volts.get)
        print(f"\nParallel check ({len(healthy)} healthy batteries):")
        print(f"  Module voltage spread: {spread * 1000.0:.0f}mV "
              f"({hi}={volts[hi]:.3f}V high, {lo}={volts[lo]:.3f}V low)")
        if spread <= PARALLEL_OK_V:
            print("  <= 100mV: OK to parallel directly.")
        elif spread <= PARALLEL_PRECHARGE_V:
            print("  100-500mV: parallel through a precharge resistor (or ~10-50 ohm "
                  "power resistor for a few minutes) to limit inrush, or charge the "
                  "low ones up first.")
        else:
            print("  > 500mV: do NOT parallel yet — bring modules to matching "
                  "voltage first (charge low ones / let high ones rest).")
    bad = [b for b, r in latest.items() if r["health"] == "BAD"]
    if bad:
        print(f"\nExcluded from parallel check (health=BAD): {', '.join(sorted(bad))}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_log = sub.add_parser("log", help="sample the connected battery and append to the log")
    p_log.add_argument("--id", help="battery label written on the module (e.g. B1)")
    p_log.add_argument("--port", help="serial port (default: auto-detect)")
    p_log.add_argument("--samples", type=int, default=5, help="snapshots to average (default 5)")
    p_log.add_argument("--notes", help="freeform note stored with this entry")
    p_log.set_defaults(func=cmd_log)

    p_rep = sub.add_parser("report", help="show all logged batteries + parallel compatibility")
    p_rep.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
