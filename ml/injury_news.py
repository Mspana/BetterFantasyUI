"""ESPN's injury list as it stood at the cutoff: status, expected return, comment.

Live, it comes from ESPN's public injuries feed. For past seasons it comes from
the Wayback Machine's captures of espn.com/nfl/injuries, which archived the page
almost daily -- so each season is read exactly as it looked the week-3 Tuesday,
with nothing known later leaking in. Same source both ways, so what the model
trains on is what it sees live.

    python -m ml.injury_news            # fetch and summarise every past season
"""
import datetime as dt
import html, json, os, re, time, urllib.request

import numpy as np
import pandas as pd

from . import data

CACHE = os.path.join(data.CACHE, "espn_injuries")
PAGE = "espn.com/nfl/injuries"
FIRST_SEASON = 2020              # the page carries return dates from here on
# Players healthy through week 3 in 2020-2025 played 78% of the rest; it caps
# an Out / Questionable player's games from his return date.
HEALTHY_RATE = 0.78
# Before there is enough IR history to measure (2020, the first archived
# season), an IR player plays this share of the games after ESPN's date.
IR_RETURNER_RATE = 0.68
MIN_HISTORY = 40                 # IR players needed to measure how stints played out
LONG_TERM = re.compile(r"Reserve|PUP|Physically Unable", re.I)   # IR, PUP, NFI...
SKILL = ("RB", "WR", "TE")
MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], 1)}


def _get(url, tries=8):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            return urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "ignore")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(10 * (i + 1))      # the archive sheds load with 503s


def cutoff_window(games, season, cutoff=3):
    """From the day the cutoff week's last game was played to the next kickoff."""
    g = games[(games.season == season) & (games.game_type == "REG")]
    last = pd.to_datetime(g[g.week == cutoff].gameday).max()
    nxt = pd.to_datetime(g[g.week == cutoff + 1].gameday).min()
    return last, nxt


def _capture(season, games, cutoff):
    """The first capture after the cutoff week, before the next week kicks off.
    Failing that, the last one on the cutoff week's final day."""
    last, nxt = cutoff_window(games, season, cutoff)
    rows = json.loads(_get(
        f"http://web.archive.org/cdx/search/cdx?url={PAGE}&from={last:%Y%m%d}&to={nxt:%Y%m%d}"
        "&output=json&filter=statuscode:200"))[1:]
    stamps = [r[1] for r in rows]
    before_kickoff = [s for s in stamps if s[:8] < f"{nxt:%Y%m%d}"]
    after = [s for s in before_kickoff if s[:8] > f"{last:%Y%m%d}"]
    pick = after[0] if after else (before_kickoff[-1] if before_kickoff else None)
    return pick


def _parse(page, season):
    out = []
    for row in re.findall(r'<tr class="Table__TR[^"]*"[^>]*>(.*?)</tr>', page, re.S):
        link = re.search(r'/nfl/player/_/id/(\d+)/[^"]*">(.*?)</a>', row)
        cell = lambda c: re.search(rf'class="col-{c} Table__TD">(.*?)</td>', row, re.S)
        if not link or not cell("pos"):
            continue
        text = lambda c: html.unescape(re.sub(r"<[^>]+>", "", cell(c).group(1))).strip() if cell(c) else ""
        out.append({"espn_id": int(link.group(1)), "name": html.unescape(link.group(2)),
                    "pos": text("pos"), "status": text("stat"),
                    "return_date": _date(text("date"), season), "comment": text("desc")})
    return out


def _date(s, season):
    """'Oct 6' -> 2024-10-06; January-July belong to the next calendar year."""
    m = re.match(r"([A-Z][a-z]{2})\w* (\d{1,2})", s or "")
    if not m or m.group(1) not in MONTHS:
        return None
    mo = MONTHS[m.group(1)]
    return dt.date(season + (1 if mo < 8 else 0), mo, int(m.group(2))).isoformat()


def archived(season, cutoff=3):
    """Whether that week's page has been fetched -- the backtest never fetches on its own."""
    return os.path.exists(os.path.join(CACHE, f"{season}_wk{cutoff}.json"))


def history(season, games, cutoff=3):
    """The injury page as it stood at `season`'s cutoff, cached for good."""
    path = os.path.join(CACHE, f"{season}_wk{cutoff}.json")
    if os.path.exists(path):
        return pd.DataFrame(json.load(open(path, encoding="utf-8"))["rows"])
    stamp = _capture(season, games, cutoff)
    if stamp is None:
        return pd.DataFrame()
    rows = _parse(_get(f"http://web.archive.org/web/{stamp}/https://www.espn.com/nfl/injuries"), season)
    os.makedirs(CACHE, exist_ok=True)
    json.dump({"season": season, "capture": stamp, "rows": rows},
              open(path, "w", encoding="utf-8"), indent=0)
    return pd.DataFrame(rows)


def live():
    """The same table from ESPN's live feed, in the same shape."""
    d = data.espn_injuries()
    if d.empty:
        return d
    return pd.DataFrame({
        "espn_id": d.espn_id, "name": d.name, "pos": d.get("pos"),
        "status": d.status, "comment": d.comment,
        "injury": [" ".join(v for v in (t, x) if isinstance(v, str) and v != "Not Specified") or None
                   for t, x in zip(d.type, d.detail)],
        "return_date": pd.to_datetime(d.return_date, errors="coerce").dt.date.astype(str)
                        .where(d.return_date.notna(), None),
    })


def _injury(comment):
    """The page names the injury in brackets: 'Ali (neck) has been placed on IR'."""
    m = re.search(r"\(([a-z][a-z /-]{2,30})\)", comment or "")
    return m.group(1) if m else None


def _espn_to_gsis(ids):
    x = ids.dropna(subset=["espn_id", "gsis_id"]).copy()
    x["espn_id"] = pd.to_numeric(x.espn_id, errors="coerce")
    return x.dropna(subset=["espn_id"]).drop_duplicates("espn_id").set_index("espn_id").gsis_id


def return_params(games, ids, stats, before, cutoff=3, labels=None):
    """How IR stints actually played out in the archived seasons before `before`.

    ESPN's date is the earliest a player may return, so it is always early.
    For each kind of comment (a timeline given / season-ending / no detail):
    the share of players who came back that season, and how many weeks after
    ESPN's week they did -- plus the share of games returners then played.
    None while there is too little history.
    """
    from . import injury_labels as L
    labels = L.load() if labels is None else labels
    e2g = _espn_to_gsis(ids)
    rows = []
    for y in range(FIRST_SEASON, before):
        t = history(y, games, cutoff)
        if t.empty:
            continue
        t = t[t.pos.isin(SKILL) & t.status.fillna("").map(lambda v: bool(LONG_TERM.search(v)))]
        t = L.attach(t, y, labels)
        s = stats[(stats.season == y) & (stats.week > cutoff)]
        mattered = stats[stats.season.isin([y, y - 1])].groupby("player_id").week.nunique()
        team = stats[stats.season <= y].sort_values(["season", "week"]).groupby("player_id").team.last()
        g = games[(games.season == y) & (games.game_type == "REG") & (games.week > cutoff)]
        for r in t.itertuples():
            pid = e2g.get(r.espn_id)
            if pid is None or mattered.get(pid, 0) < 4 or pid not in team.index or not r.return_date:
                continue
            tg = g[(g.home_team == team[pid]) | (g.away_team == team[pid])]
            est = tg[pd.to_datetime(tg.gameday) >= pd.Timestamp(r.return_date)].week.min()
            ps = s[s.player_id == pid]
            back = ps.week.min() if len(ps) else np.nan
            rows.append({"cls": r.sev_class, "est": est, "back": back, "played": ps.week.nunique(),
                         "possible": int((tg.week >= back).sum()) if len(ps) else 0})
    d = pd.DataFrame(rows)
    if len(d) < MIN_HISTORY:
        return None
    came = d.dropna(subset=["back", "est"])
    out = {"n": len(d), "rate": d.played.sum() / max(d.possible.sum(), 1)}
    for c in ("timeline", "unknown", "season_ending"):
        g = d[d.cls == c]
        gc = g.dropna(subset=["back", "est"])
        out[c] = {"n": len(g),
                  "p": g.back.notna().mean() if len(g) else d.back.notna().mean(),
                  "delay": float((gc.back - gc.est).median()) if len(gc) >= 3
                           else float((came.back - came.est).median())}
    return out


def apply(now, inj, ids, games, season, cutoff, params=None):
    """Swap the model's average-IR guess for ESPN's expected return date.

    The model only knows a player is hurt, so every IR stint looks like the
    historical average. For a long-term (IR / PUP) player, `params` from
    return_params() says how that kind of stint went before: the chance he
    comes back, how far past ESPN's date, and how much he plays once back.
    `inj` carries the comment's class from injury_labels.attach(); unlabelled
    comments count as "no detail". For anyone else the date only caps the
    model's estimate. `now` needs player_id, team and m_games (games over the
    remaining WEEKS).
    """
    now = now.copy()
    now["m_games_model"] = now.m_games
    now["back_week"] = np.nan
    now["p_return"] = np.nan
    now["injury"] = None
    now["news_status"] = None
    if inj is None or inj.empty:
        return now
    inj = inj.assign(player_id=inj.espn_id.map(_espn_to_gsis(ids))).dropna(subset=["player_id", "return_date"])
    if "sev_class" not in inj:
        inj = inj.assign(sev_class="unknown")
    if "injury" not in inj:
        inj = inj.assign(injury=inj.comment.map(_injury))
    inj = inj.drop_duplicates("player_id").set_index("player_id")

    g = games[(games.season == season) & (games.game_type == "REG") & (games.week > cutoff)]
    sched = pd.concat([g[["home_team", "gameday", "week"]].rename(columns={"home_team": "team"}),
                       g[["away_team", "gameday", "week"]].rename(columns={"away_team": "team"})])
    sched["gameday"] = pd.to_datetime(sched.gameday)
    left = g.week.max() - cutoff

    cols = {c: now.columns.get_loc(c) for c in ("back_week", "p_return", "injury", "news_status", "m_games")}
    for i, (pid, team) in enumerate(zip(now.player_id, now.team)):
        if pid not in inj.index:
            continue
        r = inj.loc[pid]
        s = sched[sched.team == team]
        if s.empty:
            continue
        after = s[s.gameday >= pd.Timestamp(r.return_date)]
        espn_week = after.week.min() if len(after) else 99
        now.iloc[i, cols["injury"]] = r.injury
        now.iloc[i, cols["news_status"]] = r.status
        # the model's games are per remaining WEEK (bye included), so keep that scale
        per_game = left / len(s)
        long_term = bool(LONG_TERM.search(r.status or ""))
        if long_term and params and espn_week < 99:
            c = params[r.sev_class or "unknown"]
            back = espn_week + max(c["delay"], 0)
            now.iloc[i, cols["back_week"]] = round(back)
            now.iloc[i, cols["p_return"]] = c["p"]
            now.iloc[i, cols["m_games"]] = c["p"] * params["rate"] * (s.week >= back).sum() * per_game
        elif long_term:
            now.iloc[i, cols["back_week"]] = espn_week
            now.iloc[i, cols["m_games"]] = IR_RETURNER_RATE * len(after) * per_game
        else:
            now.iloc[i, cols["back_week"]] = espn_week
            now.iloc[i, cols["m_games"]] = min(now.m_games.iloc[i], HEALTHY_RATE * len(after) * per_game)
    return now


def table(season, games, cutoff=3, current=None):
    """History for past seasons, the live feed for the current one."""
    current = current or data.current_season()
    return live() if season == current else history(season, games, cutoff)


if __name__ == "__main__":
    gm = data.games()
    for y in range(FIRST_SEASON, data.current_season()):
        t = history(y, gm)
        cap = json.load(open(os.path.join(CACHE, f"{y}_wk3.json"), encoding="utf-8"))["capture"]
        sk = t[t.pos.isin(["RB", "WR", "TE"])] if len(t) else t
        print(f"{y}: capture {cap}  {len(t):>4} listed, {len(sk):>3} RB/WR/TE, "
              f"{sk.return_date.notna().mean():.0%} with a return date, "
              f"{(sk.comment.str.len() > 0).mean():.0%} with a comment")
