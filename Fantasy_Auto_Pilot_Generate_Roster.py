"""
Fantasy Baseball Roster Optimizer
----------------------------------
Fixes: 
 - Force-formats XML to match Yahoo API's rigid requirements.
 - Ensures the 'xmlns' attribute is present in the root tag.
 - Removes extra whitespace that can cause 'Invalid XML' errors.
"""

import json
import argparse
import sys
import xml.etree.ElementTree as ET

# Default File Paths
ROSTER_JSON  = "current_roster.json"
GAMES_JSON   = "mlb_games.json"
OUTPUT_XML   = "roster_update.xml"

ACTIVE_SLOTS = [
    "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "Util", "Util",
    "SP", "SP", "SP", "RP", "RP", "RP", "P", "P", "P"
]

def load_playing_teams(games_path):
    try:
        with open(games_path, 'r') as f:
            data = json.load(f)
        playing = set()
        for game in data.get("mlb_games", []):
            if not game.get("postponed"):
                playing.add(game["away_team"]["name"].strip().lower())
                playing.add(game["home_team"]["name"].strip().lower())
        return playing
    except Exception:
        return None

def get_composite_score(player, pool):
    def s_int(v):
        try: return int(v)
        except: return 9999
    pre_ranks = [s_int(p["preseason_rank"]) for p in pool]
    cur_ranks = [s_int(p["current_rank"]) for p in pool]
    min_pre, max_pre = min(pre_ranks), max(pre_ranks)
    min_cur, max_cur = min(cur_ranks), max(cur_ranks)
    s1 = 1.0 - (s_int(player["preseason_rank"]) - min_pre) / (max_pre - min_pre) if max_pre != min_pre else 1.0
    s2 = 1.0 - (s_int(player["current_rank"]) - min_cur) / (max_cur - min_cur) if max_cur != min_cur else 1.0
    score = (s1 * 0.5) + (s2 * 0.5)
    if player.get("is_starting") == 1:
        score += 10.0
    return score

def generate_roster(target_date):
    try:
        with open(ROSTER_JSON, 'r') as f:
            roster = json.load(f)
    except FileNotFoundError:
        print(f"Error: {ROSTER_JSON} not found.")
        sys.exit(1)

    playing_teams = load_playing_teams(GAMES_JSON)
    available_pool = []
    final_assignments = {}

    for p in roster:
        if p["selected_position"] in ["IL", "IL15", "IL60", "NA"]:
            final_assignments[p["player_key"]] = p["selected_position"]
            continue
        
        team_name = p.get("team", "").strip().lower()
        if not p.get("is_editable") or p.get("is_starting") == 0 or team_name not in playing_teams:
            final_assignments[p["player_key"]] = "BN"
            continue
        
        pos_list = p["position"].split(",")
        if "SP" in pos_list and "RP" not in pos_list and p.get("is_starting") != 1:
            final_assignments[p["player_key"]] = "BN"
            continue
        available_pool.append(p)

    for p in available_pool:
        p["score"] = get_composite_score(p, available_pool)
    available_pool.sort(key=lambda x: x["score"], reverse=True)

    remaining_slots = list(ACTIVE_SLOTS)
    for p in available_pool:
        player_positions = p["position"].split(",")
        assigned = False
        for pos in player_positions:
            if pos in remaining_slots:
                final_assignments[p["player_key"]] = pos
                remaining_slots.remove(pos)
                assigned = True
                break
        if not assigned:
            is_hitter = any(pos in ["C", "1B", "2B", "3B", "SS", "OF"] for pos in player_positions)
            if is_hitter and "Util" in remaining_slots:
                final_assignments[p["player_key"]] = "Util"
                remaining_slots.remove("Util")
                assigned = True
            elif not is_hitter and "P" in remaining_slots:
                final_assignments[p["player_key"]] = "P"
                remaining_slots.remove("P")
                assigned = True
        if not assigned:
            final_assignments[p["player_key"]] = "BN"

    # --- UPDATED YAHOO COMPLIANT XML GENERATION ---
    # We use a manual string template to ensure no extra whitespace/formatting 
    # interferes with the Yahoo API's strict parser.
    xml_header = '<?xml version="1.0" encoding="UTF-8"?>'
    root_open = '<fantasy_content xmlns="http://fantasysports.yahooapis.com/fantasy/v2/base.rng">'
    roster_open = '<roster>'
    cov_type = f'<coverage_type>date</coverage_type>'
    date_tag = f'<date>{target_date}</date>'
    players_open = '<players>'
    
    player_entries = []
    for p in roster:
        pos = final_assignments.get(p['player_key'], 'BN')
        entry = (
            f"<player>"
            f"<player_key>{p['player_key']}</player_key>"
            f"<position>{pos}</position>"
            f"</player>"
        )
        player_entries.append(entry)
    
    players_close = '</players>'
    roster_close = '</roster>'
    root_close = '</fantasy_content>'

    full_xml = (
        xml_header + root_open + roster_open + cov_type + 
        date_tag + players_open + "".join(player_entries) + 
        players_close + roster_close + root_close
    )
    
    with open(OUTPUT_XML, "w", encoding='utf-8') as f:
        f.write(full_xml)
    
    print(f"Successfully generated Yahoo-compliant {OUTPUT_XML} for {target_date}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    generate_roster(args.date)
