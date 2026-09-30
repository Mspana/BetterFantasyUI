"""Build the static site published at gibdulbas.it/fantasy.

The artifact build embeds its data, because a published artifact may not fetch
anything. GitHub Pages has no such restriction, so the site fetches its data
instead -- which matters when a scheduled job rewrites it every hour: the shell
stays byte-identical and only the changed JSON lands in a commit.

    python build_site.py <league> <out-dir>
    python build_site.py <league> <out-dir> --hidden   # unlisted: no link card, not indexed
"""
import hashlib, io, json, os, re, shutil, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = ("RB", "WR", "TE")
KEEP_SKILL = 200        # ranked skill players kept beyond the rostered ones
KEEP_SIDE = 25          # per side position (QB / DST / K)


def trim_players(payload):
    """Drop players the page can never surface, which is most of the tail."""
    ps = payload["players"]
    keep = {p["k"] for p in ps if p["own"]}

    skill = [p for p in ps if p["p"] in SKILL and p["s"]["ros"]["sk"]]
    skill.sort(key=lambda p: p["s"]["ros"]["sk"])
    keep.update(p["k"] for p in skill[:KEEP_SKILL])
    # the weekly board can rank someone the rest-of-season board does not
    weekly = [p for p in ps if p["p"] in SKILL and p["s"]["week"]["sk"]]
    weekly.sort(key=lambda p: p["s"]["week"]["sk"])
    keep.update(p["k"] for p in weekly[:KEEP_SKILL])

    for pos in ("QB", "DST", "K"):
        c = [p for p in ps if p["p"] == pos and p["s"]["week"]["pn"]]
        c.sort(key=lambda p: p["s"]["week"]["pn"])
        keep.update(p["k"] for p in c[:KEEP_SIDE])

    payload["players"] = [p for p in ps if p["k"] in keep]
    return keep


def load_people():
    """The prepared portraits' manifest, every league's."""
    man = os.path.join(HERE, "people_img", "people.json")
    return json.load(io.open(man, encoding="utf-8")) if os.path.exists(man) else []


def copy_people(out, people):
    """Copy only the portraits this league's page shows."""
    if not people:
        return
    src = os.path.join(HERE, "people_img")
    dst = os.path.join(out, "people")
    os.makedirs(dst, exist_ok=True)
    for rec in people:
        for key in ("img", "img2"):
            rel = rec.get(key)
            if not rel:
                continue
            f = os.path.basename(rel)
            target = os.path.join(dst, f)
            if not os.path.exists(target):
                shutil.copy(os.path.join(src, f), target)


def split(html, people=None):
    """Pull the embedded payload out and rewrite the page to fetch it."""
    m = re.search(r"<script>window\.__DATA__ = (\{.*?\});</script>\s*<script>(.*?)</script>\s*$",
                  html, re.S)
    if not m:
        raise RuntimeError("could not find the embedded payload and page script")
    payload, js = json.loads(m.group(1)), m.group(2)

    a = "const D = window.__DATA__;"
    if a not in js:
        raise RuntimeError("page script no longer starts from window.__DATA__")
    js = js.replace(a, "", 1)

    news = payload.pop("detail", {})
    # The site copies assets next to the page, so no climb back up is needed
    # and the portraits are served from people/, not people_img/.
    payload["base"] = ""
    if people:
        # the portraits are shared across leagues; the picker shows this league's teams only
        teams = {p["own"] for p in payload["players"] if p.get("own")}
        payload["people"] = [r for r in people if r["team"] in teams]
    payload["people"] = [dict(r, img="people/" + os.path.basename(r["img"]),
                              img2=("people/" + os.path.basename(r["img2"]))
                                   if r.get("img2") else None)
                         for r in payload.get("people", [])]
    keep = trim_players(payload)
    news = {k: v for k, v in news.items() if k in keep}

    # Cache-bust and stamp from CONTENT, never the clock. A timestamp rewrites
    # the shell and the data every hour and defeats the point of committing
    # only what changed.
    def digest(obj):
        return hashlib.sha1(json.dumps(obj, separators=(",", ":"), sort_keys=True)
                            .encode()).hexdigest()[:10]

    # No cache-busting query string: Pages serves these with a ten minute
    # cache, well inside an hourly refresh, and leaving the shell free of any
    # varying token keeps it byte-identical forever -- so an hourly commit
    # carries the data that changed and nothing else.
    payload.pop("build", None)
    payload["build"] = digest(payload)[:6]
    loader = (
        '<script type="module">\n'
        'const [D, NEWS] = await Promise.all([\n'
        '  fetch("data.json").then(r => r.json()),\n'
        '  fetch("news.json").then(r => r.json())\n'
        ']);\n'
        'D.detail = NEWS;\n'
        f'{js}\n'
        '</script>\n'
    )
    # An artifact is wrapped in a skeleton that supplies the doctype, charset
    # and viewport. Pages serves this file raw, so without these a phone
    # assumes a 980px viewport -- skipping the 2-column rule -- and the whole
    # page renders in quirks mode.
    head = (
        '<!doctype html>\n'
        '<html lang="en">\n'
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
    )
    return head + html[:m.start()] + loader, payload, news


def hide(html):
    """An unlisted board: no link-preview card, and asked out of search engines."""
    html = re.sub(r'<meta (?:property="og:|name="twitter:)[^>]*>\n?', "", html)
    return html.replace('<meta charset="utf-8">\n',
                        '<meta charset="utf-8">\n<meta name="robots" content="noindex, nofollow">\n', 1)


def main(league="brunch", out=None, hidden=False):
    src = os.path.join(HERE, "leagues", league, "report.html")
    if not os.path.exists(src):
        sys.exit(f"no built report for '{league}' -- run run.py {league} first")
    out = out or os.path.join(HERE, "site")
    os.makedirs(os.path.join(out, "img"), exist_ok=True)

    html, data, news = split(io.open(src, encoding="utf-8").read(), load_people())
    copy_people(out, data["people"])
    people = data["people"]
    html = html.replace(f'src="../../site_assets/{league}-og.jpg"', 'src="og.jpg"')
    html = html.replace(f'src="site_assets/{league}-og.jpg"', 'src="og.jpg"')
    if hidden:
        html = hide(html)

    def write(name, obj):
        path = os.path.join(out, name)
        blob = json.dumps(obj, separators=(",", ":"), sort_keys=True)
        old = io.open(path, encoding="utf-8").read() if os.path.exists(path) else None
        if old != blob:
            io.open(path, "w", encoding="utf-8").write(blob)
        return len(blob), old != blob

    n1, c1 = write("data.json", data)
    n2, c2 = write("news.json", news)

    index = os.path.join(out, "index.html")
    old = io.open(index, encoding="utf-8").read() if os.path.exists(index) else None
    if old != html:
        io.open(index, "w", encoding="utf-8").write(html)

    card = os.path.join(HERE, "site_assets", f"{league}-og.jpg")
    if os.path.exists(card):
        dst_card = os.path.join(out, "og.jpg")
        if (not os.path.exists(dst_card)
                or os.path.getsize(dst_card) != os.path.getsize(card)):
            shutil.copy(card, dst_card)

    copied = 0
    for pid in data.get("photos", {}):
        dst = os.path.join(out, "img", pid + ".png")
        if not os.path.exists(dst):
            shutil.copy(os.path.join(HERE, "img", pid + ".png"), dst)
            copied += 1

    print(f"{out}")
    print(f"  index.html {len(html)/1024:7.0f} KB  {'changed' if old != html else 'unchanged'}")
    print(f"  data.json  {n1/1024:7.0f} KB  {'changed' if c1 else 'unchanged'}  "
          f"({len(data['players'])} players)")
    print(f"  news.json  {n2/1024:7.0f} KB  {'changed' if c2 else 'unchanged'}  "
          f"({len(news)} players)")
    print(f"  img/       {copied} new, {len(data.get('photos', {}))} referenced")
    print(f"  people/    {len(people)} portraits")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(*args, hidden="--hidden" in sys.argv)
