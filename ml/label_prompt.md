You are labelling short NFL injury-news blurbs for a fantasy football model. Your labels are tested against what actually happened later, so the only thing that matters is reading each blurb honestly and consistently.

INPUT: `ml/cache/labels/pending.jsonl` (under `C:/Users/Matthew/Documents/FantasyRankings`)
Each line is `{"id": "n0000", "pos": "RB"|"WR"|"TE", "text": "..."}`. The blurbs may come from several NFL seasons, shuffled together. The subject player's name is replaced by PLAYER, other players by OTHER1/OTHER2..., coaches/GMs by STAFF, and team names/cities by TEAM. A "Sep 23:" prefix (when present) is the blurb's date, month and day only. Some blurbs are a single word like "doubtful".

OUTPUT: `ml/cache/labels/labelled.jsonl`, exactly one JSON object per input id, same ids, one per line:

```
{"id": "n0000",
 "injury": short body part / injury in lowercase ("hamstring", "high ankle sprain", "torn acl") or null,
 "severity": "none" | "minor" | "multi_week" | "long_term" | "season_ending" | "unknown",
 "weeks_out": number or null,
 "surgery": true | false,
 "workload": "limited" or null,
 "role": "up" | "down" | null,
 "suspended_games": number or null,
 "outlook": -2 | -1 | 0 | 1 | 2,
 "evidence": verbatim quote of at most 20 words ("" if nothing to quote)}
```

**severity**
- `none`: not about an injury (suspension, personal matter, depth chart, performance, healthy scratch).
- `minor`: day-to-day, questionable, left a game but not described as serious, expected to play soon or miss about one game.
- `multi_week`: expected to miss roughly 2-8 weeks. Covers short-term IR, IR with a designation to return, "several weeks", "at least four weeks", a high ankle sprain, and most fractures with a return timeline.
- `long_term`: out indefinitely, "months", or major surgery, but NOT stated or clearly implied to end the season.
- `season_ending`: stated as out for the season, or an injury that by general medical norms ends an NFL season (torn ACL, torn Achilles, an Achilles injury needing surgery). Also covers a player placed on IR, reverted to IR, or put on reserve/injured before final roster cuts (a blurb dated before about Aug 26). By league rule those players cannot return that season.
- `unknown`: an injury is mentioned but the text gives no way to judge how serious it is, e.g. "placed on IR", PUP or NFI with no detail.

**weeks_out** is the number of FURTHER weeks/games the text says he will miss from the blurb's date. Fill it only from explicit wording:
- "at least six weeks" -> 6
- "four to six weeks" -> 5
- questionable or day-to-day -> 0
- doubtful or inactive -> 1
- "out for the season" -> 20

Otherwise null. Never infer it from severity alone.

**workload** is `limited` only if the text says he will be on a snap count, eased in, or have a reduced role when he plays.

**role**
- `up`: his role is growing (named the starter, will lead the backfield, more targets because a teammate is out).
- `down`: his role is shrinking (lost the job, demoted, healthy scratch, coach's-decision inactive, waived).

**suspended_games**: games suspended, or 99 for the commissioner exempt list or an indefinite suspension. A player coming OFF a suspension is not suspended.

**outlook** is his rest-of-season fantasy value as the text presents it:
- -2: season likely over
- -1: will miss meaningful time, or his role is diminished
- 0: neutral, unclear or minor
- +1: positive (healthy soon, returning, practicing)
- +2: clearly positive (role growing, fully cleared for a big role)

**Rules. These matter more than anything else.**
1. Judge ONLY from the blurb text plus general football/medical knowledge. Do NOT try to work out who PLAYER is, or which team or season this is. Do NOT use anything you remember about how a real player's season went.
2. Do not open, read or search any other file, directory or website. Read only the input file; write only the output file.
3. Be consistent: the same wording always gets the same labels.
4. Every input id must appear exactly once in the output, with valid JSON on every line.

When done, check that the ids in the output match the input exactly. Report back only the counts per severity value and any ids you found genuinely ambiguous.
