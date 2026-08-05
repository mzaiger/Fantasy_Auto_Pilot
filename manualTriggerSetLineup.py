"""
Yahoo Fantasy roster automation for use in GitHub Actions.

Instead of logging in interactively (impossible in a headless CI
runner with 2FA), this loads a previously-exported, authenticated
session via cookies stored in the YAHOO_COOKIES_B64 secret.

Env vars required:
    YAHOO_COOKIES_B64  - base64-encoded JSON cookie export (see export_yahoo_cookies.py)

Usage:
    python set_active_players_ci.py "https://baseball.fantasysports.yahoo.com/b1/XXXXX/YYYYY"
"""

import base64
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager


COOKIES_B64 = os.environ.get("YAHOO_COOKIES_B64")
if not COOKIES_B64:
    sys.exit("Set YAHOO_COOKIES_B64 environment variable (base64-encoded cookie export).")


def build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def load_cookies(driver: webdriver.Chrome) -> None:
    cookies = json.loads(base64.b64decode(COOKIES_B64))

    # Must be on the target domain before cookies can be added
    driver.get("https://baseball.fantasysports.yahoo.com")

    for cookie in cookies:
        # Selenium chokes on some fields (e.g. sameSite values, expiry as float)
        cookie.pop("sameSite", None)
        if "expiry" in cookie:
            cookie["expiry"] = int(cookie["expiry"])
        try:
            driver.add_cookie(cookie)
        except Exception as e:
            print(f"Skipped cookie {cookie.get('name')}: {e}")

    driver.refresh()


def click_set_active_players(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    strategies = [
        (By.XPATH, "//button[contains(., 'Set Active Players')]"),
        (By.XPATH, "//a[contains(., 'Set Active Players')]"),
        (By.XPATH, "//*[contains(text(), 'Set Active Players')]"),
        (By.CSS_SELECTOR, "input[value*='Set Active']"),
    ]
    for by, selector in strategies:
        try:
            button = wait.until(EC.element_to_be_clickable((by, selector)))
            button.click()
            print(f"Clicked button using strategy: {by} -> {selector}")
            return
        except TimeoutException:
            continue
    raise NoSuchElementException("Could not find 'Set Active Players' button.")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python set_active_players_ci.py <roster_page_url> (e.g. your baseball.fantasysports.yahoo.com roster URL)")

    roster_url = sys.argv[1]
    driver = build_driver()
    wait = WebDriverWait(driver, 20)

    try:
        load_cookies(driver)
        driver.get(roster_url)

        # If cookies were stale/expired, we'll land on a login page instead
        if "login.yahoo.com" in driver.current_url:
            sys.exit("Session cookies expired — re-run export_yahoo_cookies.py locally and update the secret.")

        click_set_active_players(driver, wait)
        time.sleep(2)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
