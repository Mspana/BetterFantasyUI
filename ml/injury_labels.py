"""What the injury comments say, read by Claude, kept as labels.

ESPN's return date is the earliest a player MAY come back, not a forecast: of
players on IR at week 3 in 2020-2025, nine in ten came back later than it and a
third never came back at all. The comment beside it tells them apart ("four to
six weeks" vs "torn ACL"), so a Claude subagent reads each comment -- names,
teams and coaches masked, seasons shuffled, so it judges the text and not its
memory of how a season went -- and its labels are stored here.

Only a fingerprint of each comment is kept, never ESPN's text.

Weekly, before predicting:
    python -m ml.injury_labels pending    # masks new comments -> ml/cache/labels/pending.jsonl
    (a Claude subagent follows ml/label_prompt.md -> ml/cache/labels/labelled.jsonl)
    python -m ml.injury_labels merge      # folds the labels into the store
"""
import hashlib, json, os, random, re, sys, time

import pandas as pd

from . import data, injury_news as N

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(HERE, "labels", "injury_labels.jsonl")
WORK = os.path.join(data.CACHE, "labels")
FIELDS = ("severity", "weeks_out", "surgery", "workload", "role", "suspended_games", "outlook")

TEAMS = ["Cardinals", "Falcons", "Ravens", "Bills", "Panthers", "Bears", "Bengals", "Browns", "Cowboys",
         "Broncos", "Lions", "Packers", "Texans", "Colts", "Jaguars", "Chiefs", "Raiders", "Chargers", "Rams",
         "Dolphins", "Vikings", "Patriots", "Saints", "Giants", "Jets", "Eagles", "Steelers", "49ers", "Niners",
         "Seahawks", "Buccaneers", "Bucs", "Titans", "Commanders", "Washington Football Team", "Redskins",
         "Arizona", "Atlanta", "Baltimore", "Buffalo", "Carolina", "Chicago", "Cincinnati", "Cleveland",
         "Dallas", "Denver", "Detroit", "Green Bay", "Houston", "Indianapolis", "Jacksonville", "Kansas City",
         "Las Vegas", "Oakland", "Los Angeles", "Miami", "Minnesota", "New England", "New Orleans", "New York",
         "Philadelphia", "Pittsburgh", "San Francisco", "Seattle", "Tampa Bay", "Tennessee", "Washington"]
TEAM_RE = re.compile(r"\b(" + "|".join(sorted(map(re.escape, TEAMS), key=len, reverse=True)) + r")\b")
STAFF_RE = re.compile(r"\b((?:[Hh]ead |[Oo]ffensive |[Dd]efensive |[Aa]ssistant )?"
                      r"(?:[Cc]oach(?:es)?|[Cc]oordinator|GM|[Gg]eneral [Mm]anager|[Oo]wner))"
                      r" [A-Z][a-z]+(?: [A-Z][A-Za-z'-]+)+")
NAME_RE = re.compile(r"\b[A-Z][A-Za-z.'-]+(?: [A-Z][A-Za-z.'-]+){1,2}\b")


def fingerprint(comment):
    return hashlib.sha1((comment or "").strip().encode("utf-8")).hexdigest()[:16]


def severity_class(sev):
    """The three groups that behave differently: who comes back, and when."""
    if sev == "season_ending":
        return "season_ending"
    if sev in ("multi_week", "minor"):
        return "timeline"
    return "unknown"


def mask(comment, name, known):
    """Hide who and where: the player, other players, coaches, teams."""
    parts = [name] + [p for p in re.split(r"[ .'-]+", name) if len(p) >= 3 and p not in ("Jr", "Sr", "III")]
    text = STAFF_RE.sub(lambda m: m.group(1) + " STAFF", comment)
    for p in sorted(set(parts), key=len, reverse=True):
        text = re.sub(rf"\b{re.escape(p)}\b", "PLAYER", text)
    others = {}

    def other(m):
        n = m.group(0)
        if n not in known:
            return n
        return others.setdefault(n, f"OTHER{len(others) + 1}")
    return TEAM_RE.sub("TEAM", NAME_RE.sub(other, text))


def load():
    if not os.path.exists(STORE):
        return pd.DataFrame(columns=["season", "espn_id", "fp", "labelled"] + list(FIELDS))
    return pd.DataFrame([json.loads(l) for l in open(STORE, encoding="utf-8") if l.strip()])


def attach(inj, season, labels=None):
    """Add each comment's label to an injury table. A comment that changed since
    it was read falls back to that player's latest label this season."""
    labels = load() if labels is None else labels
    inj = inj.copy()
    inj["fp"] = inj.comment.map(fingerprint)
    lab = labels[labels.season == season]
    exact = lab.drop_duplicates(["espn_id", "fp"], keep="last").set_index(["espn_id", "fp"])
    latest = lab.sort_values("labelled").drop_duplicates("espn_id", keep="last").set_index("espn_id")
    sev, fresh = [], []
    for e, f in zip(inj.espn_id, inj.fp):
        if (e, f) in exact.index:
            sev.append(exact.at[(e, f), "severity"]); fresh.append(True)
        elif e in latest.index:
            sev.append(latest.at[e, "severity"]); fresh.append(False)
        else:
            sev.append(None); fresh.append(False)
    inj["severity"] = sev
    inj["label_fresh"] = fresh
    inj["sev_class"] = inj.severity.map(severity_class)
    return inj


def _tables(seasons):
    gm = data.games()
    now = data.current_season()
    out = {}
    for y in seasons:
        t = N.live() if y == now else N.history(y, gm)
        if y == now and len(t):
            t = t[t.status != "Active"]        # the archived page only ever listed the injured
        out[y] = t[t.pos.isin(["RB", "WR", "TE"]) & (t.comment.fillna("").str.len() > 0)] if len(t) else t
    return out


def pending(seasons=None):
    """Mask every comment without a label and write it out for the subagent."""
    seasons = seasons or range(N.FIRST_SEASON, data.current_season() + 1)
    ix = data.ids()
    known = {n for n in ix.name.dropna().astype(str) if " " in n and len(n) > 5}
    have = set(zip(load().espn_id, load().fp)) if os.path.exists(STORE) else set()
    items = []
    for y, t in _tables(seasons).items():
        for r in t.itertuples():
            fp = fingerprint(r.comment)
            if (int(r.espn_id), fp) in have:
                continue
            items.append({"season": y, "espn_id": int(r.espn_id), "fp": fp, "pos": r.pos,
                          "text": mask(r.comment, r.name, known)})
    random.Random(len(items)).shuffle(items)
    os.makedirs(WORK, exist_ok=True)
    key = {}
    with open(os.path.join(WORK, "pending.jsonl"), "w", encoding="utf-8") as f:
        for i, it in enumerate(items):
            iid = f"n{i:04d}"
            key[iid] = {k: it[k] for k in ("season", "espn_id", "fp")}
            f.write(json.dumps({"id": iid, "pos": it["pos"], "text": it["text"]}) + "\n")
    json.dump(key, open(os.path.join(WORK, "pending_key.json"), "w", encoding="utf-8"))
    return len(items)


def merge(path=None):
    """Fold the subagent's labels into the store."""
    path = path or os.path.join(WORK, "labelled.jsonl")
    key = json.load(open(os.path.join(WORK, "pending_key.json"), encoding="utf-8"))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    new = []
    for line in open(path, encoding="utf-8"):
        if not line.strip():
            continue
        o = json.loads(line)
        if o["id"] not in key:
            continue
        rec = dict(key[o["id"]], labelled=stamp)
        rec.update({k: o.get(k) for k in FIELDS})
        new.append(rec)
    os.makedirs(os.path.dirname(STORE), exist_ok=True)
    with open(STORE, "a", encoding="utf-8") as f:
        for rec in new:
            f.write(json.dumps(rec) + "\n")
    return len(new), len(key)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "pending"
    if cmd == "pending":
        n = pending()
        print(f"{n} comments need labels -> {os.path.join(WORK, 'pending.jsonl')}")
        if n:
            print("have a Claude subagent follow ml/label_prompt.md, then run: python -m ml.injury_labels merge")
    elif cmd == "merge":
        got, asked = merge(sys.argv[2] if len(sys.argv) > 2 else None)
        print(f"merged {got} of {asked} labels into {STORE}")
