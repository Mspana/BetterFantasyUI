"""Pull full FantasyPros consensus rankings from the public rankings pages.

The public API key is capped at the top 10 players per list, so we read the
same ecrData blob the rankings page itself renders from.
"""
import json, os, re, time, urllib.request

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
BASE = "https://www.fantasypros.com/nfl/rankings/"
CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")


def fetch(slug, refresh=False, max_age=3600):
    """Return the ecrData dict for a rankings page slug, e.g. 'ppr-superflex'."""
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"page_{slug}.json")
    if os.path.exists(path) and not refresh and time.time() - os.path.getmtime(path) < max_age:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    req = urllib.request.Request(BASE + slug + ".php", headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=45) as r:
        html = r.read().decode("utf-8", "replace")

    m = re.search(r"var\s+ecrData\s*=\s*", html)
    if not m:
        raise RuntimeError(f"no ecrData on {slug}.php")
    data, _ = json.JSONDecoder().raw_decode(html[html.index("{", m.end() - 1):])
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    time.sleep(1.0)
    return data
