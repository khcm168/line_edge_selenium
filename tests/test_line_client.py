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
        self.quit_calls = 0

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

    def quit(self):
        self.quit_calls += 1


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

    def test_dismisses_temporary_error_logout_confirmation(self):
        button = FakeElement(text="確定")
        driver = FakeDriver()

        with patch(
            "app.line_client.visible_text",
            return_value="由於發生暫時性錯誤，已為您登出，請重新登入。",
        ):
            with patch.object(driver, "find_elements", return_value=[button]):
                dismissed = _dismiss_auto_logout_modal(driver)

        self.assertTrue(dismissed)
        self.assertEqual(button.clicks, 1)

    def test_ensure_friends_recovers_from_logout_modal_then_login_prompt(self):
        driver = FakeDriver()
        client = LineClient(driver)

        with (
            patch("app.line_client.visible_text", return_value="LINE"),
            patch(
                "app.line_client._friends_or_reauth_ready",
                side_effect=["auto_logout", "login", "friends"],
            ),
            patch("app.line_client.maybe_login", return_value=True) as maybe_login,
            patch("app.line_client.wait_for_phone_verification") as wait_for_phone,
            patch("app.line_client.time.sleep"),
        ):
            client.ensure_friends()

        maybe_login.assert_called_once_with(driver)
        wait_for_phone.assert_called_once_with(driver)
        self.assertEqual(len(driver.urls), 3)

    def test_reuse_or_handoff_attaches_to_live_session(self):
        expected = LineClient(FakeDriver())

        with (
            patch("app.line_client.handoff_session_is_live", return_value=True),
            patch.object(
                LineClient,
                "attach_existing",
                return_value=expected,
            ) as attach_existing,
            patch.object(LineClient, "open_handoff") as open_handoff,
        ):
            client = LineClient.open_reuse_or_handoff()

        self.assertIs(client, expected)
        attach_existing.assert_called_once_with(preserve_on_close=True)
        open_handoff.assert_not_called()

    def test_reuse_or_handoff_opens_handoff_when_no_live_session_exists(self):
        expected = LineClient(FakeDriver(), preserve_on_close=True)

        with (
            patch("app.line_client.handoff_session_is_live", return_value=False),
            patch.object(LineClient, "attach_existing") as attach_existing,
            patch.object(LineClient, "open_handoff", return_value=expected) as open_handoff,
        ):
            client = LineClient.open_reuse_or_handoff()

        self.assertIs(client, expected)
        attach_existing.assert_not_called()
        open_handoff.assert_called_once_with(preserve_on_close=True)

    def test_preserved_client_close_does_not_quit_borrowed_session(self):
        driver = FakeDriver()
        client = LineClient(driver, preserve_on_close=True)

        client.close()

        self.assertEqual(driver.quit_calls, 0)


if __name__ == "__main__":
    unittest.main()
