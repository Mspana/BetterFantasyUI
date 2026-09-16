"""Turn the merged data into waiver / drop / trade shortlists."""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
STARTABLE = {"QB": 12, "RB": 24, "WR": 24, "TE": 12, "DST": 12, "K": 12}


def on_ir(p):
    """IR/bench-stash players don't occupy an active roster spot."""
    return p.get("slot") == "IR" or p.get("injury") == "INJURY_RESERVE"


def rk(p):
    return (p["week_pos_num"] is None, p["week_pos_num"] or 9999)


def fmt(p, show_owner=False):
    wk = p["week_pos_rank"] or "unranked"
    dr = p["draft_pos_rank"] or "undrafted"
    d = p["pos_delta"]
    arrow = f"{d:+d}" if d is not None else "  - "
    inj = ""
    if p.get("injury") and p["injury"] not in ("ACTIVE", None):
        inj = " " + p["injury"].replace("_", " ").title()
    owner = f"  [{p['owner']}]" if show_owner and p.get("owner") else ""
    return (f"{p['name']:<24} {p['pos']:<4}{str(p['team'] or ''):<4} "
            f"{dr:>7} -> {wk:>9}  {arrow:>5}{inj}{owner}")


def main(path=os.path.join(HERE, "data.json"), size=8):
    d = json.load(open(path))
    ps = d["players"]
    mine = [p for p in ps if p["mine"]]
    fa = [p for p in ps if not p["owner"]]
    others = [p for p in ps if p["owner"] and not p["mine"]]
    me = d["my_team"]["name"]

    print(f"\n{'='*78}\n {d['league']['name']} -- Week {d['week']}  |  you are '{me}'\n{'='*78}")

    print(f"\n--- YOUR ROSTER (FantasyPros Week {d['week']} positional rank) ---")
    for pos in ["QB", "RB", "WR", "TE", "DST", "K"]:
        grp = sorted([p for p in mine if p["pos"] == pos], key=rk)
        for p in grp:
            print("  " + fmt(p))

    print(f"\n--- TOP FREE AGENTS by position ---")
    for pos in ["QB", "RB", "WR", "TE", "DST", "K"]:
        grp = [p for p in fa if p["pos"] == pos and p["week_pos_num"]]
        grp = sorted(grp, key=rk)[:6]
        if grp:
            print(f"  {pos}:")
            for p in grp:
                print("    " + fmt(p))

    print(f"\n--- WAIVER UPGRADES: free agent ranked above your weakest active ---")
    for pos in ["QB", "RB", "WR", "TE", "DST", "K"]:
        # compare against the weakest player actually holding an active roster spot
        mypos = sorted([p for p in mine if p["pos"] == pos and not on_ir(p)], key=rk)
        if not mypos:
            continue
        worst = mypos[-1]
        better = [p for p in fa if p["pos"] == pos and p["week_pos_num"]
                  and (worst["week_pos_num"] is None
                       or p["week_pos_num"] < worst["week_pos_num"])]
        for p in sorted(better, key=rk)[:4]:
            print(f"  ADD {fmt(p)}")
            print(f"      over your {fmt(worst)}")

    print(f"\n--- SELL HIGH: your players with draft-day name value they no longer earn ---")
    sell = [p for p in mine
            if p["draft_pos_num"] and (p["pos_delta"] is None or p["pos_delta"] < -8)]
    for p in sorted(sell, key=lambda x: (x["pos_delta"] is not None, x["pos_delta"] or 0)):
        print("  " + fmt(p))

    print(f"\n--- BUY LOW: rostered elsewhere, drafted late, producing now ---")
    buy = [p for p in others if p["pos_delta"] and p["pos_delta"] > 8
           and p["week_pos_num"] and p["week_pos_num"] <= STARTABLE.get(p["pos"], 24) * size / 8]
    for p in sorted(buy, key=lambda x: -x["pos_delta"])[:15]:
        print("  " + fmt(p, show_owner=True))

    print(f"\n--- DROP CANDIDATES: active players below the best free agent there ---")
    best_fa = {}
    for p in fa:
        if p["week_pos_num"]:
            cur = best_fa.get(p["pos"])
            if cur is None or p["week_pos_num"] < cur["week_pos_num"]:
                best_fa[p["pos"]] = p
    for p in sorted([x for x in mine if not on_ir(x)], key=rk, reverse=True):
        b = best_fa.get(p["pos"])
        if b and (p["week_pos_num"] is None or p["week_pos_num"] > b["week_pos_num"]):
            print("  " + fmt(p))
            print(f"      worse than free agent {b['name']} ({b['week_pos_rank']})")

    stash = [p for p in mine if on_ir(p)]
    if stash:
        print(f"\n--- IR STASH (costs no active spot; judge on return timeline) ---")
        for p in stash:
            print("  " + fmt(p))
    print()


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
