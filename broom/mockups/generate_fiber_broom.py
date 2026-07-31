#!/usr/bin/env python3
"""Laser-broom variant: mixed bristles — LED tubes + 14 mm side-glow fiber.

Same as generate_laser_broom.py (tall wrapped translucent handle tube, hidden
120 W laser shining up through it), but the bristle curtain alternates:
  - 22 mm addressable LED neon tubes (rainbow chase at night), and
  - between each pair, a 14 mm PMMA side-emitting optical fiber cable —
    half the diameter, glowing one single solid color along its length.

Reads REPLICATE_API_TOKEN from ../../.env. Writes fiberbroom_<src>_<mode>.jpg.
"""

import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
ENV_PATH = os.path.join(REPO_ROOT, ".env")
OUT_DIR = os.path.dirname(__file__)
MODEL = "google/nano-banana-pro"

SOURCES = {
    "corner": os.path.join(REPO_ROOT, "glorb-2023.jpeg"),
    "side":   os.path.join(REPO_ROOT, "glorb-2023-2.jpeg"),
}

# broom body: panels -> glowing LED-tube bristles (kept in every render)
BRISTLES = (
    "This is a boxy two-story art car at Burning Man with a colorful striped "
    "wrap on its side wall panels and an open upper deck with a scaffold-style "
    "railing frame and speakers. Transform it into a giant broom while keeping "
    "the SAME car: keep the boxy two-story chassis, the upper deck and its "
    "metal railing frame, the speakers, the wheels/tires, and the desert playa "
    "ground and background. "
    "REMOVE the colorful striped side wall panels completely and in their place "
    "hang a curtain of vertical glowing strands straight down around the ENTIRE "
    "perimeter, mounted from the upper-deck frame down to just above the "
    "ground, densely and evenly spaced like broom bristles, so the lower body "
    "is a curtain of vertical light strands instead of solid walls. The strands "
    "STRICTLY ALTERNATE between two types: (1) thin ~22 mm addressable LED neon "
    "tubes, and (2) between every pair of tubes, a noticeably THINNER ~14 mm "
    "side-emitting PMMA optical fiber cable — HALF the diameter of the tubes — "
    "that glows evenly along its whole length in ONE single solid color. "
    "The alternating thick/thin, multicolor/solid-color rhythm should be "
    "clearly visible. "
)

# the handle: a fat wrapped translucent tube standing on the deck
HANDLE = (
    "Standing upright on the open upper deck is the broom's HANDLE: a tall "
    "hollow translucent cylindrical tube, about 30 cm in diameter and 16 feet "
    "tall (roughly as tall as the whole car again), mounted vertically. The "
    "tube is wrapped like a vehicle wrap in a solid BROWN pattern with GENEROUS "
    "clear/transparent vertical gaps, so light passes through it. The tube "
    "rises straight up out of a hole in the first-floor roof / deck floor; the "
    "laser source is hidden below the deck and shines up through the tube (do "
    "not show any light fixture or box on the deck). "
)

# zoomed-out, tall composition so the beam/handle climbing the sky is in frame
FRAMING = (
    "Wide zoomed-OUT shot with the whole art car placed small in the lower "
    "portion of the frame, leaving lots of open sky above so the full tall "
    "handle and the beam above it are visible. Tall vertical composition. "
)

MODES = {
    "day": (
        FRAMING +
        "DAYTIME, bright clear blue desert sky, harsh midday sun. The laser is "
        "OFF. The tall wrapped translucent tube simply reads as a big solid "
        "broom handle standing up from the deck. The bristle strands are unlit "
        "in the daylight — white/translucent silicone tubes alternating with "
        "thinner clear fiber cables. Clean, documentary, photorealistic — "
        "looks obviously like a giant broom."
    ),
    "night": (
        FRAMING +
        "NIGHT on the open playa under a dark starry sky. The laser is ON: a "
        "razor-thin, brilliant, intensely bright WHITE laser beam erupts from "
        "the TOP of the tall translucent tube and shoots perfectly straight UP "
        "high into the sky, continuing up and up seemingly to infinity, so the "
        "broom handle appears impossibly tall. The tube itself glows from the "
        "laser and its internal LED strips, its brown wrap backlit through the "
        "clear gaps. The thick LED bristle tubes glow bright saturated rainbow "
        "in a vertical chase, while the thin fiber strands between them each "
        "glow a single steady solid color (cool white / ice blue), creating a "
        "clear alternating thick-rainbow / thin-solid rhythm. Dramatic, vivid, "
        "long-exposure night photography, beam visible against the stars."
    ),
}


def load_token():
    if os.environ.get("REPLICATE_API_TOKEN"):
        return os.environ["REPLICATE_API_TOKEN"]
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line.startswith("REPLICATE_API_TOKEN"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    sys.exit("REPLICATE_API_TOKEN not found in env or .env")


def data_uri(path):
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"data:image/jpeg;base64,{b64}"


def run(token, img_uri, tag, mode):
    prompt = BRISTLES + HANDLE + MODES[mode]
    body = json.dumps({
        "input": {
            "prompt": prompt,
            "image_input": [img_uri],
            "aspect_ratio": "9:16",
            "resolution": "2K",
            "output_format": "jpg",
        }
    }).encode()
    req = urllib.request.Request(
        f"https://api.replicate.com/v1/models/{MODEL}/predictions",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    print(f"[{tag}/{mode}] submitting...", flush=True)
    with urllib.request.urlopen(req, timeout=60) as resp:
        pred = json.load(resp)

    get_url = pred.get("urls", {}).get("get")
    waited = 0
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        time.sleep(4)
        waited += 4
        if waited > 600:
            print(f"[{tag}/{mode}] gave up after 10 min", flush=True)
            return
        r = urllib.request.Request(get_url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                pred = json.load(resp)
        except urllib.error.URLError:
            continue

    if pred.get("status") != "succeeded":
        print(f"[{tag}/{mode}] FAILED: {pred.get('error')}", flush=True)
        return
    out = pred["output"]
    url = out[0] if isinstance(out, list) else out
    dest = os.path.join(OUT_DIR, f"fiberbroom_{tag}_{mode}.jpg")
    urllib.request.urlretrieve(url, dest)
    print(f"[{tag}/{mode}] saved -> {dest}", flush=True)


def main():
    token = load_token()
    jobs = []
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            tag, _, mode = a.partition(":")
            jobs.append((tag, mode or "night"))
    else:
        jobs = [(t, m) for t in SOURCES for m in MODES]

    uris = {}
    for tag, mode in jobs:
        if tag not in uris:
            uris[tag] = data_uri(SOURCES[tag])
        run(token, uris[tag], tag, mode)


if __name__ == "__main__":
    main()
