#!/usr/bin/env python3
"""'Laser handle' broom concept — reads as a broom day AND night.

Replaces the (hard-to-source) 20 ft custom pole with:
  - a wide hollow clear/translucent tube standing on the upper deck as the
    broom handle, wrapped like a car wrap with a bold pattern that has
    GENEROUS transparent gaps (same trick as the Glorb acrylic panels), with
    LED strips inside so it glows;
  - a 120 W white LASER moving-head (Blue Sea, ultra-narrow 0.9 deg beam, RGB
    LED ring, IP65) sitting on the first-floor roof / deck, aimed straight up
    through a hole into the base of the tube.
  - DAY: laser off — the wrapped tube just reads as a fat broom handle (DMV).
  - NIGHT: laser on — a razor-thin brilliant white beam erupts from the top of
    the tube and shoots up into the sky seemingly forever, so the handle looks
    infinitely tall.

Body is still the LED-tube bristle curtain from the finished-broom design.

Reads REPLICATE_API_TOKEN from ../../.env. Writes laserbroom_<src>_<mode>.jpg.
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
    "hang about 100 thin (~22 mm) vertical LED neon tubes straight down around "
    "the ENTIRE perimeter, mounted from the upper-deck frame down to just above "
    "the ground, densely and evenly spaced like broom bristles, so the lower "
    "body is a curtain of vertical tubes instead of solid walls. "
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
        "broom handle standing up from the deck. The LED bristle tubes are "
        "unlit (just white/translucent silicone tubes) in the daylight. Clean, "
        "documentary, photorealistic — looks obviously like a giant broom."
    ),
    "night": (
        FRAMING +
        "NIGHT on the open playa under a dark starry sky. The laser is ON: a "
        "razor-thin, brilliant, intensely bright WHITE laser beam erupts from "
        "the TOP of the tall translucent tube and shoots perfectly straight UP "
        "high into the sky, continuing up and up seemingly to infinity, so the "
        "broom handle appears impossibly tall. The tube itself glows from the "
        "laser and its internal LED strips, its brown wrap backlit through the "
        "clear gaps. The LED bristle tubes "
        "glow bright saturated rainbow in a vertical chase. Dramatic, vivid, "
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
    dest = os.path.join(OUT_DIR, f"laserbroom_{tag}_{mode}.jpg")
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
