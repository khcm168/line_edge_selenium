from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import InvalidSessionIdException, NoSuchWindowException
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from login_probe import (
    EDGE_BINARY,
    LINE_EXTENSION_DIR,
    LINE_EXTENSION_URL,
    build_driver,
    dump_state,
    edge_profile_dir,
    maybe_login,
    prepare_edge_profile_dir,
    _tcp_port_is_listening,
    visible_text,
    wait_for_phone_verification,
)


SEARCH_INPUT_SELECTOR = ".searchInput-module__input__ekGp7"
DEFAULT_HANDOFF_PORT = "9227"
MAXIMIZE_WINDOW_ENV = "LINE_MAXIMIZE_WINDOW"
AUTO_LOGOUT_TERMS = (
    "auto logged out",
    "automatically logged out",
    "logged out",
    "temporary error",
    "已自動登出",
    "自動登出",
    "暫時性錯誤",
    "已為您登出",
    "重新登入",
)
AUTO_LOGOUT_CONFIRM_TERMS = ("ok", "okay", "confirm", "確定")
LOGIN_RECOVERY_ATTEMPTS_ENV = "LINE_LOGIN_RECOVERY_ATTEMPTS"


@dataclass
class LineClient:
    driver: Any
    preserve_on_close: bool = False

    @classmethod
    def open(cls) -> "LineClient":
        return cls(build_driver())

    @classmethod
    def open_reuse_or_handoff(cls) -> "LineClient":
        if handoff_session_is_live():
            return cls.attach_existing(preserve_on_close=True)
        return cls.open_handoff(preserve_on_close=True)

    @classmethod
    def open_handoff(cls, *, preserve_on_close: bool = True) -> "LineClient":
        options = Options()
        options.binary_location = str(EDGE_BINARY)
        options.add_argument(f"--user-data-dir={prepare_edge_profile_dir(edge_profile_dir())}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument(f"--load-extension={LINE_EXTENSION_DIR}")
        options.add_argument(f"--disable-extensions-except={LINE_EXTENSION_DIR}")
        options.add_argument("--window-size=1180,900")
        options.add_argument(f"--remote-debugging-port={handoff_port()}")
        options.set_capability("webSocketUrl", True)
        options.add_experimental_option("detach", True)
        return cls(webdriver.Edge(options=options), preserve_on_close=preserve_on_close)

    @classmethod
    def attach_existing(cls, *, preserve_on_close: bool = False) -> "LineClient":
        debugger_address = read_debugger_address()
        options = Options()
        options.binary_location = str(EDGE_BINARY)
        options.add_experimental_option("debuggerAddress", debugger_address)
        options.set_capability("webSocketUrl", True)
        return cls(webdriver.Edge(options=options), preserve_on_close=preserve_on_close)

    def close(self) -> None:
        if self.preserve_on_close:
            return
        self.driver.quit()

    def ensure_friends(self) -> None:
        try:
            self._open_friends_view()
            for _attempt in range(_login_recovery_attempts()):
                state = _friends_or_reauth_ready(self.driver)
                if state == "friends":
                    time.sleep(float(os.getenv("LINE_FRIENDS_SETTLE_SECONDS", "2")))
                    return
                if state == "auto_logout":
                    time.sleep(float(os.getenv("LINE_POST_MODAL_SETTLE_SECONDS", "1")))
                    self._open_friends_view()
                    continue
                if state == "login" and maybe_login(self.driver):
                    try:
                        wait_for_phone_verification(self.driver)
                    except NoSuchWindowException:
                        _recover_extension_window(self.driver)
                    time.sleep(float(os.getenv("LINE_POST_LOGIN_SETTLE_SECONDS", "8")))
                    self._open_friends_view()
                    continue
                state = WebDriverWait(self.driver, 30).until(_friends_or_reauth_ready)
                if state == "friends":
                    time.sleep(float(os.getenv("LINE_FRIENDS_SETTLE_SECONDS", "2")))
                    return
            raise RuntimeError(
                "LINE login recovery did not reach the friends view after "
                f"{_login_recovery_attempts()} attempts"
            )
        except InvalidSessionIdException as exc:
            raise RuntimeError(
                "LINE browser session was lost before startup completed. "
                "Close any stale automation Edge windows, reclaim the worker owner if needed, "
                "then start the persistent worker again."
            ) from exc

    def _open_friends_view(self) -> None:
        _recover_extension_window(self.driver)
        self.driver.get(LINE_EXTENSION_URL + "#/friends")
        WebDriverWait(self.driver, 30).until(
            lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input")
        )

    def dump_state(self, label: str) -> None:
        dump_state(self.driver, label)

    def visible_text(self) -> str:
        return visible_text(self.driver)


def read_debugger_address() -> str:
    port = handoff_port()
    if port:
        return f"127.0.0.1:{port}"
    active_port = edge_profile_dir() / "DevToolsActivePort"
    if not active_port.exists():
        raise RuntimeError(
            "No running LINE Edge handoff session found. "
            "Start one with `python -m app.line_batch --handoff-start`."
        )
    lines = active_port.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines or not lines[0].strip().isdigit():
        raise RuntimeError(f"Invalid DevToolsActivePort file: {active_port}")
    return f"127.0.0.1:{lines[0].strip()}"


def handoff_port() -> str:
    return os.getenv("LINE_HANDOFF_DEBUGGING_PORT", DEFAULT_HANDOFF_PORT).strip()


def handoff_session_is_live() -> bool:
    port = handoff_port()
    return port.isdigit() and _tcp_port_is_listening(int(port))


def maybe_maximize_window(driver: Any) -> None:
    if os.getenv(MAXIMIZE_WINDOW_ENV, "").strip().casefold() in {"1", "true", "yes", "on"}:
        driver.maximize_window()


def _visible_search_inputs(driver: Any) -> list[Any]:
    return _visible_elements(driver.find_elements(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR))


def _visible_password_inputs(driver: Any) -> list[Any]:
    return _visible_elements(driver.find_elements(By.CSS_SELECTOR, "input[type='password']"))


def _visible_elements(elements: list[Any]) -> list[Any]:
    return [
        element
        for element in elements
        if element.rect.get("width", 0) > 0 and element.rect.get("height", 0) > 0
    ]


def _friends_or_reauth_ready(driver: Any) -> str | bool:
    if _visible_search_inputs(driver):
        return "friends"
    if _dismiss_auto_logout_modal(driver):
        return "auto_logout"
    if _visible_password_inputs(driver):
        return "login"
    return False


def _login_recovery_attempts() -> int:
    raw = os.getenv(LOGIN_RECOVERY_ATTEMPTS_ENV, "3")
    try:
        return max(1, int(raw))
    except ValueError:
        return 3


def _dismiss_auto_logout_modal(driver: Any) -> bool:
    text = visible_text(driver).casefold()
    if not any(term.casefold() in text for term in AUTO_LOGOUT_TERMS):
        return False
    for selector in ("button", "[role='button']"):
        for element in driver.find_elements(By.CSS_SELECTOR, selector):
            try:
                if not _visible_elements([element]):
                    continue
                label = (
                    element.get_attribute("aria-label")
                    or element.get_attribute("title")
                    or element.text
                    or ""
                ).strip().casefold()
            except Exception:
                continue
            if any(term.casefold() in label for term in AUTO_LOGOUT_CONFIRM_TERMS):
                try:
                    element.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                return True
    return False


def _recover_extension_window(driver: Any) -> None:
    handles = driver.window_handles
    if not handles:
        raise NoSuchWindowException("LINE browser window is no longer available")
    try:
        current_handle = driver.current_window_handle
    except NoSuchWindowException:
        current_handle = ""
    target_handle = current_handle if current_handle in handles else handles[-1]
    driver.switch_to.window(target_handle)
