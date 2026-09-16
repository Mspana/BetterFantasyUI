"""Rank an ESPN league's rosters and free agents against FantasyPros consensus."""
import argparse, json, os, sys
import build, espn, match

HERE = os.path.dirname(os.path.abspath(__file__))


def load(cfg_path, week=None, refresh=False, log=print):
    cfg = json.load(open(cfg_path))
    teams, settings, _ = espn.league(cfg["league_id"], cfg["season"],
                                     cfg.get("espn_s2"), cfg.get("swid"))
    wk = week or settings.get("current_week") or 1
    log(f"League: {settings['name']}  |  {settings['size']} teams  |  "
        f"PPR={settings['ppr']}  superflex={settings['superflex']}  week={wk}")
    log(f"Starters: {settings['slots']}\n")

    uni, nick, meta = build.universe(settings["ppr"], wk, refresh, log)
    log(f"\nFantasyPros universe: {len(uni)} players")

    loose = {}
    for p in uni.values():
        loose.setdefault(match.key_loose(p["name"], p["pos"]), p)

    rostered, unmatched = {}, []
    for t in teams:
        for pl in t["roster"]:
            k = match.key_for(pl["name"], pl["pos"], None, nick)
            rec = uni.get(k) or loose.get(match.key_loose(pl["name"], pl["pos"]))
            if rec:
                rostered[rec["key"]] = {"team_id": t["id"], "team_name": t["name"],
                                        "slot": pl["slot"], "injury": pl["injury"]}
            else:
                unmatched.append({"team": t["name"], **pl})

    me = next((t for t in teams if t["id"] == cfg["team_id"]), None)
    my_name = me["name"] if me else f"Team {cfg['team_id']}"

    players = []
    for rec in uni.values():
        own = rostered.get(rec["key"])
        players.append({**rec,
                        "owner": own["team_name"] if own else None,
                        "owner_id": own["team_id"] if own else None,
                        "slot": own["slot"] if own else None,
                        "injury": own["injury"] if own else None,
                        "mine": bool(own and own["team_id"] == cfg["team_id"])})

    return {"league": settings, "week": wk, "season": cfg["season"], "boards": meta,
            "my_team": {"id": cfg["team_id"], "name": my_name},
            "teams": [{"id": t["id"], "name": t["name"]} for t in teams],
            "players": players, "unmatched": unmatched}


def sort_key(p, scale="week"):
    """Overall board order; players absent from that board sink to the bottom."""
    e = p["scales"][scale]["ecr"]
    return (e is None, e or 99999)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=os.path.join(HERE, "config.json"))
    ap.add_argument("--week", type=int)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--out", default=os.path.join(HERE, "data.json"))
    a = ap.parse_args()

    data = load(a.config, a.week, a.refresh)
    json.dump(data, open(a.out, "w"), indent=1)

    ps = data["players"]
    mine = sorted([p for p in ps if p["mine"]], key=sort_key)
    fa = sorted([p for p in ps if not p["owner"]], key=sort_key)
    print(f"My team ({data['my_team']['name']}): {len(mine)} matched")
    print(f"Free agents: {len(fa)}")
    for sc, m in data["boards"].items():
        print(f"  {sc:6} board={m['board']:4} {m['slug']}.php  "
              f"updated {m['updated']}  {m['experts']} experts"
              + ("  [superflex-ordered]" if m["superflex_ordered"] else ""))
    if data["unmatched"]:
        print(f"\n!! {len(data['unmatched'])} rostered players with no FantasyPros rank:")
        for u in data["unmatched"]:
            print(f"   {u['name']:26} {u['pos']:4} ({u['team']})")
    print(f"\nWrote {a.out}")


if __name__ == "__main__":
    main()
