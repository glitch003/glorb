# LED Tubes (360° silicone)

Flexible 360° black/white silicone-jacketed addressable LED tube.

## Specs

- **Voltage:** 24 V DC
- **IC:** SM16703 (single-wire, WS2811-compatible protocol)
- **LED:** SMD3535
- **Density:** 96 LEDs/m per side, 192 LEDs/m total (double-sided)
- **Addressable groups:** 6 physical LEDs per SM16703 IC → **16 pixels/m** (per side)
- **Power:** 28–30 W / m
- **Current:** ~1.17–1.25 A/m @ 24 V (full white)
- **Data signal:** 5 V logic (use level shifter from 3.3 V MCUs; Trinket 5V is fine direct)

## Wiring

- `+24V` → strip V+
- `GND`  → strip GND **and** MCU GND (common ground required)
- `DATA` → strip DIN (through ~330–470 Ω resistor recommended)
- 1000 µF cap across V+/GND at strip injection point

## Sub-pixel color layout (observed on the car, 2026-08)

The 6 LEDs in one addressable group are **single-color series pairs laid out
along the tube**: R,R,G,G,B,B — red pair at the top of the ~62 mm pixel, blue
at the bottom, pair centres ⅓ pixel apart. Mid-shape it blends in the
diffuser, but a hard horizontal edge fringes: red line above, blue/teal
below, most visible on mixed colors (pink, skin). Not a data/mapping
problem — glorbleds' engine compensates with a ⅓-pixel R/B resample, and the
web preview draws the candy-stripe structure (`--subpixel`, see
[glorbleds/README.md](glorbleds/README.md)).

## Source

https://www.alibaba.com/product-detail/Flexible-360-Degree-Black-White-Silicone_1601739508491.html

## FastLED notes

- Chipset: `SM16703` (supported natively in FastLED 3.x)
- Color order: **`RGB`** (confirmed on this strip)
- Each SM16703 IC drives a group of **6 physical LEDs** (24 V series chain), so they're not individually addressable. `NUM_LEDS = 16 * meters` (per side). 5 m = **80 pixels**.
- Test sketch: [nano_sm16703_cylon/](nano_sm16703_cylon/nano_sm16703_cylon.ino)
