from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from selenium import webdriver
from selenium.common.exceptions import NoSuchWindowException
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
    visible_text,
    wait_for_phone_verification,
)


SEARCH_INPUT_SELECTOR = ".searchInput-module__input__ekGp7"
DEFAULT_HANDOFF_PORT = "9227"


@dataclass
class LineClient:
    driver: Any

    @classmethod
    def open(cls) -> "LineClient":
        return cls(build_driver())

    @classmethod
    def open_handoff(cls) -> "LineClient":
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
        return cls(webdriver.Edge(options=options))

    @classmethod
    def attach_existing(cls) -> "LineClient":
        debugger_address = read_debugger_address()
        options = Options()
        options.binary_location = str(EDGE_BINARY)
        options.add_experimental_option("debuggerAddress", debugger_address)
        options.set_capability("webSocketUrl", True)
        return cls(webdriver.Edge(options=options))

    def close(self) -> None:
        self.driver.quit()

    def ensure_friends(self) -> None:
        self._open_friends_view()
        if _visible_search_inputs(self.driver):
            time.sleep(float(os.getenv("LINE_FRIENDS_SETTLE_SECONDS", "2")))
            return
        if _visible_password_inputs(self.driver):
            if maybe_login(self.driver):
                try:
                    wait_for_phone_verification(self.driver)
                except NoSuchWindowException:
                    _recover_extension_window(self.driver)
                time.sleep(float(os.getenv("LINE_POST_LOGIN_SETTLE_SECONDS", "8")))
                self._open_friends_view()
        WebDriverWait(self.driver, 30).until(
            lambda d: _visible_search_inputs(d)
        )
        time.sleep(float(os.getenv("LINE_FRIENDS_SETTLE_SECONDS", "2")))

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
