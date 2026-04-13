import json
import requests
import os

def send_to_make():
    json_file = 'mlb_games.json'
    # PASTE YOUR URL FROM MAKE HERE
    MAKE_WEBHOOK_URL = "https://hook.us2.make.com/88c77386m8dg9jacqjjx5k1tswcb8o3p"
    # IF YOU ADDED AN API KEY, PUT IT HERE
    API_KEY = "Zaiger2026"
    if not os.path.exists(json_file):
        print(f"Error: {json_file} not found.")
        return

    with open(json_file, 'r') as f:
        game_data = json.load(f)

    headers = {
        "Content-Type": "application/json",
        "x-make-apikey": API_KEY  # Remove this line if you didn't add an API key
    }

    response = requests.post(MAKE_WEBHOOK_URL, json=game_data, headers=headers)
    
    if response.status_code == 200:
        print("✅ Sent MLB game data to Make.com")
    else:
        print(f"❌ Failed to send: {response.status_code} - {response.text}")

if __name__ == "__main__":
    send_to_make()
