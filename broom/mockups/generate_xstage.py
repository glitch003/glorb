#!/usr/bin/env python3
"""Finished-broom render with the ordered X-Stage pole on a hexagon lounge.

Starts from the generate_finished.py concept (side panels removed, ~100
vertical glowing LED tube bristles) and adds to the upper deck:
  - a low HEXAGONAL seating platform / lounge (bench seating around the edges)
  - on top of it, the ordered X-Pole X-STAGE (45 mm stainless): a freestanding
    dance pole ~10.5 ft tall rising from its own circular stage/podium base —
    no ceiling fixing, pole in the center of the round platform.

Reads REPLICATE_API_TOKEN from ../../.env. Writes xstage_<src>_<scene>.jpg.
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

BRISTLES = (
    "This is a boxy two-story art car at Burning Man with a colorful striped "
    "wrap on its side wall panels and an open upper deck with a scaffold-style "
    "railing frame and speakers. Transform it into a giant glowing broom while "
    "keeping the SAME car: keep the boxy two-story chassis, the upper deck and "
    "its metal railing frame, the speakers, the wheels/tires, and the desert "
    "playa ground and background. "
    "REMOVE the colorful striped side wall panels completely. In their place, "
    "hang about 100 thin (~22 mm) vertical glowing LED neon tubes straight "
    "down around the ENTIRE perimeter of the car, mounted from the upper-deck "
    "frame and hanging to just above the ground, densely and evenly spaced "
    "(~10 cm apart) like the bristles of a broom, so the whole lower body is a "
    "curtain of vertical light tubes instead of solid walls. "
)

XSTAGE = (
    "Centered on the open upper deck sits a freestanding professional dance "
    "pole stage (X-Pole X-Stage): a round polished stage podium about 1.6 m "
    "in diameter and 20 cm tall, with a single vertical 45 mm polished "
    "stainless-steel dance pole rising about 3 meters (10 feet) straight up "
    "from its center — completely freestanding, no ceiling attachment, held "
    "by its weighted stage base. The pole and stage should look like real "
    "professional pole-dance equipment. The deck is otherwise open and clear. "
    "The car keeps its full two-story height: the pole stage is ABOVE the "
    "bristle curtain, on top of the second floor. Show the full pole top to "
    "bottom in frame. Photorealistic."
)

SCENES = {
    "night": (
        "Night scene on the open playa under a dark starry sky. The LED tube "
        "bristles glow bright saturated rainbow colors in a vertical chase "
        "pattern, casting colored light on the dusty ground. The chrome pole "
        "catches colorful reflections. Dramatic, vivid night photography."
    ),
    "dusk": (
        "Dusk / blue hour, deep blue sky just after sunset. The LED tube "
        "bristles glow bright warm white so the broom-bristle curtain reads "
        "clearly. Cinematic, atmospheric."
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


def run(token, img_uri, tag, scene):
    prompt = BRISTLES + XSTAGE + " " + SCENES[scene]
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
    print(f"[{tag}/{scene}] submitting...", flush=True)
    with urllib.request.urlopen(req, timeout=60) as resp:
        pred = json.load(resp)

    get_url = pred.get("urls", {}).get("get")
    waited = 0
    while pred.get("status") not in ("succeeded", "failed", "canceled"):
        time.sleep(4)
        waited += 4
        if waited > 600:
            print(f"[{tag}/{scene}] gave up after 10 min", flush=True)
            return
        r = urllib.request.Request(get_url, headers={"Authorization": f"Bearer {token}"})
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                pred = json.load(resp)
        except urllib.error.URLError:
            continue

    if pred.get("status") != "succeeded":
        print(f"[{tag}/{scene}] FAILED: {pred.get('error')}", flush=True)
        return
    out = pred["output"]
    url = out[0] if isinstance(out, list) else out
    dest = os.path.join(OUT_DIR, f"xstage_{tag}_{scene}.jpg")
    urllib.request.urlretrieve(url, dest)
    print(f"[{tag}/{scene}] saved -> {dest}", flush=True)


def main():
    token = load_token()
    jobs = []
    if len(sys.argv) > 1:
        for a in sys.argv[1:]:
            tag, _, scene = a.partition(":")
            jobs.append((tag, scene or "night"))
    else:
        jobs = [(t, s) for t in SOURCES for s in SCENES]

    uris = {}
    for tag, scene in jobs:
        if tag not in uris:
            uris[tag] = data_uri(SOURCES[tag])
        run(token, uris[tag], tag, scene)


if __name__ == "__main__":
    main()
