from __future__ import annotations

import sys
import time

from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

from login_probe import LINE_EXTENSION_URL, build_driver, maybe_login, visible_text, wait_for_phone_verification, dump_state

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")


def ensure_friends(driver):
    driver.get(LINE_EXTENSION_URL + "#/friends")
    WebDriverWait(driver, 30).until(lambda d: visible_text(d) or d.find_elements(By.CSS_SELECTOR, "input"))
    if driver.find_elements(By.CSS_SELECTOR, "input[type='password']"):
        if maybe_login(driver):
            wait_for_phone_verification(driver)
            time.sleep(2)
            driver.get(LINE_EXTENSION_URL + "#/friends")
    WebDriverWait(driver, 30).until(lambda d: d.find_elements(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7"))


def main():
    query = sys.argv[1] if len(sys.argv) > 1 else "慕光"
    driver = build_driver()
    try:
        driver.maximize_window()
        ensure_friends(driver)
        box = driver.find_element(By.CSS_SELECTOR, ".searchInput-module__input__ekGp7")
        box.click()
        box.send_keys(Keys.CONTROL, "a")
        box.send_keys(query)
        time.sleep(1.5)
        row = driver.find_element(By.CSS_SELECTOR, ".friendlistItem-module__item__1tuZn")
        ActionChains(driver).move_to_element(row).context_click(row).perform()
        WebDriverWait(driver, 5).until(lambda d: d.find_elements(By.XPATH, "//button[normalize-space(.)='變更好友名稱']"))
        data = driver.execute_script(
            """
            const btn = document.evaluate("//button[normalize-space(.)='變更好友名稱']", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            const propsKeys = Object.keys(btn).filter(k => k.startsWith('__reactProps$') || k.startsWith('__reactEventHandlers$'));
            const fiberKeys = Object.keys(btn).filter(k => k.startsWith('__reactFiber$'));
            const props = propsKeys.length ? btn[propsKeys[0]] : {};
            return {propsKeys, fiberKeys, props: propsKeys.map(k => Object.keys(btn[k] || {})), text: btn.innerText,
                    onClick: props.onClick ? String(props.onClick).slice(0, 1000) : null};
            """
        )
        print(f"react_data={data}")
        clicked = driver.execute_script(
            """
            const btn = document.evaluate("//button[normalize-space(.)='變更好友名稱']", document, null, XPathResult.FIRST_ORDERED_NODE_TYPE, null).singleNodeValue;
            const propsKey = Object.keys(btn).find(k => k.startsWith('__reactProps$') || k.startsWith('__reactEventHandlers$'));
            const props = propsKey ? btn[propsKey] : {};
            const evt = {target: btn, currentTarget: btn, preventDefault(){}, stopPropagation(){}, nativeEvent:{target: btn, currentTarget: btn, preventDefault(){}, stopPropagation(){}}};
            if (props.onMouseDown) props.onMouseDown(evt);
            if (props.onClick) props.onClick(evt);
            return {hasMouseDown: !!props.onMouseDown, hasClick: !!props.onClick};
            """
        )
        print(f"react_invoked={clicked}")
        time.sleep(1)
        dump_state(driver, f"react_menu_after_{query}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
