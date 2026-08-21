"""
Yahoo Fantasy roster automation for use in GitHub Actions.

Loads a previously-exported Yahoo authenticated session from:
    YAHOO_COOKIES_B64

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
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
)


COOKIES_B64 = os.environ.get("YAHOO_COOKIES_B64")

if not COOKIES_B64:
    sys.exit(
        "Set YAHOO_COOKIES_B64 environment variable "
        "(base64-encoded cookie export)."
    )


def build_driver() -> webdriver.Chrome:
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


def load_cookies(driver: webdriver.Chrome) -> None:
    """
    Decode YAHOO_COOKIES_B64 and load only cookies whose domains
    are valid for Yahoo Fantasy.
    """

    cleaned = "".join(COOKIES_B64.split())
    cleaned += "=" * (-len(cleaned) % 4)

    # ---------------------------------------------------------
    # Decode Base64
    # ---------------------------------------------------------

    try:
        decoded = base64.b64decode(cleaned, validate=True)
    except Exception as e:
        sys.exit(
            f"YAHOO_COOKIES_B64 is not valid base64 ({e}). "
            "Regenerate yahoo_cookies.json and update the GitHub secret."
        )

    # ---------------------------------------------------------
    # Decode JSON
    # ---------------------------------------------------------

    try:
        cookies = json.loads(decoded)
    except Exception as e:
        sys.exit(
            f"YAHOO_COOKIES_B64 decoded but is not valid JSON ({e}). "
            "Regenerate yahoo_cookies.json and update the GitHub secret."
        )

    if not isinstance(cookies, list):
        sys.exit("Cookie JSON must contain a list of cookies.")

    print(f"Cookie export contains {len(cookies)} cookies.")

    # ---------------------------------------------------------
    # Open Yahoo Fantasy domain FIRST
    # ---------------------------------------------------------

    yahoo_domain = "baseball.fantasysports.yahoo.com"

    try:
        driver.get("https://baseball.fantasysports.yahoo.com/")
    except TimeoutException:
        driver.execute_script("window.stop();")

    print("Initial Yahoo URL:", driver.current_url)

    # ---------------------------------------------------------
    # Load cookies
    # ---------------------------------------------------------

    loaded = 0
    skipped = 0

    for original_cookie in cookies:

        cookie = original_cookie.copy()

        name = cookie.get("name", "UNKNOWN")
        domain = cookie.get("domain", "")

        # Remove leading dot:
        # .yahoo.com -> yahoo.com
        clean_domain = domain.lstrip(".")

        # -----------------------------------------------------
        # Domain validation
        # -----------------------------------------------------

        if clean_domain:

            valid_domain = (
                yahoo_domain == clean_domain
                or yahoo_domain.endswith("." + clean_domain)
            )

            if not valid_domain:
                print(
                    f"Skipped cookie {name}: "
                    f"domain {domain} does not apply to {yahoo_domain}"
                )
                skipped += 1
                continue

        # -----------------------------------------------------
        # Selenium doesn't need these exported fields
        # -----------------------------------------------------

        cookie.pop("sameSite", None)

        if "expiry" in cookie:
            try:
                cookie["expiry"] = int(cookie["expiry"])
            except (ValueError, TypeError):
                cookie.pop("expiry", None)

        # Selenium doesn't accept some cookie fields depending
        # on the browser/export format.
        cookie.pop("storeId", None)
        cookie.pop("hostOnly", None)
        cookie.pop("session", None)

        # -----------------------------------------------------
        # Add cookie
        # -----------------------------------------------------

        try:
            driver.add_cookie(cookie)

            print(
                f"Loaded cookie: {name} "
                f"({domain or 'no domain'})"
            )

            loaded += 1

        except Exception as e:
            print(
                f"Skipped cookie {name}: {e}"
            )
            skipped += 1

    print()
    print("======================================")
    print("COOKIE LOAD SUMMARY")
    print("======================================")
    print(f"Exported cookies : {len(cookies)}")
    print(f"Loaded cookies   : {loaded}")
    print(f"Skipped cookies  : {skipped}")
    print("======================================")
    print()

    # ---------------------------------------------------------
    # Show cookies actually installed in Chrome
    # ---------------------------------------------------------

    browser_cookies = driver.get_cookies()

    print(
        f"Cookies currently installed in browser: "
        f"{len(browser_cookies)}"
    )

    for cookie in browser_cookies:
        print(
            f"  {cookie.get('name')} -> "
            f"{cookie.get('domain')}"
        )

    print()

    # ---------------------------------------------------------
    # Refresh Yahoo with authenticated cookies
    # ---------------------------------------------------------

    try:
        driver.refresh()
    except TimeoutException:
        driver.execute_script("window.stop();")

    time.sleep(3)

    print("URL after cookie refresh:", driver.current_url)

    if "login.yahoo.com" in driver.current_url:
        raise RuntimeError(
            "Yahoo redirected to login immediately after loading cookies. "
            "The exported Yahoo session is expired or invalid."
        )


def click_set_active_players(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
) -> None:

    strategies = [
        (
            By.XPATH,
            "//button[contains(., 'Start Active Players')]",
        ),
        (
            By.XPATH,
            "//a[contains(., 'Start Active Players')]",
        ),
        (
            By.XPATH,
            "//*[contains(text(), 'Start Active Players')]",
        ),
        (
            By.CSS_SELECTOR,
            "input[value*='Start Active']",
        ),
    ]

    for by, selector in strategies:

        try:

            button = wait.until(
                EC.element_to_be_clickable(
                    (by, selector)
                )
            )

            print(
                f"Found Start Active Players using: "
                f"{by} -> {selector}"
            )

            # -------------------------------------------------
            # Click
            # -------------------------------------------------

            button.click()

            print("Clicked Start Active Players.")

            # IMPORTANT:
            # Do not access button.text here.
            # Yahoo may replace the DOM after the click.

            time.sleep(8)

            current_url = driver.current_url

            print(
                "URL AFTER CLICK:",
                current_url
            )

            # -------------------------------------------------
            # Yahoo authentication failure
            # -------------------------------------------------

            if "login.yahoo.com" in current_url:

                raise RuntimeError(
                    "Yahoo redirected to login after Start Active Players "
                    "click. Yahoo session/cookies are not being accepted "
                    "for this action."
                )

            # -------------------------------------------------
            # Still on Yahoo Fantasy
            # -------------------------------------------------

            if "baseball.fantasysports.yahoo.com" in current_url:

                print(
                    "Yahoo remained on the Fantasy page after the click."
                )

                print(
                    "Start Active Players click completed "
                    "without a login redirect."
                )

                return

            # Unexpected destination
            raise RuntimeError(
                f"Yahoo navigated to an unexpected URL: "
                f"{current_url}"
            )

        except TimeoutException:

            print(
                f"Selector did not find Start Active Players: "
                f"{selector}"
            )

            continue

    raise NoSuchElementException(
        "Could not find 'Start Active Players' button."
    )


def main() -> None:

    if len(sys.argv) < 2:

        sys.exit(
            "Usage: python manualTriggerSetLineup.py "
            "<roster_page_url>"
        )

    roster_url = sys.argv[1]

    print()
    print("======================================")
    print("YAHOO MANUAL BACKUP")
    print("======================================")
    print("Roster URL:")
    print(roster_url)
    print("======================================")
    print()

    driver = build_driver()
    wait = WebDriverWait(driver, 20)

    try:

        # -----------------------------------------------------
        # Load authenticated cookies
        # -----------------------------------------------------

        load_cookies(driver)

        # -----------------------------------------------------
        # Go to actual roster page
        # -----------------------------------------------------

        try:
            driver.get(roster_url)

        except TimeoutException:
            driver.execute_script("window.stop();")

        time.sleep(3)

        print()
        print("ROSTER PAGE URL:")
        print(driver.current_url)

        print(
            "PAGE TITLE:",
            driver.title
        )

        # -----------------------------------------------------
        # Check authentication before clicking
        # -----------------------------------------------------

        if "login.yahoo.com" in driver.current_url:

            raise RuntimeError(
                "Yahoo session cookies are expired or invalid. "
                "Yahoo opened the login page before the button "
                "could be clicked."
            )

        # -----------------------------------------------------
        # Click Start Active Players
        # -----------------------------------------------------

        click_set_active_players(
            driver,
            wait
        )

        time.sleep(2)

        print()
        print("======================================")
        print("BACKUP MANUAL TRIGGER COMPLETED")
        print("======================================")

    finally:

        driver.quit()


if __name__ == "__main__":
    main()
