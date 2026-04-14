import subprocess
import argparse
import sys

def run_command(command):
    """Runs a shell command and waits for it to complete."""
    print(f"Executing: {' '.join(command)}")
    try:
        # check=True will raise an error if a script fails
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error occurred while running {command[0]}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run full Fantasy Auto-Pilot pipeline.")
    parser.add_argument("--date", required=True, help="Target date in YYYY-MM-DD format")
    parser.add_argument("--league", default="469.l.23321", help="Yahoo League ID")
    parser.add_argument("--team", default="Zegster", help="Fantasy Team Name")
    
    args = parser.parse_args()
    target_date = args.date
    league = args.league
    team = args.team

    # 1. Get Roster
    run_command([
        "python", "Fantasy_Auto_Pilot_Get_Roster.py", 
        "--league", league, 
        "--team", team, 
        "--date", target_date
    ])

    # 2. Get Games
    run_command([
        "python", "Fantasy_Auto_Pilot_Get_Games.py", 
        "--date", target_date
    ])

    # 3. Generate Roster
    run_command([
        "python", "Fantasy_Auto_Pilot_Generate_Roster.py", 
        "--date", target_date
    ])

    # 4. Update Roster
    run_command([
        "python", "Fantasy_Auto_Pilot_Update_Roster.py", 
        "--league", league, 
        "--team", team, 
        "--date", target_date
    ])

    # 5. Update YAML
    #run_command([
    #    "python", "Fantasy_Auto_Pilot_Update_YAML.py"
    #])

    # 5. Schedule External Triggers via Make.com
    #run_command([
    #    "python", "Fantasy_Auto_Pilot_Schedule_Make.py"
    #])
    
    print(f"\n✅ All tasks completed for {team} on {target_date}!")

if __name__ == "__main__":
    main()
