# Fantasy Auto Pilot

Automatically sets an optimal daily lineup for a Yahoo Fantasy Baseball
team, running unattended on a GitHub Actions schedule.

## How it works

The pipeline runs as a sequence of steps (`Fantasy_Auto_Pilot_Main.py`
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
   back to Yahoo via the Fantasy API. On a confirmed success (`✅ Roster
   updated successfully!`), it also writes `last_updated.json` with that
   day's date — this is what `index.html` reads to show when the roster
   was actually last updated.
5. **Backup trigger** — `Fantasy_Auto_Pilot_Main.py` checks whether step 4 printed the
   `✅ Roster updated successfully!` message. If it didn't (API call
   failed, timed out, etc.), `Fantasy_Auto_Pilot_Main.py` automatically falls back to
   `manualTriggerSetLineup.py`, which drives a headless Chrome/Selenium
   session (authenticated via the `YAHOO_COOKIES_B64` secret) to click
   "Start Active Players" directly on the Yahoo roster page. This no
   longer runs as its own workflow step — it's only invoked as a backup
   when the API push doesn't confirm success.
6. **`Fantasy_Auto_Pilot_Update_YAML.py`** — (currently disabled in
   `Fantasy_Auto_Pilot_Main.py`) rewrites the GitHub Actions cron schedule based on that
   day's game start times

`Fantasy_Auto_Pilot_Schedule_Make.py` optionally forwards `mlb_games.json`
to a Make.com webhook for external automation triggers.

## Automation

`.github/workflows/fantasy_autopilot.yml` (referenced as
`fantasy_autopilot.yml` here) runs the full pipeline on a cron schedule
timed around MLB game start windows, then commits and pushes any roster
changes back to the repo.

## GitHub secrets required

The workflow (`.github/workflows/fantasy_autopilot_schedule.yml`) needs
these added under repo → Settings → Secrets and variables → Actions:

| Secret | Used for |
|---|---|
| `YAHOO_CLIENT_ID` | Yahoo Fantasy API OAuth2 |
| `YAHOO_CLIENT_SECRET` | Yahoo Fantasy API OAuth2 |
| `YAHOO_TOKEN` | Cached Yahoo OAuth token (JSON), so the workflow doesn't need an interactive login each run |
| `YAHOO_COOKIES_B64` | Base64-encoded, authenticated Yahoo session cookies. Used only as a backup — `manualTriggerSetLineup.py` reads this to drive a headless browser and click "Start Active Players" when the API push in step 4 doesn't confirm success. See [Generating the cookies secret](#generating-the-cookies-secret) below. |
| `MAKE_API_KEY` | Sent as the `x-make-apikey` header when forwarding `mlb_games.json` to the Make.com webhook (`Fantasy_Auto_Pilot_Schedule_Make.py`) — only needed if you use that step |

**Important:** secrets need to be declared at the **job level**
`env:` (or repeated on every step that needs them) — a secret declared
only under one step's `env:` block isn't visible to later steps in the
same job. This bit us once already: `MAKE_API_KEY` was only wired into
step 1's `env:`, so step 2 (`Fantasy_Auto_Pilot_Schedule_Make.py`) saw an
empty key and Make.com rejected the request as unauthorized.

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

## Generating the cookies secret

`YAHOO_COOKIES_B64` powers the backup trigger (`manualTriggerSetLineup.py`).
GitHub Actions runs headless and can't complete Yahoo's interactive
login/2FA, so instead you capture an already-authenticated Yahoo session
as cookies once, and store those as a secret for the workflow to reuse.

**⚠️ Both steps below must be run locally on your own machine** (not in
GitHub Actions) — step 1 opens a real, visible Chrome window so you can
log in and complete 2FA by hand.

**Step 1 — Export the cookies (Python, run locally):**

```bash
pip install selenium webdriver-manager

python CookiesCredentialsYahoo.py
```

This opens a Chrome window. Log into Yahoo (completing 2FA if prompted),
confirm you've landed on a logged-in Fantasy page, then press Enter in
the terminal when prompted. This saves your session cookies to
`yahoo_cookies.json` in the current folder. **Do not commit this file to
the repo** — it contains live session credentials.

**Step 2 — Base64-encode the cookies for the secret (PowerShell, run
locally):**

```powershell
.\CookiesConvertToTextForSecret.ps1
```

This reads `yahoo_cookies.json` and writes a base64-encoded copy to
`yahoo_cookies_b64.txt` in the same folder.

**Step 3 — Store it as a GitHub secret:**

Open `yahoo_cookies_b64.txt`, copy its full contents, and paste them as
the value of the `YAHOO_COOKIES_B64` repo secret (Settings → Secrets and
variables → Actions → New repository secret).

Yahoo sessions expire periodically — if the backup trigger starts failing
with a "Session cookies expired" error, just repeat steps 1–3 to
refresh the secret.

## Structure

```
Fantasy_Auto_Pilot-main/
├── Fantasy_Auto_Pilot_Main.py             # orchestrates the full pipeline; runs the backup trigger if needed
├── Fantasy_Auto_Pilot_Get_Roster.py        # Yahoo API -> current_roster.json
├── Fantasy_Auto_Pilot_Get_Games.py         # MLB schedule -> mlb_games.json
├── Fantasy_Auto_Pilot_Generate_Roster.py   # optimizer -> roster_update.xml
├── Fantasy_Auto_Pilot_Update_Roster.py     # roster_update.xml -> Yahoo API; writes last_updated.json on success
├── Fantasy_Auto_Pilot_Update_YAML.py       # rewrites cron schedule
├── Fantasy_Auto_Pilot_Schedule_Make.py     # optional Make.com webhook forward
├── manualTriggerSetLineup.py               # Selenium backup trigger (run automatically by Main.py, not a separate workflow step)
├── CookiesCredentialsYahoo.py              # run LOCALLY to export Yahoo session cookies
├── CookiesConvertToTextForSecret.ps1       # run LOCALLY to base64-encode cookies for the secret
├── current_roster.json / mlb_games.json / roster_update.xml / last_updated.json   # generated
├── .github/workflows/fantasy_autopilot.yml # GitHub Actions workflow
└── index.html
```
