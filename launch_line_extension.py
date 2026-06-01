from __future__ import annotations

import os
import pathlib
import time

from selenium import webdriver
from selenium.webdriver.edge.options import Options


ROOT = pathlib.Path(__file__).resolve().parent
SCREENSHOTS = ROOT / "screenshots"
EDGE_BINARY = pathlib.Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe")
LINE_EXTENSION_ID = "ophjlpahpchlmihnnnihgmmeilfjmjjc"
LINE_EXTENSION_DIR = pathlib.Path(
    rf"C:\Users\khcm1\AppData\Local\Microsoft\Edge\User Data\Default\Extensions\{LINE_EXTENSION_ID}\3.7.2_0"
)
LINE_EXTENSION_URL = f"chrome-extension://{LINE_EXTENSION_ID}/index.html"


def build_driver() -> webdriver.Edge:
    options = Options()
    options.binary_location = str(EDGE_BINARY)
    options.add_argument(f"--user-data-dir={ROOT / 'edge-profile'}")
    options.add_argument("--no-first-run")
    options.add_argument("--no-default-browser-check")
    options.add_argument(f"--load-extension={LINE_EXTENSION_DIR}")
    options.add_argument(f"--disable-extensions-except={LINE_EXTENSION_DIR}")
    options.add_argument("--window-size=1180,900")

    return webdriver.Edge(options=options)


def main() -> None:
    if not EDGE_BINARY.exists():
        raise FileNotFoundError(f"Edge binary not found: {EDGE_BINARY}")
    if not LINE_EXTENSION_DIR.exists():
        raise FileNotFoundError(f"LINE extension not found: {LINE_EXTENSION_DIR}")

    SCREENSHOTS.mkdir(exist_ok=True)
    driver = build_driver()
    try:
        driver.get(LINE_EXTENSION_URL)
        time.sleep(5)
        screenshot_path = SCREENSHOTS / "line_extension_probe.png"
        driver.save_screenshot(str(screenshot_path))

        body_text = ""
        try:
            body_text = driver.find_element("tag name", "body").text
        except Exception:
            body_text = ""

        print(f"title={driver.title!r}")
        print(f"url={driver.current_url}")
        print(f"screenshot={screenshot_path}")
        print("body_text_begin")
        print(body_text[:2000])
        print("body_text_end")
        print("LINE_EMAIL configured:", bool(os.environ.get("LINE_EMAIL")))
        print("LINE_PASSWORD configured:", bool(os.environ.get("LINE_PASSWORD")))
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
