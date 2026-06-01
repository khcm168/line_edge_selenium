from __future__ import annotations

import sys

from login_probe import build_driver
from send_test_message import ensure_friends, open_exact_chat, send_message


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def main() -> None:
    tasks = [
        ("洪啓明", "好友", "小測試：洪啓明，這是一則 LINE 自動化測試訊息。"),
        ("001N1備份區", None, "小測試：001N1備份區，這是一則同一個 Selenium session 的測試訊息。"),
    ]
    driver = build_driver()
    try:
        driver.maximize_window()
        ensure_friends(driver)
        for query, preferred_category, message in tasks:
            opened = open_exact_chat(driver, query, preferred_category)
            print(f"opened_chat={opened}")
            send_message(driver, message)
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
