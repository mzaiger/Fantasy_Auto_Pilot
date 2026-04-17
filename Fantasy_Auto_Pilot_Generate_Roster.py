"""
Fantasy Baseball Roster Optimizer
----------------------------------
Fixes: 
 - Generates multi-line, "pretty" XML for readability and compatibility.
 - Uses the official Yahoo Fantasy XML namespace.
 - Retains strict benching rules for PPD and non-starting pitchers.
"""

import json
import argparse
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom

# Default File Paths
ROSTER_JSON  = "current_roster.json"
GAMES_JSON   = "mlb_games.json"
OUTPUT_XML   = "roster_update.xml"

# Standard MLB Roster Slots
ACTIVE_SLOTS = [
    "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "Util", "Util",
    "SP", "SP", "SP", "RP", "RP", "RP", "P", "P", "P"
]

def load_playing_teams(games_path):
    """Identifies teams that have an active (non-postponed) game."""
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
    """Priority scoring: Preseason Rank + Current Rank + Start Status."""
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
    
    # Priority boost for confirmed starters
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
        # Keep IL/NA players where they are
        if p["selected_position"] in ["IL", "IL15", "IL60", "NA"]:
            final_assignments[p["player_key"]] = p["selected_position"]
            continue
        
        # Bench if: Not editable OR Confirmed Benched (0) OR Team is PPD/No Game
        team_name = p.get("team", "").strip().lower()
        if not p.get("is_editable") or p.get("is_starting") == 0 or (playing_teams is not None and team_name not in playing_teams):
            final_assignments[p["player_key"]] = "BN"
            continue
        
        # Bench SPs who are not the confirmed starter for today
        pos_list = p["position"].split(",")
        if "SP" in pos_list and "RP" not in pos_list and p.get("is_starting") != 1:
            final_assignments[p["player_key"]] = "BN"
            continue
            
        available_pool.append(p)

    # Sort players by priority score
    for p in available_pool:
        p["score"] = get_composite_score(p, available_pool)
    available_pool.sort(key=lambda x: x["score"], reverse=True)

    # Fill Roster
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

    # --- FORMATTED XML GENERATION ---
    # Register the namespace to avoid "ns0" prefixes
    namespace = "http://fantasysports.yahooapis.com/fantasy/v2/base.rng"
    ET.register_namespace('', namespace)
    
    root = ET.Element("{%s}fantasy_content" % namespace)
    roster_el = ET.SubElement(root, "roster")
    
    ET.SubElement(roster_el, "coverage_type").text = "date"
    ET.SubElement(roster_el, "date").text = target_date
    
    players_el = ET.SubElement(roster_el, "players")
    for p in roster:
        p_el = ET.SubElement(players_el, "player")
        ET.SubElement(p_el, "player_key").text = str(p["player_key"])
        ET.SubElement(p_el, "position").text = final_assignments.get(p["player_key"], "BN")

    # Create pretty string with minidom
    raw_xml = ET.tostring(root, encoding='utf-8')
    pretty_xml = minidom.parseString(raw_xml).toprettyxml(indent="  ")
    
    # Save with UTF-8 encoding
    with open(OUTPUT_XML, "w", encoding='utf-8') as f:
        f.write(pretty_xml)
    
    print(f"Generated formatted XML for {target_date} in {OUTPUT_XML}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True)
    args = parser.parse_args()
    generate_roster(args.date)
