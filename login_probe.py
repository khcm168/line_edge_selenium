from __future__ import annotations

import os
import pathlib
import socket
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


STALE_PROFILE_MARKERS = (
    "DevToolsActivePort",
    "SingletonCookie",
    "SingletonLock",
    "SingletonSocket",
)


def prepare_edge_profile_dir(profile_dir: pathlib.Path) -> pathlib.Path:
    profile_dir.mkdir(parents=True, exist_ok=True)
    active_port = profile_dir / "DevToolsActivePort"
    if _debug_port_is_live(active_port):
        raise RuntimeError(
            f"LINE Edge profile is already in use: {profile_dir}. "
            "A live DevTools endpoint is still attached to this profile."
        )
    for name in STALE_PROFILE_MARKERS:
        marker = profile_dir / name
        if marker.exists():
            _unlink_with_retries(marker)
    return profile_dir


def _debug_port_is_live(active_port: pathlib.Path) -> bool:
    if not active_port.exists():
        return False
    try:
        lines = active_port.read_text(encoding="utf-8", errors="ignore").splitlines()
    except OSError:
        return False
    if not lines:
        return False
    port_text = lines[0].strip()
    if not port_text.isdigit():
        return False
    return _tcp_port_is_listening(int(port_text))


def _tcp_port_is_listening(port: int, *, timeout_seconds: float = 0.2) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout_seconds)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def _unlink_with_retries(path: pathlib.Path, *, attempts: int = 20, delay_seconds: float = 0.25) -> None:
    last_error: OSError | None = None
    for attempt in range(attempts):
        try:
            path.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError as exc:
            last_error = exc
            if attempt == attempts - 1:
                break
            time.sleep(delay_seconds)
    raise RuntimeError(
        f"LINE Edge profile startup marker is locked: {path}. "
        "Another process still owns the shared profile."
    ) from last_error


def build_driver() -> webdriver.Edge:
    options = Options()
    options.binary_location = str(EDGE_BINARY)
    options.add_argument(f"--user-data-dir={prepare_edge_profile_dir(edge_profile_dir())}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument(f"--load-extension={LINE_EXTENSION_DIR}")
    options.add_argument(f"--disable-extensions-except={LINE_EXTENSION_DIR}")
    options.add_argument("--window-size=1180,900")
    options.set_capability("webSocketUrl", True)
    options.add_experimental_option("detach", True)
    return webdriver.Edge(options=options)


def edge_profile_dir() -> pathlib.Path:
    configured = os.environ.get("LINE_EDGE_PROFILE_DIR", "").strip()
    return pathlib.Path(configured) if configured else ROOT / "edge-profile"


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
        login_button = _wait_for_visible_submit_button(driver, timeout_seconds=10)
        try:
            login_button.click()
        except Exception as exc:
            print(f"login_button_native_click_fallback={type(exc).__name__}")
            driver.execute_script("arguments[0].click();", login_button)
    except Exception as exc:
        print(f"login_button_fallback={type(exc).__name__}")
        login_button = _first_visible_submit_button(driver)
        if login_button is None:
            print("login_skipped=no_login_button")
            return False
        driver.execute_script("arguments[0].click();", login_button)
    print("login_submitted=true")
    return True


def _wait_for_visible_submit_button(
    driver: webdriver.Edge, *, timeout_seconds: int
):
    return WebDriverWait(driver, timeout_seconds).until(
        lambda current_driver: _first_visible_submit_button(current_driver)
    )


def _first_visible_submit_button(driver: webdriver.Edge):
    buttons = driver.find_elements(By.CSS_SELECTOR, "button[type='submit']")
    for button in buttons:
        if button.rect["width"] > 0 and button.rect["height"] > 0:
            return button
    return None


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
