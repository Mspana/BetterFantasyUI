"""Merge FantasyPros draft / weekly / rest-of-season consensus into one universe.

Every player carries an overall rank on each of the three scales, all taken from
the same OP board, so draft -> week and draft -> ros moves are directly
comparable. K and D/ST have no cross-position board and are flagged `kdst`.
"""
import fpweb, match, sources


def pos_num(pos_rank):
    """'TE35' -> 35."""
    if not pos_rank:
        return None
    d = "".join(c for c in str(pos_rank) if c.isdigit())
    return int(d) if d else None


def _collect(slugs, scale, week, nick, refresh, log, required=True):
    """First slug to mention a player wins, so callers order by authority.

    Coverage pages are optional: FantasyPros empties some of them over a season
    (the positional draft cheatsheets, for one), and losing one only thins
    coverage. The overall and flex boards are required.
    """
    out = {}
    for slug in slugs:
        data = fpweb.fetch(slug, refresh=refresh)
        try:
            sources.validate(slug, data, scale, week)
        except RuntimeError as e:
            if required:
                raise
            log(f"    {slug}.php: skipped ({e})")
            continue
        log(f"    {slug}.php: {len(data['players']):>4}  "
            f"({data.get('scoring')}, updated {data.get('last_updated')})")
        for p in data["players"]:
            pos = p.get("player_position_id") or "?"
            k = match.key_for(p["player_name"], pos, p.get("player_team_id"), nick)
            out.setdefault(k, p)
    return out


def universe(ppr, week, refresh=False, log=print):
    nick = match.build_nick_map(fpweb.fetch("dst", refresh=refresh)["players"])
    scales, meta = {}, {}

    for scale in sources.SCALES:
        overall_slug, flex_slug, cov_slugs, kdst_slugs = sources.pages(scale, ppr)
        log(f"  {scale}:")
        # overall board first: it owns the cross-position rank_ecr
        overall = _collect([overall_slug], scale, week, nick, refresh, log)
        flex = _collect([flex_slug], scale, week, nick, refresh, log)
        cov = _collect(cov_slugs + kdst_slugs, scale, week, nick, refresh, log,
                       required=False)
        scales[scale] = {"overall": overall, "flex": flex, "cov": cov}
        src = fpweb.fetch(overall_slug, refresh=refresh)
        # position_id is the board's real shape, which the slug can misreport:
        # ros-ppr-superflex.php actually serves the ALL (1-QB) board, so an
        # overall rank is only comparable to another board of the same shape.
        meta[scale] = {"updated": src.get("last_updated"),
                       "experts": src.get("total_experts"), "slug": overall_slug,
                       "board": src.get("position_id"),
                       "superflex_ordered": src.get("position_id") == "OP"}

    keys = set()
    for s in scales.values():
        keys |= set(s["overall"]) | set(s["cov"])

    uni = {}
    for k in keys:
        rec, any_src = {}, None
        for scale in sources.SCALES:
            s = scales[scale]
            o, f, c = s["overall"].get(k), s["flex"].get(k), s["cov"].get(k)
            any_src = any_src or o or c
            rec[scale] = {
                "ecr": (o or {}).get("rank_ecr"),
                "flex": (f or {}).get("rank_ecr"),
                "pos_rank": (c or o or {}).get("pos_rank"),
                "pos_num": pos_num((c or o or {}).get("pos_rank")),
                "lo": (c or o or {}).get("rank_min"),
                "hi": (c or o or {}).get("rank_max"),
            }
        if not any_src:
            continue
        pos = any_src.get("player_position_id") or "?"
        wk = scales["week"]["cov"].get(k) or scales["week"]["overall"].get(k) or {}
        uni[k] = {
            "key": k,
            "name": any_src["player_name"],
            "pos": pos,
            "kdst": pos in ("K", "DST"),
            "team": any_src.get("player_team_id"),
            "opponent": wk.get("player_opponent"),
            "bye": any_src.get("player_bye_week"),
            "scales": rec,
            # overall move since draft day, on one shared board
            "move_week": (rec["draft"]["ecr"] - rec["week"]["ecr"])
                         if (rec["draft"]["ecr"] and rec["week"]["ecr"]) else None,
            "move_ros": (rec["draft"]["ecr"] - rec["ros"]["ecr"])
                        if (rec["draft"]["ecr"] and rec["ros"]["ecr"]) else None,
            # positional move, the only one defined for K and D/ST
            "pmove_week": (rec["draft"]["pos_num"] - rec["week"]["pos_num"])
                          if (rec["draft"]["pos_num"] and rec["week"]["pos_num"]) else None,
            "pmove_ros": (rec["draft"]["pos_num"] - rec["ros"]["pos_num"])
                         if (rec["draft"]["pos_num"] and rec["ros"]["pos_num"]) else None,
            "url": any_src.get("player_page_url"),
            "pid": any_src.get("player_id"),      # keys the headshot image
            # 'jahmyr-gibbs' -- keys the /nfl/news/ and /nfl/games/ pages
            "slug": (any_src.get("player_filename") or "").replace(".php", "") or None,
            "note": wk.get("note"),
        }

    _skill_ranks(uni)
    return uni, nick, meta


def _skill_ranks(uni):
    """Dense RB/WR/TE-only rank per scale.

    The published boards can't be used directly: there is no draft-day FLEX
    board (ppr-flex-cheatsheets serves the ALL board, QBs included), and the
    weekly/ROS FLEX boards cover fewer players than the universe. So order by
    flex rank where it exists, fall back to the overall board, then positional,
    and re-number 1..N over the same population on every scale.
    """
    INF = float("inf")
    skill = [p for p in uni.values() if p["pos"] in ("RB", "WR", "TE")]
    for scale in sources.SCALES:
        def key(p):
            s = p["scales"][scale]
            return (s["flex"] if s["flex"] else INF,
                    s["ecr"] if s["ecr"] else INF,
                    s["pos_num"] if s["pos_num"] else INF,
                    p["name"])
        ranked = sorted(skill, key=key)
        n = 0
        for p in ranked:
            s = p["scales"][scale]
            if s["flex"] or s["ecr"] or s["pos_num"]:
                n += 1
                s["skill"] = n
            else:
                s["skill"] = None
        for p in uni.values():
            p["scales"][scale].setdefault("skill", None)

    for p in uni.values():
        d, w, r = (p["scales"][s]["skill"] for s in ("draft", "week", "ros"))
        p["smove_week"] = (d - w) if (d and w) else None
        p["smove_ros"] = (d - r) if (d and r) else None
