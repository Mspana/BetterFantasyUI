"""The final exam: 2026, the one season nothing was tuned on.

Every design choice was judged on 2020-2025 (ml/backtest.py), so those scores
run a little optimistic. This is the honest test. Each week, once the week has
been played and FantasyPros has updated its rest-of-season board, the frozen
model's projections and the experts' ranks are saved side by side -- the same
moment, the same information. As the season plays out both are scored on what
happened, exactly the way the backtest scores past seasons.

    python -m ml.exam snapshot     # once a week, after the week is played
                                   # (ml.predict takes one automatically)
    python -m ml.exam score        # any time; final once the season ends

Snapshots live in ml/exam/<season>/ and are never overwritten. They hold
FantasyPros' ranks, so they stay out of the public repo.
"""
import glob, io, json, os, sys, time

import numpy as np
import pandas as pd

import fpweb

from . import data
from .backtest import MODEL_VERSION, EXPERT_TOP, MIN_ROS_GAMES, score

HERE = os.path.dirname(os.path.abspath(__file__))
DIR = os.path.join(HERE, "exam")
PAGE = "ros-ppr-overall"         # the board the backtest's expert history comes from


def _path(season, cutoff):
    return os.path.join(DIR, str(season), f"week{cutoff:02d}.json")


def _updated(d, season):
    ts = d.get("last_updated_ts")
    if ts:
        return pd.to_datetime(int(ts), unit="ms" if int(ts) > 1e12 else "s")
    mo, day = (int(v) for v in str(d.get("last_updated", "")).split("/")[:2])
    return pd.Timestamp(season + (1 if mo < 8 else 0), mo, day)


def experts(games, season, cutoff):
    """FantasyPros' ROS PPR ranks, or None while the board predates the week's games."""
    d = fpweb.fetch(PAGE, refresh=True)
    if d.get("ranking_type_name") != "ros" or not d.get("players"):
        raise RuntimeError(f"{PAGE}.php did not return rest-of-season rankings")
    g = games[(games.season == season) & (games.game_type == "REG")]
    last_game = pd.to_datetime(g[g.week == cutoff].gameday).max()
    updated = _updated(d, season)
    if updated.normalize() <= last_game.normalize():
        return None, updated, d
    return {int(p["player_id"]): int(p["rank_ecr"]) for p in d["players"]}, updated, d


def snapshot(season=None, pred=None, cutoff=None, log=print):
    """Save this week's model and expert ranks, once, if the experts are up to date."""
    season = season or data.current_season()
    if pred is None:
        from .predict import train_and_predict
        pred, cutoff = train_and_predict(season, "ppr", log=lambda *a: None)
    path = _path(season, cutoff)
    if os.path.exists(path):
        return path
    ranks, updated, raw = experts(data.games(), season, cutoff)
    if ranks is None:
        log(f"exam: FantasyPros' board was last updated {updated:%b %d}, before week {cutoff} "
            "finished -- no snapshot yet")
        return None
    ix = data.ids().dropna(subset=["gsis_id", "fantasypros_id"])
    g2fp = ix.assign(fp=pd.to_numeric(ix.fantasypros_id, errors="coerce")).dropna(subset=["fp"]) \
             .drop_duplicates("gsis_id").set_index("gsis_id").fp.astype(int)
    players = []
    for r in pred.itertuples():
        fp = g2fp.get(r.player_id)
        players.append({"player_id": r.player_id, "name": r.name, "pos": r.pos, "team": r.team,
                        "ppg": round(float(r.m_ppg), 3), "games": round(float(r.m_games), 3),
                        "total": round(float(r.m_total), 2),
                        "ecr": ranks.get(fp) if fp is not None else None})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump({"season": season, "cutoff": cutoff, "model_version": MODEL_VERSION,
               "saved": time.strftime("%Y-%m-%dT%H:%M:%S"), "experts_updated": f"{updated:%Y-%m-%d %H:%M} UTC",
               "experts": raw.get("total_experts"), "players": players},
              io.open(path, "w", encoding="utf-8"), indent=0)
    log(f"exam: saved the week-{cutoff} snapshot ({sum(p['ecr'] is not None for p in players)} "
        f"players the experts rank) -> {path}")
    return path


def score_season(season=None):
    season = season or data.current_season()
    files = sorted(glob.glob(os.path.join(DIR, str(season), "week*.json")))
    if not files:
        print(f"no exam snapshots for {season} yet")
        return
    from .predict import last_complete_week
    gm = data.games()
    done = last_complete_week(gm, season)
    end = int(gm[(gm.season == season) & (gm.game_type == "REG")].week.max())
    st = data.stats([season])
    print(f"{season} final exam -- scored through week {done}"
          + ("" if done >= end else f" of {end} (provisional)"))
    print(f"        {'points per game':^22}  {'within position':^22}  {'total points':^22}")
    print(f"  week  {'experts  model  blend':>22}  {'experts  model  blend':>22}  {'experts  model  blend':>22}  weeks scored")
    tally = []
    for f in files:
        snap = json.load(open(f, encoding="utf-8"))
        c = snap["cutoff"]
        if done <= c:
            print(f"  {c:>4}  (no games played since)")
            continue
        s = st[(st.week > c) & (st.week <= done)]
        agg = s.groupby("player_id").agg(ros_g=("week", "nunique"), ros_pts=("fantasy_points_ppr", "sum"))
        df = pd.DataFrame(snap["players"])
        df = df[df.ecr.notna() & (df.ecr <= EXPERT_TOP)].copy()
        df["ros_g"] = df.player_id.map(agg.ros_g).fillna(0)
        df["ros_pts"] = df.player_id.map(agg.ros_pts).fillna(0)
        df["ros_ppg"] = df.ros_pts / df.ros_g.replace(0, np.nan)
        e = (-df.ecr).rank(pct=True)
        df["s_expert"] = -df.ecr
        df["s_blend"] = (df.ppg.rank(pct=True) + e) / 2
        df["s_blend_total"] = (df.total.rank(pct=True) + e) / 2
        played = df[df.ros_g >= min(MIN_ROS_GAMES, done - c)]
        cells = [*[score(played, col, "ros_ppg")[0] for col in ("s_expert", "ppg", "s_blend")],
                 *[score(played, col, "ros_ppg")[1] for col in ("s_expert", "ppg", "s_blend")],
                 *[score(df, col, "ros_pts")[0] for col in ("s_expert", "total", "s_blend_total")]]
        tally.append(cells)
        print(f"  {c:>4}  " + "  ".join(" ".join(f"{v:>6.3f}" for v in cells[i:i + 3]) for i in (0, 3, 6))
              + f"  {c + 1}-{done}")
    if len(tally) > 1:
        t = np.nanmean(tally, axis=0)
        print(f"  {'all':>4}  " + "  ".join(" ".join(f"{v:>6.3f}" for v in t[i:i + 3]) for i in (0, 3, 6)))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "score"
    if cmd == "snapshot":
        snapshot()
    else:
        score_season(int(sys.argv[2]) if len(sys.argv) > 2 else None)
