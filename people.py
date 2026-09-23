"""Prepare the team-picker portraits.

Source photos vary from 0.46 to 1.03 in aspect and up to 2.8MB, so each is
cropped to a square and re-encoded small enough to put eight of them (times two
states) on one page. The crop sits above centre: these are portraits, and a
centred square on a tall photo cuts the head off.

    python people.py <out-dir>
"""
import io, json, os, sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = r"C:\Users\Matthew\Downloads\people"
SIZE = 560           # never upscaled past the source
QUALITY = 82
TOP_BIAS = 0.38      # 0.5 would be a centred crop; faces sit higher than that

# person -> ESPN team name. Taken from Matthew's list; note that gibby is on
# The Matt Fundraised Conference and chula is on Gibbin in it, not the reverse.
ROSTER = {
    "chula":    "Gibbin in it",
    "gibby":    "The Matt Fundraised Conference",
    "harrison": "Big body",
    "josiah":   "Jew England Patriots",
    "julian":   "Goyim Compliance Department",
    "kyle":     "Yallah Habibi",
    "matt":     "j*b",
    "vel":      "The Jeffries Mr. Bankers",
}
EXTS = (".jpg", ".jpeg", ".png", ".jfif", ".webp")


def find(name, second):
    """The file for a person, in either state, whatever it was saved as."""
    want = f"{name} 2" if second else name
    for f in sorted(os.listdir(SRC)):
        stem, ext = os.path.splitext(f)
        if ext.lower() in EXTS and stem.lower() == want:
            return os.path.join(SRC, f)
    return None


def square(path, dst):
    im = Image.open(path)
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    w, h = im.size
    side = min(w, h)
    left = (w - side) // 2
    top = int((h - side) * TOP_BIAS)
    im = im.crop((left, top, left + side, top + side))
    if side > SIZE:
        im = im.resize((SIZE, SIZE), Image.LANCZOS)
    im.save(dst, "WEBP", quality=QUALITY, method=6)
    return im.size[0], os.path.getsize(dst)


def main(out=None):
    # Default to a folder inside the project, which gets committed: the CI
    # runner has no access to the original photos and no Pillow, so this is a
    # one-off local step and the build just copies what it produced.
    out = out or os.path.join(HERE, "people_img")
    os.makedirs(out, exist_ok=True)
    people, missing = [], []

    for name in sorted(ROSTER):                      # alphabetical by person
        a, b = find(name, False), find(name, True)
        if not a:
            missing.append(name)
            continue
        rec = {"name": name, "team": ROSTER[name], "img": f"people/{name}.webp"}
        px, sz = square(a, os.path.join(out, f"{name}.webp"))
        line = f"  {name:9} {px}px {sz//1024:4} KB"
        if b:
            px2, sz2 = square(b, os.path.join(out, f"{name}-2.webp"))
            rec["img2"] = f"people/{name}-2.webp"
            line += f"   second {px2}px {sz2//1024:4} KB"
        else:
            line += "   (no second photo)"
        print(line)
        people.append(rec)

    if missing:
        print("missing photos for: " + ", ".join(missing), file=sys.stderr)
    with io.open(os.path.join(out, "people.json"), "w", encoding="utf-8") as f:
        json.dump(people, f, indent=1)
    total = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out)
                if f.endswith(".webp"))
    print(f"{len(people)} people, {total/1024:.0f} KB total -> {out}")
    return people


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
