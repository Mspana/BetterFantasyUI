"""Fetch per-player news and game logs from FantasyPros.

These live on one page each, so pulling them for all ~850 ranked players would be
~1700 requests. Instead this covers only players the report can actually surface:
everyone on a roster in the league, plus the top free agents.

Results are cached on disk, so re-runs during a week cost almost nothing.
"""
import concurrent.futures as cf
import json, os, re, sys, threading, time, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache", "detail")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")
SKILL = ("RB", "WR", "TE")

_throttle = threading.Semaphore(3)      # be polite: at most 3 in flight
_tag = re.compile(r"<[^>]+>")


def _text(s):
    return re.sub(r"\s+", " ", _tag.sub(" ", s)).replace("&nbsp;", " ").strip()


def _get(url, tries=3):
    for a in range(tries):
        try:
            with _throttle:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r:
                    return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if a == tries - 1:
                raise
            time.sleep(1.5 * (a + 1))
        except Exception:
            if a == tries - 1:
                raise
            time.sleep(1.5 * (a + 1))
    return None


def news(slug, limit=4):
    html = _get(f"https://www.fantasypros.com/nfl/news/{slug}.php")
    if not html:
        return []
    out = []
    # The author/date sit in a sibling foot-row, so split on the section marker
    # and keep each whole chunk rather than trying to match balanced divs.
    chunks = html.split('<div class="subsection feature-stretch')[1:]
    for block in chunks:
        m = re.search(r'<a href="/nfl/news/\d+/[^"]+"><b>(.*?)</b></a>(.*?)</div>', block, re.S)
        if not m:
            continue
        head, rest = _text(m.group(1)), m.group(2)
        paras = [_text(p) for p in re.findall(r"<p>(.*?)</p>", rest, re.S)]
        paras = [p for p in paras if p and p.lower() != "fantasy impact"]
        date = re.search(r'class="pull-right timestamp">(.*?)<', block)
        author = re.search(r'target="_blank">(.*?)</a>', block)
        out.append({"head": head,
                    "body": paras[0] if paras else "",
                    "impact": paras[1] if len(paras) > 1 else "",
                    "date": _text(date.group(1)) if date else "",
                    "by": _text(author.group(1)) if author else ""})
        if len(out) >= limit:
            break
    return out


def gamelog(slug, limit=6):
    html = _get(f"https://www.fantasypros.com/nfl/games/{slug}.php")
    if not html:
        return {}
    i = html.find("<table")
    if i < 0:
        return {}
    seg = html[i:i + 60000]
    heads = [_text(h) for h in re.findall(r"<th[^>]*>(.*?)</th>", seg, re.S)]
    # the header is two rows: group labels, then the real column names
    cols = heads[heads.index("OPP"):] if "OPP" in heads else heads
    rows = []
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", seg, re.S):
        cells = [_text(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
        if not cells or len(cells) < 4:
            continue
        if all(c in ("-", "") for c in cells[3:]):
            continue                      # unplayed future week
        if cells[0].lower().startswith(("total", "average", "avg")):
            continue                      # summary row, not a game
        rows.append(cells)
        if len(rows) >= limit:
            break
    return {"cols": ["Week"] + cols, "rows": rows} if rows else {}


def targets(data, top_fa=50):
    """Rostered players (any team) plus the best free agents."""
    ps = data["players"]
    want = {p["key"]: p for p in ps if p["owner"]}
    skill_fa = sorted([p for p in ps if not p["owner"] and p["pos"] in SKILL
                       and p["scales"]["week"]["skill"]],
                      key=lambda p: p["scales"]["week"]["skill"])[:top_fa]
    for p in skill_fa:
        want[p["key"]] = p
    for pos in ("QB", "DST", "K"):
        best = sorted([p for p in ps if not p["owner"] and p["pos"] == pos
                       and p["scales"]["week"]["pos_num"]],
                      key=lambda p: p["scales"]["week"]["pos_num"])[:5]
        for p in best:
            want[p["key"]] = p
    return [p for p in want.values() if p.get("slug")]


def one(p, refresh):
    path = os.path.join(CACHE, f"{p['slug']}.json")
    if os.path.exists(path) and not refresh:
        try:
            with open(path, encoding="utf-8") as f:
                return p["key"], json.load(f)
        except Exception:
            pass
    rec = {"news": news(p["slug"]), "log": gamelog(p["slug"])}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rec, f)
    return p["key"], rec


def main():
    refresh = "--refresh" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    src = args[0] if args else os.path.join(HERE, "data.json")
    os.makedirs(CACHE, exist_ok=True)
    data = json.load(open(src, encoding="utf-8"))
    tg = targets(data)
    print(f"Fetching news + game logs for {len(tg)} players "
          f"({sum(1 for p in tg if p['owner'])} rostered)...")

    out, done, failed = {}, 0, []
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(one, p, refresh): p for p in tg}
        for f in cf.as_completed(futs):
            p = futs[f]
            try:
                k, rec = f.result()
                out[k] = rec
            except Exception as e:
                failed.append(f"{p['name']}: {type(e).__name__}")
            done += 1
            if done % 25 == 0:
                print(f"  {done}/{len(tg)}")

    dst = os.path.join(os.path.dirname(os.path.abspath(src)), "details.json")
    json.dump(out, open(dst, "w", encoding="utf-8"))
    withnews = sum(1 for v in out.values() if v["news"])
    withlog = sum(1 for v in out.values() if v["log"])
    print(f"Wrote {dst}: {len(out)} players, {withnews} with news, {withlog} with a game log")
    if failed:
        print(f"{len(failed)} failed: {failed[:5]}")


if __name__ == "__main__":
    main()
