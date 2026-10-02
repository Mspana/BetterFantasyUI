"""Season-to-date usage and receiving splits for the board's Advanced stats table.

Descriptive numbers, not predictions: how much of the offense runs through a
player, what that usage usually scores, what he has actually scored, where his
receiving yards come from (in the air or after the catch), and how good his
offense and quarterback are.

What tested on 2020-2025 (freeze weeks 3-8, against players the experts ranked
the same): scoring below his usage did NOT mean a player later beat the
experts' rank -- they already price the bounce-back -- while scoring above it
held up slightly. WRs ranked 61-150 whose share of yards after the catch was in
the top third of that group beat the experts' rank about 70% of the time, 55%
for the rest, in all six seasons; in the top 60 that edge didn't hold. The board
flags those WRs itself, from the experts' live ranks.
"""
import numpy as np
import pandas as pd

from . import data

MIN_TARGETS = 3           # below this, per-target and per-catch splits are mostly noise


def _r(v, d=1):
    return None if v is None or pd.isna(v) else round(float(v), d)


def advanced(now, season, cutoff):
    """{player_id: {...}} for the season's players, through week `cutoff`.

    now: the season's feature rows (ml.features.build), for usage, expected points and the Vegas line.
    Expected and actual points are PPR whatever the league plays: the usage model publishes PPR."""
    w = data.weekly_all(season)
    w = w[w.week <= cutoff]
    rec = w[w.position.isin(data.SKILL)].groupby("player_id").agg(
        tgt=("targets", "sum"), rec=("receptions", "sum"), ryd=("receiving_yards", "sum"),
        air=("receiving_air_yards", "sum"), yac=("receiving_yards_after_catch", "sum"))
    team = w.sort_values("week").groupby("player_id").team.last()
    # the quarterbacks' EPA per dropback (passes + sacks), whoever threw them for that team
    qb = w[w.position == "QB"].groupby("team").agg(epa=("passing_epa", "sum"), att=("attempts", "sum"),
                                                  sk=("sacks_suffered", "sum"))
    qb_epa = qb.epa / (qb.att + qb.sk).replace(0, np.nan)

    out = {}
    for r in now.itertuples():
        if not (pd.notna(r.g_cur) and r.g_cur > 0):
            continue
        x = rec.loc[r.player_id] if r.player_id in rec.index else None
        enough = x is not None and x.tgt >= MIN_TARGETS
        caught = enough and x.rec > 0
        e = {"g": int(r.g_cur), "tsh": _r(r.tshare_cur, 3), "opp": _r(r.opp_g),
             "xfp": _r(r.xfp_cur), "vs": _r(r.xdiff_cur),
             "pts": _r(r.xfp_cur + r.xdiff_cur) if pd.notna(r.xfp_cur) and pd.notna(r.xdiff_cur) else None,
             "rec": int(x.rec) if x is not None else 0,
             "adot": _r(x.air / x.tgt) if enough else None,
             "yacc": _r(x.yac / x.rec) if caught else None,
             "yacsh": _r(x.yac / x.ryd, 3) if caught and x.ryd > 0 else None,
             "imp": _r(r.implied_cur),
             "qb": _r(qb_epa.get(team.get(r.player_id), np.nan), 3)}
        out[r.player_id] = {k: v for k, v in e.items() if v is not None}
    return out
