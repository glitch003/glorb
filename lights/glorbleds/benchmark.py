"""Reproducible stdlib-only performance audit for the Glorb LED pipeline.

Run from lights/:
    python3 -m glorbleds.benchmark --frames 120 --fps 30
"""

import argparse
import copy
import json
import math
import random
import statistics
import time

from .controller import load_map
from .e131 import Sender, UNIVERSE_BYTES, build_packet, send_span
from .webui.model import CarModel
from .webui.patterns import NAMES, REGISTRY


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, min(len(values) - 1, int(len(values) * fraction) - 1))]


def _benchmark_udp_send(model, host, frames):
    """Time snapshot, wire-order conversion, packet build, and UDP send."""
    if frames < 1:
        raise ValueError("udp_frames must be positive")
    sender = Sender(host=host)
    logical = bytes(model.nbytes)
    lut = bytes(range(256))
    samples = []
    try:
        for _ in range(frames):
            started = time.perf_counter_ns()
            snapshot = logical.translate(lut)
            physical = model.to_physical(snapshot)
            for universe, start, length in model.angio_slices:
                send_span(sender, universe, physical[start:start + length])
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
    finally:
        sender.close()
    packets_per_frame = sum(
        (length + UNIVERSE_BYTES - 1) // UNIVERSE_BYTES
        for _, _, length in model.angio_slices
    )
    return {
        "host": host,
        "frames": frames,
        "packets": frames * packets_per_frame,
        "mean_ms": round(statistics.mean(samples), 3),
        "p95_ms": round(percentile(samples, 0.95), 3),
        "max_ms": round(max(samples), 3),
    }


def run(frames=120, fps=30.0, udp_host=None, udp_frames=1000):
    if frames < 1:
        raise ValueError("frames must be positive")
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be a positive finite number")

    model = CarModel(load_map())
    period_ms = 1000.0 / fps
    pattern_rows = []
    for name in NAMES:
        pattern = copy.deepcopy(REGISTRY[name])
        params = pattern.params()
        buf = bytearray(model.nbytes)
        random.seed(0x474C4F52)
        for i in range(5):
            pattern.render(model, params, i / fps, buf)
        samples = []
        for i in range(frames):
            started = time.perf_counter_ns()
            pattern.render(model, params, (i + 5) / fps, buf)
            samples.append((time.perf_counter_ns() - started) / 1_000_000)
        pattern_rows.append({
            "pattern": name,
            "mean_ms": round(statistics.mean(samples), 3),
            "p95_ms": round(percentile(samples, 0.95), 3),
            "max_ms": round(max(samples), 3),
            "budget_pct": round(statistics.mean(samples) / period_ms * 100, 1),
        })

    packets = sum(
        (length + UNIVERSE_BYTES - 1) // UNIVERSE_BYTES
        for _, _, length in model.angio_slices
    )
    packet_bytes = len(build_packet(1, bytes(UNIVERSE_BYTES), 1, bytes(16)))
    payload_per_frame = packets * packet_bytes
    result = {
        "fps": fps,
        "frame_budget_ms": round(period_ms, 3),
        "pixels": model.total_pixels,
        "rgb_bytes_per_frame": model.nbytes,
        "e131_packets_per_frame": packets,
        "e131_udp_payload_bytes_per_frame": payload_per_frame,
        "e131_udp_payload_mbps": round(payload_per_frame * fps * 8 / 1_000_000, 3),
        "patterns": pattern_rows,
    }
    if udp_host is not None:
        result["udp_send"] = _benchmark_udp_send(model, udp_host, udp_frames)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frames", type=int, default=120)
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--udp-host",
        help="also time complete E1.31 frame sends, e.g. 127.0.0.1",
    )
    parser.add_argument("--udp-frames", type=int, default=1000)
    args = parser.parse_args(argv)
    result = run(args.frames, args.fps, args.udp_host, args.udp_frames)
    if args.json:
        print(json.dumps(result, indent=2))
        return

    print(f"{result['pixels']} pixels | {result['e131_packets_per_frame']} packets/frame | "
          f"{result['e131_udp_payload_mbps']:.3f} Mbit/s UDP payload at {args.fps:g} FPS")
    print(f"{'pattern':<14} {'mean ms':>9} {'p95 ms':>9} {'max ms':>9} {'budget':>8}")
    for row in result["patterns"]:
        print(f"{row['pattern']:<14} {row['mean_ms']:>9.3f} {row['p95_ms']:>9.3f} "
              f"{row['max_ms']:>9.3f} {row['budget_pct']:>7.1f}%")
    if "udp_send" in result:
        udp = result["udp_send"]
        print(f"UDP pipeline -> {udp['host']}: {udp['frames']} frames / "
              f"{udp['packets']} packets, {udp['mean_ms']:.3f} ms mean, "
              f"{udp['p95_ms']:.3f} ms p95, {udp['max_ms']:.3f} ms max")


if __name__ == "__main__":
    main()
