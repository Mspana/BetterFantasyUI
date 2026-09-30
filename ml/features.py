"""One row per player-season, as the season looked at the end of a cutoff week.

Everything here must be knowable at that moment, or the backtest is a lie:
  - this season's weeks 1..cutoff
  - the previous two full seasons
  - age, draft slot, years in the league
  - Vegas implied points for games ALREADY played (future lines were not
    public at the cutoff, so they are never used)

The target is what happened after the cutoff: points per game over the rest of
the regular season, and how many of those games the player actually played.
"""
import numpy as np
import pandas as pd

SKILL = ("RB", "WR", "TE")
POINTS = {"ppr": "fantasy_points_ppr", "half": "fp_half", "std": "fantasy_points"}

FEATURES = [
    "pos_RB", "pos_WR", "pos_TE",
    "age", "draft_ovr", "seasons_in",
    # this season, weeks 1..cutoff
    "g_cur", "ppg_cur", "tgt_g", "rec_g", "car_g", "opp_g", "yds_g", "td_g",
    "tshare_cur", "ayshare_cur", "wopr_cur",
    # last season
    "g_prev", "ppg_prev", "tgt_g_prev", "car_g_prev", "opp_g_prev",
    "tshare_prev", "wopr_prev",
    # two seasons ago
    "g_prev2", "ppg_prev2",
    # team context
    "implied_cur", "team_changed",
    # how much of the offence the player is on the field for
    "snap_cur", "snap_last", "snap_prev",
    # what the opportunities were worth, and how far actual points ran from it
    "xfp_cur", "xdiff_cur", "xshare_cur", "xfp_prev", "xdiff_prev",
    # health, as of the cutoff week
    "missed_cur", "ir_now", "inactive_now", "off_roster", "inj_last", "inj_weeks",
    "ir_weeks", "ir_rule", "suspended_now",
    # this season with the games played hurt taken out
    "ppg_healthy", "snap_healthy",
]

# injury-report designations, by how likely the player is to sit
SEVERITY = {"Out": 3, "Doubtful": 2, "Questionable": 1, "Probable": 0}

# Before 2016 the weekly roster files carry each player's END-of-season status
# in every week, so "on IR in week 3" there really means "finishes the year on
# IR" -- the future, leaked. Roster status is only trusted from here on.
WEEKLY_STATUS_FROM = 2016
RESERVE = {"RES", "PUP", "RSN"}              # injured reserve, PUP, non-football injury
SUSPENDED = {"SUS", "EXE", "E14"}            # suspended, commissioner's exempt list


def ir_rule(season):
    """Minimum weeks an IR stint lasts under that season's rules.

    Through 2019 IR was mostly the end of a season (one or two players a team
    could bring back, after eight weeks). From 2020 any player can return,
    after three weeks, then four from 2022.
    """
    return 8 if season < 2020 else 3 if season < 2022 else 4


def hurt_weeks(injuries, season, cutoff, rosters=None):
    """(player, week) games played hurt: listed Questionable or worse that week,
    or hurt during it -- listed the week after, or put straight on IR (players
    on IR drop off the injury report). None when no reports exist."""
    if injuries is None or injuries.empty:
        return None
    i = injuries[(injuries.season == season) & (injuries.week <= cutoff)]
    if i.empty:
        return None
    i = i[i.report_status.map(SEVERITY).fillna(0) >= 1]
    hurt = set(zip(i.gsis_id, i.week)) | set(zip(i.gsis_id, i.week - 1))
    if rosters is not None and season >= WEEKLY_STATUS_FROM:
        r = rosters[(rosters.season == season) & (rosters.week <= cutoff) & rosters.status.isin(RESERVE)]
        hurt |= set(zip(r.gsis_id, r.week - 1))
    return hurt


def _healthy(frame, pid, week, hurt):
    """Rows of a weekly frame the player was not playing hurt in."""
    return frame[~pd.MultiIndex.from_arrays([frame[pid], frame[week]]).isin(list(hurt))]


def last_reg_week(games, season):
    g = games[(games.season == season) & (games.game_type == "REG")]
    return int(g.week.max()) if len(g) else 18


def implied_points(games):
    """Each team's Vegas-implied score per game, from the closing spread/total.

    nflverse spread_line is from the home side: positive = home favoured.
    """
    g = games[games.game_type == "REG"].dropna(subset=["spread_line", "total_line"])
    home = pd.DataFrame({"season": g.season, "week": g.week, "team": g.home_team,
                         "implied": (g.total_line + g.spread_line) / 2})
    away = pd.DataFrame({"season": g.season, "week": g.week, "team": g.away_team,
                         "implied": (g.total_line - g.spread_line) / 2})
    return pd.concat([home, away], ignore_index=True)


def _agg(df, pts):
    """Per-player totals and rates over whatever weeks df holds."""
    if df.empty:
        return pd.DataFrame()
    df = df.assign(
        _pts=df[pts].fillna(0),
        _opp=df.targets.fillna(0) + df.carries.fillna(0),
        _yds=df.receiving_yards.fillna(0) + df.rushing_yards.fillna(0),
        _td=df.receiving_tds.fillna(0) + df.rushing_tds.fillna(0),
    )
    a = df.sort_values("week").groupby("player_id").agg(
        g=("week", "nunique"),
        pts=("_pts", "sum"),
        tgt=("targets", "sum"), rec=("receptions", "sum"), car=("carries", "sum"),
        opp=("_opp", "sum"), yds=("_yds", "sum"), td=("_td", "sum"),
        tshare=("target_share", "mean"), ayshare=("air_yards_share", "mean"),
        wopr=("wopr", "mean"),
        team=("team", "last"), pos=("position", "last"), name=("player_display_name", "last"),
    )
    g = a.g.replace(0, np.nan)
    for col in ("pts", "tgt", "rec", "car", "opp", "yds", "td"):
        a[f"{col}_g"] = a[col] / g
    return a


def snap_features(snaps, ids, season, cutoff, hurt=None):
    """Snap share this season so far, last week alone, and last season.

    Snap counts are keyed by Pro-Football-Reference id, so they go through the
    crosswalk to reach the nflverse id everything else uses.
    """
    if snaps is None or snaps.empty:
        return pd.DataFrame()
    x = ids.dropna(subset=["pfr_id", "gsis_id"]).drop_duplicates("pfr_id").set_index("pfr_id").gsis_id
    sn = snaps.assign(player_id=snaps.pfr_player_id.map(x)).dropna(subset=["player_id"])
    sn = sn[sn.offense_snaps > 0]
    cur = sn[(sn.season == season) & (sn.week <= cutoff)]
    last = cur[cur.week == cur.week.max()] if len(cur) else cur
    prev = sn[sn.season == season - 1]
    out = pd.DataFrame({
        "snap_cur": cur.groupby("player_id").offense_pct.mean(),
        "snap_last": last.groupby("player_id").offense_pct.mean(),
        "snap_prev": prev.groupby("player_id").offense_pct.mean(),
    })
    if hurt is not None and len(cur):
        out["snap_healthy"] = _healthy(cur, "player_id", "week", hurt).groupby("player_id").offense_pct.mean()
    return out


def xfp_features(xfp, season, cutoff):
    if xfp is None or xfp.empty:
        return pd.DataFrame()
    cur = xfp[(xfp.season == season) & (xfp.week <= cutoff)]
    prev = xfp[xfp.season == season - 1]
    share = cur.total_fantasy_points_exp / cur.total_fantasy_points_exp_team.replace(0, np.nan)
    return pd.DataFrame({
        "xfp_cur": cur.groupby("player_id").total_fantasy_points_exp.mean(),
        "xdiff_cur": cur.groupby("player_id").total_fantasy_points_diff.mean(),
        "xshare_cur": share.groupby(cur.player_id).mean(),
        "xfp_prev": prev.groupby("player_id").total_fantasy_points_exp.mean(),
        "xdiff_prev": prev.groupby("player_id").total_fantasy_points_diff.mean(),
    })


def health_features(rows, games, injuries, rosters, season, cutoff):
    """Is the player hurt right now? Only what was public by the cutoff week.

    The roster file puts a player on reserve (IR) the week it happens, and the
    injury report names who is Out or Questionable -- the two things an expert
    reading the news knows and a box score does not.
    """
    out = pd.DataFrame(index=rows.index)
    g = games[(games.season == season) & (games.game_type == "REG") & (games.week <= cutoff)]
    played = pd.concat([g.home_team, g.away_team]).value_counts()
    out["missed_cur"] = (rows.team.map(played) - rows.g_cur).clip(lower=0)

    if rosters is not None and len(rosters) and season >= WEEKLY_STATUS_FROM:
        r = rosters[(rosters.season == season) & (rosters.week <= cutoff)]
        if len(r):
            last = r[r.week == r.week.max()].drop_duplicates("gsis_id").set_index("gsis_id").status
            st = last.reindex(rows.index)
            out["ir_now"] = st.isin(RESERVE).astype(float)
            out["inactive_now"] = (st == "INA").astype(float)
            out["suspended_now"] = st.isin(SUSPENDED).astype(float)
            out["off_roster"] = (st.isna() | ~st.isin(RESERVE | SUSPENDED | {"ACT", "INA"})).astype(float)
            # how much of the stint is already served, under the rules of the day
            res = r[r.status.isin(RESERVE)].groupby("gsis_id").week.nunique()
            out["ir_weeks"] = res.reindex(rows.index).fillna(0).where(out.ir_now == 1, 0)
            out["ir_rule"] = ir_rule(season)

    if injuries is not None and len(injuries):
        i = injuries[(injuries.season == season) & (injuries.week <= cutoff)]
        if len(i):
            i = i.assign(sev=i.report_status.map(SEVERITY))
            wk = i[i.week == i.week.max()].groupby("gsis_id").sev.max()
            out["inj_last"] = wk.reindex(rows.index).fillna(0)
            out["inj_weeks"] = i[i.sev > 0].groupby("gsis_id").week.nunique().reindex(rows.index).fillna(0)
    return out


def build(stats, games, ids, season, cutoff=3, scoring="ppr", with_target=True, snaps=None, xfp=None,
          injuries=None, rosters=None):
    pts = POINTS[scoring]
    s = stats
    cur = _agg(s[(s.season == season) & (s.week <= cutoff)], pts)
    prev = _agg(s[s.season == season - 1], pts)
    prev2 = _agg(s[s.season == season - 2], pts)

    # the population: anyone active this season so far, or a real contributor last year
    pop = set(cur.index) | set(prev[prev.g >= 4].index if len(prev) else [])
    rows = pd.DataFrame(index=sorted(pop))
    rows.index.name = "player_id"

    def take(frame, cols, prefix=""):
        for src, dst in cols:
            rows[dst] = frame[src].reindex(rows.index) if len(frame) else np.nan

    take(cur, [("g", "g_cur"), ("pts_g", "ppg_cur"), ("tgt_g", "tgt_g"), ("rec_g", "rec_g"),
               ("car_g", "car_g"), ("opp_g", "opp_g"), ("yds_g", "yds_g"), ("td_g", "td_g"),
               ("tshare", "tshare_cur"), ("ayshare", "ayshare_cur"), ("wopr", "wopr_cur")])
    take(prev, [("g", "g_prev"), ("pts_g", "ppg_prev"), ("tgt_g", "tgt_g_prev"),
                ("car_g", "car_g_prev"), ("opp_g", "opp_g_prev"),
                ("tshare", "tshare_prev"), ("wopr", "wopr_prev")])
    take(prev2, [("g", "g_prev2"), ("pts_g", "ppg_prev2")])
    rows["g_cur"] = rows.g_cur.fillna(0)

    # identity: prefer this season's team and position, fall back to last season's
    def first(*series):
        out = series[0]
        for x in series[1:]:
            out = out.combine_first(x)
        return out
    rows["team"] = first(cur.team.reindex(rows.index) if len(cur) else pd.Series(index=rows.index, dtype=object),
                         prev.team.reindex(rows.index) if len(prev) else pd.Series(index=rows.index, dtype=object))
    rows["pos"] = first(cur.pos.reindex(rows.index) if len(cur) else pd.Series(index=rows.index, dtype=object),
                        prev.pos.reindex(rows.index) if len(prev) else pd.Series(index=rows.index, dtype=object))
    rows["name"] = first(cur.name.reindex(rows.index) if len(cur) else pd.Series(index=rows.index, dtype=object),
                         prev.name.reindex(rows.index) if len(prev) else pd.Series(index=rows.index, dtype=object))
    rows = rows[rows.pos.isin(SKILL)]
    for p in SKILL:
        rows[f"pos_{p}"] = (rows.pos == p).astype(int)

    prev_team = prev.team.reindex(rows.index) if len(prev) else pd.Series(np.nan, index=rows.index)
    rows["team_changed"] = np.where(prev_team.isna(), np.nan,
                                    (prev_team != rows.team).astype(float))

    # years of NFL production before this season
    before = s[s.season < season].groupby("player_id").season.nunique()
    rows["seasons_in"] = before.reindex(rows.index).fillna(0)

    # age at 1 September, and draft slot (undrafted -> 260, past the last pick)
    x = ids.dropna(subset=["gsis_id"]).drop_duplicates("gsis_id").set_index("gsis_id")
    bd = pd.to_datetime(x.birthdate, errors="coerce").reindex(rows.index)
    rows["age"] = (pd.Timestamp(f"{season}-09-01") - bd).dt.days / 365.25
    rows["draft_ovr"] = pd.to_numeric(x.draft_ovr, errors="coerce").reindex(rows.index).fillna(260)

    # Vegas: how many points the market expected this team to score, games so far
    imp = implied_points(games)
    imp = imp[(imp.season == season) & (imp.week <= cutoff)].groupby("team").implied.mean()
    rows["implied_cur"] = rows.team.map(imp)

    hurt = hurt_weeks(injuries, season, cutoff, rosters)
    sf = snap_features(snaps, ids, season, cutoff, hurt)
    for col in ("snap_cur", "snap_last", "snap_prev", "snap_healthy"):
        rows[col] = sf[col].reindex(rows.index) if col in sf else np.nan

    xf = xfp_features(xfp, season, cutoff)
    for col in ("xfp_cur", "xdiff_cur", "xshare_cur", "xfp_prev", "xdiff_prev"):
        rows[col] = xf[col].reindex(rows.index) if col in xf else np.nan

    hf = health_features(rows, games, injuries, rosters, season, cutoff)
    for col in ("missed_cur", "ir_now", "inactive_now", "off_roster", "inj_last", "inj_weeks",
                "ir_weeks", "ir_rule", "suspended_now"):
        rows[col] = hf[col] if col in hf else np.nan

    # points per game in the games he was healthy for
    rows["ppg_healthy"] = np.nan
    wk = s[(s.season == season) & (s.week <= cutoff)]
    if hurt is not None and len(wk):
        rows["ppg_healthy"] = _healthy(wk, "player_id", "week", hurt)             .groupby("player_id")[pts].mean().reindex(rows.index)

    rows["season"] = season
    rows["cutoff"] = cutoff

    if with_target:
        end = last_reg_week(games, season)
        ros = _agg(s[(s.season == season) & (s.week > cutoff) & (s.week <= end)], pts)
        rows["ros_g"] = ros.g.reindex(rows.index).fillna(0) if len(ros) else 0
        rows["ros_pts"] = ros.pts.reindex(rows.index).fillna(0) if len(ros) else 0
        rows["ros_ppg"] = rows.ros_pts / rows.ros_g.replace(0, np.nan)
        rows["ros_possible"] = end - cutoff
    return rows.reset_index()


if __name__ == "__main__":
    import time
    from . import data
    t = time.time()
    st, gm, ix = data.stats(), data.games(), data.ids()
    f = build(st, gm, ix, 2024, cutoff=3)
    print(f"2024 as of week 3: {len(f)} players, {len(FEATURES)} features ({time.time()-t:.0f}s)")
    show = f[f.name.isin(["Jahmyr Gibbs", "Ja'Marr Chase", "Brock Bowers", "Malik Nabers"])]
    cols = ["name", "pos", "team", "age", "draft_ovr", "g_cur", "ppg_cur", "ppg_prev",
            "tshare_cur", "implied_cur", "ros_g", "ros_ppg"]
    print(show[cols].round(2).to_string(index=False))
    missing = f[FEATURES].isna().mean().sort_values(ascending=False).head(6)
    print("\nmost-missing features:", (missing * 100).round(0).astype(int).astype(str).add("%").to_dict())
