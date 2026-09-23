"""Build the site favicon from a portrait.

The source is a head on a white field, so the square is taken from the ink
rather than the canvas: a centred crop of the whole image would be mostly
background and the face would vanish at 16px.

    python favicon.py <source-image> <out-dir>
"""
import os, sys

from PIL import Image, ImageChops

ICO = (16, 32, 48, 64)
PNGS = {"icon-192.png": 192, "icon-512.png": 512, "apple-touch-icon.png": 180}
MARGIN = 0.05    # breathing room around the subject, as a fraction of its height


def content_box(im, tol=14):
    rgb = im.convert("RGB")
    white = Image.new("RGB", rgb.size, (255, 255, 255))
    mask = ImageChops.difference(rgb, white).convert("L").point(lambda p: 255 if p > tol else 0)
    return mask.getbbox() or (0, 0, *im.size)


def crop_head(path):
    """Square framing of the subject, padded rather than cropped.

    The head is taller than the source is wide, so any square crop takes the
    chin off. Pad to square on the same white field instead: a smaller face
    reads better than a severed one.
    """
    im = Image.open(path).convert("RGB")
    l, t, r, b = content_box(im)
    pad = int((b - t) * MARGIN)
    l, t = max(0, l - pad), max(0, t - pad)
    r, b = min(im.size[0], r + pad), min(im.size[1], b + pad)
    subject = im.crop((l, t, r, b))
    side = max(subject.size)
    square = Image.new("RGB", (side, side), (255, 255, 255))
    square.paste(subject, ((side - subject.size[0]) // 2,
                           (side - subject.size[1]) // 2))
    return square


def main(src, out=None):
    out = out or os.getcwd()
    os.makedirs(out, exist_ok=True)
    head = crop_head(src)

    big = head.resize((512, 512), Image.LANCZOS)
    big.save(os.path.join(out, "favicon.ico"), sizes=[(s, s) for s in ICO])
    print(f"  favicon.ico      {', '.join(f'{s}x{s}' for s in ICO)}")
    for name, size in PNGS.items():
        big.resize((size, size), Image.LANCZOS).save(os.path.join(out, name), optimize=True)
        print(f"  {name:17} {size}x{size}  "
              f"{os.path.getsize(os.path.join(out, name))//1024} KB")
    # a large preview so the crop can be eyeballed before it ships
    big.save(os.path.join(out, "_favicon-preview.png"))
    print(f"  source crop {head.size[0]}px square")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(*sys.argv[1:])
