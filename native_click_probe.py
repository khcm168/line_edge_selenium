from __future__ import annotations

import ctypes
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


MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004


def native_click(x: float, y: float) -> None:
    user32 = ctypes.windll.user32
    user32.SetCursorPos(int(round(x)), int(round(y)))
    time.sleep(0.1)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


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


def viewport_to_screen(driver, element):
    return driver.execute_script(
        """
        const r = arguments[0].getBoundingClientRect();
        const chromeTop = window.outerHeight - window.innerHeight;
        const chromeLeft = Math.max(0, (window.outerWidth - window.innerWidth) / 2);
        return {
          x: window.screenX + chromeLeft + r.x + r.width / 2,
          y: window.screenY + chromeTop + r.y + r.height / 2,
          rect: {x:r.x, y:r.y, w:r.width, h:r.height},
          window: {
            screenX: window.screenX, screenY: window.screenY,
            outerWidth: window.outerWidth, outerHeight: window.outerHeight,
            innerWidth: window.innerWidth, innerHeight: window.innerHeight,
            devicePixelRatio: window.devicePixelRatio
          }
        };
        """,
        element,
    )


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    index = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    mode = sys.argv[3] if len(sys.argv) > 3 else "avatar"
    scale_mode = sys.argv[4] if len(sys.argv) > 4 else "logical"
    y_offset = float(sys.argv[5]) if len(sys.argv) > 5 else 0.0
    driver = build_driver()
    try:
        driver.maximize_window()
        ensure_friends(driver)
        search(driver, query)
        rows = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn")
        row = rows[index]
        if mode == "avatar":
            target = row.find_element(By.CSS_SELECTOR, ".profileImage-module__button_profile__GqKue")
        elif mode == "name":
            target = row.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX")
        else:
            target = row
        info = viewport_to_screen(driver, target)
        print(f"target_info={info}")
        scale = info["window"]["devicePixelRatio"] if scale_mode == "scaled" else 1.0
        native_click(info["x"] * scale, info["y"] * scale + y_offset)
        time.sleep(2)
        dump_state(driver, f"native_click_{mode}_{query}_{index}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
