#!/usr/bin/env python3
"""Geometrically accurate broom-bristle density mockups.

Unlike the AI mockups, this places the CORRECT number of tubes per visible
face at the real pitch (11600mm perimeter / N), so the 50/60/75/80 density
differences are true. Draws onto glorb-2023.jpeg. Approximate (linear edge
interpolation, no lens correction) but faithful on count + spacing.
"""

from PIL import Image, ImageDraw, ImageFont

SRC = "../../glorb-2023.jpeg"  # run from this dir
PERIMETER = 11600  # mm
LONG_FACE = 4000   # mm (left face in photo)
SHORT_FACE = 1800  # mm (right face in photo)

# Box face corners in full-res pixel coords, read off _grid2.jpg.
# Left (long) face: far-left-top, near-corner-top, near-corner-bot, far-left-bot
LEFT = [(1490, 610), (2300, 545), (2300, 2330), (1490, 1960)]
# Right (short) face: near-corner-top, far-right-top, far-right-bot, near-corner-bot
RIGHT = [(2300, 545), (3020, 690), (3010, 1770), (2300, 2330)]

VARIANTS = [50, 60, 75, 80]


def lerp(a, b, t):
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


def draw_face(draw, quad, face_mm, pitch_mm, scale_pxmm):
    # quad = [top_left, top_right, bot_right, bot_left]
    top_l, top_r, bot_r, bot_l = quad
    n = max(0, int(face_mm / pitch_mm))
    core = max(2, int(round(22 * scale_pxmm)))
    for i in range(n):
        t = (i + 0.5) / n if n else 0.5
        p_top = lerp(top_l, top_r, t)
        p_bot = lerp(bot_l, bot_r, t)
        # soft glow: wider translucent passes, then white core
        for w, col in ((core * 4, (255, 255, 255, 40)),
                       (core * 2, (255, 255, 255, 90))):
            draw.line([p_top, p_bot], fill=col, width=w)
        draw.line([p_top, p_bot], fill=(255, 255, 255, 255), width=core)
    return n


def main():
    base = Image.open(SRC).convert("RGB")
    # px-per-mm estimate from the long face width in pixels / 4000mm
    face_px = abs(LEFT[1][0] - LEFT[0][0])
    scale_pxmm = face_px / LONG_FACE
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except Exception:
        font = ImageFont.load_default()

    for N in VARIANTS:
        pitch = PERIMETER / N
        gap = pitch - 22
        img = base.copy().convert("RGBA")
        layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        nl = draw_face(d, LEFT, LONG_FACE, pitch, scale_pxmm)
        nr = draw_face(d, RIGHT, SHORT_FACE, pitch, scale_pxmm)
        out = Image.alpha_composite(img, layer).convert("RGB")
        dd = ImageDraw.Draw(out)
        label = f"{N} tubes total | pitch {pitch:.0f}mm | gap {gap:.0f}mm | {nl}+{nr} on visible faces"
        dd.rectangle([0, 0, out.width, 80], fill=(0, 0, 0))
        dd.text((20, 12), label, fill=(255, 255, 255), font=font)
        dest = f"overlay_{N}tubes.jpg"
        out.save(dest, quality=88)
        print("saved", dest, "->", label)


if __name__ == "__main__":
    main()
