import os
import json
import time
import argparse
from pathlib import Path
from requests_oauthlib import OAuth2Session

# --- CONFIG (Using your provided keys) ---
# --- CONFIG ---
CLIENT_ID     = os.getenv("YAHOO_CLIENT_ID")
CLIENT_SECRET = os.getenv("YAHOO_CLIENT_SECRET")
REDIRECT_URI = "https://localhost"
AUTHORIZATION_URL = "https://api.login.yahoo.com/oauth2/request_auth"
TOKEN_URL = "https://api.login.yahoo.com/oauth2/get_token"
TOKEN_CACHE = Path("token_cache.json")
BASE_URL = "https://fantasysports.yahooapis.com/fantasy/v2"

# --- AUTH HELPERS (Standard from your previous scripts) ---
def _save_token(token): 
    TOKEN_CACHE.write_text(json.dumps(token, indent=2))

def _load_token():
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
        token = session.fetch_token(TOKEN_URL, authorization_response=redirect_response, client_secret=CLIENT_SECRET)
        _save_token(token)
    return session

# --- CORE LOGIC ---

def push_roster_update(session, team_key, xml_file, date_str=None):
    """Sends a PUT request with the XML lineup data."""
    if not os.path.exists(xml_file):
        print(f"Error: {xml_file} not found.")
        return

    # Read the XML content
    with open(xml_file, "r", encoding="utf-8") as f:
        xml_data = f.read()

    """Fetches roster with ranks and starting_status, then merges percent_started."""
    date_param = f";date={date_str}" if date_str else ""

    # API Endpoint for roster updates
    url = f"{BASE_URL}/team/{team_key}/roster{date_param}"
    
    # Headers must specify XML
    headers = {"Content-Type": "application/xml"}
    
    print(f"Pushing roster update to {team_key}...")
    resp = session.put(url, data=xml_data, headers=headers)

    if resp.status_code == 200 or resp.status_code == 201:
        print("✅ Roster updated successfully!")
    else:
        print(f"❌ Failed to update roster. Status Code: {resp.status_code}")
        print(f"Response: {resp.text}")

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

def api_get(session, url):
    resp = session.get(url, params={"format": "json"})
    return resp.json() if resp.status_code == 200 else {}


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

    print(f"Updating roster for {t_key}...")
    TEAM_KEY = t_key
    XML_FILENAME = "roster_update.xml"

    push_roster_update(session, TEAM_KEY, XML_FILENAME, args.date)

if __name__ == "__main__":
    main()