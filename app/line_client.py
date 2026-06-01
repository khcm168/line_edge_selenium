from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from login_probe import (
    EDGE_BINARY,
    LINE_EXTENSION_DIR,
    LINE_EXTENSION_URL,
    ROOT,
    build_driver,
    dump_state,
    maybe_login,
    visible_text,
    wait_for_phone_verification,
)


SEARCH_INPUT_SELECTOR = ".searchInput-module__input__ekGp7"
DEVTOOLS_ACTIVE_PORT = ROOT / "edge-profile" / "DevToolsActivePort"
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
        options.add_argument(f"--user-data-dir={ROOT / 'edge-profile'}")
        options.add_argument("--no-first-run")
        options.add_argument("--no-default-browser-check")
        options.add_argument(f"--load-extension={LINE_EXTENSION_DIR}")
        options.add_argument(f"--disable-extensions-except={LINE_EXTENSION_DIR}")
        options.add_argument("--window-size=1180,900")
        options.add_argument(f"--remote-debugging-port={handoff_port()}")
        options.add_experimental_option("detach", True)
        return cls(webdriver.Edge(options=options))

    @classmethod
    def attach_existing(cls) -> "LineClient":
        debugger_address = read_debugger_address()
        options = Options()
        options.binary_location = str(EDGE_BINARY)
        options.add_experimental_option("debuggerAddress", debugger_address)
        return cls(webdriver.Edge(options=options))

    def close(self) -> None:
        self.driver.quit()

    def ensure_friends(self) -> None:
        self.driver.get(LINE_EXTENSION_URL + "#/friends")
        WebDriverWait(self.driver, 30).until(
            lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input")
        )
        if self.driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
            if maybe_login(self.driver):
                wait_for_phone_verification(self.driver)
                time.sleep(float(os.getenv("LINE_POST_LOGIN_SETTLE_SECONDS", "8")))
                self.driver.get(LINE_EXTENSION_URL + "#/friends")
        WebDriverWait(self.driver, 30).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
        )
        time.sleep(float(os.getenv("LINE_FRIENDS_SETTLE_SECONDS", "2")))

    def dump_state(self, label: str) -> None:
        dump_state(self.driver, label)

    def visible_text(self) -> str:
        return visible_text(self.driver)


def read_debugger_address() -> str:
    port = handoff_port()
    if port:
        return f"127.0.0.1:{port}"
    if not DEVTOOLS_ACTIVE_PORT.exists():
        raise RuntimeError(
            "No running LINE Edge handoff session found. "
            "Start one with `python -m app.line_batch --handoff-start`."
        )
    lines = DEVTOOLS_ACTIVE_PORT.read_text(encoding="utf-8", errors="ignore").splitlines()
    if not lines or not lines[0].strip().isdigit():
        raise RuntimeError(f"Invalid DevToolsActivePort file: {DEVTOOLS_ACTIVE_PORT}")
    return f"127.0.0.1:{lines[0].strip()}"


def handoff_port() -> str:
    return os.getenv("LINE_HANDOFF_DEBUGGING_PORT", DEFAULT_HANDOFF_PORT).strip()
