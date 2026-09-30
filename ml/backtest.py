"""Walk-forward backtest: our model vs FantasyPros experts vs naive baselines.

For each test season T (2020 onward, where expert history exists) and each
week N the season is frozen at:
  - train only on seasons before T, so nothing from T's future leaks in
  - give the model T's weeks 1..N and nothing after
  - compare against the FantasyPros rest-of-season PPR ranks scraped right
    after week N of T -- the experts had the same weeks we did
  - score every method on what actually happened in weeks N+1..end

Seasons are never mixed at random: a player's later season carries his earlier
one as "last season" features, so a random split would hand the model the
answers it is being tested on.

The metric is Spearman rank correlation: we care about getting the ORDER
right, which is what drafts, waivers and trades turn on.

FROZEN (model version below). Every design choice so far was judged on
2020-2025, so those scores run a little optimistic; they are closed for
tuning. The honest test is 2026, which nothing was tuned on -- see ml/exam.py.

    python -m ml.backtest              # every freeze week 1-14, means over 2020-2025
    python -m ml.backtest --week 3     # one week, season by season
"""
import sys, time, warnings

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor

from . import data, features as F, injury_news as N, injury_labels as L

warnings.filterwarnings("ignore", category=RuntimeWarning)

MODEL_VERSION = "2026-09-29"
CUTOFF = 3
WEEKS = range(1, 15)
FIRST_TRAIN = 2008          # enough history; the backtest was no better reaching back to 2001
TEST = range(2020, 2026)
MIN_ROS_GAMES = 4           # rest-of-season ppg over fewer games is mostly noise
EXPERT_TOP = 200            # compare on the players the experts actually ranked


def ppg_model():
    return HistGradientBoostingRegressor(max_iter=400, learning_rate=0.04, max_leaf_nodes=24,
                                         min_samples_leaf=40, l2_regularization=1.0,
                                         random_state=7)


def avail_model():
    return HistGradientBoostingRegressor(max_iter=250, learning_rate=0.04, max_leaf_nodes=16,
                                         min_samples_leaf=60, random_state=7)


def enough_games(frame):
    """Rows whose rest of season is a real sample: 4+ games, or every game left
    when fewer remain (a late freeze; 17-week seasons before 2021)."""
    return frame.ros_g >= np.minimum(MIN_ROS_GAMES, frame.ros_possible)


def expert_snapshot(ecr, games, season, cutoff=CUTOFF):
    """ROS PPR ranks from the first scrape after week `cutoff` of `season` finished."""
    wk = games[(games.season == season) & (games.game_type == "REG")]
    end = pd.to_datetime(wk[wk.week == cutoff].gameday).max()
    ros = ecr[ecr.fp_page.str.contains("ros-ppr-overall", na=False)]
    after = ros[ros.scrape_date > end]
    if after.empty:
        return None, None
    when = after.scrape_date.min()
    snap = after[after.scrape_date == when][["id", "ecr", "pos"]].copy()
    return snap, when


def attach_experts(frame, snap, ids):
    x = ids.dropna(subset=["gsis_id", "fantasypros_id"]).copy()
    x["fantasypros_id"] = pd.to_numeric(x.fantasypros_id, errors="coerce")
    fp2gsis = x.dropna(subset=["fantasypros_id"]).drop_duplicates("fantasypros_id") \
               .set_index("fantasypros_id").gsis_id
    snap = snap.assign(gsis=pd.to_numeric(snap.id, errors="coerce").map(fp2gsis))
    rank = snap.dropna(subset=["gsis"]).drop_duplicates("gsis").set_index("gsis").ecr
    return frame.assign(ecr=frame.player_id.map(rank))


def spear(a, b):
    ok = a.notna() & b.notna()
    return spearmanr(a[ok], b[ok]).statistic if ok.sum() > 5 else np.nan


def score(df, col, target):
    """Pooled Spearman, plus the mean of the per-position Spearmans."""
    pooled = spear(df[col], df[target])
    by_pos = np.nanmean([spear(g[col], g[target]) for _, g in df.groupby("pos")])
    return pooled, by_pos


def load():
    return dict(st=data.stats(), gm=data.games(), ix=data.ids(), ecr=data.ecr(),
                extra=dict(snaps=data.snaps(), xfp=data.xfp(), injuries=data.injuries(),
                           rosters=data.rosters()))


def evaluate(cutoff, d):
    """Every test season frozen after `cutoff`: one result row and the scored players each."""
    st, gm, ix, ecr = d["st"], d["gm"], d["ix"], d["ecr"]
    seasons = range(FIRST_TRAIN, max(TEST) + 1)
    frames = {y: F.build(st, gm, ix, y, cutoff, **d["extra"]) for y in seasons}

    results, rows = [], []
    for T in TEST:
        train = pd.concat([frames[y] for y in seasons if y < T], ignore_index=True)
        fit = train[enough_games(train)]
        m = ppg_model().fit(fit[F.FEATURES], fit.ros_ppg)
        a = avail_model().fit(train[F.FEATURES], (train.ros_g / train.ros_possible).clip(0, 1))

        test = frames[T].copy()
        test["m_ppg"] = m.predict(test[F.FEATURES])
        test["m_avail"] = np.clip(a.predict(test[F.FEATURES]), 0, 1)
        test["m_games"] = test.m_avail * test.ros_possible
        test["m_total"] = test.m_ppg * test.m_games
        # the same return-date rule the live prediction uses, from ESPN's page
        # exactly as it was archived that week -- where that week was archived
        news = test
        if N.archived(T, cutoff):
            hist = L.attach(N.history(T, gm, cutoff), T)
            news = N.apply(test, hist, ix, gm, T, cutoff, N.return_params(gm, ix, st, before=T, cutoff=cutoff))
        test["m_total_news"] = test.m_ppg * news.m_games.values

        snap, when = expert_snapshot(ecr, gm, T, cutoff)
        if snap is None:
            continue
        test = attach_experts(test, snap, ix)
        test = test[test.ecr.notna() & (test.ecr <= EXPERT_TOP)]

        # higher is better for every score column
        e = (-test.ecr).rank(pct=True)
        test["s_expert"] = -test.ecr
        test["s_model"] = test.m_ppg
        test["s_blend"] = (test.m_ppg.rank(pct=True) + e) / 2
        test["s_model_total"] = test.m_total_news
        test["s_blend_total"] = (test.m_total_news.rank(pct=True) + e) / 2
        test["s_last"] = test.ppg_cur.fillna(test.ppg_prev)
        test["s_lastyr"] = test.ppg_prev.fillna(test.ppg_cur)

        played = test[enough_games(test)]
        row = {"season": T, "snapshot": when.date(), "n": len(test), "news": N.archived(T, cutoff)}
        for name, col in [("experts", "s_expert"), ("model", "s_model"), ("blend", "s_blend"),
                          ("so far", "s_last"), ("last season", "s_lastyr")]:
            row[name] = score(played, col, "ros_ppg")
        # rest-of-season TOTAL points: now availability counts, injuries included
        for name, col in [("tot_experts", "s_expert"), ("tot_model", "s_model_total"),
                          ("tot_blend", "s_blend_total")]:
            row[name] = score(test, col, "ros_pts")
        results.append(row)
        rows.append(test.assign(season=T, cutoff=cutoff))
    return results, rows


def mean(results, key, idx):
    return np.nanmean([r[key][idx] for r in results])


def detail(cutoff):
    t0 = time.time()
    results, rows = evaluate(cutoff, load())

    def show(title, keys, idx):
        print(title)
        print(f"  {'season':6} {'n':>4}  " + "".join(f"{k:>12}" for k in keys))
        for r in results:
            print(f"  {r['season']:<6} {r['n']:>4}  " + "".join(f"{r[k][idx]:>12.3f}" for k in keys))
        means = {k: mean(results, k, idx) for k in keys}
        print(f"  {'mean':6} {'':>4}  " + "".join(f"{means[k]:>12.3f}" for k in keys) + "\n")

    keys = ["experts", "model", "blend", "so far", "last season"]
    print(f"Frozen after week {cutoff}, model {MODEL_VERSION}\n")
    show("Points per game, rest of season -- all positions pooled (Spearman)", keys, 0)
    show("Points per game, rest of season -- within position, averaged", keys, 1)
    show("TOTAL rest-of-season points, injuries included -- pooled"
         + (" (ESPN return dates applied)" if all(r["news"] for r in results) else ""),
         ["tot_experts", "tot_model", "tot_blend"], 0)
    pd.concat(rows, ignore_index=True).to_parquet(data.os.path.join(data.CACHE, "backtest_rows.parquet"))
    print(f"({time.time() - t0:.0f}s)")


def summary(weeks=WEEKS):
    t0 = time.time()
    d = load()
    print(f"Walk-forward backtest, model {MODEL_VERSION}: each season predicted by a model trained only on")
    print(f"earlier seasons, frozen after week N, scored on the rest. Means over {min(TEST)}-{max(TEST)}.\n")
    print(f"        {'points per game':^22}  {'within position':^22}  {'total points':^22}")
    print(f"  week  {'experts  model  blend':>22}  {'experts  model  blend':>22}  {'experts  model  blend':>22}")
    allrows, tally = [], []
    for w in weeks:
        results, rows = evaluate(w, d)
        allrows += rows
        cells = [mean(results, k, i) for i, ks in ((0, ("experts", "model", "blend")),
                                                   (1, ("experts", "model", "blend")),
                                                   (0, ("tot_experts", "tot_model", "tot_blend")))
                 for k in ks]
        tally.append(cells)
        news = "*" if all(r["news"] for r in results) else " "
        print(f"  {w:>4}  " + "  ".join(" ".join(f"{c:>6.3f}" for c in cells[i:i + 3]) for i in (0, 3, 6)) + news)
    t = np.array(tally).mean(axis=0)
    print(f"  {'all':>4}  " + "  ".join(" ".join(f"{c:>6.3f}" for c in t[i:i + 3]) for i in (0, 3, 6)))
    print("\n  * total points include ESPN's archived return dates (only week 3 is archived)")
    pd.concat(allrows, ignore_index=True).to_parquet(data.os.path.join(data.CACHE, "backtest_weeks.parquet"))
    print(f"({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    if "--week" in sys.argv:
        detail(int(sys.argv[sys.argv.index("--week") + 1]))
    else:
        summary()
