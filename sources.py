"""Which FantasyPros pages to read, per scoring format and ranking scale.

Three scales, all read off the same OP (QB/RB/WR/TE) overall board so ranks are
directly comparable between them:

    draft  -- preseason consensus, i.e. draft-day reputation
    week   -- this week's consensus
    ros    -- rest of season

FantasyPros publishes NO weekly list that ranks K and D/ST against skill
players, so those two positions are carried on their own positional boards and
kept out of the overall table.

FantasyPros also serves a generic draft page (HTTP 200) for unknown slugs
instead of 404ing, so every fetch is validated against what the page claims.
"""

SCALES = ("draft", "week", "ros")


def tier(ppr):
    return 1.0 if ppr >= 0.75 else (0.5 if ppr >= 0.25 else 0.0)


# Cross-position overall board (QB/RB/WR/TE together).
OVERALL = {
    ("draft", 1.0): "ppr-superflex-cheatsheets",
    ("draft", 0.5): "half-point-ppr-superflex-cheatsheets",
    ("draft", 0.0): "superflex-cheatsheets",
    ("week", 1.0): "ppr-superflex",
    ("week", 0.5): "half-point-ppr-superflex",
    ("week", 0.0): "superflex",
    ("ros", 1.0): "ros-ppr-superflex",
    ("ros", 0.5): "ros-half-point-ppr-superflex",
    ("ros", 0.0): "ros-superflex",
}

# RB/WR/TE-only board -- the correct cross-position order for a 1-QB league,
# since the overall board above is built for superflex and lifts QBs.
FLEX = {
    ("draft", 1.0): "ppr-cheatsheets", ("draft", 0.5): "half-point-ppr-cheatsheets",
    ("draft", 0.0): "consensus-cheatsheets",
    ("week", 1.0): "ppr-flex", ("week", 0.5): "half-point-ppr-flex", ("week", 0.0): "flex",
    ("ros", 1.0): "ros-ppr-flex", ("ros", 0.5): "ros-half-point-ppr-flex",
    ("ros", 0.0): "ros-flex",
}

# Positional boards -- coverage backbone. No single list is a superset of the
# others (the OP board carries 124 RBs where ppr-rb carries 112), and a player's
# positional rank is format-independent, so these fill the gaps safely.
_SKILL = {
    ("draft", 1.0): ["ppr-rb-cheatsheets", "ppr-wr-cheatsheets", "ppr-te-cheatsheets"],
    ("draft", 0.5): ["half-point-ppr-rb-cheatsheets", "half-point-ppr-wr-cheatsheets",
                     "half-point-ppr-te-cheatsheets"],
    ("draft", 0.0): ["rb-cheatsheets", "wr-cheatsheets", "te-cheatsheets"],
    ("week", 1.0): ["ppr-rb", "ppr-wr", "ppr-te"],
    ("week", 0.5): ["half-point-ppr-rb", "half-point-ppr-wr", "half-point-ppr-te"],
    ("week", 0.0): ["rb", "wr", "te"],
    ("ros", 1.0): ["ros-ppr-rb", "ros-ppr-wr", "ros-ppr-te"],
    ("ros", 0.5): ["ros-half-point-ppr-rb", "ros-half-point-ppr-wr", "ros-half-point-ppr-te"],
    ("ros", 0.0): ["ros-rb", "ros-wr", "ros-te"],
}
_QB = {"draft": "qb-cheatsheets", "week": "qb", "ros": "ros-qb"}

# Kicker and defense: separate boards, never mixed into the overall table.
KDST = {"draft": ["dst-cheatsheets", "k-cheatsheets"], "week": ["dst", "k"],
        "ros": ["ros-dst", "ros-k"]}


def pages(scale, ppr):
    """(overall_slug, flex_slug, skill+qb coverage slugs, k/dst slugs)."""
    t = tier(ppr)
    return (OVERALL[(scale, t)], FLEX[(scale, t)],
            _SKILL[(scale, t)] + [_QB[scale]], KDST[scale])


EXPECTED_TYPE = {"draft": "draft", "week": "weekly", "ros": "ros"}


def validate(slug, data, scale, week=None):
    want = EXPECTED_TYPE[scale]
    got = data.get("ranking_type_name")
    if got != want:
        raise RuntimeError(f"{slug}.php returned '{got}' rankings, expected '{want}' "
                           "-- slug is probably wrong (FantasyPros serves a fallback)")
    if scale == "week" and week and int(data.get("week") or 0) != int(week):
        raise RuntimeError(f"{slug}.php is week {data.get('week')}, expected {week}")
    if not data.get("players"):
        raise RuntimeError(f"{slug}.php returned no players")
