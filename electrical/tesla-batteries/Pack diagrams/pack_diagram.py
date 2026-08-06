#!/usr/bin/env python3
"""6x Tesla module 24V parallel pack — circuit diagram generator.

Layout: two stacks of three modules, positive/negative busbars down the
center, master fuse + switch below, distribution busbar feeding charger
and load.
"""

W, H = 1500, 1320
RED = "#c62828"
BLK = "#111"
GRY = "#666"
YEL = "#f9a825"
BG = "#fafafa"

MOD_W, MOD_H = 240, 110
FUSE_W, FUSE_H = 60, 26

# Module vertical positions (3 per stack)
MOD_YS = [90, 260, 430]
LEFT_X = 120           # left edge of left-stack modules
RIGHT_X = W - 120 - MOD_W   # left edge of right-stack modules
POS_BUS_X = W // 2 - 30
NEG_BUS_X = W // 2 + 30
BUS_TOP = 70
BUS_BOT = 560

out = []

def tag(name, **attrs):
    parts = [f'{k.replace("_","-")}="{v}"' for k, v in attrs.items()]
    return f'<{name} ' + " ".join(parts) + '/>'

def rect(x, y, w, h, fill="none", stroke=BLK, sw=2, rx=0):
    return tag("rect", x=x, y=y, width=w, height=h, fill=fill,
              stroke=stroke, stroke_width=sw, rx=rx)

def line(x1, y1, x2, y2, stroke=BLK, sw=3):
    return tag("line", x1=x1, y1=y1, x2=x2, y2=y2,
              stroke=stroke, stroke_width=sw, stroke_linecap="round")

def circle(cx, cy, r, fill="white", stroke=BLK, sw=2):
    return tag("circle", cx=cx, cy=cy, r=r, fill=fill,
              stroke=stroke, stroke_width=sw)

def text(x, y, s, size=15, anchor="middle", fill=BLK, weight="normal"):
    return (f'<text x="{x}" y="{y}" font-family="Inter,Helvetica,sans-serif" '
            f'font-size="{size}" text-anchor="{anchor}" fill="{fill}" '
            f'font-weight="{weight}">{s}</text>')

def module(x, y, name):
    """Draw a Tesla module. + terminal on the inward-facing side."""
    out.append(rect(x, y, MOD_W, MOD_H, fill="#eef2f7", stroke=BLK, sw=2, rx=6))
    out.append(text(x + MOD_W/2, y + 34, name, size=18, weight="bold"))
    out.append(text(x + MOD_W/2, y + 58, "Tesla 6S ~22V nominal", size=12, fill=GRY))
    out.append(text(x + MOD_W/2, y + 76, "~25.2V full  •  ~232Ah", size=12, fill=GRY))
    # + and - terminal dots (both on inward side for cleanliness)
    is_left = x < W/2
    tx_pos = x + MOD_W if is_left else x
    tx_neg = tx_pos
    out.append(circle(tx_pos, y + 28, 6, fill=RED, stroke=RED))
    out.append(circle(tx_neg, y + MOD_H - 28, 6, fill=BLK, stroke=BLK))
    out.append(text(tx_pos + (12 if is_left else -12), y + 32,
                   "+", size=16, anchor="start" if is_left else "end",
                   fill=RED, weight="bold"))
    out.append(text(tx_neg + (12 if is_left else -12), y + MOD_H - 24,
                   "−", size=16, anchor="start" if is_left else "end",
                   fill=BLK, weight="bold"))
    return tx_pos, y + 28, tx_neg, y + MOD_H - 28

def fuse_symbol(cx, cy, label, sublabel=None, horizontal=True):
    if horizontal:
        out.append(rect(cx - FUSE_W/2, cy - FUSE_H/2, FUSE_W, FUSE_H,
                       fill=YEL, stroke=BLK, sw=2, rx=4))
        # zigzag
        zx = [cx-20, cx-10, cx, cx+10, cx+20]
        zy = [cy, cy-6, cy, cy+6, cy]
        pts = " ".join(f"{a},{b}" for a,b in zip(zx, zy))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{BLK}" stroke-width="2"/>')
        out.append(text(cx, cy - FUSE_H/2 - 6, label, size=12, weight="bold"))
        if sublabel:
            out.append(text(cx, cy + FUSE_H/2 + 14, sublabel, size=10, fill=GRY))
    else:
        out.append(rect(cx - FUSE_H/2, cy - FUSE_W/2, FUSE_H, FUSE_W,
                       fill=YEL, stroke=BLK, sw=2, rx=4))
        zy = [cy-20, cy-10, cy, cy+10, cy+20]
        zx = [cx, cx-6, cx, cx+6, cx]
        pts = " ".join(f"{a},{b}" for a,b in zip(zx, zy))
        out.append(f'<polyline points="{pts}" fill="none" stroke="{BLK}" stroke-width="2"/>')
        out.append(text(cx + FUSE_H/2 + 40, cy + 4, label, size=12,
                       anchor="middle", weight="bold"))
        if sublabel:
            out.append(text(cx + FUSE_H/2 + 40, cy + 20, sublabel, size=10,
                           anchor="middle", fill=GRY))

def switch_symbol(cx, cy):
    out.append(rect(cx - 50, cy - 22, 100, 44, fill="white", stroke=BLK, sw=2, rx=4))
    # switch drawn as diagonal line breaking the contact
    out.append(circle(cx - 25, cy, 4, fill=BLK))
    out.append(circle(cx + 25, cy, 4, fill=BLK))
    out.append(line(cx - 25, cy, cx + 20, cy - 15, stroke=BLK, sw=3))
    out.append(text(cx, cy - 30, "MASTER SWITCH", size=12, weight="bold"))
    out.append(text(cx, cy + 40, "200A battery disconnect", size=10, fill=GRY))

def label_box(x, y, w, h, title, sub, fill="#e3f2fd"):
    out.append(rect(x, y, w, h, fill=fill, stroke=BLK, sw=2, rx=6))
    out.append(text(x + w/2, y + 26, title, size=16, weight="bold"))
    out.append(text(x + w/2, y + 46, sub, size=12, fill=GRY))

def cable_tag(cx, cy, gauge, lug_a, lug_b, cable_id="", above=True):
    """Compact pill label showing cable ID, wire gauge, and lug sizes."""
    prefix = f'#{cable_id}  ' if cable_id else ''
    s = f'{prefix}{gauge} · {lug_a}→{lug_b}'
    w = len(s) * 6.2 + 10
    y = cy - 14 if above else cy + 14
    out.append(rect(cx - w/2, y - 9, w, 15, fill="white", stroke=GRY, sw=0.75, rx=7))
    # draw ID in bold blue if present
    if cable_id:
        # measure the prefix so we can color-highlight it
        id_str = f'#{cable_id}'
        rest = f'  {gauge} · {lug_a}→{lug_b}'
        # use a single text with tspan for the colored ID
        out.append(
            f'<text x="{cx}" y="{y+3}" font-family="Inter,Helvetica,sans-serif" '
            f'font-size="10" text-anchor="middle" fill="{BLK}">'
            f'<tspan fill="#1565c0" font-weight="bold">{id_str}</tspan>{rest}</text>'
        )
    else:
        out.append(text(cx, y + 3, s, size=10, fill=BLK))

# --- background ---
out.append(rect(0, 0, W, H, fill=BG, stroke="none"))
out.append(text(W/2, 40, "24V PACK — 6× Tesla 6S modules in parallel",
               size=22, weight="bold"))

# --- draw modules ---
positions = []
for i, y in enumerate(MOD_YS):
    positions.append(module(LEFT_X, y, f"A{i+1}"))
for i, y in enumerate(MOD_YS):
    positions.append(module(RIGHT_X, y, f"B{i+1}"))

# --- positive and negative busbars ---
out.append(rect(POS_BUS_X - 8, BUS_TOP, 16, BUS_BOT - BUS_TOP,
               fill=RED, stroke=BLK, sw=1, rx=3))
out.append(text(POS_BUS_X, BUS_TOP - 8, "+ BUSBAR", size=12,
               fill=RED, weight="bold"))
out.append(rect(NEG_BUS_X - 8, BUS_TOP, 16, BUS_BOT - BUS_TOP,
               fill=BLK, stroke=BLK, sw=1, rx=3))
out.append(text(NEG_BUS_X, BUS_TOP - 8, "− BUSBAR", size=12,
               fill=BLK, weight="bold"))

# --- wire each module through its own fuse to the busbars ---
# Assumption: right stack (B) has + terminal near the busbars, left stack (A)
# has − terminal near. Flip stack orientation if you want it the other way.
for idx, (px, py, nx, ny) in enumerate(positions):
    is_left = px < W/2
    # positive circuit: near (1a) if right stack, far (1b) if left stack
    pos_id = "1b" if is_left else "1a"
    # negative circuit: near (3a) if left stack, far (3b) if right stack
    neg_id = "3a" if is_left else "3b"

    fuse_cx = (px + POS_BUS_X) / 2
    seg_a_mid = (px + fuse_cx - FUSE_W/2) / 2
    seg_b_mid = (fuse_cx + FUSE_W/2 + POS_BUS_X) / 2
    out.append(line(px, py, fuse_cx - FUSE_W/2, py, stroke=RED, sw=4))
    cable_tag(seg_a_mid, py, "4 AWG", '3/8"', '1/4"', cable_id=pos_id)
    fuse_symbol(fuse_cx, py, "50A", "MRBF / Class T")
    out.append(line(fuse_cx + FUSE_W/2, py, POS_BUS_X, py, stroke=RED, sw=4))
    cable_tag(seg_b_mid, py, "4 AWG", '1/4"', '3/8"', cable_id="2")
    # negative: module - -> - busbar
    out.append(line(nx, ny, NEG_BUS_X, ny, stroke=BLK, sw=4))
    cable_tag((nx + NEG_BUS_X)/2, ny, "4 AWG", '3/8"', '3/8"', cable_id=neg_id)

# --- master fuse + switch below busbars ---
# tap off the + busbar
tap_x = POS_BUS_X
tap_y = BUS_BOT
out.append(line(tap_x, tap_y, tap_x, tap_y + 40, stroke=RED, sw=5))
out.append(line(tap_x, tap_y + 40, W/2 - 200, tap_y + 40, stroke=RED, sw=5))
out.append(line(W/2 - 200, tap_y + 40, W/2 - 200, tap_y + 90, stroke=RED, sw=5))
cable_tag((tap_x + W/2 - 200)/2, tap_y + 40, "2/0 AWG", '3/8"', '3/8"', cable_id="4")

fuse_symbol(W/2 - 200, tap_y + 120, "200A", "Class T (DC-rated)")
out.append(line(W/2 - 200, tap_y + 133, W/2 - 200, tap_y + 180, stroke=RED, sw=5))
out.append(line(W/2 - 200, tap_y + 180, W/2 - 80, tap_y + 180, stroke=RED, sw=5))
cable_tag(W/2 - 140, tap_y + 180, "2/0 AWG", '3/8"', '3/8"', cable_id="5")

switch_symbol(W/2, tap_y + 180)

out.append(line(W/2 + 50, tap_y + 180, W/2 + 200, tap_y + 180, stroke=RED, sw=5))
cable_tag(W/2 + 125, tap_y + 180, "2/0 AWG", '3/8"', '3/8"', cable_id="6")

# --- distribution busbars ---
dist_y_pos = tap_y + 260
dist_y_neg = tap_y + 310
out.append(rect(W/2 - 300, dist_y_pos - 10, 600, 20,
               fill=RED, stroke=BLK, sw=1, rx=3))
out.append(text(W/2, dist_y_pos + 5, "+ DISTRIBUTION BUSBAR",
               size=13, fill="white", weight="bold"))
out.append(rect(W/2 - 300, dist_y_neg - 10, 600, 20,
               fill=BLK, stroke=BLK, sw=1, rx=3))
out.append(text(W/2, dist_y_neg + 5, "− DISTRIBUTION BUSBAR",
               size=13, fill="white", weight="bold"))

# drop from switch to + dist bus
out.append(line(W/2 + 200, tap_y + 180, W/2 + 200, dist_y_pos - 10, stroke=RED, sw=5))
cable_tag(W/2 + 200, (tap_y + 180 + dist_y_pos)/2, "2/0 AWG", '3/8"', '3/8"', cable_id="6")
# drop from - pack bus to - dist bus (straight down)
out.append(line(NEG_BUS_X, BUS_BOT, NEG_BUS_X, dist_y_neg - 10, stroke=BLK, sw=5))
cable_tag(NEG_BUS_X + 90, (BUS_BOT + dist_y_neg)/2, "2/0 AWG", '3/8"', '3/8"', cable_id="7")

# --- charger + load boxes ---
charger_x = W/2 - 380
load_x = W/2 + 100
box_y = dist_y_neg + 60
label_box(charger_x, box_y, 280, 70, "CHARGER", "Li-ion CC/CV  •  25.2V full (4.2V/cell)", fill="#e8f5e9")
label_box(load_x, box_y, 280, 70, "LOAD (LED zones A–E)", "~150A peak, 24V", fill="#fff3e0")

# Charger + wire
out.append(line(charger_x + 100, box_y, charger_x + 100, dist_y_pos + 10, stroke=RED, sw=4))
cable_tag(charger_x + 100, (box_y + dist_y_pos)/2 - 10, "8 AWG", '3/8"', "chgr", cable_id="8")
# Charger - wire
out.append(line(charger_x + 180, box_y, charger_x + 180, dist_y_neg + 10, stroke=BLK, sw=4))
cable_tag(charger_x + 180, (box_y + dist_y_neg)/2 + 8, "8 AWG", '3/8"', "chgr", cable_id="8")
# Load + wire
out.append(line(load_x + 100, box_y, load_x + 100, dist_y_pos + 10, stroke=RED, sw=4))
cable_tag(load_x + 100, (box_y + dist_y_pos)/2 - 10, "2/0 AWG", '3/8"', "load", cable_id="9")
# Load - wire
out.append(line(load_x + 180, box_y, load_x + 180, dist_y_neg + 10, stroke=BLK, sw=4))
cable_tag(load_x + 180, (box_y + dist_y_neg)/2 + 8, "2/0 AWG", '3/8"', "load", cable_id="9")

# small + / - markers where wires meet the boxes
out.append(text(charger_x + 100, box_y - 4, "+", size=14, fill=RED, weight="bold"))
out.append(text(charger_x + 180, box_y - 4, "−", size=14, weight="bold"))
out.append(text(load_x + 100, box_y - 4, "+", size=14, fill=RED, weight="bold"))
out.append(text(load_x + 180, box_y - 4, "−", size=14, weight="bold"))

# --- cable BOM table ---
lg_x, lg_y = 40, H - 300
lg_w = 780
out.append(rect(lg_x, lg_y, lg_w, 270, fill="white", stroke=BLK, sw=1, rx=6))
out.append(text(lg_x + lg_w/2, lg_y + 22, "CABLE BOM — build list",
               size=14, weight="bold"))

# Column headers
cols = [
    ("#",           lg_x + 20,  "start"),
    ("Segment",     lg_x + 50,  "start"),
    ("Qty",         lg_x + 340, "middle"),
    ("Gauge",       lg_x + 430, "middle"),
    ("Lug A",       lg_x + 530, "middle"),
    ("Lug B",       lg_x + 620, "middle"),
    ("Length",      lg_x + 705, "middle"),
]
for name, x, anchor in cols:
    out.append(text(x, lg_y + 44, name, size=11, weight="bold", anchor=anchor))
out.append(line(lg_x + 10, lg_y + 50, lg_x + lg_w - 10, lg_y + 50, stroke=GRY, sw=1))

bom = [
    ("1a", "Module + → fuse in  (near, b/m/t)",  "1/1/1", "4 AWG",   '3/8"', '1/4"', '4" / 7" / 10"'),
    ("1b", "Module + → fuse in  (far, b/m/t)",   "1/1/1", "4 AWG",   '3/8"', '1/4"', '15.5" / 18.5" / 21.5"'),
    ("2",  "Fuse out → + pack busbar (jumper)",  "6",     "4 AWG",   '1/4"', '3/8"', '2"'),
    ("3a", "Module − → − pack busbar (near, b/m/t)", "1/1/1", "4 AWG", '3/8"', '3/8"', '6" / 9" / 12"'),
    ("3b", "Module − → − pack busbar (far, b/m/t)",  "1/1/1", "4 AWG", '3/8"', '3/8"', '17.5" / 20.5" / 23.5"'),
    ("4",  "+ busbar → master fuse in",          "1",     "2/0 AWG", '3/8"', '3/8"', '~8"'),
    ("5",  "Master fuse out → switch in",        "1",     "2/0 AWG", '3/8"', '3/8"', '~4"'),
    ("6",  "Switch out → + distro bus",          "1",     "2/0 AWG", '3/8"', '3/8"', '~8"'),
    ("7",  "− pack bus → − distro bus",          "1",     "2/0 AWG", '3/8"', '3/8"', '~10"'),
    ("8",  "+/− distro → charger",               "2",     "8 AWG",   '3/8"', "TBD",  "TBD"),
    ("9",  "+/− distro → LED load",              "2",     "2/0 AWG", '3/8"', "TBD",  "TBD"),
]
# Table needs a bit more vertical room now
for i, row in enumerate(bom):
    y = lg_y + 66 + i*14
    xs = [lg_x + 20, lg_x + 50, lg_x + 340, lg_x + 430, lg_x + 530, lg_x + 620, lg_x + 705]
    anchors = ["start", "start", "middle", "middle", "middle", "middle", "middle"]
    for val, x, anchor in zip(row, xs, anchors):
        out.append(text(x, y, val, size=10, anchor=anchor))

# footnote
fn_y = lg_y + 66 + len(bom)*14 + 6
out.append(text(lg_x + 20, fn_y,
               "NEAR = terminal on the busbar-facing corner (short run). "
               "FAR = terminal on the opposite corner (adds 11.5\" for module-width traverse).",
               size=10, anchor="start", fill=GRY))
out.append(text(lg_x + 20, fn_y + 14,
               "b/m/t = bottom / middle / top stack level (+3\" per level up). "
               "Add ~1\" per cable for bend & strain relief.",
               size=10, anchor="start", fill=GRY))

# --- fusing note ---
nt_x, nt_y = W - 460, H - 180
out.append(rect(nt_x, nt_y, 420, 150, fill="white", stroke=BLK, sw=1, rx=6))
out.append(text(nt_x + 210, nt_y + 22, "FUSING", size=14, weight="bold"))
notes = [
    "• 50A per-module fuse: protects against inter-module",
    "  fault current if any single module shorts internally",
    "• 200A master fuse: protects the main pack wiring",
    "  and interrupts a downstream short at the load",
    "• Use DC-rated fuses (MRBF, Class T). Automotive blade",
    "  fuses arc at DC and are not safe here.",
]
for i, s in enumerate(notes):
    out.append(text(nt_x + 12, nt_y + 46 + i*18, s, size=11, anchor="start"))

# --- write file ---
import os, shutil, subprocess, sys, tempfile

svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
       f'viewBox="0 0 {W} {H}">\n' + "\n".join(out) + "\n</svg>\n")

here = os.path.dirname(os.path.abspath(__file__))
svg_path = os.path.join(here, "pack_diagram.svg")
pdf_path = os.path.join(here, "pack_diagram.pdf")
png_path = os.path.join(here, "pack_diagram.png")

with open(svg_path, "w") as f:
    f.write(svg)
print(f"wrote {svg_path} ({W}x{H})")

# --- render PDF + PNG via headless Chrome ---
CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    shutil.which("google-chrome") or "",
    shutil.which("chromium") or "",
]
chrome = next((c for c in CHROME_CANDIDATES if c and os.path.exists(c)), None)
if not chrome:
    print("no Chrome/Chromium found — skipping PDF/PNG", file=sys.stderr)
    sys.exit(0)

# Wrap SVG in HTML sized exactly to the diagram so Chrome renders it 1:1.
html = f"""<!doctype html><html><head><meta charset="utf-8"><style>
@page {{ size: {W}px {H}px; margin: 0; }}
html,body {{ margin:0; padding:0; background:{BG}; }}
svg {{ display:block; }}
</style></head><body>{svg}</body></html>"""

with tempfile.TemporaryDirectory() as td:
    html_path = os.path.join(td, "pack.html")
    with open(html_path, "w") as f:
        f.write(html)
    url = "file://" + html_path

    def run_chrome(out_path, extra):
        # --headless=new produces the output file but sometimes doesn't
        # exit cleanly; give it a short window and then kill it.
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox",
               "--hide-scrollbars", "--no-first-run",
               "--no-default-browser-check",
               "--disable-features=Translate,MediaRouter",
               "--virtual-time-budget=3000",
               f"--user-data-dir={td}/profile-{out_path[-3:]}"] + extra + [url]
        if os.path.exists(out_path):
            os.remove(out_path)
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        # Poll for the file to appear, then give Chrome a moment to finalize.
        import time
        deadline = time.time() + 30
        while time.time() < deadline:
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                time.sleep(0.4)
                break
            if p.poll() is not None:
                break
            time.sleep(0.2)
        if p.poll() is None:
            p.terminate()
            try: p.wait(timeout=3)
            except subprocess.TimeoutExpired: p.kill()
        if not os.path.exists(out_path):
            raise RuntimeError(f"chrome failed to produce {out_path}")

    run_chrome(pdf_path, [f"--print-to-pdf={pdf_path}", "--no-pdf-header-footer"])
    print(f"wrote {pdf_path}")

    run_chrome(png_path, [f"--screenshot={png_path}", f"--window-size={W},{H}"])
    print(f"wrote {png_path}")
