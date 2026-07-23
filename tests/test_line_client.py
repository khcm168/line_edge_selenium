import unittest
from selenium.common.exceptions import NoSuchWindowException
from unittest.mock import patch

from app.line_client import (
    SEARCH_INPUT_SELECTOR,
    LineClient,
    _dismiss_auto_logout_modal,
    _recover_extension_window,
)


class FakeElement:
    def __init__(self, width=100, height=20, *, text="", aria_label="", title=""):
        self.rect = {"width": width, "height": height}
        self.text = text
        self.aria_label = aria_label
        self.title = title
        self.clicks = 0

    def get_attribute(self, name):
        return {
            "aria-label": self.aria_label,
            "title": self.title,
        }.get(name, "")

    def click(self):
        self.clicks += 1


class FakeDriver:
    def __init__(self):
        self.urls = []
        self.window_handles = ["main", "popup"]
        self.current_window_handle = "main"
        self.switched_to = []
        self.switch_to = self

    def get(self, url):
        self.urls.append(url)

    def find_elements(self, by, selector):
        if selector == SEARCH_INPUT_SELECTOR:
            return [FakeElement()]
        if selector == "input[type='password']":
            return [FakeElement()]
        if selector == "input":
            return [FakeElement()]
        return []

    def window(self, handle):
        self.current_window_handle = handle
        self.switched_to.append(handle)


class LineClientTest(unittest.TestCase):
    def test_ensure_friends_does_not_login_when_search_is_visible(self):
        driver = FakeDriver()
        client = LineClient(driver)

        with (
            patch("app.line_client.visible_text", return_value="friends visible"),
            patch("app.line_client.maybe_login") as maybe_login,
            patch("app.line_client.time.sleep"),
        ):
            client.ensure_friends()

        maybe_login.assert_not_called()
        self.assertEqual(len(driver.urls), 1)

    def test_recover_extension_window_switches_when_current_handle_closed(self):
        driver = FakeDriver()
        driver.current_window_handle = "closed"

        _recover_extension_window(driver)

        self.assertEqual(driver.current_window_handle, "popup")
        self.assertEqual(driver.switched_to, ["popup"])

    def test_recover_extension_window_raises_without_handles(self):
        driver = FakeDriver()
        driver.window_handles = []

        with self.assertRaises(NoSuchWindowException):
            _recover_extension_window(driver)

    def test_dismisses_auto_logout_confirmation(self):
        button = FakeElement(text="確定")
        driver = FakeDriver()

        with patch("app.line_client.visible_text", return_value="您已自動登出，請重新登入。"):
            with patch.object(driver, "find_elements", return_value=[button]):
                dismissed = _dismiss_auto_logout_modal(driver)

        self.assertTrue(dismissed)
        self.assertEqual(button.clicks, 1)


if __name__ == "__main__":
    unittest.main()
