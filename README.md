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
- **Experts | Model** — the rest of the season read two ways: the FantasyPros
  experts, or our own season model blended with them (see below). This week and
  draft day are there too.
- **Model vs experts** — the players the two boards disagree on, by 20+ places,
  split into free agents, trade targets and your own roster; every table shows
  the other board's rank beside the one you picked. Every gap of 5+ places
  carries the model's reason ("targets", "age", "games"...), in full in the
  drawer: the stat that sets the player apart from the players the experts rank
  near him.
- **Model insights on/off** — a switch beside the board buttons hides everything
  the model adds, for the experts' boards alone. Each league remembers it.
- **Advanced stats** — season-to-date target share, touches, points vs what that
  usage usually scores, air yards vs yards after the catch, and each player's
  offense and quarterback, for the experts' top 60 or ranks 61–150. WRs in 61–150
  with the biggest share of yards after the catch are tagged YAC-heavy: in
  2020–2025 they beat the experts' rank about 70% of the time.
- **Viewing as** — switch to any team in the league to scout a trade partner.
- **Player drawer** — click a player for their game log and recent FantasyPros news.
- **Flag / dismiss** — click the dot next to a name to cycle green, red, clear.

QBs, kickers and defenses are kept out of the cross-position table, because
FantasyPros publishes no board that ranks them against skill players.

## Requirements

Python 3.10+, standard library only, for the board. The season model needs
pandas and scikit-learn in its own virtual environment:

```
python -m venv .venv
.venv/Scripts/python -m pip install -r ml/requirements.txt
```

`run.py` uses the model when `.venv` exists and quietly builds without it when it
doesn't (as on the hourly GitHub Actions build).

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

## The season model

`ml/` predicts every RB/WR/TE's rest of season from the weeks played so far:
points per game, games he will play, total points and a stat line. It trains on
every season since 2008 from free public data -- nflverse weekly stats, snap
counts, injury reports and rosters, ffopportunity expected points, Vegas lines,
and ESPN's injury page as archived by the Wayback Machine for past seasons.

The **Model** board averages the model's ranking with the FantasyPros
rest-of-season ranking. In a walk-forward backtest -- every season from 2020 to
2025 predicted by a model trained only on the seasons before it, frozen after
each of weeks 1-14 -- that blend out-ranked the experts at every week.

```
python -m ml.predict brunch        # this week's predictions -> leagues/brunch/model.json
python -m ml.backtest              # the walk-forward backtest, weeks 1-14
python -m ml.backtest --week 3     # one week, season by season
python -m ml.exam score            # 2026, which nothing was tuned on, scored so far
python -m ml.injury_labels pending # new injury comments for Claude to label
```

Players on IR get their games from ESPN's expected return date, corrected by
how IR stints actually played out: Claude reads each injury comment, with names
and teams masked, and labels whether a timeline was given
(`ml/label_prompt.md`); the labels live in `ml/labels/`.

The model is frozen (`MODEL_VERSION` in `ml/backtest.py`). Its 2020-2025 scores
were used to make design choices, so they run a little optimistic; `ml/exam.py`
saves the model's and the experts' ranks every week of 2026 and scores both at
season end.

## Weekly job

`weekly.py` runs every league's board and model, takes the week's exam snapshot,
and commits and pushes each league's `model.json` so the live site picks it up.
It runs from a Windows scheduled task on Tuesday and Wednesday evenings and logs
to `logs/weekly.log`.

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
| `build_site.py` | Turns a league's page into the static site (`--hidden` for an unlisted board) |
| `weekly.py` | The weekly job: boards, model, exam snapshot, publish `model.json` |
| `ml/predict.py` | This week's rest-of-season predictions for a league |
| `ml/advanced.py` | Season-to-date usage and receiving splits for the Advanced stats table |
| `ml/explain.py` | The model's reason for each gap from the experts (what-ifs against his expert-rank peers) |
| `ml/features.py` | One row per player-season, frozen at a week |
| `ml/data.py` | Downloads and caches the public datasets |
| `ml/backtest.py` | Walk-forward backtest and the frozen model settings |
| `ml/injury_news.py` | ESPN's injury page, live and archived; the IR return rule |
| `ml/injury_labels.py` | Masked injury comments out to Claude, labels back in |
| `ml/exam.py` | The 2026 snapshots and their score |
