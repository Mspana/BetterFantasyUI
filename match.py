"""Name matching between ESPN and FantasyPros player lists."""
import re

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}
_DST_TAIL = re.compile(r"\b(d ?st|dst|defense|special teams)\b")


def norm(name):
    n = name.lower().replace("&", "and")
    n = re.sub(r"[.'`\u2019]", "", n)
    n = re.sub(r"[^a-z0-9]+", " ", n).strip()
    return " ".join(p for p in n.split() if p not in SUFFIXES)


def dst_key(name, team_abbr=None, nick_map=None):
    """Reduce any D/ST spelling to a team abbreviation."""
    if team_abbr:
        return team_abbr.upper()
    n = _DST_TAIL.sub("", norm(name)).strip()
    if nick_map:
        if n in nick_map:
            return nick_map[n]
        last = n.split()[-1] if n.split() else ""
        if last in nick_map:
            return nick_map[last]
    return n.upper()


def build_nick_map(fp_dst_players):
    """Map 'philadelphia eagles' and 'eagles' -> 'PHI' from FantasyPros' own list."""
    m = {}
    for p in fp_dst_players:
        abbr = (p.get("player_team_id") or "").upper()
        full = norm(p["player_name"])
        m[full] = abbr
        parts = full.split()
        if parts:
            m[parts[-1]] = abbr          # 'eagles'
            if len(parts) > 2:
                m[" ".join(parts[-2:])] = abbr   # 'football team' style
        m[abbr.lower()] = abbr
    return m


def key_for(name, pos, team=None, nick_map=None):
    """Canonical join key for a player from either source."""
    if pos == "DST":
        return "DST:" + dst_key(name, team if team and team != "FA" else None, nick_map)
    return f"{pos}:{norm(name)}"


def key_loose(name, pos):
    """Fallback key ignoring position, for position-disagreement cases."""
    return norm(name)
