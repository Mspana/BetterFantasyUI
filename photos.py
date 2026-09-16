"""Download FantasyPros headshots for the players the report can surface.

Images are published as files alongside the artifact rather than inlined as
data URIs: same origin, so the page stays small and the CSP is satisfied.
D/ST ids resolve to a team logo through the same URL.
"""
import concurrent.futures as cf
import json, os, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
URL = "https://images.fantasypros.com/images/players/nfl/{pid}/headshot/70x70.png"


def fetch(pid, refresh=False):
    path = os.path.join(IMG, f"{pid}.png")
    if os.path.exists(path) and os.path.getsize(path) > 0 and not refresh:
        return pid, True
    try:
        req = urllib.request.Request(URL.format(pid=pid), headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            data = r.read()
        if not data:
            return pid, False
        with open(path, "wb") as f:
            f.write(data)
        return pid, True
    except urllib.error.HTTPError:
        return pid, False
    except Exception:
        return pid, False


def main():
    refresh = "--refresh" in sys.argv
    os.makedirs(IMG, exist_ok=True)
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = args[0] if args else os.path.join(HERE, "data.json")
    data = json.load(open(src, encoding="utf-8"))
    detail_path = os.path.join(os.path.dirname(os.path.abspath(src)), "details.json")
    keys = set(json.load(open(detail_path, encoding="utf-8"))) \
        if os.path.exists(detail_path) else None

    # same population details.py covers, so every clickable player has a face
    pids = {p["pid"] for p in data["players"]
            if p.get("pid") and (keys is None or p["key"] in keys)}
    print(f"Fetching {len(pids)} headshots...")

    ok = 0
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for pid, got in ex.map(lambda i: fetch(i, refresh), sorted(pids)):
            ok += bool(got)
    total = sum(os.path.getsize(os.path.join(IMG, f)) for f in os.listdir(IMG))
    print(f"{ok}/{len(pids)} saved to img/  ({total/1024/1024:.1f} MB)")


if __name__ == "__main__":
    main()
