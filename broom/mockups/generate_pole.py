#!/usr/bin/env python3
"""Renders of the 20 ft ILLUMINATED stripper/dance pole 'broom handle'.

For sending to the pole manufacturer building a light-up pole. Produces:
  - full-car shots showing the 20 ft glowing pole in context (broom handle)
  - a zoomed detail of the pole where it mounts on the upper deck
  - an isolated product-style render of the glowing pole on a plain background

Reads REPLICATE_API_TOKEN from ../../.env. Writes pole_<name>.jpg here.
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

CORNER = os.path.join(REPO_ROOT, "glorb-2023.jpeg")
SIDE = os.path.join(REPO_ROOT, "glorb-2023-2.jpeg")

# The pole spec, stated identically everywhere so the vendor sees one design.
POLE = (
    "The pole is a single vertical polished-chrome dance/stripper pole, about "
    "20 feet (6 meters) tall and ~50 mm in diameter, mounted upright on the "
    "open upper deck and rising straight up far above the car — roughly twice "
    "the car's own height. The ENTIRE pole glows and lights up along its full "
    "length: it has bright addressable LEDs running its whole height under a "
    "frosted/translucent sleeve, emitting a smooth even glow with a subtle "
    "vertical color-chase, while still reading as a real metal dance pole. "
    "The pole is topped with a small bright glowing finial."
)

# keep-the-car context for the full-car shots
CAR = (
    "This is a boxy two-story art car at Burning Man with a striped wrap and an "
    "open upper deck with a scaffold railing frame and speakers. Keep the same "
    "car, upper deck, railing, speakers, wheels, and desert playa ground. "
)

JOBS = {
    # full car, pole towering as the broom handle
    "full_side_night": (SIDE, CAR + POLE + " Night on the open playa, dark "
        "starry sky. The tall glowing pole dominates the silhouette like the "
        "handle of a giant broom. Photorealistic, dramatic night photography, "
        "show the full pole top to bottom in frame."),
    "full_corner_dusk": (CORNER, CAR + POLE + " Dusk / blue hour, deep blue "
        "sky. Three-quarter view showing the full height of the glowing pole "
        "above the deck. Cinematic, photorealistic, whole pole in frame."),
    # zoomed detail: how it mounts + how it glows
    "detail_mount": (SIDE, "Close-up detail shot of the base of a vertical "
        "polished-chrome dance/stripper pole where it mounts to the metal "
        "railing frame of an art car's upper deck. " + POLE + " Focus tightly "
        "on the lower ~1/3 of the pole and its deck mounting flange/bracket, "
        "showing the glowing translucent LED sleeve and the metal base clamp. "
        "Dusk light, sharp, photorealistic product-detail photograph."),
    # isolated product render for the manufacturer
    "product_studio": (SIDE, "Studio product photograph of a single vertical "
        "polished-chrome dance/stripper pole, isolated and centered on a plain "
        "dark seamless background, full length top to bottom in frame. " + POLE
        + " No car, no people — just the illuminated pole as a product shot, "
        "clean, high-detail, even studio lighting plus the pole's own glow."),
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


def run(token, img_uri, name, prompt):
    body = json.dumps({
        "input": {
            "prompt": prompt,
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
    print(f"[{name}] submitting...", flush=True)
    with urllib.request.urlopen(req, timeout=60) as resp:
        pred = json.load(resp)

    get_url = pred.get("urls", {}).get("get")
    waited = 0
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        time.sleep(4)
        waited += 4
        if waited > 600:
            print(f"[{name}] gave up after 10 min", flush=True)
            return
        r = urllib.request.Request(get_url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                pred = json.load(resp)
        except urllib.error.URLError:
            continue

    if pred.get("status") != "succeeded":
        print(f"[{name}] FAILED: {pred.get('error')}", flush=True)
        return
    out = pred["output"]
    url = out[0] if isinstance(out, list) else out
    dest = os.path.join(OUT_DIR, f"pole_{name}.jpg")
    urllib.request.urlretrieve(url, dest)
    print(f"[{name}] saved -> {dest}", flush=True)


def main():
    token = load_token()
    names = sys.argv[1:] or list(JOBS)
    uris = {}
    for name in names:
        src, prompt = JOBS[name]
        if src not in uris:
            uris[src] = data_uri(src)
        run(token, uris[src], name, prompt)


if __name__ == "__main__":
    main()
