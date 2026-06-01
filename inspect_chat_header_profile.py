from __future__ import annotations

import ctypes
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


def native_click(x: float, y: float) -> None:
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(round(x)), int(round(y)))
    time.sleep(0.08)
    user32.mouse_event(0x0002, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(0x0004, 0, 0, 0, 0)


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


def center(driver, element):
    return driver.execute_script(
        """
        const r = arguments[0].getBoundingClientRect();
        return {
          x: window.screenX + Math.max(0, (window.outerWidth-window.innerWidth)/2) + r.x + r.width/2,
          y: window.screenY + (window.outerHeight-window.innerHeight) + r.y + r.height/2,
          rect: {x:r.x,y:r.y,w:r.width,h:r.height},
          win: {screenX:window.screenX,screenY:window.screenY,outerHeight:window.outerHeight,innerHeight:window.innerHeight,devicePixelRatio:window.devicePixelRatio}
        };
        """,
        element,
    )


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    click_mode = sys.argv[3] if len(sys.argv) > 3 else "selenium"
    driver = build_driver()
    try:
        driver.maximize_window()
        ensure_friends(driver)
        search(driver, query)
        rows = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__button_friendlist_item__xoWur")
        names = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX")
        print(f"row_count={len(rows)} selected_name={names[index].text}")
        driver.execute_script("arguments[0].click();", rows[index])
        WebDriverWait(driver, 20).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".chatroomHeader-module__button_name__US7lb"))
        time.sleep(1)
        if click_mode in ("message_avatar", "message_avatar_scaled"):
            target = [el for el in driver.find_elements(By.CSS_SELECTOR, ".profileImage-module__button_profile__GqKue") if el.rect["width"] > 0 and el.rect["x"] > 300][-1]
            print("target=message_avatar")
        else:
            target = driver.find_element(By.CSS_SELECTOR, ".chatroomHeader-module__button_name__US7lb")
            print(f"header_text={target.text}")
        info = center(driver, target)
        print(f"target_center={info}")
        if click_mode == "native":
            native_click(info["x"], info["y"])
        elif click_mode == "message_avatar":
            native_click(info["x"], info["y"])
        elif click_mode == "message_avatar_scaled":
            native_click(info["x"] * info["win"]["devicePixelRatio"], info["y"] * info["win"]["devicePixelRatio"])
        else:
            ActionChains(driver).move_to_element(target).click(target).perform()
        time.sleep(2)
        dump_state(driver, f"chat_header_profile_{click_mode}_{query}_{index}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
