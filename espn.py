"""ESPN fantasy football league reader (private leagues via espn_s2 + SWID)."""
import json, urllib.request, urllib.error

HOST = "https://lm-api-reads.fantasy.espn.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36")

POS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DST"}

# Slot 7 (OP) is the only slot where a QB may start besides QB itself.
# Careful: slot 6 is TE, not superflex.
SUPERFLEX_SLOTS = {7}
SLOT_NAMES = {0: "QB", 2: "RB", 3: "RB/WR", 4: "WR", 5: "WR/TE", 6: "TE", 7: "OP",
              16: "D/ST", 17: "K", 20: "Bench", 21: "IR", 23: "FLEX"}

RECEPTION_STAT = 53


def _get(league_id, season, views, espn_s2=None, swid=None):
    url = (f"{HOST}/apis/v3/games/ffl/seasons/{season}/segments/0/leagues/{league_id}"
           "?" + "&".join(f"view={v}" for v in views))
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if espn_s2 and swid:
        swid = swid if swid.startswith("{") else "{" + swid + "}"
        headers["Cookie"] = f"espn_s2={espn_s2}; SWID={swid}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        if e.code == 401:
            raise RuntimeError(
                "ESPN says not authorized. The league is private, so espn_s2 and "
                "SWID are required and must be current (they expire).\n" + body)
        raise RuntimeError(f"ESPN HTTP {e.code}: {body}")


def league(league_id, season, espn_s2=None, swid=None):
    """Return (teams, settings_summary, raw). teams: list of dicts with roster."""
    raw = _get(league_id, season, ["mTeam", "mRoster", "mSettings"], espn_s2, swid)

    s = raw.get("settings", {})
    slots = s.get("rosterSettings", {}).get("lineupSlotCounts", {})
    slots = {int(k): v for k, v in slots.items() if v}
    superflex = any(slots.get(sl, 0) for sl in SUPERFLEX_SLOTS)

    ppr = 0.0
    for item in s.get("scoringSettings", {}).get("scoringItems", []):
        if item.get("statId") == RECEPTION_STAT:
            ppr = item.get("points", 0.0) or 0.0
            break

    settings = {
        "name": s.get("name"),
        "size": raw.get("status", {}).get("teamsJoined") or len(raw.get("teams", [])),
        "ppr": ppr,
        "superflex": superflex,
        "slots": {SLOT_NAMES.get(k, str(k)): v for k, v in sorted(slots.items())},
        "current_week": raw.get("scoringPeriodId"),
    }

    teams = []
    for t in raw.get("teams", []):
        nm = t.get("name") or " ".join(
            x for x in [t.get("location"), t.get("nickname")] if x).strip()
        roster = []
        for e in (t.get("roster") or {}).get("entries", []):
            p = (e.get("playerPoolEntry") or {}).get("player") or {}
            if not p.get("fullName"):
                continue
            roster.append({
                "espn_id": p.get("id"),
                "name": p["fullName"],
                "pos": POS.get(p.get("defaultPositionId"), "?"),
                "slot": SLOT_NAMES.get(e.get("lineupSlotId"), str(e.get("lineupSlotId"))),
                "injury": p.get("injuryStatus"),
            })
        teams.append({"id": t.get("id"), "name": nm or f"Team {t.get('id')}",
                      "roster": roster})
    return teams, settings, raw
