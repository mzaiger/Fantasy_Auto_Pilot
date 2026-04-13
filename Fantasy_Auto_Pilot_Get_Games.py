import os
import json
import time
import requests
import argparse  # Added for command-line arguments
from datetime import date
from pathlib import Path
from requests_oauthlib import OAuth2Session

# --- CONFIG ---
CLIENT_ID     = os.getenv("YAHOO_CLIENT_ID")
CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
REDIRECT_URI = "https://localhost"
AUTHORIZATION_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
TOKEN_CACHE = Path("token_cache.json")
BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

LEAGUE_KEY = "469.l.23321"
TODAY = date.today().isoformat()

# MLB Stats API — public, no auth required
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

# --- AUTH ---
def _save_token(token): TOKEN_CACHE.write_text(json.dumps(token, indent=2))

def _load_token():
    token_from_env = os.getenv("YAHOO_TOKEN")
    if token_from_env:
        try: return json.loads(token_from_env)
        except: pass
    if TOKEN_CACHE.exists():
        try: return json.loads(TOKEN_CACHE.read_text())
        except: pass
    return None

def get_oauth_session() -> OAuth2Session:
    cached = _load_token()
    session = OAuth2Session(
        client_id=CLIENT_ID,
        redirect_uri=REDIRECT_URI,
        auto_refresh_url=TOKEN_URL,
        auto_refresh_kwargs={"client_id": CLIENT_ID, "client_secret": CLIENT_SECRET},
        token_updater=_save_token,
    )
    if cached:
        session.token = cached
        if time.time() > cached.get("expires_at", 0) - 300:
            session.refresh_token(TOKEN_URL, client_id=CLIENT_ID, client_secret=CLIENT_SECRET)
    else:
        auth_url, _ = session.authorization_url(AUTHORIZATION_URL)
        print(f"Authorize here: {auth_url}")
        redirect_response = input("Paste redirect URL: ").strip()
        token = session.fetch_token(
            TOKEN_URL,
            authorization_response=redirect_response,
            client_secret=CLIENT_SECRET,
        )
        _save_token(token)
    return session

# --- MLB GAME FETCHER ---
POSTPONED_CODES = {"PPD", "DR", "DI"}

def get_mlb_games_today(target_date: str) -> list[dict]:
    params = {
        "sportId": 1,
        "date": target_date,
        "hydrate": "team,venue,game(content(summary)),linescore",
    }

    print(f"  GET {MLB_SCHEDULE_URL} (date={target_date}) ...", end=" ")
    resp = requests.get(MLB_SCHEDULE_URL, params=params, timeout=15)
    print(f"→ {resp.status_code}")

    if resp.status_code != 200:
        print(f"  ERROR: {resp.text[:200]}")
        return []

    data = resp.json()
    games_out = []
    for date_block in data.get("dates", []):
        for g in date_block.get("games", []):
            status      = g.get("status", {})
            status_code = status.get("statusCode", "")
            abstract    = status.get("abstractGameState", "")
            detailed    = status.get("detailedState", "")

            is_postponed = (
                status_code in POSTPONED_CODES
                or "postponed" in detailed.lower()
                or "suspended" in detailed.lower()
            )

            away = g.get("teams", {}).get("away", {}).get("team", {})
            home = g.get("teams", {}).get("home", {}).get("team", {})

            games_out.append({
                "game_pk":          g.get("gamePk"),
                "game_date":        g.get("gameDate", "")[:10],
                "start_time_utc":   g.get("gameDate"),
                "status_abstract":  abstract,
                "status_detailed":  detailed,
                "status_code":      status_code,
                "postponed":        is_postponed,
                "postpone_reason":  detailed if is_postponed else None,
                "away_team": {
                    "id":           away.get("id"),
                    "name":         away.get("name"),
                    "abbreviation": away.get("abbreviation"),
                },
                "home_team": {
                    "id":           home.get("id"),
                    "name":         home.get("name"),
                    "abbreviation": home.get("abbreviation"),
                },
                "venue":            g.get("venue", {}).get("name"),
                "series_desc":      g.get("seriesDescription", "Regular Season"),
                "doubleheader":     g.get("doubleHeader", "N"),
                "game_number":      g.get("gameNumber", 1),
            })

    games_out.sort(key=lambda x: (x["postponed"], x["start_time_utc"] or ""))
    return games_out

def print_games_summary(games: list[dict], target_date: str) -> None:
    if not games:
        print(f"  No MLB games found for {target_date}.")
        return

    print(f"\n{'#':<4} {'AWAY':<27} {'HOME':<27} {'START (UTC)':<22} {'STATUS':<20} {'POSTPONED'}")
    print("-" * 115)
    for i, g in enumerate(games, 1):
        away = f"{g['away_team']['abbreviation']:>3}  {g['away_team']['name']}"
        home = f"{g['home_team']['abbreviation']:>3}  {g['home_team']['name']}"
        start = g["start_time_utc"] or "TBD"
        status = g["status_detailed"] or g["status_abstract"] or "—"
        ppd = "⚠ YES" if g["postponed"] else "No"
        dh = f" (DH G{g['game_number']})" if g["doubleheader"] != "N" else ""
        print(f"{i:<4} {away:<27} {home:<27} {start:<22} {status:<20} {ppd}{dh}")

# --- MAIN ---

def main():
    # Setup Argument Parser
    parser = argparse.ArgumentParser(description="Fetch MLB games for a specific date.")
    parser.add_argument(
        "-d", "--date", 
        type=str, 
        default=TODAY, 
        help="Target date in YYYY-MM-DD format (defaults to today)"
    )
    args = parser.parse_args()
    
    target_date = args.date
    print(f"=== MLB Games Dump | Target Date: {target_date} ===\n")

    get_oauth_session()  # Auth for future fantasy use

    print(f"Fetching real MLB games for {target_date}...")
    games = get_mlb_games_today(target_date)

    dump = {
        "dump_date":  target_date,
        "game_count": len(games),
        "mlb_games":  games,
    }

    output_file = f"mlb_games.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Saved {len(games)} game(s) to {output_file}")
    print_games_summary(games, target_date)

    postponed = [g for g in games if g["postponed"]]
    if postponed:
        print(f"\n⚠  {len(postponed)} game(s) postponed/suspended:")
        for g in postponed:
            print(f"   • {g['away_team']['abbreviation']} @ {g['home_team']['abbreviation']} — {g['postpone_reason']}")

if __name__ == "__main__":
    main()