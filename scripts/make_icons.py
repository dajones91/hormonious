"""Draw the app icons (run once; the PNGs are committed in app/static/icons).

    .venv\\Scripts\\python.exe scripts\\make_icons.py

A chocolate-brown square with a cream "H" and a small sage leaf. iPhones round the
corners themselves, so the square fills the whole image with no transparency.
"""

from pathlib import Path

from PIL import Image, ImageDraw

CHOC, CREAM, SAGE = (154, 107, 75), (250, 246, 240), (111, 143, 92)
OUT = Path(__file__).resolve().parent.parent / "app" / "static" / "icons"


def draw(size: int) -> Image.Image:
    img = Image.new("RGB", (size, size), CHOC)
    d = ImageDraw.Draw(img)
    # A bold block "H": two thick uprights and a crossbar, with rounded ends.
    s = size / 100
    radius = 3 * s
    for x in (26, 61):
        d.rounded_rectangle([x * s, 27 * s, (x + 13) * s, 78 * s], radius=radius, fill=CREAM)
    d.rounded_rectangle([30 * s, 46 * s, 70 * s, 58 * s], radius=radius, fill=CREAM)
    # A sage leaf sprouting from the top of the right upright.
    d.ellipse([66 * s, 10 * s, 88 * s, 26 * s], fill=SAGE)
    d.line([(68 * s, 25 * s), (86 * s, 11 * s)], fill=CHOC, width=max(2, round(1.6 * s)))
    return img


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        draw(size).save(OUT / name, optimize=True)
        print("wrote", OUT / name)
