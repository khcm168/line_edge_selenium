from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from selenium.common.exceptions import InvalidSessionIdException
from selenium.webdriver.common.by import By

from app.line_client import AUTO_LOGOUT_TERMS, SEARCH_INPUT_SELECTOR, LineClient
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
        try:
            fallback = infer_login_state(client.driver)
        except InvalidSessionIdException:
            return UiHealth(
                False,
                "browser_session_lost",
                f"LINE browser session was lost; original={type(exc).__name__}: {exc}",
            )
        if fallback is not None:
            return fallback_with_context(fallback, exc)
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


def infer_login_state(driver: Any) -> UiHealth | None:
    if _has_visible_search_box(driver):
        return UiHealth(True, "friends_view_visible", "LINE friends view appears reachable")
    text = _visible_body_text(driver)
    if any(term.casefold() in text.casefold() for term in AUTO_LOGOUT_TERMS):
        return UiHealth(
            False,
            "auto_logout_prompt_visible",
            "LINE auto-logout prompt is visible and needs confirmation before login can continue",
        )
    if _has_visible_password_input(driver):
        return UiHealth(
            False,
            "login_prompt_visible",
            "LINE login prompt is visible and needs an updated submit-path check",
        )
    if any(term in text.casefold() for term in ("log in", "login", "sign in", "verify")):
        return UiHealth(
            False,
            "login_prompt_visible",
            "LINE login or verification prompt is visible",
        )
    if text.strip():
        return UiHealth(
            False,
            "unknown_dom_changed",
            "LINE page loaded visible content, but expected friends/login selectors did not match",
        )
    return None


def fallback_with_context(health: UiHealth, exc: Exception) -> UiHealth:
    return UiHealth(
        health.ok,
        health.status,
        f"{health.detail}; original={type(exc).__name__}: {exc}",
    )


def _has_visible_search_box(driver: Any) -> bool:
    fields = driver.find_elements(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
    return any(field.rect["width"] > 0 and field.rect["height"] > 0 for field in fields)


def _has_visible_password_input(driver: Any) -> bool:
    fields = driver.find_elements(By.CSS_SELECTOR, "input[type='password']")
    return any(field.rect["width"] > 0 and field.rect["height"] > 0 for field in fields)


def _visible_body_text(driver: Any) -> str:
    try:
        body = driver.find_element(By.TAG_NAME, "body")
    except Exception:
        return ""
    return body.text or ""
