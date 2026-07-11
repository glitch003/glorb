#!/usr/bin/env python3
"""Composite glowing broom-bristle tubes onto the Glorb photo at different
gap densities, using Replicate's google/nano-banana-pro image-edit model.

Reads REPLICATE_API_TOKEN from ../../.env. Writes mockup_<N>tubes.jpg here.
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
SRC_IMAGE = os.path.join(REPO_ROOT, "glorb-2023.jpeg")
OUT_DIR = os.path.dirname(__file__)
MODEL = "google/nano-banana-pro"

# gap sizes around the 11,600 mm perimeter (pitch = 11600/N, gap = pitch - 22mm tube)
VARIANTS = {
    50: "about 21 cm",
    60: "about 17 cm",
    75: "about 13 cm",
    80: "about 12 cm",
}

BASE_PROMPT = (
    "Edit this photo of a boxy two-story art car at Burning Man. Keep the car, "
    "its colorful striped wrap, the desert background, sky, and lighting exactly "
    "as they are. Add vertical glowing white LED neon tubes hanging straight down "
    "around the visible edges/perimeter of the car like broom bristles, mounted "
    "from the top frame and hanging to just above the ground. The tubes are thin "
    "(~22 mm), evenly spaced {gap} apart, emitting a soft bright white glow. "
    "Photorealistic, consistent with the existing daytime lighting and perspective."
)


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


def run(token, img_uri, n_tubes, gap):
    body = json.dumps({
        "input": {
            "prompt": BASE_PROMPT.format(gap=gap),
            "image_input": [img_uri],
            "aspect_ratio": "match_input_image",
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
    print(f"[{n_tubes} tubes] submitting...", flush=True)
    with urllib.request.urlopen(req, timeout=60) as resp:
        pred = json.load(resp)

    # poll until done (nano-banana-pro 2K can take a few minutes)
    get_url = pred.get("urls", {}).get("get")
    waited = 0
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        time.sleep(4)
        waited += 4
        if waited > 600:
            print(f"[{n_tubes} tubes] gave up after 10 min", flush=True)
            return
        r = urllib.request.Request(get_url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                pred = json.load(resp)
        except urllib.error.URLError:
            continue  # transient; keep polling

    if pred.get("status") != "succeeded":
        print(f"[{n_tubes} tubes] FAILED: {pred.get('error')}", flush=True)
        return
    out = pred["output"]
    url = out[0] if isinstance(out, list) else out
    dest = os.path.join(OUT_DIR, f"mockup_{n_tubes}tubes.jpg")
    urllib.request.urlretrieve(url, dest)
    print(f"[{n_tubes} tubes] saved -> {dest}", flush=True)


def main():
    token = load_token()
    img_uri = data_uri(SRC_IMAGE)
    targets = [int(a) for a in sys.argv[1:]] or list(VARIANTS)
    for n in targets:
        run(token, img_uri, n, VARIANTS[n])


if __name__ == "__main__":
    main()
