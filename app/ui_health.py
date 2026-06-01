from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from selenium.webdriver.common.by import By

from app.line_client import SEARCH_INPUT_SELECTOR, LineClient
from app.line_messaging import shadow_message_field, visible_message_fields


@dataclass(frozen=True)
class UiHealth:
    ok: bool
    status: str
    detail: str


def check_login_state(client: LineClient) -> UiHealth:
    try:
        client.ensure_friends()
    except Exception as exc:
        return UiHealth(False, "login_state_failed", f"{type(exc).__name__}: {exc}")
    return UiHealth(True, "login_state_ok", "LINE friends view is reachable")


def check_search_box(driver: Any) -> UiHealth:
    fields = driver.find_elements(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
    visible = [field for field in fields if field.rect["width"] > 0 and field.rect["height"] > 0]
    if not visible:
        return UiHealth(False, "search_box_missing", "LINE search box was not visible")
    return UiHealth(True, "search_box_ok", "LINE search box is visible")


def check_composer(driver: Any) -> UiHealth:
    if shadow_message_field(driver) is not None or visible_message_fields(driver):
        return UiHealth(True, "composer_ok", "LINE composer textbox is visible")
    return UiHealth(False, "composer_missing", "LINE composer textbox was not visible")
