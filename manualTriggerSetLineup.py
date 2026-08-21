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
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException


COOKIES_B64 = os.environ.get("YAHOO_COOKIES_B64")
if not COOKIES_B64:
    sys.exit("Set YAHOO_COOKIES_B64 environment variable (base64-encoded cookie export).")


def build_driver() -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    # Required in CI containers (running as root) or Chrome can hang/crash silently
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    # Yahoo's pages carry a lot of ad/analytics scripts that can keep the
    # "load" event from ever firing. "eager" returns once the DOM is parsed
    # instead of waiting on every subresource, which is what was causing the
    # "Timed out receiving message from renderer" TimeoutException.
    options.page_load_strategy = "eager"
    # Selenium 4.6+ auto-downloads a matching driver via Selenium Manager —
    # no need for webdriver-manager, which can grab a mismatched version.
    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(45)  # fail loudly instead of hanging forever
    return driver


def load_cookies(driver: webdriver.Chrome) -> None:
    # Strip stray whitespace/newlines that copy-paste often introduces,
    # and fix missing padding (base64 length must be a multiple of 4).
    cleaned = "".join(COOKIES_B64.split())
    cleaned += "=" * (-len(cleaned) % 4)

    try:
        decoded = base64.b64decode(cleaned, validate=True)
    except Exception as e:
        sys.exit(
            f"YAHOO_COOKIES_B64 is not valid base64 ({e}). "
            "Regenerate it from yahoo_cookies.json and re-paste the secret without editing it."
        )

    try:
        cookies = json.loads(decoded)
    except Exception as e:
        sys.exit(
            f"YAHOO_COOKIES_B64 decoded but isn't valid JSON ({e}). "
            "The secret is likely corrupted or truncated — regenerate and re-paste it."
        )

    # Must be on the target domain before cookies can be added. Even with the
    # "eager" strategy Yahoo can occasionally hang past the timeout on a slow
    # CI network — treat that as "good enough to add cookies", not a fatal
    # error, since window.stop() leaves us on the right domain either way.
    try:
        driver.get("https://baseball.fantasysports.yahoo.com")
    except TimeoutException:
        driver.execute_script("window.stop();")

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
        (By.XPATH, "//button[contains(., 'Start Active Players')]"),
        (By.XPATH, "//a[contains(., 'Start Active Players')]"),
        (By.XPATH, "//*[contains(text(), 'Start Active Players')]"),
        (By.CSS_SELECTOR, "input[value*='Start Active']"),
    ]
    for by, selector in strategies:
        try:
            button = wait.until(EC.element_to_be_clickable((by, selector)))
            button.click()

            # Wait for Yahoo to finish processing the click/navigation
            time.sleep(8)

            print("URL AFTER CLICK:", driver.current_url)

            if "login.yahoo.com" in driver.current_url:
                raise RuntimeError(
                "Yahoo redirected to login after Start Active Players click. "
                "Yahoo session/cookies are not being accepted for this action."
                )
            print("Yahoo remained on fantasy page after click.")
            print(f"Clicked button using strategy: {by} -> {selector}")
            return
        except TimeoutException:
            continue
    raise NoSuchElementException("Could not find 'Start Active Players' button.")


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("Usage: python set_active_players_ci.py <roster_page_url> (e.g. your baseball.fantasysports.yahoo.com roster URL)")

    roster_url = sys.argv[1]
    driver = build_driver()
    wait = WebDriverWait(driver, 20)

    try:
        load_cookies(driver)
        try:
            driver.get(roster_url)
        except TimeoutException:
            driver.execute_script("window.stop();")

        # If cookies were stale/expired, we'll land on a login page instead
        if "login.yahoo.com" in driver.current_url:
            sys.exit("Session cookies expired — re-run export_yahoo_cookies.py locally and update the secret.")

        click_set_active_players(driver, wait)
        time.sleep(2)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
