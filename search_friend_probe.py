from __future__ import annotations

import pathlib
import sys
import time

from selenium.common.exceptions import TimeoutException
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


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    driver = build_driver()
    try:
        driver.get(LINE_EXTENSION_URL + "#/friends")
        WebDriverWait(driver, 30).until(lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input"))
        if driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
            dump_state(driver, "search_before_login")
            if maybe_login(driver):
                wait_for_phone_verification(driver)
                time.sleep(2)
                driver.get(LINE_EXTENSION_URL + "#/friends")

        try:
            WebDriverWait(driver, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7"))
        except TimeoutException:
            dump_state(driver, "search_no_friends_page")
            raise
        search = WebDriverWait(driver, 20).until(
            lambda d: d.find_element(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7")
        )
        search.click()
        search.send_keys(Keys.CONTROL, "a")
        search.send_keys(query)
        time.sleep(2)
        dump_state(driver, f"search_{query}")

        names = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('[class*="friendlistItem-module__name_box"]'))
              .map((el, i) => ({i, text: el.innerText, rect: (() => { const r = el.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height}; })()}));
            """
        )
        print("names_begin")
        for name in names:
            print(name)
        print("names_end")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
