"""Draw the Open Animal Stage mark and wordmark from pixel grids.

    .venv/bin/python docs/brand/make_brand.py

Writes, next to this file: logo-mark.svg, logo.svg, logo.png (1024 wide),
logo-512.png, logo-mark.png (512), and preview.png (the mark at tab sizes on a
light and a dark strip). Then the favicon set into docs/itch/favicon/.

Everything is drawn from the two grids below, so the SVG needs no font and the
PNGs are exact nearest-neighbour scalings of the same pixels: the same method as
Open Fly's docs/itch/favicon/make_favicon.py, in this project's palette.

THE MARK. A stage seen from the seats: the amber rail across the top (Open Fly's
gold top edge), teal curtains either side, a spotlight falling on one neuron
standing on the boards. Amber is the game, teal and paper are the animals --
the page's own split (web/index.html :root).
"""
import os
import subprocess
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

ROOM = "#0C1113"
PAL = {
    "A": "#F2B84B",  # amber: the game, the light
    "a": "#5A4622",  # the spotlight pool, and the boards in shadow
    "b": "#A07A35",  # the pool's hot centre
    "T": "#6FB7AE",  # teal: curtain
    "t": "#3F7A73",  # curtain fold
    "P": "#EDE6D6",  # paper: the neuron
}

MARK = """
AAAAAAAAAAAAAAAA
TTTTt......tTTTT
TTTt........tTTT
TTt..P....P..tTT
TTt...P..P...tTT
TTt...PPPP...tTT
TTt..PPPPPP..tTT
Tt...PPPPPP...tT
Tt....PPPP....tT
Tt.....PP.....tT
Tt.....PP.....tT
T......PP......T
T...aaabbaaa...T
AAAAAAAAAAAAAAAA
aaaaaaaaaaaaaaaa
................
""".split()

FONT = {
    "O": [".XXXX.", "XX..XX", "XX..XX", "XX..XX", "XX..XX", "XX..XX", ".XXXX."],
    "P": ["XXXXX.", "XX..XX", "XX..XX", "XXXXX.", "XX....", "XX....", "XX...."],
    "E": ["XXXXXX", "XX....", "XX....", "XXXXX.", "XX....", "XX....", "XXXXXX"],
    "N": ["XX..XX", "XXX.XX", "XXXXXX", "XX.XXX", "XX..XX", "XX..XX", "XX..XX"],
    "A": [".XXXX.", "XX..XX", "XX..XX", "XXXXXX", "XX..XX", "XX..XX", "XX..XX"],
    "I": ["XXXXXX", "..XX..", "..XX..", "..XX..", "..XX..", "..XX..", "XXXXXX"],
    "M": ["XX...XX", "XXX.XXX", "XXXXXXX", "XX.X.XX", "XX...XX", "XX...XX", "XX...XX"],
    "L": ["XX....", "XX....", "XX....", "XX....", "XX....", "XX....", "XXXXXX"],
    "S": [".XXXXX", "XX....", "XX....", ".XXXX.", "....XX", "....XX", "XXXXX."],
    "T": ["XXXXXX", "..XX..", "..XX..", "..XX..", "..XX..", "..XX..", "..XX.."],
    "G": [".XXXXX", "XX....", "XX....", "XX.XXX", "XX..XX", "XX..XX", ".XXXXX"],
    " ": ["...", "...", "...", "...", "...", "...", "..."],
}

assert len(MARK) == 16 and all(len(r) == 16 for r in MARK), [len(r) for r in MARK]
for k, g in FONT.items():
    assert len(g) == 7 and len({len(r) for r in g}) == 1, k


def text_cells(s, x0, y0, color):
    """[(x, y, color)] for a string set in FONT, one cell per pixel."""
    out, x = [], x0
    for ch in s:
        g = FONT[ch]
        for y, row in enumerate(g):
            for dx, c in enumerate(row):
                if c == "X":
                    out.append((x + dx, y0 + y, color))
        x += len(g[0]) + 1
    return out, x - 1


def text_width(s):
    return sum(len(FONT[c][0]) + 1 for c in s) - 1


def mark_cells(x0=0, y0=0, bg=True):
    out = []
    for y, row in enumerate(MARK):
        for x, c in enumerate(row):
            if c == ".":
                if bg:
                    out.append((x0 + x, y0 + y, ROOM))
            else:
                out.append((x0 + x, y0 + y, PAL[c]))
    return out


def svg(cells, w, h, unit, title, pad=0):
    """One <path> per colour, a unit square per cell, crisp edges."""
    by = {}
    for x, y, c in cells:
        by.setdefault(c, []).append(f"M{(x + pad) * unit} {(y + pad) * unit}h{unit}v{unit}h-{unit}z")
    W, H = (w + 2 * pad) * unit, (h + 2 * pad) * unit
    body = "\n".join(f'  <path fill="{c}" d="{"".join(p)}"/>' for c, p in by.items())
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'shape-rendering="crispEdges" role="img" aria-label="{title}">\n'
            f"  <title>{title}</title>\n{body}\n</svg>\n")


def raster(cells, w, h, scale, pad=0, bg=None):
    im = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), bg or (0, 0, 0, 0))
    for x, y, c in cells:
        im.putpixel((x + pad, y + pad), tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) + (255,))
    return im.resize(((w + 2 * pad) * scale, (h + 2 * pad) * scale), Image.NEAREST)


def main():
    # ---- the mark: an opaque square tile, like Open Fly's favicon ---------
    mark = mark_cells()
    open(f"{HERE}/logo-mark.svg", "w").write(svg(mark, 16, 16, 10, "Open Animal Stage"))
    raster(mark, 16, 16, 32).save(f"{HERE}/logo-mark.png", optimize=True)

    # ---- the lockup: mark, then the wordmark in two lines of 7 -------------
    # 16 cells tall = 7 + 2 + 7, so the two lines stand exactly as tall as the
    # tile. Paper for OPEN ANIMAL, amber for STAGE: the page's h1 does the same.
    gap = 4
    l1, _ = text_cells("OPEN ANIMAL", 16 + gap, 0, PAL["P"])
    l2, _ = text_cells("STAGE", 16 + gap, 9, PAL["A"])
    W = 16 + gap + max(text_width("OPEN ANIMAL"), text_width("STAGE"))
    cells = mark + l1 + l2
    pad = 2
    open(f"{HERE}/logo.svg", "w").write(svg(cells, W, 16, 10, "Open Animal Stage", pad=pad))
    # logo.png at 1024 and 512 wide, transparent around the tile
    for width, name in ((1024, "logo.png"), (512, "logo-512.png")):
        subprocess.run(["rsvg-convert", "-w", str(width), "-o", f"{HERE}/{name}", f"{HERE}/logo.svg"], check=True)

    # ---- favicon set, from the same 16x16 grid -----------------------------
    fav = f"{REPO}/docs/itch/favicon"
    os.makedirs(fav, exist_ok=True)
    base = raster(mark, 16, 16, 1)
    sizes = {}
    for s in (16, 32, 48, 64, 128, 180, 256, 512):
        im = base.resize((s, s), Image.NEAREST) if s % 16 == 0 else None
        if im is None:  # 180 is not a multiple of 16: pad the tile with room
            k = s // 16
            inner = base.resize((16 * k, 16 * k), Image.NEAREST)
            im = Image.new("RGBA", (s, s), ROOM)
            off = (s - 16 * k) // 2
            im.paste(inner, (off, off))
        sizes[s] = im
        im.save(f"{fav}/favicon-{s}.png", optimize=True)
    sizes[180].save(f"{fav}/apple-touch-icon.png", optimize=True)
    sizes[48].save(f"{fav}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)],
                   append_images=[sizes[16], sizes[32]])

    # a preview at real size on a light and a dark tab strip
    prev = Image.new("RGBA", (560, 200), (235, 235, 235, 255))
    prev.paste(sizes[128], (20, 36)); prev.paste(sizes[32], (170, 84)); prev.paste(sizes[16], (220, 92))
    dark = Image.new("RGBA", (260, 200), (40, 40, 44, 255))
    dark.paste(sizes[32], (40, 84)); dark.paste(sizes[16], (100, 92)); dark.paste(sizes[64], (150, 68))
    prev.paste(dark, (300, 0))
    prev.save(f"{HERE}/preview.png")
    print("ok", W, "cells wide")


if __name__ == "__main__":
    main()
