"""
Yahoo Fantasy roster automation for GitHub Actions.

Loads an authenticated Yahoo session from YAHOO_COOKIES_B64
and clicks "Start Active Players".

Usage:
    python manualTriggerSetLineup.py "https://baseball.fantasysports.yahoo.com/b1/XXXXX/YYYYY"
"""

import base64
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


COOKIES_B64 = os.environ.get("YAHOO_COOKIES_B64")

if not COOKIES_B64:
    sys.exit(
        "Set YAHOO_COOKIES_B64 environment variable "
        "(base64-encoded Yahoo cookie export)."
    )


def build_driver():
    options = webdriver.ChromeOptions()

    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    options.page_load_strategy = "eager"

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)

    return driver


def load_cookies(driver):
    cleaned = "".join(COOKIES_B64.split())
    cleaned += "=" * (-len(cleaned) % 4)

    try:
        decoded = base64.b64decode(cleaned, validate=True)
        cookies = json.loads(decoded)
    except Exception as e:
        raise RuntimeError(
            f"Could not decode YAHOO_COOKIES_B64: {e}"
        )

    # Get onto Yahoo's domain before adding cookies.
    try:
        driver.get("https://baseball.fantasysports.yahoo.com/")
    except TimeoutException:
        driver.execute_script("window.stop();")

    # Install cookies.
    for cookie in cookies:
        cookie = cookie.copy()

        # Selenium does not need this field and some exports
        # contain values Selenium rejects.
        cookie.pop("sameSite", None)

        if "expiry" in cookie:
            try:
                cookie["expiry"] = int(cookie["expiry"])
            except Exception:
                cookie.pop("expiry", None)

        try:
            driver.add_cookie(cookie)
        except Exception:
            # Ignore cookies that belong to another Yahoo subdomain
            # such as football.fantasysports.yahoo.com.
            pass

    # Refresh so Yahoo sees the authenticated cookies.
    try:
        driver.refresh()
    except TimeoutException:
        driver.execute_script("window.stop();")


def click_set_active_players(driver, wait):
    strategies = [
        (By.XPATH, "//button[contains(., 'Start Active Players')]"),
        (By.XPATH, "//a[contains(., 'Start Active Players')]"),
        (By.XPATH, "//*[contains(text(), 'Start Active Players')]"),
        (By.CSS_SELECTOR, "input[value*='Start Active']"),
    ]

    for by, selector in strategies:
        try:
            button = wait.until(
                EC.element_to_be_clickable((by, selector))
            )

            button.click()

            # Give Yahoo time to process the action.
            time.sleep(8)

            # If Yahoo sent us to login, fail this attempt.
            if "login.yahoo.com" in driver.current_url:
                raise RuntimeError(
                    "Yahoo redirected to login after clicking "
                    "'Start Active Players'."
                )

            print("✅ Start Active Players clicked successfully.")
            return

        except TimeoutException:
            continue

    raise NoSuchElementException(
        "Could not find 'Start Active Players' button."
    )


def main():
    if len(sys.argv) < 2:
        sys.exit(
            "Usage: python manualTriggerSetLineup.py "
            "<roster_page_url>"
        )

    roster_url = sys.argv[1]

    driver = build_driver()
    wait = WebDriverWait(driver, 20)

    try:
        load_cookies(driver)

        # Navigate to the actual roster page.
        try:
            driver.get(roster_url)
        except TimeoutException:
            driver.execute_script("window.stop();")

        # Check whether Yahoo immediately rejected the session.
        if "login.yahoo.com" in driver.current_url:
            raise RuntimeError(
                "Yahoo session cookies are invalid or expired."
            )

        click_set_active_players(driver, wait)

        time.sleep(2)

        print("✅ Manual Yahoo lineup trigger completed.")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()
