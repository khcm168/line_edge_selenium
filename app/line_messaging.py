from __future__ import annotations

import time
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from app.line_client import SEARCH_INPUT_SELECTOR
from app.line_matcher import LineCandidate, MatchDecision, apply_match_policy


RESULT_SELECTOR = ".friendlistItem-module__item__1tuZn"
NAME_SELECTOR = ".friendlistItem-module__name_box__fUKhX"
CATEGORY_OR_ROW_SELECTOR = (
    ".categoryLayout-module__button_category__nqIZM, "
    ".friendlistItem-module__item__1tuZn"
)
NO_RESULT_TERMS = ("無搜尋結果", "找不到", "No results", "No search")


def search_line(driver: Any, query: str) -> None:
    search = driver.find_element(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
    search.click()
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.BACKSPACE)
    WebDriverWait(driver, 5).until(lambda d: search_value(d) == "")
    search.send_keys(query)
    WebDriverWait(driver, 5).until(lambda d: search_value(d) == query)
    wait_for_search_settle(driver, query)


def wait_for_search_settle(driver: Any, query: str, timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    stable_since: float | None = None
    last_signature = ""
    query_norm = query.casefold()
    while time.time() < deadline:
        if search_value(driver) != query:
            stable_since = None
            time.sleep(0.2)
            continue
        rows = collect_candidate_preview(driver)
        signature = "|".join(f"{row.category}:{row.display_name}" for row in rows)
        text = _visible_text(driver)
        text_norm = text.casefold()
        has_query_context = query_norm in text_norm
        no_result = has_query_context and any(term in text for term in NO_RESULT_TERMS)
        if rows:
            if signature == last_signature and has_query_context:
                if stable_since is None:
                    stable_since = time.time()
                if time.time() - stable_since >= 0.8:
                    return
            else:
                stable_since = None
                last_signature = signature
        elif no_result:
            return
        time.sleep(0.2)


def search_value(driver: Any) -> str:
    try:
        return driver.find_element(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR).get_attribute("value") or ""
    except Exception:
        return ""


def collect_candidate_preview(driver: Any) -> list[LineCandidate]:
    return [
        LineCandidate(
            category=row.get("category") or "",
            display_name=row.get("displayName") or "",
            row_index=int(row.get("rowIndex", 0)),
        )
        for row in raw_candidate_rows(driver)
    ]


def collect_candidates(driver: Any) -> list[LineCandidate]:
    rows = raw_candidate_rows(driver)
    candidates: list[LineCandidate] = []
    for row in rows:
        candidates.append(
            LineCandidate(
                category=row.get("category") or "",
                display_name=row.get("displayName") or "",
                row_index=int(row.get("rowIndex", len(candidates))),
                element=row.get("element"),
            )
        )
    return candidates


def raw_candidate_rows(driver: Any) -> list[dict[str, Any]]:
    return driver.execute_script(
        """
        const elements = [...document.querySelectorAll(
          '[class*="categoryLayout-module__button_category"], [class*="friendlistItem-module__item"]'
        )];
        let category = '';
        const rows = [];
        for (const el of elements) {
          const rect = el.getBoundingClientRect();
          if (rect.width <= 0 || rect.height <= 0) continue;
          const className = String(el.className || '');
          if (className.includes('categoryLayout-module__button_category')) {
            category = (el.innerText || el.textContent || '').split('\\n')[0].trim();
            continue;
          }
          if (!className.includes('friendlistItem-module__item')) continue;
          const nameEl = el.querySelector('[class*="friendlistItem-module__name_box"]');
          const displayName = ((nameEl && nameEl.innerText) || el.innerText || el.textContent || '').trim();
          rows.push({category, displayName, rowIndex: rows.length, element: el});
        }
        return rows;
        """
    )


def visible_result_rows(driver: Any) -> list[Any]:
    visible = []
    for row in driver.find_elements(By.CSS_SELECTOR, RESULT_SELECTOR):
        try:
            rect = row.rect
        except StaleElementReferenceException:
            continue
        if rect["width"] > 0 and rect["height"] > 0:
            visible.append(row)
    return visible


def resolve_match(
    driver: Any,
    *,
    query: str,
    policy: str,
    allow_group: bool = False,
    allowed_group_targets: tuple[str, ...] = (),
) -> MatchDecision:
    last_decision: MatchDecision | None = None
    for attempt in range(3):
        search_line(driver, query)
        decision = apply_match_policy(
            query=query,
            candidates=collect_candidates(driver),
            policy=policy,
            allow_group=allow_group,
            allowed_group_targets=allowed_group_targets,
        )
        if decision.status != "no_match":
            return decision
        last_decision = decision
        if attempt < 2:
            time.sleep(1.0)
    return last_decision or MatchDecision("no_match", policy, query, None, (), "no matching row")


def clear_search(driver: Any) -> None:
    search = driver.find_element(By.CSS_SELECTOR, SEARCH_INPUT_SELECTOR)
    search.click()
    search.send_keys(Keys.CONTROL, "a")
    search.send_keys(Keys.BACKSPACE)


def _visible_text(driver: Any) -> str:
    try:
        return driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        return ""


def open_chat(driver: Any, decision: MatchDecision) -> None:
    if not decision.ok or decision.selected is None:
        raise RuntimeError(f"Cannot open chat: {decision.status} {decision.detail}")
    button = decision.selected.element.find_element(
        By.CSS_SELECTOR,
        '[class*="friendlistItem-module__button_friendlist_item"]',
    )
    driver.execute_script("arguments[0].click();", button)
    expected_name = (decision.selected.display_name or "").splitlines()[0]
    WebDriverWait(driver, 20).until(
        lambda d: (
            d.find_elements(By.CSS_SELECTOR, ".chatroomHeader-module__button_name__US7lb")
            or shadow_message_field(d) is not None
            or visible_message_fields(d)
            or (expected_name and expected_name in _visible_text(d))
        )
    )


def visible_message_fields(driver: Any) -> list[tuple[Any, dict[str, float], str]]:
    fields = driver.find_elements(
        By.CSS_SELECTOR,
        "textarea, [contenteditable='true'], [role='textbox']",
    )
    visible = []
    for field in fields:
        rect = field.rect
        label = (
            field.get_attribute("placeholder")
            or field.get_attribute("aria-label")
            or field.text
            or ""
        ).strip()
        if rect["width"] > 0 and rect["height"] > 0:
            visible.append((field, rect, label))
    return visible


def shadow_message_field(driver: Any) -> tuple[Any, dict[str, float], str] | None:
    data = driver.execute_script(
        """
        const hosts = [...document.querySelectorAll('textarea-ex')];
        for (const host of hosts) {
          const root = host.shadowRoot;
          if (!root) continue;
          const input = root.querySelector('textarea[part="input"], textarea.input, textarea');
          if (!input) continue;
          const r = input.getBoundingClientRect();
          if (r.width <= 0 || r.height <= 0) continue;
          return {
            element: input,
            rect: {x: r.x, y: r.y, width: r.width, height: r.height},
            label: input.placeholder || host.getAttribute('placeholder') || ''
          };
        }
        return null;
        """
    )
    if not data:
        return None
    return data["element"], data["rect"], data.get("label", "")


def cdp_mouse_click(driver: Any, x: float, y: float) -> None:
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


def cdp_type_and_enter(driver: Any, message: str) -> None:
    driver.execute_cdp_cmd("Input.insertText", {"text": message})
    time.sleep(0.1)
    for event_type in ("keyDown", "keyUp"):
        driver.execute_cdp_cmd(
            "Input.dispatchKeyEvent",
            {
                "type": event_type,
                "key": "Enter",
                "code": "Enter",
                "windowsVirtualKeyCode": 13,
            },
        )


def composer_click_point(driver: Any) -> tuple[float, float]:
    data = driver.execute_script(
        """
        const buttons = [...document.querySelectorAll('button')].map(el => {
          const r = el.getBoundingClientRect();
          return {text: el.innerText || el.getAttribute('aria-label') || '', x:r.x, y:r.y, w:r.width, h:r.height};
        }).filter(item => item.w > 0 && item.h > 0);
        const sendFile = buttons.find(item => item.text.includes('Send file'));
        const left = sendFile ? sendFile.x + 55 : 455;
        return {x: left + 80, y: window.innerHeight - 62};
        """
    )
    return data["x"], data["y"]


def send_message(driver: Any, message: str) -> str:
    if not message.strip():
        raise ValueError("Refusing to send a blank message.")
    shadow_field = shadow_message_field(driver)
    if shadow_field is not None:
        field, _rect, _label = shadow_field
        field.click()
        field.send_keys(message)
        field.send_keys(Keys.ENTER)
        return "shadow_dom"
    fields = visible_message_fields(driver)
    if fields:
        field, _rect, _label = sorted(fields, key=lambda item: item[1]["y"], reverse=True)[0]
        field.click()
        field.send_keys(message)
        field.send_keys(Keys.ENTER)
        return "dom"
    x, y = composer_click_point(driver)
    cdp_mouse_click(driver, x, y)
    time.sleep(0.2)
    cdp_type_and_enter(driver, message)
    return "cdp"
