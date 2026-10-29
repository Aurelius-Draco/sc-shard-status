"""Draw the launcher icon (scstatus/assets/status.ico). Original artwork, MIT like the rest.

    python tools/make_icons.py

A signal trace across a dial on a graphite tile, drawn separately at every size so
the small ones stay sharp.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scstatus" / "assets"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
TILE, EDGE = (27, 31, 38), (66, 74, 88)
TEAL, AMBER = (76, 196, 176), (242, 169, 59)


def draw(size):
    ss = 8
    S = size * ss
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = round(S * 0.03)
    d.rounded_rectangle([pad, pad, S - pad, S - pad], radius=round(S * 0.18), fill=TILE,
                        outline=EDGE, width=max(ss, round(S * 0.02)))
    c, r = S / 2, S * 0.33
    w = max(ss * 2, round(S * 0.075))
    d.arc([c - r, c - r, c + r, c + r], start=150, end=390, fill=TEAL, width=w)
    pts = [(0.16, 0.56), (0.34, 0.56), (0.43, 0.34), (0.55, 0.74), (0.64, 0.50), (0.84, 0.50)]
    d.line([(x * S, y * S) for x, y in pts], fill=AMBER, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x * S - w / 2, y * S - w / 2, x * S + w / 2, y * S + w / 2], fill=AMBER)
    return im.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    imgs = [draw(s) for s in SIZES]
    imgs[-1].save(OUT / "status.ico", sizes=[(s, s) for s in SIZES], append_images=imgs[:-1])
    imgs[-1].save(OUT / "status.png")
    print("wrote", OUT / "status.ico")


if __name__ == "__main__":
    main()
