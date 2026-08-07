import subprocess
import argparse
import sys

ROSTER_SUCCESS_MESSAGE = "✅ Roster updated successfully!"

def run_command(command, capture=False):
    """Runs a shell command and waits for it to complete.

    If capture=True, stdout/stderr are captured (and still echoed to the
    console) so the caller can inspect the output, e.g. to check whether a
    particular message was printed. Returns the captured stdout, or None
    when capture=False.
    """
    print(f"Executing: {' '.join(command)}")
    try:
        if capture:
            result = subprocess.run(command, check=True, capture_output=True, text=True)
            if result.stdout:
                print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
            if result.stderr:
                print(result.stderr, end="" if result.stderr.endswith("\n") else "\n")
            return result.stdout
        else:
            # check=True will raise an error if a script fails
            subprocess.run(command, check=True)
            return None
    except subprocess.CalledProcessError as e:
        if capture:
            if e.stdout:
                print(e.stdout, end="" if e.stdout.endswith("\n") else "\n")
            if e.stderr:
                print(e.stderr, end="" if e.stderr.endswith("\n") else "\n")
        print(f"Error occurred while running {command[0]}: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Run full Fantasy Auto-Pilot pipeline.")
    parser.add_argument("--date", required=True, help="Target date in YYYY-MM-DD format")
    parser.add_argument("--league", default="469.l.23321", help="Yahoo League ID")
    parser.add_argument("--team", default="Zegster", help="Fantasy Team Name")
    parser.add_argument(
        "--roster-url",
        default="https://baseball.fantasysports.yahoo.com/b1/23321/12/",
        help="Yahoo roster page URL used by the backup manual trigger (manualTriggerSetLineup.py)",
    )

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
    update_output = run_command([
        "python", "Fantasy_Auto_Pilot_Update_Roster.py", 
        "--league", league, 
        "--team", team, 
        "--date", target_date
    ], capture=True)

    # 4b. Backup: if the API push didn't confirm success, fall back to the
    # Selenium-based manual trigger to force-set the active lineup directly
    # on the Yahoo roster page.
    if ROSTER_SUCCESS_MESSAGE not in (update_output or ""):
        print("⚠️ Roster update did not confirm success — running backup manual trigger...")
        run_command([
            "python", "manualTriggerSetLineup.py",
            args.roster_url
        ])
    else:
        print("Roster update confirmed — skipping backup manual trigger.")

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
