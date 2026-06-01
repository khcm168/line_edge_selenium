from __future__ import annotations

import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from login_probe import (
    LINE_EXTENSION_URL,
    build_driver,
    dump_state,
    maybe_login,
    visible_text,
    wait_for_phone_verification,
)


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def ensure_friends(driver):
    driver.get(LINE_EXTENSION_URL + "#/friends")
    WebDriverWait(driver, 30).until(lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input"))
    if driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
        if maybe_login(driver):
            wait_for_phone_verification(driver)
            time.sleep(2)
            driver.get(LINE_EXTENSION_URL + "#/friends")
    WebDriverWait(driver, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7"))


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    driver = build_driver()
    try:
        ensure_friends(driver)
        search = driver.find_element(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7")
        search.click()
        search.send_keys(Keys.CONTROL, "a")
        search.send_keys(query)
        time.sleep(2)
        profiles = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn .profileImage-module__button_profile__GqKue")
        print(f"profile_count={len(profiles)}")
        if index >= len(profiles):
            raise IndexError(f"profile index {index} out of range")
        driver.execute_script("arguments[0].click();", profiles[index])
        time.sleep(2)
        dump_state(driver, f"profile_popover_{query}_{index}")
        print("html_excerpt_begin")
        print(driver.execute_script("return document.body.innerHTML.slice(0, 16000);"))
        print("html_excerpt_end")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
