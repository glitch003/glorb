#!/usr/bin/env python3
"""Accurate single-face broom-bristle density mockup on glorb-2023-2.jpeg.

Near-flat-on view, so we overlay tubes on just the camera-facing long face
(4000mm) at the true pitch (11600mm perimeter / N). Even spacing across the
face -> clean density comparison without the corner distortion of the 2-face
version.
"""

from PIL import Image, ImageDraw, ImageFont

SRC = "../../glorb-2023-2.jpeg"  # run from this dir
PERIMETER = 11600  # mm
FRONT_FACE = 4000  # mm (long side facing camera)

# Front face corners in full-res px (measured manually on glorb-2023-2.jpeg):
# [top_left, top_right, bot_right, bot_left]
FACE = [(1493, 863), (3089, 980), (3153, 2018), (1543, 2200)]

VARIANTS = [50, 60, 75, 80, 100, 150, 200]


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def main():
    base = Image.open(SRC).convert("RGB")
    tl, tr, br, bl = FACE
    face_px = abs(tr[0] - tl[0])
    scale_pxmm = face_px / FRONT_FACE
    core = max(3, int(round(22 * scale_pxmm)))
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except Exception:
        font = ImageFont.load_default()

    for N in VARIANTS:
        pitch = PERIMETER / N
        gap = pitch - 22
        n = int(FRONT_FACE / pitch)
        img = base.copy().convert("RGBA")
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        for i in range(n):
            t = (i + 0.5) / n
            p_top = lerp(tl, tr, t)
            p_bot = lerp(bl, br, t)
            for w, col in ((core * 4, (255, 255, 255, 38)),
                           (core * 2, (255, 255, 255, 95))):
                d.line([p_top, p_bot], fill=col, width=w)
            d.line([p_top, p_bot], fill=(255, 255, 255, 255), width=core)
        out = Image.alpha_composite(img, layer).convert("RGB")
        dd = ImageDraw.Draw(out)
        label = f"{N} tubes total | pitch {pitch:.0f}mm | gap {gap:.0f}mm | {n} on this 4m face"
        dd.rectangle([0, 0, out.width, 80], fill=(0, 0, 0))
        dd.text((20, 12), label, fill=(255, 255, 255), font=font)
        dest = f"front_{N}tubes.jpg"
        out.save(dest, quality=88)
        print("saved", dest, "->", label)


if __name__ == "__main__":
    main()
