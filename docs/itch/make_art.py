"""Compose the itch.io art (cover, cover@2x, banner, thumbnail) from the model
renders in data/raw/previews/ and the pixel logo in docs/brand/.

    .venv/bin/python docs/brand/make_brand.py      # the logo first
    .venv/bin/python docs/itch/make_art.py

Two steps. Pillow cuts one tile per animal out of its render (the crop follows
the animal: foreground is whatever differs from the render's own backdrop), and
the layout is an HTML page per image, screenshotted by headless Chrome at 2x so
the type is real type. data/raw/ is gitignored, so the renders have to exist
locally. The tiles are written to docs/itch/art/ beside the three layouts, and
the counts on them are typed into art/wall.js from data/roster.json.

Fonts: Press Start 2P for the console lines (Open Fly's), JetBrains Mono and
Figtree (this page's), all OFL, from Google Fonts at render time.
"""
import json
import os
import subprocess
import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PREV = f"{REPO}/data/raw/previews"
ART = f"{HERE}/art"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# (id, render, label, detail, neurons line, role). Counts are data/roster.json's.
CAST = [
    ("drosophila_female", "flies/drosophila_female_front34.png", "Fruit fly", "adult female", "138,639 neurons", "plays"),
    ("drosophila_male", "flies/drosophila_male_front34.png", "Fruit fly", "adult male", "166,700 neurons", "plays"),
    ("zebrafish_larva", "vertebrates/zebrafish_larva_closeup.png", "Zebrafish", "larva, 7 days", "187,052 somas", "plays"),
    ("drosophila_larva", "flies/drosophila_larva_front34.png", "Fruit fly", "larva", "2,952 neurons", "plays"),
    ("c_elegans_herm", "worms/c_elegans_herm_wave_34.png", "Roundworm", "hermaphrodite", "302 neurons", "plays"),
    ("c_elegans_male", "worms/c_elegans_male_wave_34.png", "Roundworm", "male", "385 neurons", "plays"),
    ("ciona_larva", "worms/ciona_larva_wave_34.png", "Sea squirt", "larva", "207 neurons", "plays"),
    ("mouse_v1", "vertebrates/mouse_v1_front34.png", "Mouse", "visual cortex", "8,221 recorded neurons", "watches"),
]


# Framed by hand where the automatic crop is wrong: the mouse's render has a
# wall edge the foreground test takes for the animal.
BOXES = {"mouse_v1": (40, 200, 680, 680)}
FULL = {"zebrafish_larva"}
# the two adult flies were rendered from the same angle: face them at each other
FLIP = {"drosophila_male"}


def tile(src, out, aspect=1.0, margin=0.14, full=False, box=None):
    """Crop a render around its subject to the given w/h aspect.

    A render wider than the aspect (the worms, 1400x600) is first extended
    top and bottom by repeating its edge rows: the backdrop is a smooth
    gradient, so the seam does not show and the whole animal fits."""
    im = Image.open(src).convert("RGB")
    a = np.asarray(im)
    h, w, _ = a.shape
    if w / h > aspect * 1.3:
        extra = int((w / aspect - h) / 2)
        a = np.pad(a, ((extra, extra), (0, 0), (0, 0)), mode="edge")
        im = Image.fromarray(a)
        h = a.shape[0]
    a = a.astype(np.int16)
    if box is not None:
        box = tuple(box)
    elif full:
        box = (0, 0, w, h)
    else:
        # the backdrop is a smooth gradient: compare with a heavy blur of the
        # image's border, and keep what stands out from it
        bg = np.asarray(im.resize((8, 8), Image.BILINEAR).resize((w, h), Image.BILINEAR)).astype(np.int16)
        diff = np.abs(a - bg).sum(axis=2)
        mask = diff > 60
        ys, xs = np.nonzero(mask)
        lo_x, hi_x = np.percentile(xs, [0.5, 99.5]); lo_y, hi_y = np.percentile(ys, [0.5, 99.5])
        cx, cy = (lo_x + hi_x) / 2, (lo_y + hi_y) / 2
        bw, bh = (hi_x - lo_x) * (1 + 2 * margin), (hi_y - lo_y) * (1 + 2 * margin)
        if bw / bh > aspect:
            bh = bw / aspect
        else:
            bw = bh * aspect
        bw, bh = min(bw, w), min(bh, h)
        if bw / bh > aspect:
            bw = bh * aspect
        else:
            bh = bw / aspect
        x0 = int(max(0, min(w - bw, cx - bw / 2))); y0 = int(max(0, min(h - bh, cy - bh / 2)))
        box = (x0, y0, int(x0 + bw), int(y0 + bh))
    im = im.crop(box)
    if os.path.basename(out)[:-4] in FLIP:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    im.save(out, quality=92)
    return box


def main():
    os.makedirs(ART, exist_ok=True)
    boxes = {}
    for cid, rel, *_ in CAST:
        src = f"{PREV}/{rel}"
        if not os.path.exists(src):
            raise SystemExit(f"missing render {src}: data/raw/previews is local only")
        # the zebrafish close-up is already framed; the others are cut to the animal
        boxes[cid] = tile(src, f"{ART}/{cid}.jpg", aspect=4 / 3, margin=0.16,
                          full=cid in FULL, box=BOXES.get(cid))
    json.dump({"cast": CAST, "boxes": boxes}, open(f"{ART}/cast.json", "w"), indent=1)

    for name, (w, h) in {"cover": (630, 500), "banner": (1600, 500), "thumbnail": (1280, 720)}.items():
        page = f"{ART}/{name}.html"
        if not os.path.exists(page):
            raise SystemExit(f"missing {page}")
        scale = 2 if name == "cover" else 1
        outs = [(f"{HERE}/{name}.png", 1)] + ([(f"{HERE}/cover@2x.png", 2)] if name == "cover" else [])
        for out, s in outs:
            subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--disable-gpu",
                            f"--force-device-scale-factor={s}", f"--window-size={w},{h}",
                            "--virtual-time-budget=6000", f"--screenshot={out}", f"file://{page}"],
                           check=True, capture_output=True)
            got = Image.open(out)
            want = (w * s, h * s)
            if got.size != want:  # headless Chrome can add the window chrome's height
                got.crop((0, 0) + want).save(out)
            Image.open(out).convert("RGB").save(out, optimize=True)
            print(out, Image.open(out).size)


if __name__ == "__main__":
    main()
