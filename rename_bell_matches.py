from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

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


user32 = ctypes.windll.user32
try:
    user32.SetProcessDPIAware()
except Exception:
    pass

MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002
VK_DOWN = 0x28
VK_RETURN = 0x0D


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def native_click(x: float, y: float) -> None:
    user32.SetCursorPos(int(round(x)), int(round(y)))
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.08)
    user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)


def native_key(vk: int) -> None:
    user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.06)
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)
    time.sleep(0.08)


def element_center_viewport(driver, element) -> tuple[float, float]:
    data = driver.execute_script(
        """
        const r = arguments[0].getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2,
                rect: {x:r.x, y:r.y, w:r.width, h:r.height},
                text: arguments[0].innerText || arguments[0].value || ''};
        """,
        element,
    )
    print(f"viewport_target={data}")
    return data["x"], data["y"]


def cdp_mouse_click(driver, x: float, y: float, button: str = "left") -> None:
    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": button, "clickCount": 1},
    )
    time.sleep(0.08)
    driver.execute_cdp_cmd(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": button, "clickCount": 1},
    )


def find_line_hwnd() -> int:
    matches: list[tuple[int, int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if "LINE" in buf.value:
            client = wintypes.RECT()
            window = wintypes.RECT()
            user32.GetClientRect(hwnd, ctypes.byref(client))
            user32.GetWindowRect(hwnd, ctypes.byref(window))
            matches.append(
                (
                    hwnd,
                    client.right - client.left,
                    client.bottom - client.top,
                    window.right - window.left,
                    window.bottom - window.top,
                )
            )
        return True

    user32.EnumWindows(enum_proc, 0)
    if not matches:
        raise RuntimeError("LINE Edge window handle not found")
    print(f"line_hwnd_candidates={matches}")
    return sorted(matches, key=lambda item: item[1] * item[2], reverse=True)[0][0]


def client_origin() -> tuple[int, int]:
    hwnd = find_line_hwnd()
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    point = POINT(0, 0)
    if not user32.ClientToScreen(hwnd, ctypes.byref(point)):
        raise RuntimeError("ClientToScreen failed")
    return point.x, point.y


def element_center_screen(driver, element) -> tuple[float, float]:
    origin_x, origin_y = client_origin()
    data = driver.execute_script(
        """
        const r = arguments[0].getBoundingClientRect();
        return {x: r.x + r.width / 2, y: r.y + r.height / 2, dpr: window.devicePixelRatio,
                rect: {x:r.x, y:r.y, w:r.width, h:r.height}};
        """,
        element,
    )
    print(f"screen_map origin=({origin_x},{origin_y}) target={data}")
    if os.environ.get("LINE_COORD_MODE", "logical") == "scaled":
        return origin_x + data["x"] * data["dpr"], origin_y + data["y"] * data["dpr"]
    return origin_x + data["x"], origin_y + data["y"]


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
    search_box = driver.find_element(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7")
    search_box.click()
    search_box.send_keys(Keys.CONTROL, "a")
    search_box.send_keys(query)
    time.sleep(1.5)


def visible_result_rows(driver):
    return [
        row
        for row in driver.find_elements(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn")
        if row.rect["width"] > 0 and row.rect["height"] > 0
    ]


def result_name(row) -> str:
    return row.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX").text.strip()


def choose_change_name(driver, row):
    hwnd = find_line_hwnd()
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.2)
    before_handles = set(driver.window_handles)
    try:
        target = row.find_element(By.CSS_SELECTOR, ".friendlistItem-module__name_box__fUKhX")
    except Exception:
        target = row
    if os.environ.get("LINE_CONTEXT_METHOD", "cdp") == "cdp":
        x, y = element_center_viewport(driver, target)
        print(f"context_click_cdp_at=({x},{y})")
        cdp_mouse_click(driver, x, y, "right")
    else:
        ActionChains(driver).move_to_element(target).context_click(target).perform()
    WebDriverWait(driver, 5).until(
        lambda d: d.find_elements(By.XPATH, "//button[normalize-space(.)='變更好友名稱']")
    )
    if os.environ.get("LINE_MENU_METHOD") == "keyboard":
        for _ in range(int(os.environ.get("LINE_MENU_DOWN_COUNT", "3"))):
            native_key(VK_DOWN)
        native_key(VK_RETURN)
        print("menu_selected_by_keyboard=true")
    elif os.environ.get("LINE_MENU_METHOD") == "selenium":
        button = driver.find_element(By.XPATH, "//button[normalize-space(.)='變更好友名稱']")
        ActionChains(driver).move_to_element(button).click(button).perform()
        print("menu_selected_by_selenium=true")
    elif os.environ.get("LINE_MENU_METHOD", "cdp") == "cdp":
        button = driver.find_element(By.XPATH, "//button[normalize-space(.)='變更好友名稱']")
        x, y = element_center_viewport(driver, button)
        print(f"click_change_name_cdp_at=({x},{y})")
        cdp_mouse_click(driver, x, y, "left")
    else:
        button = driver.find_element(By.XPATH, "//button[normalize-space(.)='變更好友名稱']")
        x, y = element_center_screen(driver, button)
        y += float(os.environ.get("LINE_MENU_Y_OFFSET", "0"))
        x += float(os.environ.get("LINE_MENU_X_OFFSET", "0"))
        print(f"click_change_name_at=({x},{y})")
        native_click(x, y)
    time.sleep(0.8)
    after_handles = set(driver.window_handles)
    print(f"window_handles_before={list(before_handles)}")
    print(f"window_handles_after={list(after_handles)}")


def active_edit_field(driver):
    fields = driver.find_elements(By.CSS_SELECTOR, "input, textarea, [contenteditable='true']")
    visible = []
    for field in fields:
        rect = field.rect
        if rect["width"] > 0 and rect["height"] > 0:
            visible.append(field)
    # The search box stays visible; the edit field appears as the other input/contenteditable.
    for field in reversed(visible):
        placeholder = field.get_attribute("placeholder") or ""
        if "搜尋" not in placeholder:
            return field
    return None


def find_edit_field_in_any_window(driver):
    deadline = time.time() + 8
    last_handles: list[str] = []
    while time.time() < deadline:
        last_handles = driver.window_handles
        for handle in reversed(last_handles):
            driver.switch_to.window(handle)
            field = active_edit_field(driver)
            if field is not None:
                print(f"edit_field_window={handle} title={driver.title!r} url={driver.current_url}")
                return field
        time.sleep(0.25)
    print(f"edit_field_window_not_found handles={last_handles}")
    return None


def rename_one(driver, query: str, old_name: str, code: str) -> tuple[str, str]:
    search(driver, query)
    rows = visible_result_rows(driver)
    target = None
    for row in rows:
        if result_name(row) == old_name:
            target = row
            break
    if target is None:
        raise RuntimeError(f"row not found: {old_name}")
    if code in old_name:
        return old_name, old_name

    choose_change_name(driver, target)
    if os.environ.get("LINE_FAST_APPEND") == "1":
        time.sleep(float(os.environ.get("LINE_FAST_APPEND_DELAY", "0.35")))
        driver.switch_to.active_element.send_keys(Keys.END, f" {code}", Keys.ENTER)
        print(f"sent_append_keys={{END}} {code}{{ENTER}}")
        time.sleep(2)
        return old_name, f"{old_name} {code}"
    field = find_edit_field_in_any_window(driver)
    if field is None:
        dump_state(driver, f"change_name_no_field_{old_name}")
        raise RuntimeError(f"change-name edit field not found for {old_name}")
    current = field.get_attribute("value") or field.text or old_name
    new_name = current if code in current else f"{current} {code}"
    field.click()
    field.send_keys(Keys.END, f" {code}", Keys.ENTER)
    print(f"sent_append_keys={{END}} {code}{{ENTER}}")
    time.sleep(2)
    return old_name, new_name


def main() -> None:
    query = sys.argv[1] if len(sys.argv) > 1 else "貝爾"
    code = sys.argv[2] if len(sys.argv) > 2 else "P111045"
    driver = build_driver()
    results: list[tuple[str, str]] = []
    try:
        driver.maximize_window()
        ensure_friends(driver)
        search(driver, query)
        initial_names = [result_name(row) for row in visible_result_rows(driver)]
        print(f"initial_names={initial_names}")
        targets = [name for name in initial_names if query in name]
        if not targets:
            raise RuntimeError(f"no {query} matches found")
        for name in targets:
            old_name, new_name = rename_one(driver, query, name, code)
            print(f"renamed={old_name} -> {new_name}")
            results.append((old_name, new_name))
        print("results_begin")
        for old_name, new_name in results:
            print(f"{old_name} -> {new_name}")
        print("results_end")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
