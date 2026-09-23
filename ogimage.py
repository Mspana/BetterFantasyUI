"""Prepare the link-preview (Open Graph) image.

Social cards are 1200x630, or 1.91:1. The source is 4:3, so 326px has to go;
it comes off the bottom, which is legs and floor, rather than the middle,
which is the title and everyone's faces.

    python ogimage.py <source-image> <out-file>
"""
import os, sys

from PIL import Image

W, H = 1200, 630
TOP = 0.0        # 0 crops from the very top, 0.5 would centre it


def build(src, dst):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    want = round(w / (W / H))
    if want <= h:
        top = int((h - want) * TOP)
        im = im.crop((0, top, w, top + want))
    else:                       # source is wider than 1.91:1, trim the sides
        want_w = round(h * (W / H))
        left = (w - want_w) // 2
        im = im.crop((left, 0, left + want_w, h))
    im = im.resize((W, H), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    # JPEG, not PNG: this is a photograph, and PNG costs four times the bytes
    # for no visible gain on a card that renders at a few hundred pixels.
    im.save(dst, "JPEG", quality=86, optimize=True, progressive=True)
    print(f"{dst}  {W}x{H}  {os.path.getsize(dst)//1024} KB")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2])
