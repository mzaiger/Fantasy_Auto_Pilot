"""
Fantasy Baseball Roster Optimizer
----------------------------------
Reads current_roster.json (and optionally mlb_games_today.json) and generates
a roster_update.xml with optimal position assignments for all editable slots.

Algorithm:
  1. Load mlb_games_today.json and build the set of teams with active games
     today (postponed=true games are excluded from the set).
  2. Lock non-editable players in their current selected_position.
  3. Players with status IL/NA keep those positions regardless of editability.
  4. Players with is_starting == 0 are forced to BN.
  5. Editable players whose team has NO game today are forced to BN.
  6. All remaining editable players are ranked per eligible position using a
     composite score (33% preseason_rank↑ + 33% current_rank↑ + 33% percent_started↓)
     where "↑" means lower is better and "↓" means higher is better.
  7. Positions are filled in order: C, 1B, 2B, 3B, SS, OF, OF, OF,
     Util, Util, SP, SP, SP, RP, RP, RP, P, P, P.
     Once a player is assigned a slot they are removed from all other pools.
  8. Any editable players not placed in an active slot are marked BN.
"""

import json
import math
import copy
import argparse
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom
from datetime import date

# ── Configuration ──────────────────────────────────────────────────────────────
ROSTER_JSON  = "current_roster.json"
GAMES_JSON   = "mlb_games.json"
OUTPUT_XML   = "roster_update.xml"
parser = argparse.ArgumentParser(description="Fantasy Baseball Roster Optimizer")
parser.add_argument(
    "--date",
    default=str(date.today()),
    help="Roster date in YYYY-MM-DD format (default: today)"
)
parser.add_argument(
    "--games",
    default=GAMES_JSON,
    help="Path to mlb_games_today.json (default: %(default)s)"
)
args = parser.parse_args()
ROSTER_DATE = args.date
GAMES_JSON  = args.games

# Active position slots to fill (order matters for greedy assignment)
ACTIVE_SLOTS = [
    "C", "1B", "2B", "3B", "SS",
    "OF", "OF", "OF",
    "Util", "Util",
    "SP", "SP", "SP",
    "RP", "RP", "RP",
    "P", "P", "P",
]

# Util can hold any hitter position; P can hold any pitcher position
UTIL_ELIGIBLE  = {"C", "1B", "2B", "3B", "SS", "OF"}
P_ELIGIBLE     = {"SP", "RP"}

# Weights (must sum to 1.0)
W_PRESEASON   = 1 / 3
W_CURRENT     = 1 / 3
W_PCT_STARTED = 1 / 3

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_positions(pos_str: str) -> set:
    """Return the set of position strings from a comma-delimited field."""
    return {p.strip() for p in pos_str.split(",") if p.strip()}


def safe_rank(val):
    """Convert a rank string/number to int; missing/None → large penalty."""
    try:
        return int(val)
    except (TypeError, ValueError):
        return 9999


def safe_pct(val):
    """Convert percent_started to float; missing/None → 0."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def composite_score(player: dict, pool: list) -> float:
    """
    Higher score = better player.
    """
    pre_ranks = [safe_rank(p["preseason_rank"])   for p in pool]
    cur_ranks = [safe_rank(p["current_rank"])      for p in pool]
    pcts      = [safe_pct(p["percent_started"])    for p in pool]

    def norm_low(value, values):
        mn, mx = min(values), max(values)
        if mx == mn:
            return 1.0
        return 1.0 - (value - mn) / (mx - mn)

    def norm_high(value, values):
        mn, mx = min(values), max(values)
        if mx == mn:
            return 1.0
        return (value - mn) / (mx - mn)

    pre_score = norm_low(safe_rank(player["preseason_rank"]),   pre_ranks)
    cur_score = norm_low(safe_rank(player["current_rank"]),     cur_ranks)
    pct_score = norm_high(safe_pct(player["percent_started"]),  pcts)

    return W_PRESEASON * pre_score + W_CURRENT * cur_score + W_PCT_STARTED * pct_score


def slot_matches(slot: str, player_positions: set) -> bool:
    """Return True when the player can legally play the requested slot."""
    if slot in ("IL", "NA", "BN"):
        return True                        
    if slot == "Util":
        return bool(player_positions & UTIL_ELIGIBLE)
    if slot == "P":
        return bool(player_positions & P_ELIGIBLE)
    return slot in player_positions


def pretty_xml(element: Element) -> str:
    """Return an indented XML string."""
    raw = tostring(element, encoding="unicode")
    reparsed = minidom.parseString(raw)
    return reparsed.toprettyxml(indent="  ")


def load_playing_teams(games_path: str) -> set:
    """
    Parse mlb_games_today.json and return a set of team names.
    """
    try:
        with open(games_path) as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"  WARNING: Games file not found at '{games_path}'. "
              "All players treated as having a game today.")
        return None          

    playing = set()
    postponed_teams = set()

    for game in data.get("mlb_games", []):
        away = game["away_team"]["name"].strip().lower()
        home = game["home_team"]["name"].strip().lower()
        if game.get("postponed", False):
            postponed_teams.add(away)
            postponed_teams.add(home)
            print(f"  POSTPONED: {game['away_team']['name']} @ "
                  f"{game['home_team']['name']} "
                  f"({game.get('postpone_reason') or 'reason not given'})")
        else:
            playing.add(away)
            playing.add(home)

    playing -= postponed_teams   
    return playing


def team_has_game(player: dict, playing_teams: set) -> bool:
    """Return True if the player's team is in the active-games set."""
    if playing_teams is None:
        return True            
    raw = player.get("team", "").strip().lower()
    return raw in playing_teams


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    with open(ROSTER_JSON) as fh:
        roster = json.load(fh)

    # ── Step 1: Load today's games ────────────────────────────────────────────
    print("── MLB Games Today ───────────────────────────────────────────────")
    playing_teams = load_playing_teams(GAMES_JSON)
    if playing_teams is not None:
        print(f"  Teams with active games ({len(playing_teams)}): "
              + ", ".join(sorted(t.title() for t in playing_teams)))
    print()

    # ── Step 2: Partition players ─────────────────────────────────────────────
    locked      = []   
    il_na       = []   
    force_bn    = []   
    no_game_bn  = []   
    available   = []   

    for p in roster:
        sel_pos  = p["selected_position"]
        editable = bool(p.get("is_editable", False))

        if sel_pos in ("IL", "IL15", "IL60", "NA"):
            il_na.append(p)
        elif not editable:
            locked.append(p)
        elif p.get("is_starting") == 0:
            force_bn.append(p)
        elif not team_has_game(p, playing_teams):
            no_game_bn.append(p)
        else:
            available.append(p)

    print("── Player Partition ──────────────────────────────────────────────")
    print(f"  Locked (non-editable):       {len(locked)}")
    print(f"  IL / NA (kept):              {len(il_na)}")
    print(f"  Forced BN (not starting):    {len(force_bn)}")
    print(f"  Forced BN (no game today):   {len(no_game_bn)}")
    for p in no_game_bn:
        print(f"    → {p['name']:30s}  (team: {p['team'].strip()})")
    print(f"  Available for active slots:  {len(available)}")
    print()

    # ── Step 3: Determine which active slots are available to fill ─────────────
    locked_slot_counts: dict[str, int] = {}
    for p in locked:
        sel = p["selected_position"]
        if sel not in ("BN",):          
            locked_slot_counts[sel] = locked_slot_counts.get(sel, 0) + 1

    print("Slots consumed by locked players:")
    for slot, cnt in sorted(locked_slot_counts.items()):
        print(f"  {slot}: {cnt}")
    print()

    # Fix: Correctly calculate remaining slots without double-counting
    remaining_slot_counts = {}
    for slot in ACTIVE_SLOTS:
        remaining_slot_counts[slot] = remaining_slot_counts.get(slot, 0) + 1

    for slot, cnt in locked_slot_counts.items():
        if slot in remaining_slot_counts:
            remaining_slot_counts[slot] = max(0, remaining_slot_counts[slot] - cnt)

    # Use a temp counter to ensure we only add the remaining amount per slot type
    open_slots = []
    temp_counts = copy.deepcopy(remaining_slot_counts)
    for slot in ACTIVE_SLOTS:
        if temp_counts.get(slot, 0) > 0:
            open_slots.append(slot)
            temp_counts[slot] -= 1

    print(f"Open slots for editable players: {open_slots}")
    print(f"Editable players to place: {[p['name'] for p in available]}")
    print()

    # ── Step 4: Greedy best-fit assignment ────────────────────────────────────
    unassigned = list(available)          
    assignments: dict[str, str] = {}     

    for slot in open_slots:
        candidates = [
            p for p in unassigned
            if slot_matches(slot, parse_positions(p["position"]))
        ]
        if not candidates:
            print(f"  WARNING: No eligible player for slot '{slot}'")
            continue

        scored = sorted(
            candidates,
            key=lambda p: composite_score(p, candidates),
            reverse=True   
        )
        best = scored[0]
        assignments[best["player_key"]] = slot
        unassigned.remove(best)
        print(f"  Slot {slot:6s} → {best['name']:30s}  "
              f"(pre={best['preseason_rank']}, cur={best['current_rank']}, "
              f"pct={best['percent_started']})")

    for p in unassigned:
        assignments[p["player_key"]] = "BN"
        print(f"  Slot {'BN':6s} → {p['name']:30s}  (no suitable active slot)")

    # ── Step 5 & 6: Position map and XML ──────────────────────────────────────
    final_positions: dict[str, str] = {}

    for p in locked:
        final_positions[p["player_key"]] = p["selected_position"]

    for p in il_na:
        sel = p["selected_position"]
        final_positions[p["player_key"]] = "IL" if sel.startswith("IL") else sel

    for p in force_bn:
        final_positions[p["player_key"]] = "BN"

    for key, pos in assignments.items():
        final_positions[key] = pos

    for p in no_game_bn:
        final_positions[p["player_key"]] = "BN"

    root = Element("fantasy_content")
    roster_el = SubElement(root, "roster")
    SubElement(roster_el, "coverage_type").text = "date"
    SubElement(roster_el, "date").text = ROSTER_DATE
    players_el = SubElement(roster_el, "players")

    for p in roster:
        key = p["player_key"]
        pos = final_positions.get(key, "BN")
        player_el = SubElement(players_el, "player")
        SubElement(player_el, "player_key").text = key
        SubElement(player_el, "position").text   = pos

    xml_str = pretty_xml(root)
    with open(OUTPUT_XML, "w") as fh:
        fh.write(xml_str)

    print(f"\nXML written to: {OUTPUT_XML}")

    print("\n── Final Roster ──────────────────────────────────────────────────")
    for p in roster:
        key = p["player_key"]
        pos = final_positions.get(key, "BN")
        editable_flag = "✎" if p.get("is_editable") else " "
        no_game_flag  = "⚑" if p in no_game_bn else " "
        print(f"  {editable_flag}{no_game_flag} {p['name']:30s}  {pos:6s}  "
              f"(was: {p['selected_position']}, team: {p['team'].strip()})")


if __name__ == "__main__":
    main()