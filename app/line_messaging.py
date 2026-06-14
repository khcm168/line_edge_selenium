from __future__ import annotations

import base64
import mimetypes
import time
import threading
import ctypes
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from app.line_client import SEARCH_INPUT_SELECTOR
from app.line_matcher import LineCandidate, MatchDecision, apply_match_policy


FILE_INPUT_SELECTOR = "input[type='file']"


@dataclass(frozen=True)
class ImageUploadResult:
    input_selector: str
    preview_detected: bool
    explicit_submit_required: bool
    composer_submit_required: bool = False
    baseline_message_image_count: int = 0
    picker_method: str = ""
    auto_send_verified: bool = False


def _attachment_state(
    driver: Any,
    *,
    baseline_sources: tuple[str, ...] = (),
) -> dict[str, bool]:
    state = driver.execute_script(
        """
        const baseline = new Set(arguments[0] || []);
        const visible = (el) => {
          if (!el) return false;
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
        };
        const roots = [...document.querySelectorAll(
          '[role="dialog"], [aria-modal="true"], .modal, .dialog'
        )].filter(visible);
        const scope = roots.length ? roots : [document];
        const nodes = scope.flatMap(root => [...root.querySelectorAll('*')]);
        const labels = nodes
          .filter(visible)
          .map(el => (
            el.getAttribute('aria-label')
            || el.getAttribute('title')
            || el.textContent
            || ''
          ).trim());
        const editorPreview = nodes.some(el =>
          visible(el)
          && (
            el.matches('[class*="chatroomEditor-module__image_list_wrap"]')
            || el.matches('[class*="pastedImageList-module__image_list_item"]')
          )
        );
        const explicitSubmit = editorPreview || labels.some(label =>
          /^(send|傳送|发送|送信)$/i.test(label)
        );
        const preview = nodes.some(el => {
          if (!visible(el)) return false;
          if (el.tagName === 'IMG') {
            if (
              roots.length === 0
              && !el.closest('[class*="imageMessageContent"]')
            ) {
              return false;
            }
            const src = el.getAttribute('src') || '';
            return !baseline.has(src)
              && (src.startsWith('blob:') || src.startsWith('data:'));
          }
          return /file selected|已選擇|已选择/i.test(
            `${el.getAttribute('aria-label') || ''} ${el.textContent || ''}`
          );
        });
        return {
          preview: preview || editorPreview,
          explicitSubmit,
          editorPreview,
        };
        """,
        list(baseline_sources),
    )
    return {
        "preview": bool(state and state.get("preview")),
        "explicit_submit": bool(state and state.get("explicitSubmit")),
        "editor_preview": bool(state and state.get("editorPreview")),
    }


def wait_for_attachment_state(
    driver: Any,
    *,
    timeout_seconds: float = 10.0,
    baseline_sources: tuple[str, ...] = (),
) -> dict[str, bool]:
    deadline = time.monotonic() + timeout_seconds
    last_state = {
        "preview": False,
        "explicit_submit": False,
        "editor_preview": False,
    }
    while time.monotonic() < deadline:
        last_state = _attachment_state(
            driver,
            baseline_sources=baseline_sources,
        )
        if last_state["preview"] or last_state["explicit_submit"]:
            return last_state
        time.sleep(0.2)
    return last_state


def upload_image(
    driver: Any,
    image_path: str | Path,
    *,
    timeout_seconds: float = 10.0,
) -> ImageUploadResult:
    resolved = Path(image_path).expanduser().resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"LINE image file does not exist: {resolved}")

    baseline_sources = _stable_image_sources(
        driver,
        timeout_seconds=min(2.0, timeout_seconds),
    )
    baseline_message_image_count = _message_image_count(driver)
    inputs = driver.find_elements(By.CSS_SELECTOR, FILE_INPUT_SELECTOR)
    if inputs:
        inputs[-1].send_keys(str(resolved))
        picker_method = "dom_file_input"
    else:
        picker_method = _upload_through_file_dialog(
            driver,
            resolved,
            timeout_seconds=timeout_seconds,
        )
    state = wait_for_attachment_state(
        driver,
        timeout_seconds=timeout_seconds,
        baseline_sources=baseline_sources,
    )
    if not state["preview"] and not state["explicit_submit"]:
        raise TimeoutError(
            "LINE accepted the file selection but no new attachment state "
            "was verified; submission was not retried"
        )
    auto_send_verified = False
    if (
        picker_method == "show_open_file_picker"
        and not state["editor_preview"]
    ):
        _wait_for_auto_sent_image(
            driver,
            baseline_message_image_count=baseline_message_image_count,
            timeout_seconds=timeout_seconds,
        )
        auto_send_verified = True
    return ImageUploadResult(
        input_selector=FILE_INPUT_SELECTOR,
        preview_detected=state["preview"],
        explicit_submit_required=state["explicit_submit"],
        composer_submit_required=state["editor_preview"],
        baseline_message_image_count=baseline_message_image_count,
        picker_method=picker_method,
        auto_send_verified=auto_send_verified,
    )


def _visible_image_sources(driver: Any) -> tuple[str, ...]:
    sources = driver.execute_script(
        """
        // attachment-baseline
        return [...document.querySelectorAll(
          '[class*="imageMessageContent"] img'
        )]
          .filter(el => {
            const style = window.getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            return style.display !== 'none' && style.visibility !== 'hidden'
              && rect.width > 0 && rect.height > 0;
          })
          .map(el => el.getAttribute('src') || '')
          .filter(Boolean);
        """
    )
    return tuple(str(item) for item in (sources or ()))


def _stable_image_sources(
    driver: Any,
    *,
    timeout_seconds: float,
) -> tuple[str, ...]:
    if timeout_seconds < 0.1:
        return _visible_image_sources(driver)
    deadline = time.monotonic() + timeout_seconds
    stable_since = time.monotonic()
    previous = _visible_image_sources(driver)
    while time.monotonic() < deadline:
        time.sleep(0.1)
        current = _visible_image_sources(driver)
        if current != previous:
            previous = current
            stable_since = time.monotonic()
        elif time.monotonic() - stable_since >= 0.5:
            return current
    return previous


def _message_image_count(driver: Any) -> int:
    count = driver.execute_script(
        """
        return document.querySelectorAll(
          '[class*="imageMessageContent-module__button_view"], '
          + 'button[aria-label="Show image"]'
        ).length;
        """
    )
    return int(count or 0)


def _wait_for_auto_sent_image(
    driver: Any,
    *,
    baseline_message_image_count: int,
    timeout_seconds: float,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = driver.execute_script(
            """
            // auto-sent-image-state
            const visible = (element) => {
              const style = window.getComputedStyle(element);
              const rect = element.getBoundingClientRect();
              return style.display !== 'none'
                && style.visibility !== 'hidden'
                && rect.width > 0
                && rect.height > 0;
            };
            return {
              imageCount: document.querySelectorAll(
                '[class*="imageMessageContent-module__button_view"], '
                + 'button[aria-label="Show image"]'
              ).length,
              uploadInProgress: [...document.querySelectorAll(
                '[class*="progressBar"]'
              )].some(visible),
            };
            """
        )
        if (
            int(state.get("imageCount", 0)) > baseline_message_image_count
            and not bool(state.get("uploadInProgress"))
        ):
            return
        time.sleep(0.2)
    raise TimeoutError(
        "LINE image auto-send did not reach a verified completed state; "
        "submission was not retried"
    )


def _upload_through_file_dialog(
    driver: Any,
    image_path: Path,
    *,
    timeout_seconds: float,
) -> str:
    if _install_one_shot_file_picker(driver, image_path):
        button = _find_send_file_button(driver)
        if button is None:
            _cleanup_one_shot_file_picker(driver)
            raise RuntimeError("LINE Send file control was not found")
        button.click()
        consumed = _wait_for_one_shot_file_picker(
            driver,
            timeout_seconds=timeout_seconds,
        )
        _cleanup_one_shot_file_picker(driver)
        if consumed:
            return "show_open_file_picker"
        raise TimeoutError(
            "LINE did not consume the one-shot file picker; "
            "no native dialog fallback was attempted"
        )

    completed = threading.Event()
    outcome: dict[str, Any] = {}

    def set_selected_file(dialog: Any) -> None:
        try:
            if dialog.element is None:
                outcome["native_dialog"] = True
            else:
                driver.input.set_files(
                    context=dialog.context,
                    element=dialog.element,
                    files=[str(image_path)],
                )
                outcome["ok"] = True
        except Exception as exc:
            outcome["error"] = exc
        finally:
            completed.set()

    handler_id = driver.input.add_file_dialog_handler(set_selected_file)
    try:
        button = _find_send_file_button(driver)
        if button is None:
            raise RuntimeError("LINE Send file control was not found")
        button.click()
        if not completed.wait(timeout_seconds):
            raise TimeoutError("LINE file chooser did not open")
        if "error" in outcome:
            raise RuntimeError(
                f"LINE file chooser could not select the image: {outcome['error']}"
            )
        if outcome.get("native_dialog"):
            _select_file_in_native_dialog(
                image_path,
                timeout_seconds=timeout_seconds,
            )
            return "native_file_dialog"
        return "bidi_file_dialog"
    finally:
        driver.input.remove_file_dialog_handler(handler_id)


def _install_one_shot_file_picker(
    driver: Any,
    image_path: Path,
) -> bool:
    media_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    installed = driver.execute_script(
        """
        // codex-one-shot-file-picker
        if (typeof window.showOpenFilePicker !== 'function') return false;
        if (window.__codexOneShotFilePicker) return false;
        const original = window.showOpenFilePicker;
        const bytes = Uint8Array.from(
          atob(arguments[0]),
          character => character.charCodeAt(0)
        );
        const file = new File(
          [bytes],
          arguments[1],
          {type: arguments[2], lastModified: arguments[3]}
        );
        const state = {status: 'armed', original};
        window.__codexOneShotFilePicker = state;
        window.showOpenFilePicker = async () => {
          if (state.status !== 'armed') return [];
          state.status = 'consumed';
          window.showOpenFilePicker = original;
          return [{
            kind: 'file',
            name: file.name,
            getFile: async () => file,
            isSameEntry: async () => false,
            queryPermission: async () => 'granted',
            requestPermission: async () => 'granted',
          }];
        };
        return true;
        """,
        encoded,
        image_path.name,
        media_type,
        int(image_path.stat().st_mtime * 1000),
    )
    return bool(installed)


def _wait_for_one_shot_file_picker(
    driver: Any,
    *,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        status = driver.execute_script(
            "return window.__codexOneShotFilePicker?.status || '';"
        )
        if status == "consumed":
            return True
        time.sleep(0.1)
    return False


def _cleanup_one_shot_file_picker(driver: Any) -> None:
    driver.execute_script(
        """
        const state = window.__codexOneShotFilePicker;
        if (!state) return;
        if (state.status === 'armed') {
          window.showOpenFilePicker = state.original;
        }
        delete window.__codexOneShotFilePicker;
        """
    )


def _find_send_file_button(driver: Any) -> Any | None:
    for button in driver.find_elements(
        By.CSS_SELECTOR,
        "button, [role='button'], [aria-label], [title]",
    ):
        try:
            label = (
                button.get_attribute("aria-label")
                or button.get_attribute("title")
                or button.text
                or ""
            ).strip()
            if label.casefold() == "send file" or any(
                term in label for term in ("傳送檔案", "傳送文件", "附件", "ファイル")
            ):
                return button
        except StaleElementReferenceException:
            continue
    return driver.execute_script(
        """
        const visible = (el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
        };
        const iconButtons = [...document.querySelectorAll('button')]
          .filter(button => visible(button) && button.querySelector('svg'))
          .filter(button => {
            const rect = button.getBoundingClientRect();
            return rect.top > window.innerHeight * 0.7;
          })
          .sort((left, right) =>
            left.getBoundingClientRect().left
            - right.getBoundingClientRect().left
          );
        return iconButtons[0] || null;
        """
    )


def _select_file_in_native_dialog(
    image_path: Path,
    *,
    timeout_seconds: float,
) -> None:
    if not hasattr(ctypes, "windll"):
        raise RuntimeError("LINE native file dialog fallback requires Windows")
    user32 = ctypes.windll.user32
    dialog = _wait_for_native_file_dialog(
        user32,
        timeout_seconds=timeout_seconds,
    )
    if not user32.IsWindowVisible(dialog):
        raise RuntimeError("LINE native file dialog is not visible")
    filename_field = _find_dialog_child(
        user32,
        dialog,
        class_name="Edit",
        control_id=1148,
    )
    open_button = _find_dialog_child(
        user32,
        dialog,
        class_name="Button",
        control_id=1,
    )
    if not filename_field or not open_button:
        raise RuntimeError("LINE native file dialog controls were not found")
    if (
        not user32.IsWindowVisible(filename_field)
        or not user32.IsWindowVisible(open_button)
    ):
        raise RuntimeError(
            "LINE native file dialog controls could not be verified; "
            "no keyboard or mouse fallback was attempted"
        )
    _enter_native_dialog_filename(
        user32,
        dialog=dialog,
        filename_field=filename_field,
        image_path=image_path,
    )
    user32.SendMessageW(open_button, 0x00F5, 0, 0)  # BM_CLICK

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if not user32.IsWindow(dialog) or not user32.IsWindowVisible(dialog):
            return
        time.sleep(0.2)
    raise TimeoutError("LINE native file dialog did not close after one selection")


def _enter_native_dialog_filename(
    user32: Any,
    *,
    dialog: int,
    filename_field: int,
    image_path: Path,
) -> None:
    expected = str(image_path)
    if not user32.SetWindowTextW(filename_field, expected):
        raise ctypes.WinError()
    if _window_text(user32, filename_field) != expected:
        raise RuntimeError(
            "LINE native file dialog filename was not populated; "
            "Open was not clicked"
        )


def _window_text(user32: Any, hwnd: int) -> str:
    length = int(user32.GetWindowTextLengthW(hwnd))
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, len(buffer))
    return buffer.value


def _wait_for_native_file_dialog(
    user32: Any,
    *,
    timeout_seconds: float,
) -> int:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        foreground = user32.GetForegroundWindow()
        if (
            foreground
            and user32.IsWindowVisible(foreground)
            and _looks_like_file_dialog(user32, foreground)
        ):
            return int(foreground)

        dialogs: list[int] = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def collect(hwnd: int, _lparam: int) -> bool:
            if (
                user32.IsWindowVisible(hwnd)
                and _looks_like_file_dialog(user32, hwnd)
            ):
                dialogs.append(int(hwnd))
            return True

        user32.EnumWindows(collect, 0)
        if dialogs:
            return dialogs[-1]
        time.sleep(0.1)
    raise TimeoutError("LINE native file dialog was not found")


def _looks_like_file_dialog(user32: Any, hwnd: int) -> bool:
    class_name = _window_class(user32, hwnd)
    title = _window_text(user32, hwnd).casefold()
    if any(
        marker in title
        for marker in (
            "choose file",
            "select file",
            "選取此網站可以讀取的檔案",
            "選擇檔案",
        )
    ):
        return True
    if class_name != "#32770":
        return False
    open_button = _find_dialog_child(
        user32,
        hwnd,
        class_name="Button",
        control_id=1,
    )
    if not open_button or not user32.IsWindowVisible(open_button):
        return False
    button_text = _window_text(user32, open_button).casefold()
    return "open" in button_text or "開啟" in button_text


def _window_class(user32: Any, hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buffer, len(buffer))
    return buffer.value


def _find_dialog_child(
    user32: Any,
    dialog: int,
    *,
    class_name: str,
    control_id: int,
) -> int:
    matches: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd: int, _lparam: int) -> bool:
        if (
            user32.GetDlgCtrlID(hwnd) == control_id
            and _window_class(user32, hwnd) == class_name
        ):
            matches.append(int(hwnd))
            return False
        return True

    user32.EnumChildWindows(dialog, collect, 0)
    return matches[0] if matches else 0


def submit_image_attachment(
    driver: Any,
    upload: ImageUploadResult,
    *,
    timeout_seconds: float = 10.0,
) -> str:
    if upload.auto_send_verified:
        return "show_open_file_picker_auto_send_verified"
    if not upload.explicit_submit_required:
        return "file_input_auto_submit"
    if upload.composer_submit_required:
        return _submit_editor_image_once(
            driver,
            baseline_message_image_count=upload.baseline_message_image_count,
            timeout_seconds=timeout_seconds,
        )

    clicked = driver.execute_script(
        """
        const visible = (el) => {
          if (!el) return false;
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
        };
        const roots = [...document.querySelectorAll(
          '[role="dialog"], [aria-modal="true"], .modal, .dialog'
        )].filter(visible);
        const scope = roots.length ? roots : [document];
        const candidates = scope.flatMap(root => [...root.querySelectorAll(
          'button, [role="button"], [aria-label], [title]'
        )]).filter(visible);
        const target = candidates.find(el => {
          const label = (
            el.getAttribute('aria-label')
            || el.getAttribute('title')
            || el.textContent
            || ''
          ).trim();
          return /^(send|傳送|发送|送信)$/i.test(label);
        });
        if (!target) return false;
        target.click();
        return true;
        """
    )
    if not clicked:
        raise RuntimeError("LINE image submit control disappeared before submission")

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = _attachment_state(driver)
        if not state["explicit_submit"]:
            return "explicit_attachment_submit"
        time.sleep(0.2)

    raise TimeoutError(
        "LINE image submission state is uncertain; submission was not retried"
    )


def _submit_editor_image_once(
    driver: Any,
    *,
    baseline_message_image_count: int,
    timeout_seconds: float,
) -> str:
    shadow_field = shadow_message_field(driver)
    if shadow_field is not None:
        field = shadow_field[0]
    else:
        fields = visible_message_fields(driver)
        if not fields:
            raise RuntimeError(
                "LINE composer was not found; image submission was not attempted"
            )
        field = sorted(fields, key=lambda item: item[1]["y"], reverse=True)[0][0]

    field.click()
    field.send_keys(Keys.ENTER)

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = _attachment_state(driver)
        message_image_count = _message_image_count(driver)
        if (
            not state["editor_preview"]
            and message_image_count > baseline_message_image_count
        ):
            return "composer_enter_verified"
        time.sleep(0.2)

    raise TimeoutError(
        "LINE image submission is uncertain after one composer Enter; "
        "submission was not retried"
    )


RESULT_SELECTOR = (
    '[class*="friendlistItem-module__item"], '
    '[class*="chatlistItem-module__chatlist_item"]'
)
NAME_SELECTOR = (
    '[class*="friendlistItem-module__name_box"], '
    '[class*="chatlistItem-module__title_box"]'
)
CATEGORY_OR_ROW_SELECTOR = (
    ".categoryLayout-module__button_category__nqIZM, "
    '[class*="friendlistItem-module__item"], '
    '[class*="chatlistItem-module__chatlist_item"]'
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
            category=_candidate_category(row),
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
                category=_candidate_category(row),
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
          '[class*="categoryLayout-module__button_category"], '
          + '[class*="friendlistItem-module__item"], '
          + '[class*="chatlistItem-module__chatlist_item"]'
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
          const legacyRow = className.includes('friendlistItem-module__item');
          const chatRow = className.includes('chatlistItem-module__chatlist_item');
          if (!legacyRow && !chatRow) continue;
          const nameEl = el.querySelector(
            '[class*="friendlistItem-module__name_box"], '
            + '[class*="chatlistItem-module__title_box"]'
          );
          const displayName = ((nameEl && nameEl.innerText) || el.innerText || el.textContent || '').trim();
          const hasMemberCount = Boolean(
            el.querySelector('[class*="chatlistItem-module__member_count"]')
          );
          rows.push({
            category,
            displayName,
            rowIndex: rows.length,
            rowType: chatRow ? 'chat' : 'legacy',
            hasMemberCount,
            element: el
          });
        }
        return rows;
        """
    )


def _candidate_category(row: dict[str, Any]) -> str:
    if row.get("rowType") == "chat":
        return "group" if row.get("hasMemberCount") else "friend"
    return row.get("category") or ""


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
        '[class*="friendlistItem-module__button_friendlist_item"], '
        '[class*="chatlistItem-module__button_chatlist_item"]',
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
