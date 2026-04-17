"""
Fantasy Baseball Roster Optimizer
----------------------------------
Reads current_roster.json and mlb_games.json to generate a roster_update.xml 
with optimal position assignments for all editable slots.

Algorithm:
  1. Load mlb_games.json and build the set of teams with active games.
     *Updated: Ignores specific 'game_date' to account for UTC offsets.*
  2. Lock non-editable players in their current selected_position.
  3. Players with status IL/NA keep those positions regardless of editability.
  4. Players with is_starting == 0 (Confirmed Benched) are forced to BN.
  5. Editable players whose team has NO game in the games file are forced to BN.
  6. Remaining editable players are ranked using a composite score:
     (33% preseason_rank↑ + 33% current_rank↑ + 33% percent_started↓)
  7. Priority Balancing:
     *Pitchers* (SP/RP) with is_starting == 1 get a +10.0 score boost.
     *Hitters* with is_starting == 1 get a +0.1 tie-breaker boost.
     This ensures stars (like Vlad Jr.) aren't benched for replacement players
     simply because their official lineup wasn't posted yet.
  8. Positions are filled in order: C, 1B, 2B, 3B, SS, OF (3), Util (2), 
     SP (3), RP (3), P (3).
  9. Any editable players not placed in an active slot are marked BN.
"""

import json
import math
import copy
import argparse
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from datetime import date

# Configuration
ROSTER_JSON  = "current_roster.json"
GAMES_JSON   = "mlb_games.json"
OUTPUT_XML   = "roster_update.xml"
ROSTER_DATE  = "2026-04-17" 

ACTIVE_SLOTS = [
    "C", "1B", "2B", "3B", "SS", "OF", "OF", "OF", "Util", "Util",
    "SP", "SP", "SP", "RP", "RP", "RP", "P", "P", "P"
]

def load_playing_teams(games_path: str) -> set:
    """
    Parse mlb_games.json and return a set of team names.
    Ignores the date field to include all games present in the file.
    """
    try:
        with open(games_path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"  WARNING: Games file not found at '{games_path}'.")
        return None          

    playing = set()
    postponed_teams = set()

    for game in data.get("mlb_games", []):
        # .strip() handles the leading space found in some roster entries (e.g. " Athletics")
        away = game["away_team"]["name"].strip().lower()
        home = game["home_team"]["name"].strip().lower()
        
        if game.get("postponed", False):
            postponed_teams.add(away)
            postponed_teams.add(home)
        else:
            playing.add(away)
            playing.add(home)

    playing -= postponed_teams   
    return playing

def team_has_game(player: dict, playing_teams: set) -> bool:
    if playing_teams is None:
        return True            
    raw = player.get("team", "").strip().lower()
    return raw in playing_teams

def composite_score(player: dict, pool: list) -> float:
    """
    Ranks players based on Preseason Rank, Current Rank, and % Started.
    """
    def safe_int(val, default=9999):
        try: return int(val)
        except: return default
    def safe_float(val, default=0.0):
        try: return float(val)
        except: return default

    pre_ranks = [safe_int(p["preseason_rank"]) for p in pool]
    cur_ranks = [safe_int(p["current_rank"]) for p in pool]
    pct_stats = [safe_float(p["percent_started"]) for p in pool]

    def normalize_low(val, vals):
        mn, mx = min(vals), max(vals)
        return 1.0 - (val - mn) / (mx - mn) if mx != mn else 1.0
    def normalize_high(val, vals):
        mn, mx = min(vals), max(vals)
        return (val - mn) / (mx - mn) if mx != mn else 1.0

    s1 = normalize_low(safe_int(player["preseason_rank"]), pre_ranks)
    s2 = normalize_low(safe_int(player["current_rank"]), cur_ranks)
    s3 = normalize_high(safe_float(player["percent_started"]), pct_stats)
    
    base_score = (s1/3.0) + (s2/3.0) + (s3/3.0)

    # Priority logic to ensure stars start even if 'is_starting' is null (pending lineup)
    pos_list = player.get("position", "").split(",")
    is_pitcher = any(pos in ["SP", "RP", "P"] for pos in pos_list)
    
    if player.get("is_starting") == 1:
        if is_pitcher:
            return base_score + 10.0 
        else:
            return base_score + 0.1 
            
    return base_score

# ... [Remaining assignment logic from the previous script] ...
