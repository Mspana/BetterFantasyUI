"""Why the model parts from the experts on a player, in a sentence the board can show.

The model can't say why it likes someone, so we ask it what-ifs. A player's
peers are the ten at his position the experts rank nearest him -- the players
they see him as. Give him the peers' typical numbers for one group of inputs
(his volume, say), keep everything else, and predict again: how far his
rest-of-season projection falls is how much that group lifts him above them.
The group that lifts him most (or sinks him most) is the model's reason, and
within it the single stat that does the most work is the one quoted.

It explains the model, not the experts, and the model's reasons can be wrong.

Each player gets up to two reasons each way ("u" for why the model is higher
than the experts, "d" for lower), so the board can show whichever matches the
live gap even after the experts' ranks have moved since this ran.
"""
import numpy as np
import pandas as pd

from . import features as F

PEERS = 10
MIN_POINTS = 1.5          # below this, over the rest of the season, it isn't a reason worth quoting
SECOND = 0.4              # a second reason must carry at least this share of the first one's weight
PLURAL = {"RB": "RBs", "WR": "WRs", "TE": "TEs"}

GROUPS = {
    "volume": ["tgt_g", "rec_g", "car_g", "opp_g", "tshare_cur", "ayshare_cur", "wopr_cur", "xfp_cur", "xshare_cur"],
    "snaps": ["snap_cur", "snap_last", "snap_healthy"],
    "scoring": ["ppg_cur", "yds_g", "td_g", "xdiff_cur", "ppg_healthy"],
    "history": ["g_prev", "ppg_prev", "tgt_g_prev", "car_g_prev", "opp_g_prev", "tshare_prev", "wopr_prev",
                "g_prev2", "ppg_prev2", "snap_prev", "xfp_prev", "xdiff_prev"],
    "profile": ["age", "draft_ovr", "seasons_in"],
    "team": ["implied_cur", "team_changed"],
    "health": ["g_cur", "missed_cur", "ir_now", "inactive_now", "off_roster", "inj_last", "inj_weeks",
               "ir_weeks", "ir_rule", "suspended_now"],
}
# stats measured on this season's games, meaningless for a player who hasn't played one
THIS_SEASON = {"tgt_g", "opp_g", "tshare_cur", "xfp_cur", "snap_cur", "snap_last", "ppg_cur", "td_g", "ppg_healthy"}


def _pick(v):
    return "undrafted" if pd.isna(v) else f"#{v:.0f} overall"


# stat -> (which way is better: +1 higher, -1 lower; short tag; how it's rounded: "%" or decimals;
#          the sentence, given his value, his peers' and "WRs"). "near" is "for WRs ranked near him".
STATS = {
    "tshare_cur": (+1, "targets", "%", "Target share {h} vs {q} {near}"),
    "tgt_g": (+1, "targets", 1, "{h} targets a game vs {q} {near}"),
    "opp_g": (+1, "touches", 1, "{h} touches + targets a game vs {q} {near}"),
    "xfp_cur": (+1, "usage", 1, "Usage worth {h} pts a game vs {q} {near}"),
    "snap_cur": (+1, "snaps", "%", "On the field for {h} of snaps vs {q} {near}"),
    "snap_last": (+1, "snaps", "%", "{h} of snaps last week vs {q} {near}"),
    "ppg_cur": (+1, "scoring", 1, "{h} pts a game so far vs {q} {near}"),
    "td_g": (+1, "TDs", 1, "{h} TDs a game so far vs {q} {near}"),
    "ppg_healthy": (+1, "scoring", 1, "{h} pts a game when healthy vs {q} {near}"),
    "ppg_prev": (+1, "last season", 1, "{h} pts a game last season vs {q} {near}"),
    "tshare_prev": (+1, "last season", "%", "Target share {h} last season vs {q} {near}"),
    "opp_g_prev": (+1, "last season", 1, "{h} touches + targets a game last season vs {q} {near}"),
    "snap_prev": (+1, "last season", "%", "{h} of snaps last season vs {q} {near}"),
    "g_prev": (+1, "durability", 0, "Played {h} games last season vs {q} {near}"),
    "ppg_prev2": (+1, "track record", 1, "{h} pts a game two seasons ago vs {q} {near}"),
    "age": (-1, "age", 0, "Age {h} vs {q} {near}"),
    "draft_ovr": (-1, "draft pick", None, "Drafted {h} vs {q} {near}"),
    "implied_cur": (+1, "offense", 1, "His offense is projected for {h} pts a game by Vegas vs {q} {near}"),
    "missed_cur": (-1, "missed games", 0, "Missed {h} games already this season"),
    "inj_weeks": (-1, "injury", 0, "On the injury report {h} weeks this season"),
    "inj_last": (-1, "injury", None, "On the injury report last week"),
    "suspended_now": (-1, "suspended", None, "Suspended"),
}
ONLY = {"opp_g": {"RB"}, "tgt_g": {"WR", "TE"}}
GAMES_TAG = "games"


def _fmt(v, how):
    if how == "%":
        return f"{v * 100:.0f}%"
    return f"{v:.{how}f}"


def _say(f, h, q, P):
    better, tag, how, text = STATS[f]
    near = f"for {P} ranked near him"
    if f == "draft_ovr":
        return text.format(h=_pick(h), q=_pick(q), near=near)
    if how is None:
        return text
    return text.format(h=_fmt(h, how), q=_fmt(q, how), near=near) \
               .replace("Missed 1 games", "Missed 1 game").replace("report 1 weeks", "report 1 week")


def _peers(df):
    """Median inputs (and expected games) of each player's PEERS nearest in expert rank at his position."""
    cols = F.FEATURES + ["m_games"]
    out = pd.DataFrame(index=df.index, columns=cols, dtype=float)
    for _, g in df.groupby("pos"):
        g = g.sort_values("expert_sk")
        A = g[cols].astype(float).to_numpy()
        n = len(g)
        for i in range(n):
            lo = max(0, min(i - PEERS // 2, n - PEERS - 1))
            idx = [j for j in range(lo, min(n, lo + PEERS + 1)) if j != i][:PEERS]
            if idx:
                out.loc[g.index[i]] = np.nanmedian(A[idx], axis=0)
    return out


def _quotable(f, h, q, s, pos, played):
    """Can stat f be quoted as a reason the model is higher (s=1) or lower (s=-1)?"""
    better, _, how, _ = STATS[f]
    if pos not in ONLY.get(f, {pos}):
        return False
    if f in THIS_SEASON and not played:
        return False
    if f == "draft_ovr":           # a lower pick number is better; undrafted is worst
        return (s > 0 and pd.notna(h) and (pd.isna(q) or h < q)) or \
               (s < 0 and (pd.isna(h) or (pd.notna(q) and h > q)))
    if how is None:                # a flag: quote it only when it's set
        return bool(h) and s < 0
    if pd.isna(h) or pd.isna(q):
        return False
    # it has to point the way of the call, and visibly so once rounded
    if s * better * (h - q) <= 0 or _fmt(h, how) == _fmt(q, how):
        return False
    return True


def explain(df, now, model, cutoff=None):
    """{board key: {"u": [[tag, sentence], ...], "d": [...]}} for every player the experts rank.

    df: predict.rank_up output (key, player_id, pos, expert_sk, m_ppg, m_games, back_week, p_return).
    now: the season's feature rows (player_id + F.FEATURES). model: the fitted ppg model.
    cutoff: the last week played, so a player due back next week isn't called out."""
    d = df[df.m_ppg.notna() & df.expert_sk.notna() & df.player_id.notna()]
    d = d[["key", "player_id", "pos", "expert_sk", "m_ppg", "m_games", "back_week", "p_return"]] \
        .merge(now[["player_id"] + F.FEATURES], on="player_id", how="inner") \
        .drop_duplicates("key").reset_index(drop=True)
    if d.empty:
        return {}
    X = d[F.FEATURES].astype(float)
    peer = _peers(d)
    games = d.m_games.to_numpy()

    def lift(cols):
        """Rest-of-season points each player loses when these inputs become his peers'."""
        Xs = X.copy()
        Xs[cols] = peer[cols].to_numpy()
        return (d.m_ppg.to_numpy() - model.predict(Xs)) * games

    group = {g: lift(cols) for g, cols in GROUPS.items()}
    group[GAMES_TAG] = (games - peer.m_games.to_numpy()) * d.m_ppg.to_numpy()
    single = {f: lift([f]) for f in STATS}

    out = {}
    for i, r in d.iterrows():
        P = PLURAL.get(r.pos, r.pos + "s")
        played = pd.notna(r.g_cur) and r.g_cur > 0
        entry = {}
        for side, s in (("u", 1), ("d", -1)):
            reasons, floor = [], MIN_POINTS
            for g in sorted(group, key=lambda g: -s * group[g][i]):
                weight = s * group[g][i]
                if len(reasons) == 2 or weight < floor:
                    break
                reason = None
                if g == GAMES_TAG:
                    h, q = r.m_games, peer.m_games[i]
                    out_now = pd.notna(r.back_week) and (cutoff is None or r.back_week > cutoff + 1)
                    if s < 0 and out_now and r.back_week < 99:
                        odds = f", {r.p_return:.0%} he makes it back" if pd.notna(r.p_return) else ""
                        reason = [GAMES_TAG, f"Out now: back around week {int(r.back_week)}{odds}"]
                    elif s < 0 and out_now:
                        reason = [GAMES_TAG, "Out for the season"]
                    elif abs(h - q) >= 1.5:
                        reason = [GAMES_TAG, f"Expected to play {h:.0f} more games vs {q:.0f} for {P} ranked near him"]
                elif g == "history" and s < 0 and pd.isna(r.ppg_prev) and pd.isna(r.g_prev):
                    reason = ["rookie", "Rookie: no NFL track record yet"]
                else:
                    best, best_lift = None, 0.0
                    for f in GROUPS[g]:
                        if f in STATS and _quotable(f, r[f], peer.at[i, f], s, r.pos, played):
                            v = s * single[f][i]
                            if v > best_lift:
                                best, best_lift = f, v
                    if best:
                        reason = [STATS[best][1], _say(best, r[best], peer.at[i, best], P)]
                if reason:
                    reasons.append(reason)
                    floor = max(MIN_POINTS, SECOND * weight)
            if reasons:
                entry[side] = reasons
        if entry:
            out[r.key] = entry
    return out
