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
        time.sleep(1.5)
        rows = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn")
        print(f"row_count={len(rows)}")
        if index >= len(rows):
            raise IndexError(f"row index {index} out of range")
        name = rows[index].find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX").text
        print(f"selected_name={name}")
        ActionChains(driver).move_to_element(rows[index]).context_click(rows[index]).perform()
        time.sleep(0.5)
        action_text = sys.argv[3] if len(sys.argv) > 3 else "變更好友名稱"
        buttons = driver.find_elements(By.XPATH, f"//button[normalize-space(.)='{action_text}']")
        print(f"action_text={action_text}")
        print(f"change_button_count={len(buttons)}")
        if not buttons:
            raise RuntimeError("change name button not found")
        rect = driver.execute_script(
            "const r=arguments[0].getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height};",
            buttons[0],
        )
        x = rect["x"] + rect["w"] / 2
        y = rect["y"] + rect["h"] / 2
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
        time.sleep(3)
        dump_state(driver, f"change_name_dialog_{query}_{index}")
        print("dialog_controls_begin")
        for item in driver.execute_script(
            """
            return [...document.querySelectorAll('button,input,textarea,[role=button],[contenteditable=true]')]
              .map((el, i) => {
                const r = el.getBoundingClientRect();
                return {i, tag: el.tagName, cls: el.className, role: el.getAttribute('role'),
                        label: el.getAttribute('aria-label'), placeholder: el.getAttribute('placeholder'),
                        text: (el.innerText || el.value || '').slice(0, 160),
                        rect: {x:r.x,y:r.y,w:r.width,h:r.height}};
              })
              .filter(x => x.rect.w > 0 && x.rect.h > 0);
            """
        ):
            print(item)
        print("dialog_controls_end")
        print("html_excerpt_begin")
        print(driver.execute_script("return document.body.innerHTML.slice(0, 12000);"))
        print("html_excerpt_end")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
