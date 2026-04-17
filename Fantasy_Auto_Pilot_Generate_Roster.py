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
     - High-rank stars (like Vlad Jr.) now correctly beat low-rank replacement players.
"""

import json
import argparse
import sys
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

# Default File Paths (Adjusted to match your Get_Roster/Get_Games output)
ROSTER_JSON  = "current_roster.json"
GAMES_JSON   = "mlb_games.json"
OUTPUT_XML   = "roster_update.xml"

# Position Filling Order
ACTIVE_SLOTS = [
    "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "Util", "Util",
    "SP", "SP", "SP", "RP", "RP", "RP", "P", "P", "P"
]

def load_playing_teams(games_path):
    """Returns a set of teams that have a non-postponed game in the JSON."""
    try:
        with open(games_path, 'r') as f:
            data = json.load(f)
        playing = set()
        for game in data.get("mlb_games", []):
            if not game.get("postponed"):
                playing.add(game["away_team"]["name"].strip().lower())
                playing.add(game["home_team"]["name"].strip().lower())
        return playing
    except FileNotFoundError:
        print(f"Error: {games_path} not found.")
        return None

def get_composite_score(player, pool):
    """Calculates a priority score. Higher score = higher priority to start."""
    def s_int(v):
        try: return int(v)
        except: return 9999
    
    # Normalization (0.0 to 1.0, where 1.0 is the best rank in the pool)
    pre_ranks = [s_int(p["preseason_rank"]) for p in pool]
    cur_ranks = [s_int(p["current_rank"]) for p in pool]
    
    min_pre, max_pre = min(pre_ranks), max(pre_ranks)
    min_cur, max_cur = min(cur_ranks), max(cur_ranks)
    
    s1 = 1.0 - (s_int(player["preseason_rank"]) - min_pre) / (max_pre - min_pre) if max_pre != min_pre else 1.0
    s2 = 1.0 - (s_int(player["current_rank"]) - min_cur) / (max_cur - min_cur) if max_cur != min_cur else 1.0
    
    # Weighted Score (Average of ranks)
    score = (s1 * 0.5) + (s2 * 0.5)

    # Massive boost for confirmed starters (SP or Hitters)
    if player.get("is_starting") == 1:
        score += 10.0
        
    return score

def generate_roster(target_date):
    print(f"Starting roster generation for {target_date}...")
    
    try:
        with open(ROSTER_JSON, 'r') as f:
            roster = json.load(f)
    except FileNotFoundError:
        print(f"Error: {ROSTER_JSON} not found. Ensure Get_Roster script ran successfully.")
        sys.exit(1)

    playing_teams = load_playing_teams(GAMES_JSON)
    if playing_teams is None:
        sys.exit(1)

    available_pool = []
    final_assignments = {}

    for p in roster:
        # 1. Handle IL/NA (Keep them in their designated slots)
        if p["selected_position"] in ["IL", "IL15", "IL60", "NA"]:
            final_assignments[p["player_key"]] = p["selected_position"]
            continue
        
        # 2. Filter out non-starts
        team_name = p.get("team", "").strip().lower()
        
        # Bench if: Not editable OR Confirmed Benched (0) OR Team has no game/PPD
        if not p.get("is_editable") or p.get("is_starting") == 0 or team_name not in playing_teams:
            final_assignments[p["player_key"]] = "BN"
            continue
        
        # 3. SP Management: Bench SPs not confirmed for today (unless they are also RP eligible)
        pos_list = p["position"].split(",")
        if "SP" in pos_list and "RP" not in pos_list and p.get("is_starting") != 1:
            final_assignments[p["player_key"]] = "BN"
            continue

        available_pool.append(p)

    # Score and Sort Pool (Descending)
    for p in available_pool:
        p["score"] = get_composite_score(p, available_pool)
    
    available_pool.sort(key=lambda x: x["score"], reverse=True)

    # Position Assignment Logic
    remaining_slots = list(ACTIVE_SLOTS)
    for p in available_pool:
        player_positions = p["position"].split(",")
        assigned = False
        
        # Priority 1: Primary Position Match
        for pos in player_positions:
            if pos in remaining_slots:
                final_assignments[p["player_key"]] = pos
                remaining_slots.remove(pos)
                assigned = True
                break
        
        # Priority 2: Utility (Hitter) or P (Pitcher) Slots
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

        # Priority 3: No slots left
        if not assigned:
            final_assignments[p["player_key"]] = "BN"

    # Generate XML
    root = Element("fantasy_content")
    roster_el = SubElement(root, "roster")
    SubElement(roster_el, "date").text = target_date
    players_el = SubElement(roster_el, "players")

    for p in roster:
        p_el = SubElement(players_el, "player")
        SubElement(p_el, "player_key").text = p["player_key"]
        SubElement(p_el, "position").text = final_assignments.get(p["player_key"], "BN")

    # Final Save
    xml_str = minidom.parseString(tostring(root)).toprettyxml(indent="  ")
    with open(OUTPUT_XML, "w") as f:
        f.write(xml_str)
    
    print(f"Successfully generated {OUTPUT_XML} for {target_date}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Optimize Fantasy Roster")
    parser.add_argument("--date", help="Roster date in YYYY-MM-DD format", required=True)
    args = parser.parse_args()

    try:
        generate_roster(args.date)
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
