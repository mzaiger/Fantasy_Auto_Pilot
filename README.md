# Fantasy Auto Pilot

Automatically sets an optimal daily lineup for a Yahoo Fantasy Baseball
team, running unattended on a GitHub Actions schedule.

## How it works

The pipeline runs as five sequential steps (`Fantasy_Auto_Pilot_Main.py`
orchestrates all of them for a given `--date`):

1. **`Fantasy_Auto_Pilot_Get_Roster.py`** — pulls the current roster from
   the Yahoo Fantasy API into `current_roster.json`
2. **`Fantasy_Auto_Pilot_Get_Games.py`** — pulls that day's MLB schedule
   into `mlb_games.json`
3. **`Fantasy_Auto_Pilot_Generate_Roster.py`** — the optimizer. Builds the
   set of teams with an active game that day (excluding postponed games),
   locks non-editable/IL/NA players in place, benches editable players
   whose team has no game or who aren't starting, and ranks the rest per
   eligible position using a composite score (33% preseason rank + 33%
   current rank + 33% inverse percent-started). Writes the result to
   `roster_update.xml`.
4. **`Fantasy_Auto_Pilot_Update_Roster.py`** — pushes `roster_update.xml`
   back to Yahoo via the Fantasy API
5. **`Fantasy_Auto_Pilot_Update_YAML.py`** — (currently disabled in
   `Main.py`) rewrites the GitHub Actions cron schedule based on that
   day's game start times

`Fantasy_Auto_Pilot_Schedule_Make.py` optionally forwards `mlb_games.json`
to a Make.com webhook for external automation triggers.

## Automation

`.github/workflows/fantasy_autopilot.yml` (referenced as
`fantasy_autopilot.yml` here) runs the full pipeline on a cron schedule
timed around MLB game start windows, then commits and pushes any roster
changes back to the repo.

## Setup

Requires Yahoo Fantasy API OAuth2 credentials as environment variables /
GitHub secrets:

- `YAHOO_CLIENT_ID`
- `YAHOO_CLIENT_SECRET`
- `YAHOO_TOKEN` (cached OAuth token)

## Running locally

```bash
pip install requests-oauthlib requests

export YAHOO_CLIENT_ID="your_client_id"
export YAHOO_CLIENT_SECRET="your_client_secret"

python Fantasy_Auto_Pilot_Main.py --league 469.l.23321 --team "Zegster" --date 2026-08-03
```

## Structure

```
Fantasy_Auto_Pilot-main/
├── Fantasy_Auto_Pilot_Main.py             # orchestrates the full pipeline
├── Fantasy_Auto_Pilot_Get_Roster.py        # Yahoo API -> current_roster.json
├── Fantasy_Auto_Pilot_Get_Games.py         # MLB schedule -> mlb_games.json
├── Fantasy_Auto_Pilot_Generate_Roster.py   # optimizer -> roster_update.xml
├── Fantasy_Auto_Pilot_Update_Roster.py     # roster_update.xml -> Yahoo API
├── Fantasy_Auto_Pilot_Update_YAML.py       # rewrites cron schedule
├── Fantasy_Auto_Pilot_Schedule_Make.py     # optional Make.com webhook forward
├── current_roster.json / mlb_games.json / roster_update.xml   # generated
├── fantasy_autopilot.yml                   # GitHub Actions workflow
└── index.html
```
