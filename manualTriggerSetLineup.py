"""
Logs into Yahoo and clicks the "Set Active Players" button on a Yahoo
Fantasy roster page.

Setup:
    pip install selenium webdriver-manager

Before running, set these environment variables (do NOT hardcode creds):
    export YAHOO_EMAIL="your_email_or_username"
    export YAHOO_PASSWORD="your_password"

Usage:
    python set_active_players.py "https://football.fantasysports.yahoo.com/f1/XXXXX/YYYYY"
"""

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


YAHOO_EMAIL = os.environ.get("YAHOO_EMAIL")
YAHOO_PASSWORD = os.environ.get("YAHOO_PASSWORD")

if not YAHOO_EMAIL or not YAHOO_PASSWORD:
    sys.exit("Set YAHOO_EMAIL and YAHOO_PASSWORD environment variables first.")


def build_driver(headless: bool = False) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    service = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=service, options=options)


def login_to_yahoo(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    driver.get("https://login.yahoo.com")

    # Username step
    email_field = wait.until(EC.presence_of_element_located((By.ID, "login-username")))
    email_field.send_keys(YAHOO_EMAIL)
    driver.find_element(By.ID, "login-signin").click()

    # Password step
    password_field = wait.until(EC.presence_of_element_located((By.ID, "login-passwd")))
    password_field.send_keys(YAHOO_PASSWORD)
    driver.find_element(By.ID, "login-signin").click()

    # Give Yahoo a moment in case of a 2FA / "verify it's you" challenge.
    # If that screen appears, pause here and complete it manually.
    time.sleep(3)
    if "challenge" in driver.current_url or "verify" in driver.current_url:
        input("Complete the Yahoo verification step in the browser, then press Enter here...")


def click_set_active_players(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    # Try a few strategies since Yahoo's markup/class names shift over time.
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

    raise NoSuchElementException(
        "Could not find 'Set Active Players' button with any known strategy. "
        "Inspect the page and add the correct selector."
    )


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python set_active_players.py <roster_page_url>")

    roster_url = sys.argv[1]

    driver = build_driver(headless=False)  # keep headless=False until selectors are confirmed
    wait = WebDriverWait(driver, 20)

    try:
        login_to_yahoo(driver, wait)
        driver.get(roster_url)
        click_set_active_players(driver, wait)
        time.sleep(2)  # let any confirmation UI settle
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
