from __future__ import annotations

import sys
import time

from selenium.webdriver import ActionChains
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


def search(driver, query: str):
    box = driver.find_element(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7")
    box.click()
    box.send_keys(Keys.CONTROL, "a")
    box.send_keys(query)
    time.sleep(1.5)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    mode = sys.argv[3] if len(sys.argv) > 3 else "avatar"
    driver = build_driver()
    try:
        ensure_friends(driver)
        search(driver, query)
        rows = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn")
        print(f"row_count={len(rows)}")
        row = rows[index]
        target = row
        if mode == "avatar":
            target = row.find_element(By.CSS_SELECTOR, ".profileImage-module__button_profile__GqKue")
        elif mode == "name":
            target = row.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX")
        elif mode == "chat":
            target = row.find_element(By.CSS_SELECTOR, ".friendlistItem-module__button_friendlist_item__xoWur")
        print(f"mode={mode} name={row.find_element(By.CSS_SELECTOR, '.friendlistItem-module__name_box__fUKhX').text}")
        ActionChains(driver).move_to_element(target).click(target).perform()
        time.sleep(2)
        dump_state(driver, f"open_profile_{mode}_{query}_{index}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
