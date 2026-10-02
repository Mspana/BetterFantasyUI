"""Rest-of-season predictions for the current season, lined up against the experts.

    python -m ml.predict brunch
    python -m ml.predict poj

Trains on every season from 2008 through last year -- the configuration the
backtest settled on -- freezes this season at the last fully played week, and
predicts points per game, games played, total points and a stat line for the
rest of the regular season. Scoring (PPR / half / standard) comes from the
league's own settings.

The board's "Model" scale is the BLEND: the model's rank averaged with the
FantasyPros rest-of-season rank, which beat either alone at every week of the
backtest. Everything lands in leagues/<league>/model.json, which make_report.py
picks up.
"""
import io, json, os, sys, time, warnings

import numpy as np
import pandas as pd

from . import data, features as F, injury_news as N, injury_labels as L
from .explain import explain
from .advanced import advanced
from .backtest import ppg_model, avail_model, enough_games, FIRST_TRAIN, MODEL_VERSION

warnings.filterwarnings("ignore", category=RuntimeWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COMPARE_TOP = 200        # skill ranks deep enough to cover every roster and the useful waivers
MOVE = 20                # the Model this many places from the experts: right ~60% of the time in the backtest
SCORING = {1.0: "ppr", 0.5: "half", 0.0: "std"}
# the stat line: each is predicted per game, then multiplied by expected games
STATS = {"tgt": "targets", "rec": "receptions", "ryd": "receiving_yards", "rtd": "receiving_tds",
         "car": "carries", "uyd": "rushing_yards", "utd": "rushing_tds"}


def last_complete_week(games, season):
    g = games[(games.season == season) & (games.game_type == "REG")]
    done = g.groupby("week").home_score.apply(lambda s: s.notna().all())
    done = done[done]
    return int(done.index.max()) if len(done) else 0


def stat_targets(stats, games, season, cutoff):
    """Each player's per-game stat line over the rest of `season` after `cutoff`."""
    end = F.last_reg_week(games, season)
    s = stats[(stats.season == season) & (stats.week > cutoff) & (stats.week <= end)]
    per = s.groupby("player_id")[list(STATS.values())].sum()
    g = s.groupby("player_id").week.nunique()
    return per.div(g, axis=0).rename(columns={v: k for k, v in STATS.items()})


def train_and_predict(season, scoring, log=print, keep=None):
    """The season's rows with the model's predictions. Pass a dict as `keep`
    to get the fitted points-per-game model back in it, as keep["ppg"]."""
    t0 = time.time()
    st, gm, ix = data.stats(), data.games(), data.ids()
    sn, xf, inj, ros = data.snaps(), data.xfp(), data.injuries(), data.rosters()
    cutoff = last_complete_week(gm, season)
    if cutoff < 1:
        sys.exit(f"no complete week of {season} yet")
    extra = dict(snaps=sn, xfp=xf, injuries=inj, rosters=ros)

    train = pd.concat([F.build(st, gm, ix, y, cutoff, scoring, **extra)
                       .join(stat_targets(st, gm, y, cutoff), on="player_id")
                       for y in range(FIRST_TRAIN, season)], ignore_index=True)
    fit = train[enough_games(train)]
    m = ppg_model().fit(fit[F.FEATURES], fit.ros_ppg)
    if keep is not None:
        keep["ppg"] = m
    a = avail_model().fit(train[F.FEATURES], (train.ros_g / train.ros_possible).clip(0, 1))

    now = F.build(st, gm, ix, season, cutoff, scoring, with_target=False, **extra)
    left = F.last_reg_week(gm, season) - cutoff
    now["m_ppg"] = m.predict(now[F.FEATURES])
    now["m_avail"] = np.clip(a.predict(now[F.FEATURES]), 0, 1)
    now["m_games"] = now.m_avail * left
    for k in STATS:
        now[f"pg_{k}"] = np.clip(ppg_model().fit(fit[F.FEATURES], fit[k].fillna(0))
                                 .predict(now[F.FEATURES]), 0, None)
    try:
        live = L.attach(N.live(), season)
        hurt = live[(live.status != "Active") & live.pos.isin(F.SKILL) & (live.comment.fillna("") != "")]
        stale = int((~hurt.label_fresh).sum())
        params = N.return_params(gm, ix, st, before=season)
        now = N.apply(now, live, ix, gm, season, cutoff, params)
        log(f"ESPN return dates applied to {now.back_week.notna().sum()} players; "
            f"IR odds from {params['n'] if params else 0} past IR stints")
        if stale:
            log(f"  {stale} injury comments are new since they were labelled -- "
                "run: python -m ml.injury_labels pending, then have a subagent label them")
    except Exception as e:                      # the prediction stands without it
        log(f"ESPN injuries unavailable ({e}); using the model's own guess")
    now["m_total"] = now.m_ppg * now.m_games
    log(f"trained on {FIRST_TRAIN}-{season - 1} ({len(fit):,} player-seasons), "
        f"{season} frozen after week {cutoff}, {left} weeks left ({time.time() - t0:.0f}s)")
    return now, cutoff


def attach(board_players, pred, ids):
    """Every board skill player, with his model row where the model has one.

    A player the model cannot see (a rookie who has not played yet, an id the
    crosswalk misses) still gets a blend rank from the experts alone."""
    x = ids.dropna(subset=["gsis_id", "fantasypros_id"]).copy()
    x["fantasypros_id"] = pd.to_numeric(x.fantasypros_id, errors="coerce")
    fp2gsis = x.dropna(subset=["fantasypros_id"]).drop_duplicates("fantasypros_id") \
               .set_index("fantasypros_id").gsis_id
    p = pred.set_index("player_id")
    rows = []
    for bp in board_players:
        if bp["pos"] not in F.SKILL:
            continue
        gsis = fp2gsis.get(bp.get("pid"))
        r = p.loc[gsis] if gsis is not None and gsis in p.index else None
        expert = bp["scales"]["ros"]["skill"]
        if r is None and expert is None:
            continue
        row = {"key": bp["key"], "name": bp["name"], "pos": bp["pos"], "team": bp["team"],
               "owner": bp.get("owner"), "mine": bool(bp.get("mine")), "expert_sk": expert,
               "player_id": gsis if r is not None else None}
        if r is not None:
            row.update({
                "m_ppg": r.m_ppg, "m_games": r.m_games, "m_total": r.m_total,
                "ppg_cur": r.ppg_cur, "ir_now": r.ir_now, "inj_last": r.inj_last,
                "back_week": r.get("back_week"), "p_return": r.get("p_return"), "injury": r.get("injury"),
                **{f"pg_{k}": r[f"pg_{k}"] for k in STATS}})
        rows.append(row)
    return pd.DataFrame(rows)


def rank_up(df):
    """Model, expert and blend ranks on the board's skill-rank scale."""
    df = df.copy()
    df["model_sk"] = df.m_total.rank(ascending=False, method="first")
    ranked = df.expert_sk.notna()
    # a player the experts do not rank at all sits below everyone they do
    e_pct = (-df.expert_sk).rank(pct=True).where(ranked, 0.0)
    m_pct = df.m_total.rank(pct=True)
    df["blend"] = (e_pct + m_pct.fillna(e_pct)) / 2
    df["blend_sk"] = df.blend.rank(ascending=False, method="first").astype(int)
    df["blend_pn"] = df.groupby("pos").blend.rank(ascending=False, method="first").astype(int)
    # how far the blend moves him from the experts, in the experts' top 200 (+ = higher)
    df["move"] = (df.expert_sk - df.blend_sk).where(df.expert_sk.le(COMPARE_TOP))
    return df


def load_board(league):
    path = os.path.join(ROOT, "leagues", league, "data.json")
    return json.load(io.open(path, encoding="utf-8"))


def board_entry(r):
    """One player's slice of model.json, keyed the way the board reads it."""
    e = {"sk": int(r.blend_sk), "pr": f"{r.pos}{int(r.blend_pn)}", "pn": int(r.blend_pn)}
    if isinstance(getattr(r, "adv", None), dict):
        e["adv"] = r.adv
    if pd.isna(r.m_total):
        return e
    e.update({"msk": int(r.model_sk), "ppg": round(r.m_ppg, 1), "g": round(r.m_games, 1),
              "pts": round(r.m_total),
              "line": {k: round(getattr(r, f"pg_{k}") * r.m_games, 1 if k.endswith("td") else 0) for k in STATS}})
    if isinstance(getattr(r, "why", None), dict):
        e["why"] = r.why
    if pd.notna(r.back_week):
        e.update({"back": int(r.back_week) if r.back_week < 99 else None,
                  "pb": round(r.p_return, 2) if pd.notna(r.p_return) else None,
                  "inj": r.injury if isinstance(r.injury, str) else None})
    return e


def main(league):
    board = load_board(league)
    lg = board["league"]
    scoring = SCORING.get(float(lg["ppr"]), "ppr")
    print(f"{lg['name']}  ({scoring.upper()})")
    keep = {}
    pred, cutoff = train_and_predict(board["season"], scoring, keep=keep)
    # the 2026 final exam: one PPR snapshot a week, taken the first time it can be
    try:
        from . import exam
        exam.snapshot(board["season"], *((pred, cutoff) if scoring == "ppr" else ()))
    except Exception as e:                      # never let the exam block a prediction
        print(f"exam: snapshot skipped ({e})")
    df = rank_up(attach(board["players"], pred, data.ids()))
    # the model's reason for parting from the experts, each way, for the board to quote
    why = explain(df, pred, keep["ppg"], cutoff)
    df["why"] = df.key.map(why)
    print(f"reasons for {len(why)} players")
    # season-to-date usage and receiving splits for the board's Advanced stats table
    df["adv"] = df.player_id.map(advanced(pred, board["season"], cutoff))
    top = df[(df.expert_sk.fillna(999) <= COMPARE_TOP) | (df.model_sk <= COMPARE_TOP)]

    def table(title, rows):
        print(f"\n{title}")
        print(f"  {'player':24}{'pos':>4}{'experts':>9}{'model':>7}{'blend':>7}"
              f"{'ppg now':>9}{'m ppg':>7}{'m gms':>7}  owner")
        for _, r in rows.iterrows():
            e = f"{int(r.expert_sk)}" if pd.notna(r.expert_sk) else "--"
            mk = f"{int(r.model_sk)}" if pd.notna(r.model_sk) else "--"
            flag = " IR" if r.get("ir_now") == 1 else (" inj" if (r.get("inj_last") or 0) >= 2 else "")
            if pd.notna(r.get("back_week")) and r.back_week > cutoff + 1:
                flag += (f" wk{int(r.back_week)}" + (f" {r.p_return:.0%}" if pd.notna(r.p_return) else "")) \
                        if r.back_week < 99 else " out"
            print(f"  {(r['name'] + flag)[:24]:24}{r.pos:>4}{e:>9}{mk:>7}{int(r.blend_sk):>7}"
                  f"{r.get('ppg_cur', np.nan):>9.1f}{r.get('m_ppg', np.nan):>7.1f}{r.get('m_games', np.nan):>7.1f}"
                  f"  {r.owner if isinstance(r.owner, str) else 'FA'}")

    table(f"YOUR ROSTER ({board['my_team']['name']}) -- ranked by blend", top[top.mine].sort_values("blend_sk"))
    table(f"MODEL {MOVE}+ PLACES ABOVE THE EXPERTS", top[top.move >= MOVE].sort_values("move", ascending=False).head(12))
    table("BEST FREE AGENTS BY BLEND", top[top.owner.isna()].sort_values("blend_sk").head(10))

    out = {r.key: board_entry(r) for r in df.itertuples()}
    path = os.path.join(ROOT, "leagues", league, "model.json")
    json.dump({"season": board["season"], "cutoff": cutoff, "scoring": scoring,
               "trained": f"{FIRST_TRAIN}-{board['season'] - 1}", "version": MODEL_VERSION,
               "experts_updated": board["boards"]["ros"].get("updated"),
               "experts": board["boards"]["ros"].get("experts"),
               "players": out},
              io.open(path, "w", encoding="utf-8"), separators=(",", ":"))
    print(f"\nwrote {path} ({len(out)} players)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "brunch")
