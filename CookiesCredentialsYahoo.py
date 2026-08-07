"""
Run this LOCALLY (not in Actions) to capture an authenticated Yahoo
session as cookies, which you'll then store as a GitHub Actions secret.

Usage:
    python export_yahoo_cookies.py

This opens a real Chrome window. Log into Yahoo and complete 2FA
manually. Once you're on a logged-in Yahoo page, press Enter in the
terminal to save cookies to yahoo_cookies.json.
"""

import json
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

options = webdriver.ChromeOptions()
options.add_argument("--start-maximized")
service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

driver.get("https://login.yahoo.com")
input("Log in (and complete 2FA) in the browser window, then press Enter here...")

# Navigate to the fantasy domain so the cookies we grab are scoped correctly
driver.get("https://football.fantasysports.yahoo.com")
input("Confirm you're logged in and the page loaded, then press Enter to export cookies...")

cookies = driver.get_cookies()
with open("yahoo_cookies.json", "w") as f:
    json.dump(cookies, f)

print(f"Saved {len(cookies)} cookies to yahoo_cookies.json")
print("Next: base64-encode this file and store it as a GitHub Actions secret.")
print("Do NOT commit yahoo_cookies.json to the repo.")

driver.quit()