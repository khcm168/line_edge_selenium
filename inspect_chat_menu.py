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
        rows = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__button_friendlist_item__xoWur")
        driver.execute_script("arguments[0].click();", rows[index])
        WebDriverWait(driver, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".chatroomHeader-module__button_more__9rz-2"))
        more = driver.find_element(By.CSS_SELECTOR, ".chatroomHeader-module__button_more__9rz-2")
        driver.execute_script("arguments[0].click();", more)
        time.sleep(1)
        dump_state(driver, f"chat_menu_{query}_{index}")
        print("menu_html_begin")
        print(driver.execute_script("return document.body.innerHTML.slice(0, 12000);"))
        print("menu_html_end")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
