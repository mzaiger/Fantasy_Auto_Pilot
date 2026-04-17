"""
Fantasy Baseball Roster Optimizer
----------------------------------
Documentation:
  1. Date Agnostic: Includes all games in mlb_games.json regardless of UTC date.
  2. PPD Handling: Automatically benches players if their game is postponed.
  3. Strict Benching:
     - Benches any player with is_starting == 0.
     - Benches Starting Pitchers (SP) who are not confirmed starters (is_starting != 1), 
       unless they also have RP eligibility.
  4. Scoring: Ranks available players by Preseason Rank, Current Rank, and % Started.
"""

import json
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# Files
ROSTER_JSON  = "current_roster (1).json"
GAMES_JSON   = "mlb_games (1).json"
OUTPUT_XML   = "roster_update.xml"
ROSTER_DATE  = "2026-04-17" 

# Filling Order
ACTIVE_SLOTS = [
    "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "Util", "Util",
    "SP", "SP", "SP", "RP", "RP", "RP", "P", "P", "P"
]

def load_playing_teams(games_path):
    try:
        with open(games_path) as f:
            data = json.load(f)
        playing = set()
        for game in data.get("mlb_games", []):
            # If game is NOT postponed, add teams to playing set
            if not game.get("postponed"):
                playing.add(game["away_team"]["name"].strip().lower())
                playing.add(game["home_team"]["name"].strip().lower())
        return playing
    except:
        return None

def get_composite_score(player, pool):
    def s_int(v):
        try: return int(v)
        except: return 9999
    
    # Normalization (0.0 to 1.0, where 1.0 is best)
    pre_ranks = [s_int(p["preseason_rank"]) for p in pool]
    cur_ranks = [s_int(p["current_rank"]) for p in pool]
    
    s1 = 1.0 - (s_int(player["preseason_rank"]) - min(pre_ranks)) / (max(pre_ranks) - min(pre_ranks)) if max(pre_ranks) != min(pre_ranks) else 1.0
    s2 = 1.0 - (s_int(player["current_rank"]) - min(cur_ranks)) / (max(cur_ranks) - min(cur_ranks)) if max(cur_ranks) != min(cur_ranks) else 1.0
    
    score = (s1 * 0.5) + (s2 * 0.5)

    # Massive boost for any confirmed starter (Hitters or Pitchers)
    if player.get("is_starting") == 1:
        score += 10.0
        
    return score

def generate_roster():
    with open(ROSTER_JSON) as f:
        roster = json.load(f)
    playing_teams = load_playing_teams(GAMES_JSON)

    available_pool = []
    final_assignments = {}

    for p in roster:
        # 1. Keep IL/NA players locked
        if p["selected_position"] in ["IL", "IL15", "IL60", "NA"]:
            final_assignments[p["player_key"]] = p["selected_position"]
            continue
        
        # 2. Basic Filtering (Not Editable, Confirmed Benched, or Postponed/No Game)
        team_name = p.get("team", "").strip().lower()
        if not p.get("is_editable") or p.get("is_starting") == 0 or team_name not in playing_teams:
            final_assignments[p["player_key"]] = "BN"
            continue
        
        # 3. Strict SP Benching:
        # Bench SPs who aren't the confirmed starter for today (unless they are also RPs)
        pos_list = p["position"].split(",")
        if "SP" in pos_list and "RP" not in pos_list and p.get("is_starting") != 1:
            final_assignments[p["player_key"]] = "BN"
            continue

        available_pool.append(p)

    # Score and Sort
    for p in available_pool:
        p["score"] = get_composite_score(p, available_pool)
    
    available_pool.sort(key=lambda x: x["score"], reverse=True)

    # Assign Positions
    remaining_slots = list(ACTIVE_SLOTS)
    for p in available_pool:
        player_positions = p["position"].split(",")
        assigned = False
        
        # Try Primary Positions
        for pos in player_positions:
            if pos in remaining_slots:
                final_assignments[p["player_key"]] = pos
                remaining_slots.remove(pos)
                assigned = True
                break
        
        # Try Utility/Generic P slots
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

    # XML Output
    root = Element("fantasy_content")
    roster_el = SubElement(root, "roster")
    SubElement(roster_el, "date").text = ROSTER_DATE
    players_el = SubElement(roster_el, "players")

    for p in roster:
        p_el = SubElement(players_el, "player")
        SubElement(p_el, "player_key").text = p["player_key"]
        SubElement(p_el, "position").text = final_assignments.get(p["player_key"], "BN")

    xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="  ")
    with open(OUTPUT_XML, "w") as f:
        f.write(xml_str)
    print(f"Generated {OUTPUT_XML}")

if __name__ == "__main__":
    generate_roster()
