# BetterFantasyUI

A waiver, trade and lineup board for ESPN fantasy football leagues, built on
FantasyPros expert consensus rankings.

For each league it produces one self-contained HTML page with:

- **Sell high / Buy low** — players whose value has moved a long way since draft
  day, so you can trade away fading names and target risers.
- **Waiver adds / Drop candidates** — free agents who outrank someone you start.
- **Roster** and **Waiver wire** — every free agent measured against the weakest
  player you hold at that position.
- **Every skill player** — all RB/WR/TE ranked against each other, sortable and
  filterable by position and owner.
- **Three ranking boards** — this week, rest of season, and draft day.
- **Viewing as** — switch to any team in the league to scout a trade partner.
- **Player drawer** — click a player for their game log and recent FantasyPros news.
- **Flag / dismiss** — click the dot next to a name to cycle green, red, clear.

QBs, kickers and defenses are kept out of the cross-position table, because
FantasyPros publishes no board that ranks them against skill players.

## Requirements

Python 3.10+, standard library only.

## Setup

Each league is a directory under `leagues/` holding a `config.json`:

```
leagues/
  brunch/config.json
  heights/config.json
```

Copy `config.example.json` into a new league directory and fill it in:

```json
{
  "league_id": 437516043,
  "team_id": 7,
  "season": 2026,
  "espn_s2": "...",
  "swid": "{...}"
}
```

- `league_id` and `team_id` come from your team page URL:
  `fantasy.espn.com/football/team?leagueId=437516043&teamId=7`
- `espn_s2` and `swid` are needed for private leagues. In a browser signed in to
  ESPN, open DevTools → Application → Cookies → `espn.com` and copy both values.
  One ESPN account's cookies work for every league that account is in.

**These cookies are credentials for your ESPN account.** `config.json` is
gitignored; keep it that way.

Scoring (full/half/no PPR), superflex, roster slots, team count and the current
week are all read from ESPN, so nothing else needs configuring.

## Running

```
python run.py heights          # one league
python run.py --all            # every league
python run.py heights --fast   # rankings and report only, skip news and photos
python run.py heights --refresh  # ignore the FantasyPros page cache
```

Each run writes `leagues/<name>/report.html`. Open it directly in a browser.

`run.py` chains four steps, which can also be run on their own:

| Step | Script | Writes |
|---|---|---|
| Rankings from ESPN and FantasyPros | `fantasy.py --config <cfg> --out <data.json>` | `data.json` |
| News and game logs | `details.py <data.json>` | `details.json` |
| Player headshots | `photos.py <data.json>` | `img/` |
| Page | `make_report.py <data.json> <report.html>` | `report.html` |

FantasyPros pages, per-player news and headshots are cached and shared across
leagues, so a second league or a re-run later in the week is fast.

## How the rankings are sourced

FantasyPros' public API key returns only the top 10 players per list, so the
rankings are read from the `ecrData` JSON embedded in its public rankings pages
instead (`fpweb.py`). `sources.py` maps each scoring format to the right pages.

Some traps worth knowing if you change that mapping:

- **An unknown page name does not 404.** FantasyPros serves a generic draft list
  with HTTP 200, so every fetch is checked against the board type, week and
  scoring it was supposed to return.
- **Page names can misdescribe the board.** `ros-ppr-superflex.php` serves the
  1-QB board, not a superflex one.
- **No single list covers everyone.** The flex list stops at 410 players and the
  positional lists carry different players than the overall list, so the
  universe is the union of several pages. Injured players are kept even when
  they have no weekly rank, since their draft-day value is the point.
- **There is no draft-day flex board**, so draft-day skill rank is derived by
  removing QBs from the overall board and renumbering.

"Move" is the change in *positional* rank since draft day (e.g. `TE3 → TE35`),
because it is the only measure that means the same thing across all three boards.

## Files

| File | Role |
|---|---|
| `run.py` | Builds one league or all of them |
| `fantasy.py` | Joins ESPN rosters to FantasyPros rankings |
| `espn.py` | ESPN league, roster and settings reader |
| `fpweb.py` | FantasyPros rankings page scraper with cache |
| `sources.py` | Which FantasyPros pages to read per format and board |
| `build.py` | Merges draft, weekly and rest-of-season rankings |
| `match.py` | Name matching between ESPN and FantasyPros |
| `details.py` | News and game log scraper |
| `photos.py` | Headshot downloader |
| `make_report.py` | Renders the HTML page |
