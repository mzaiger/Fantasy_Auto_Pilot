import os
import json
import time
import argparse
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

# --- AUTH HELPERS ---
def _save_token(token): TOKEN_CACHE.write_text(json.dumps(token, indent=2))
def _load_token():
    # 1. Try loading from Environment Variable
    token_from_env = os.getenv("YAHOO_TOKEN")
    if token_from_env:
        try: 
            return json.loads(token_from_env)
        except Exception as e:
            print(f"❌ YAHOO_TOKEN env var found, but failed to parse JSON: {e}")
    else:
        print("ℹ️ YAHOO_TOKEN environment variable is not set.")

    # 2. Try loading from Local Cache File
    if TOKEN_CACHE.exists():
        try: 
            return json.loads(TOKEN_CACHE.read_text())
        except Exception as e:
            print(f"❌ token_cache.json found, but failed to parse: {e}")
    else:
        print("ℹ️ token_cache.json file not found.")

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
        token = session.fetch_token(TOKEN_URL, authorization_response=redirect_response, client_secret=CLIENT_SECRET)
        _save_token(token)
    return session

def api_get(session, url):
    resp = session.get(url, params={"format": "json"})
    return resp.json() if resp.status_code == 200 else {}

# --- PARSING HELPERS ---

def flatten_yahoo_player(p_list):
    flat = {}
    for item in p_list:
        # If it's the list containing name/team info
        if isinstance(item, list):
            for sub in item:
                if isinstance(sub, dict):
                    flat.update(sub)

        # If it's a dictionary
        elif isinstance(item, dict):
            # Capture starting_status
            if "starting_status" in item:
                flat["starting_status"] = item["starting_status"]

            # Capture selected_position
            if "selected_position" in item:
                flat["selected_position"] = item["selected_position"]

            # Capture player_ranks
            if "player_ranks" in item:
                ranks = item["player_ranks"]
                if isinstance(ranks, list):
                    for r_wrap in ranks:
                        r = r_wrap.get("player_rank", {})
                        if r.get("rank_type") == "OR":
                            flat["preseason_rank"] = r.get("rank_value")
                        if r.get("rank_type") == "S" and r.get("rank_season") == "2026":
                            flat["current_rank"] = r.get("rank_value")

            # Update anything else found (includes is_editable as raw int)
            flat.update(item)
    return flat

def get_team_key(session, league_key, target_name):
    """Finds the team_key by flattening the team metadata list."""
    url = f"{BASE_URL}/league/{league_key}/teams"
    data = api_get(session, url)

    l_content = data.get("fantasy_content", {}).get("league", [])
    if not isinstance(l_content, list) or len(l_content) < 2:
        return None

    teams_dict = l_content[1].get("teams", {})
    for i in range(int(teams_dict.get("count", 0))):
        team_data = teams_dict.get(str(i), {}).get("team", [])

        team_info = {}
        for entry in team_data:
            if isinstance(entry, list):
                for sub in entry:
                    if isinstance(sub, dict): team_info.update(sub)
            elif isinstance(entry, dict):
                team_info.update(entry)

        if team_info.get("name", "").lower() == target_name.lower():
            return team_info.get("team_key")
    return None

def get_percent_started(session, player_keys, batch_size=25):
    """Fetches percent_started for a list of player_keys, batching every 25 (API limit)."""
    pct_started_map = {}

    for batch_start in range(0, len(player_keys), batch_size):
        batch = player_keys[batch_start:batch_start + batch_size]
        keys_str = ",".join(batch)
        url = f"{BASE_URL}/players;player_keys={keys_str}/percent_started"
        data = api_get(session, url)

        players_block = data.get("fantasy_content", {}).get("players", {})

        for i in range(int(players_block.get("count", 0))):
            p_data = players_block.get(str(i), {}).get("player", [])
            p_key = None
            percent_started = None

            for item in p_data:
                if isinstance(item, list):
                    for sub in item:
                        if isinstance(sub, dict) and "player_key" in sub:
                            p_key = sub["player_key"]
                elif isinstance(item, dict) and "percent_started" in item:
                    ps_list = item["percent_started"]
                    for entry in ps_list:
                        if isinstance(entry, dict) and "value" in entry:
                            percent_started = entry["value"]
                            break

            if p_key:
                pct_started_map[p_key] = percent_started

    return pct_started_map

def get_roster(session, league_key, team_key, date_str=None):
    """Fetches roster with ranks and starting_status, then merges percent_started."""
    date_param = f";date={date_str}" if date_str else ""
    url = f"{BASE_URL}/team/{team_key}/roster{date_param}/players;out=ranks,starting_status"
    data = api_get(session, url)

    t_content = data.get("fantasy_content", {}).get("team", [])
    if not isinstance(t_content, list) or len(t_content) < 2:
        return []

    players_block = t_content[1].get("roster", {}).get("0", {}).get("players", {})
    results = []
    player_keys = []

    for i in range(int(players_block.get("count", 0))):
        p_data = players_block.get(str(i), {}).get("player", [])
        p_info = flatten_yahoo_player(p_data)
        p_key = p_info.get("player_key")
        player_keys.append(p_key)

        # selected_position extraction
        selected_position_raw = p_info.get("selected_position")
        selected_position = None

        if isinstance(selected_position_raw, list):
            for item in selected_position_raw:
                if isinstance(item, dict) and "position" in item:
                    selected_position = item.get("position")
        else:
            selected_position = selected_position_raw

        # FIX: is_editable is a standalone sibling dict in the player array,
        # not nested inside selected_position. flatten_yahoo_player captures it
        # via flat.update(item), so read it directly from p_info and convert to bool.
        raw_editable = p_info.get("is_editable")
        is_editable = bool(int(raw_editable)) if raw_editable is not None else None

        # starting_status extraction
        starting_status_raw = p_info.get("starting_status", [])
        if isinstance(starting_status_raw, list):
            is_starting = next(
                (item.get("is_starting") for item in starting_status_raw
                 if isinstance(item, dict) and "is_starting" in item),
                None
            )
        else:
            is_starting = None

        results.append({
            "player_key": p_key,
            "name": p_info.get("name", {}).get("full"),
            "team": p_info.get("editorial_team_full_name"),
            "position": p_info.get("display_position"),
            "selected_position": selected_position,
            "is_editable": is_editable,
            "is_starting": is_starting,
            "status": p_info.get("status", "Healthy"),
            "preseason_rank": p_info.get("preseason_rank"),
            "current_rank": p_info.get("current_rank"),
            "percent_started": None
        })

    # Second call: fetch percent_started from ownership endpoint
    pct_started_map = get_percent_started(session, player_keys)
    for player in results:
        player["percent_started"] = pct_started_map.get(player["player_key"])

    return results

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--league", default="469.l.23321")
    parser.add_argument("--team", default="Zegster")
    parser.add_argument("--date", help="Date in YYYY-MM-DD format", default=None)
    args = parser.parse_args()

    session = get_oauth_session()

    print(f"Finding team '{args.team}'...")
    t_key = get_team_key(session, args.league, args.team)

    if not t_key:
        print("Team not found.")
        return

    print(f"Fetching roster for {t_key}...")
    roster = get_roster(session, args.league, t_key,args.date)

    output_file = f"current_roster.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, ensure_ascii=False)

    print(f"✅ Saved {len(roster)} players to {output_file}")

if __name__ == "__main__":
    main()