import json
import os
from datetime import datetime, timedelta

def update_workflow_schedule():
    # File paths
    json_file = 'mlb_games.json'
    workflow_path = '.github/workflows/fantasy_autopilot.yml'
    
    # Ensure the directory exists
    os.makedirs(os.path.dirname(workflow_path), exist_ok=True)

    # Base cron schedules - Start with 4:00 AM Central (09:00 UTC)
    # Using a set to ensure no duplicate times
    cron_schedules = {"0 9 * * *"}

    try:
        if os.path.exists(json_file):
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            for game in data.get('mlb_games', []):
                start_time_str = game.get('start_time_utc')
                if start_time_str:
                    # Parse UTC time (Format: 2026-04-15T16:35:00Z)
                    start_time = datetime.strptime(start_time_str, "%Y-%m-%dT%H:%M:%SZ")
                    
                    # Subtract 5 minutes
                    trigger_time = start_time - timedelta(minutes=5)
                    
                    # Create cron string: "minute hour * * *"
                    cron_str = f"{trigger_time.minute} {trigger_time.hour} * * *"
                    cron_schedules.add(cron_str)
        else:
            print(f"Warning: {json_file} not found. Using default 4am schedule only.")
            
    except Exception as e:
        print(f"Error parsing games: {e}")

    # Sort schedules for clean YAML output
    # (Note: simple string sort won't be chronological by time, but keeps it organized)
    sorted_schedules = sorted(list(cron_schedules))

    # Build the YAML content
    yaml_content = [
        "name: Fantasy Baseball Auto Pilot",
        "",
        "on:",
        "  schedule:"
    ]

    for cron in sorted_schedules:
        # Add comment for the 4am Central time for clarity
        comment = " # 4am Central" if cron == "0 9 * * *" else ""
        yaml_content.append(f"    - cron: '{cron}'{comment}")

    yaml_content.extend([
        "  workflow_dispatch:",
        "",
        "jobs:",
        "  build:",
        "    runs-on: ubuntu-latest",
        "    steps:",
        "      - name: Checkout repository",
        "        uses: actions/checkout@v4",
        "        with:",
        "          token: ${{ secrets.PAT_TOKEN }}",
        "",
        "      - name: Set up Python",
        "        uses: actions/setup-python@v5",
        "        with:",
        "          python-version: '3.10'",
        "",
        "      - name: Install dependencies",
        "        run: |",
        "          pip install yahoofantasy lxml requests-oauthlib",
        "",
        "      - name: Run Fantasy Auto Pilot",
        "        env:",
        "          YAHOO_CLIENT_ID: ${{ secrets.YAHOO_CLIENT_ID }}",
        "          YAHOO_CLIENT_SECRET: ${{ secrets.YAHOO_CLIENT_SECRET }}",
        "          YAHOO_TOKEN: ${{ secrets.YAHOO_TOKEN }}",
        "        run: |",
        "          CURRENT_DATE=$(TZ="""America/Chicago""" date +%Y-%m-%d)",
        "          python Fantasy_Auto_Pilot_Main.py --league 469.l.23321 --team \"Zegster\" --date \"$CURRENT_DATE\"",
        "",
        "      - name: Commit and Push changes",
        "        run: |",
        "          git config --global user.name \"GitHub Action\"",
        "          git config --global user.email \"action@github.com\"",
        "          git add .",
        "          git commit -m \"Auto-update roster for $(date +%Y-%m-%d)\" || echo \"No changes to commit\"",
        "          git push"
    ])

    with open(workflow_path, 'w') as f:
        f.write("\n".join(yaml_content))
    
    print(f"Successfully updated {workflow_path}")
    print(f"Total triggers scheduled: {len(sorted_schedules)}")

if __name__ == "__main__":
    update_workflow_schedule()
