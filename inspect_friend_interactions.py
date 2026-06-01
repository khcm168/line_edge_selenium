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


def visible_controls(driver):
    return driver.execute_script(
        """
        return [...document.querySelectorAll('button,input,textarea,[role=button],[role=menuitem],[contenteditable=true]')]
          .map((el, i) => {
            const r = el.getBoundingClientRect();
            return {i, tag: el.tagName, cls: el.className, role: el.getAttribute('role'),
                    label: el.getAttribute('aria-label'), text: (el.innerText || el.value || '').slice(0, 120),
                    rect: {x:r.x,y:r.y,w:r.width,h:r.height}};
          })
          .filter(x => x.rect.w > 0 && x.rect.h > 0);
        """
    )


def dump_controls(driver, label: str):
    print(f"{label}_controls_begin")
    for item in visible_controls(driver):
        print(item)
    print(f"{label}_controls_end")


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    driver = build_driver()
    try:
        ensure_friends(driver)
        search(driver, query)
        item_selector = ".friendlistItem-module__item__1tuZn"
        items = driver.find_elements(By.CSS_SELECTOR, item_selector)
        print(f"item_count={len(items)}")
        if index >= len(items):
            raise IndexError(f"item index {index} out of range")
        item = items[index]
        targets = {
            "item": item,
            "name": item.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX"),
            "avatar": item.find_element(By.CSS_SELECTOR, ".profileImage-module__button_profile__GqKue"),
        }
        for target_name, target in targets.items():
            search(driver, query)
            items = driver.find_elements(By.CSS_SELECTOR, item_selector)
            target = {
                "item": items[index],
                "name": items[index].find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX"),
                "avatar": items[index].find_element(By.CSS_SELECTOR, ".profileImage-module__button_profile__GqKue"),
            }[target_name]
            ActionChains(driver).move_to_element(target).context_click(target).perform()
            time.sleep(1)
            dump_state(driver, f"context_{target_name}_{query}_{index}")
            dump_controls(driver, f"context_{target_name}")
            ActionChains(driver).send_keys(Keys.ESCAPE).perform()
            time.sleep(0.5)
        search(driver, query)
        item = driver.find_elements(By.CSS_SELECTOR, item_selector)[index]
        name = item.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX")
        ActionChains(driver).move_to_element(name).double_click(name).perform()
        time.sleep(1)
        dump_state(driver, f"double_name_{query}_{index}")
        dump_controls(driver, "double_name")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
