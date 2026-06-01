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


def ensure_friends(driver) -> None:
    driver.get(LINE_EXTENSION_URL + "#/friends")
    WebDriverWait(driver, 30).until(lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input"))
    if driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
        if maybe_login(driver):
            wait_for_phone_verification(driver)
            time.sleep(2)
            driver.get(LINE_EXTENSION_URL + "#/friends")
    WebDriverWait(driver, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7"))


def search_friend(driver, query: str) -> None:
    search = driver.find_element(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7")
    search.click()
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(query)
    time.sleep(1.5)


def visible_rows(driver):
    rows = driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn")
    return [row for row in rows if row.rect["width"] > 0 and row.rect["height"] > 0]


def row_name(row) -> str:
    return row.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX").text.strip()


def norm_name(value: str) -> str:
    return value.replace("啓", "啟").strip()


def visible_rows_with_category(driver):
    elements = driver.find_elements(
        By.CSS_SELECTOR,
        ".categoryLayout-module__button_category__nqIZM, .friendlistItem-module__item__1tuZn",
    )
    category = ""
    rows = []
    for element in elements:
        class_name = element.get_attribute("class") or ""
        if "categoryLayout-module__button_category" in class_name:
            category = element.text.splitlines()[0].strip()
            continue
        rect = element.rect
        if rect["width"] > 0 and rect["height"] > 0:
            rows.append((category, element, row_name(element)))
    return rows


def open_exact_chat(driver, query: str, preferred_category: str | None = None) -> str:
    search_friend(driver, query)
    rows = visible_rows_with_category(driver)
    names = [f"{category}: {name}" for category, _row, name in rows]
    print(f"initial_names={names}")
    query_norm = norm_name(query)
    matches = [
        row
        for category, row, name in rows
        if (preferred_category is None or preferred_category in category)
        and (norm_name(name) == query_norm or norm_name(name).startswith(query_norm + "\n"))
    ]
    if not matches:
        contains_matches = [
            row
            for category, row, name in rows
            if (preferred_category is None or preferred_category in category) and query_norm in norm_name(name)
        ]
        if len(contains_matches) == 1:
            matches = contains_matches
    if len(matches) != 1:
        raise RuntimeError(f"expected exactly one exact match for {query!r}, got {len(matches)}: {names}")
    button = matches[0].find_element(By.CSS_SELECTOR, ".friendlistItem-module__button_friendlist_item__xoWur")
    driver.execute_script("arguments[0].click();", button)
    WebDriverWait(driver, 20).until(
        lambda d: query in visible_text(d)
        and d.find_elements(By.CSS_SELECTOR, ".chatroomHeader-module__button_name__US7lb")
    )
    return query


def visible_message_fields(driver):
    candidates = driver.find_elements(By.CSS_SELECTOR, "textarea, [contenteditable='true'], [role='textbox']")
    visible = []
    for field in candidates:
        rect = field.rect
        text = (field.get_attribute("placeholder") or field.get_attribute("aria-label") or field.text or "").strip()
        if rect["width"] > 0 and rect["height"] > 0:
            visible.append((field, rect, text))
    return visible


def cdp_mouse_click(driver, x: float, y: float) -> None:
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
    )
    time.sleep(0.08)
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
    )


def cdp_type_and_enter(driver, message: str) -> None:
    driver.execute_cdp_cmd("Input.insertText", {"text": message})
    time.sleep(0.1)
    driver.execute_cdp_cmd(
        "Input.dispatchKeyEvent",
        {"type": "keyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
    )
    driver.execute_cdp_cmd(
        "Input.dispatchKeyEvent",
        {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13},
    )


def composer_click_point(driver) -> tuple[float, float]:
    data = driver.execute_script(
        """
        const buttons = [...document.querySelectorAll('button')].map(el => {
          const r = el.getBoundingClientRect();
          return {text: el.innerText || el.getAttribute('aria-label') || '', x:r.x, y:r.y, w:r.width, h:r.height};
        }).filter(item => item.w > 0 && item.h > 0);
        const sendFile = buttons.find(item => item.text.includes('Send file'));
        const left = sendFile ? sendFile.x + 55 : 455;
        return {x: left + 80, y: window.innerHeight - 62, innerWidth: window.innerWidth, innerHeight: window.innerHeight};
        """
    )
    print(f"composer_click_point={data}")
    return data["x"], data["y"]


def send_message(driver, message: str) -> None:
    fields = visible_message_fields(driver)
    if fields:
        field, rect, label = sorted(fields, key=lambda item: item[1]["y"], reverse=True)[0]
        print(f"message_field_rect={rect} label={label!r}")
        field.click()
        field.send_keys(message)
        field.send_keys(Keys.ENTER)
    else:
        x, y = composer_click_point(driver)
        cdp_mouse_click(driver, x, y)
        time.sleep(0.2)
        cdp_type_and_enter(driver, message)
    print(f"sent_message={message!r}")
    time.sleep(1.5)


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "001N1備份區"
    message = sys.argv[2] if len(sys.argv) > 2 else "this is a test for fun"
    driver = build_driver()
    try:
        driver.maximize_window()
        ensure_friends(driver)
        opened = open_exact_chat(driver, query)
        print(f"opened_chat={opened}")
        send_message(driver, message)
    except Exception:
        dump_state(driver, "send_test_message_error")
        raise
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
