from __future__ import annotations

import os
import pathlib
import sys
import time

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


ROOT = pathlib.Path(__file__).resolve().parent
SCREENSHOTS = ROOT / "screenshots"
EDGE_BINARY = pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
LINE_EXTENSION_ID = "ophjlpahpchlmihnnnihgmmeilfjmjjc"
LINE_EXTENSION_DIR = pathlib.Path(
    rf"C:\Users\khcm1\AppData\Local\Microsoft\Edge\User Data\Default\Extensions\{LINE_EXTENSION_ID}\3.7.2_0"
)
LINE_EXTENSION_URL = f"chrome-extension://{LINE_EXTENSION_ID}/index.html"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def build_driver() -> webdriver.Edge:
    options = Options()
    options.binary_location = str(EDGE_BINARY)
    options.add_argument(f"--user-data-dir={ROOT / 'edge-profile'}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument(f"--load-extension={LINE_EXTENSION_DIR}")
    options.add_argument(f"--disable-extensions-except={LINE_EXTENSION_DIR}")
    options.add_argument("--window-size=1180,900")
    options.add_experimental_option("detach", True)
    return webdriver.Edge(options=options)


def visible_text(driver: webdriver.Edge) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return ""


def dump_state(driver: webdriver.Edge, label: str) -> None:
    SCREENSHOTS.mkdir(exist_ok=True)
    path = SCREENSHOTS / f"{label}.png"
    driver.save_screenshot(str(path))
    controls = driver.execute_script(
        """
        return Array.from(document.querySelectorAll('input, button, textarea, [role="button"], a'))
          .map((el, i) => {
            const r = el.getBoundingClientRect();
            return {
              i,
              tag: el.tagName,
              type: el.getAttribute('type') || '',
              text: (el.getAttribute('type') === 'password')
                ? '<redacted>'
                : (el.innerText || el.value || el.placeholder || el.getAttribute('aria-label') || ''),
              id: el.id || '',
              className: String(el.className || ''),
              rect: {x: r.x, y: r.y, w: r.width, h: r.height},
            };
          });
        """
    )
    print(f"state={label}")
    print(f"title={driver.title!r}")
    print(f"url={driver.current_url}")
    print(f"screenshot={path}")
    print("body_text_begin")
    print(visible_text(driver)[:3000])
    print("body_text_end")
    print("controls_begin")
    for control in controls[:80]:
        print(control)
    print("controls_end")


def maybe_login(driver: webdriver.Edge) -> bool:
    email = os.environ.get("LINE_EMAIL")
    password = os.environ.get("LINE_PASSWORD")
    if not email or not password:
        print("login_skipped=missing_env")
        return False

    inputs = [
        field
        for field in driver.find_elements(By.CSS_SELECTOR, "input")
        if field.rect["width"] > 0 and field.rect["height"] > 0
    ]
    if len(inputs) < 2:
        print("login_skipped=no_login_inputs")
        return False

    if inputs[0].get_attribute("type") != "email" or inputs[1].get_attribute("type") != "password":
        print("login_skipped=not_login_form")
        return False

    try:
        inputs[0].clear()
        inputs[0].send_keys(email)
        inputs[1].clear()
        inputs[1].send_keys(password)
    except Exception as exc:
        print(f"login_input_fallback={type(exc).__name__}")
        driver.execute_script(
            """
            const [emailInput, passwordInput, emailValue, passwordValue] = arguments;
            const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
            for (const [input, value] of [[emailInput, emailValue], [passwordInput, passwordValue]]) {
              input.focus();
              setter.call(input, value);
              input.dispatchEvent(new Event('input', {bubbles: true}));
              input.dispatchEvent(new Event('change', {bubbles: true}));
              input.dispatchEvent(new KeyboardEvent('keyup', {bubbles: true}));
            }
            """,
            inputs[0],
            inputs[1],
            email,
            password,
        )

    try:
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        login_button.click()
    except Exception as exc:
        print(f"login_button_fallback={type(exc).__name__}")
        login_button = driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
        driver.execute_script("arguments[0].click();", login_button)
    print("login_submitted=true")
    return True


def wait_for_phone_verification(driver: webdriver.Edge) -> None:
    deadline = time.time() + 180
    last_code = ""
    while time.time() < deadline:
        text = visible_text(driver)
        password_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
        if "電腦版認證" in text or password_inputs:
            digits = "".join(ch for ch in text if ch.isdigit())
            if len(digits) >= 6 and digits[-6:] != last_code:
                last_code = digits[-6:]
                print(f"phone_verification_code={last_code}", flush=True)
            time.sleep(3)
            continue
        if text.strip():
            print("phone_verification=complete")
            return
        time.sleep(3)
    print("phone_verification=timeout")


def main() -> None:
    driver = build_driver()
    try:
        driver.get(LINE_EXTENSION_URL)
        WebDriverWait(driver, 20).until(lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input"))
        dump_state(driver, "before_login")
        submitted = maybe_login(driver)
        if submitted:
            try:
                WebDriverWait(driver, 60).until(
                    lambda d: "登入" not in visible_text(d)
                    or "驗證" in visible_text(d)
                    or "認證" in visible_text(d)
                    or "搜尋" in visible_text(d)
                    or "好友" in visible_text(d)
                )
            except TimeoutException:
                print("post_login_wait=timeout")
            wait_for_phone_verification(driver)
            time.sleep(2)
        dump_state(driver, "after_login")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
