"""Download and cache every dataset the season model trains and predicts on.

    nflverse weekly player stats   1999 -> current season, one file a season
    nflverse schedule              every game, with closing Vegas spread/total
    FantasyPros ECR history        weekly expert snapshots 2019 -> now (via DynastyProcess)
    player ID crosswalk            FantasyPros id <-> nflverse gsis id, birthdates

Past seasons never change, so they are fetched once. The current season, the
schedule and the expert history move every week and are refreshed when stale.
"""
import datetime as dt
import json, os, re, time, urllib.request

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "cache")
NV = "https://github.com/nflverse/nflverse-data/releases/download"
DP = "https://github.com/dynastyprocess/data/raw/master/files"

FIRST_SEASON = 1999
SKILL = ("RB", "WR", "TE")
LIVE_MAX_AGE = 6 * 3600          # current-season files refresh after six hours


def current_season(today=None):
    today = today or dt.date.today()
    return today.year if today.month >= 8 else today.year - 1


def _fetch(url, path, max_age=None):
    fresh = os.path.exists(path) and (
        max_age is None or time.time() - os.path.getmtime(path) < max_age)
    if fresh:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
    os.replace(tmp, path)            # never leave a half-written file behind
    return path


def stats(seasons=None):
    """Regular-season weekly stats for skill players, one row per player-game."""
    now = current_season()
    seasons = seasons or range(FIRST_SEASON, now + 1)
    frames = []
    for y in seasons:
        p = _fetch(f"{NV}/stats_player/stats_player_week_{y}.parquet",
                   os.path.join(CACHE, "stats", f"week_{y}.parquet"),
                   LIVE_MAX_AGE if y == now else None)
        d = pd.read_parquet(p)
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    df = df[(df.season_type == "REG") & (df.position.isin(SKILL))].copy()
    # half PPR is not published, but it sits exactly between the two that are
    df["fp_half"] = (df.fantasy_points + df.fantasy_points_ppr) / 2
    return df


def snaps(seasons=None):
    """Offensive snap share per player-game. Published from 2012 only."""
    now = current_season()
    seasons = seasons or range(2012, now + 1)
    frames = []
    for y in seasons:
        p = _fetch(f"{NV}/snap_counts/snap_counts_{y}.parquet",
                   os.path.join(CACHE, "snaps", f"snap_{y}.parquet"),
                   LIVE_MAX_AGE if y == now else None)
        frames.append(pd.read_parquet(p))
    d = pd.concat(frames, ignore_index=True)
    return d[d.game_type == "REG"]


def xfp(seasons=None):
    """Expected fantasy points per player-game (ffopportunity). From 2006.

    What a player's opportunities were worth given where they happened, so the
    gap to actual points separates role from luck.
    """
    now = current_season()
    seasons = seasons or range(2006, now + 1)
    frames = []
    for y in seasons:
        p = _fetch(f"https://github.com/ffverse/ffopportunity/releases/download/latest-data/ep_weekly_{y}.parquet",
                   os.path.join(CACHE, "xfp", f"ep_{y}.parquet"),
                   LIVE_MAX_AGE if y == now else None)
        d = pd.read_parquet(p)
        frames.append(d[["season", "week", "player_id", "position", "total_fantasy_points_exp",
                         "total_fantasy_points_diff", "total_fantasy_points_exp_team"]])
    d = pd.concat(frames, ignore_index=True)
    d["season"] = d.season.astype(int)
    d["week"] = d.week.astype(int)
    return d


def injuries(seasons=None):
    """Official weekly injury reports (Out / Doubtful / Questionable). From 2009."""
    now = current_season()
    seasons = seasons or range(2009, now + 1)
    frames = []
    for y in seasons:
        p = _fetch(f"{NV}/injuries/injuries_{y}.parquet",
                   os.path.join(CACHE, "injuries", f"injuries_{y}.parquet"),
                   LIVE_MAX_AGE if y == now else None)
        d = pd.read_parquet(p, columns=["season", "week", "game_type", "gsis_id", "report_status"])
        frames.append(d[d.game_type == "REG"])
    d = pd.concat(frames, ignore_index=True)
    d["season"] = d.season.astype(int)
    d["week"] = d.week.astype(int)
    return d


def rosters(seasons=None):
    """Each player's roster status per week: active, inactive, injured reserve... From 2002."""
    now = current_season()
    seasons = seasons or range(2002, now + 1)
    frames = []
    for y in seasons:
        p = _fetch(f"{NV}/weekly_rosters/roster_weekly_{y}.parquet",
                   os.path.join(CACHE, "rosters", f"roster_{y}.parquet"),
                   LIVE_MAX_AGE if y == now else None)
        d = pd.read_parquet(p, columns=["season", "week", "game_type", "gsis_id", "position", "status"])
        frames.append(d[(d.game_type == "REG") & d.position.isin(SKILL)])
    d = pd.concat(frames, ignore_index=True)
    d["season"] = d.season.astype(int)
    d["week"] = d.week.astype(int)
    return d


def espn_injuries():
    """ESPN's live injury list: status, body part, and an expected return date.

    Current only -- ESPN keeps no history of past return dates, so this can
    steer a prediction but never be trained or backtested on.
    """
    p = _fetch("https://site.api.espn.com/apis/site/v2/sports/football/nfl/injuries",
               os.path.join(CACHE, "espn_injuries.json"), 3600)
    d = json.load(open(p, encoding="utf-8"))
    rows = []
    for t in d.get("injuries", []):
        for i in t.get("injuries", []):
            a, det = i.get("athlete") or {}, i.get("details") or {}
            link = next((l.get("href", "") for l in a.get("links", []) if "playercard" in l.get("rel", [])), "")
            m = re.search(r"/id/(\d+)", link)
            when = pd.to_datetime(i.get("date"), errors="coerce")
            note = i.get("shortComment") or ""
            rows.append({"espn_id": int(m.group(1)) if m else None, "name": a.get("displayName"),
                         "pos": (a.get("position") or {}).get("abbreviation"),
                         "status": i.get("status"), "type": det.get("type"), "detail": det.get("detail"),
                         "return_date": det.get("returnDate"), "updated": i.get("date"),
                         # dated like the archived page's comments: "Sep 28: ..."
                         "comment": f"{when:%b} {when.day}: {note}" if note and pd.notna(when) else note})
    return pd.DataFrame(rows)


def weekly_all(season):
    """One season's regular-season weekly stats for every position (stats() keeps skill players)."""
    p = _fetch(f"{NV}/stats_player/stats_player_week_{season}.parquet",
               os.path.join(CACHE, "stats", f"week_{season}.parquet"),
               LIVE_MAX_AGE if season == current_season() else None)
    d = pd.read_parquet(p)
    return d[d.season_type == "REG"]


def games():
    p = _fetch("https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv",
               os.path.join(CACHE, "games.csv"), LIVE_MAX_AGE)
    return pd.read_csv(p, low_memory=False)


def ecr():
    p = _fetch(f"{DP}/db_fpecr.parquet", os.path.join(CACHE, "db_fpecr.parquet"), LIVE_MAX_AGE)
    e = pd.read_parquet(p)
    e["scrape_date"] = pd.to_datetime(e.scrape_date)
    return e


def ids():
    p = _fetch(f"{DP}/db_playerids.csv", os.path.join(CACHE, "db_playerids.csv"), LIVE_MAX_AGE)
    return pd.read_csv(p, low_memory=False)


if __name__ == "__main__":
    t = time.time()
    s = stats()
    print(f"stats   {len(s):>8,} skill player-games, seasons {s.season.min()}-{s.season.max()}")
    g = games()
    print(f"games   {len(g):>8,} games, {g.spread_line.notna().sum():,} with a Vegas line")
    e = ecr()
    print(f"ecr     {len(e):>8,} expert rows, {e.scrape_date.min().date()} -> {e.scrape_date.max().date()}")
    i = ids()
    print(f"ids     {len(i):>8,} players in the crosswalk")
    print(f"({time.time() - t:.0f}s)")
