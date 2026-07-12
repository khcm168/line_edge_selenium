import shutil
import unittest
from pathlib import Path
from unittest.mock import call, patch
from uuid import uuid4

from selenium.common.exceptions import NoSuchElementException

from login_probe import prepare_edge_profile_dir


class LoginProbeProfileGuardTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_removes_stale_devtools_and_singleton_markers(self):
        active_port = self.root / "DevToolsActivePort"
        active_port.write_text("65534\n/devtools/browser/test\n", encoding="utf-8")
        (self.root / "SingletonLock").write_text("", encoding="utf-8")
        (self.root / "SingletonCookie").write_text("", encoding="utf-8")

        with (
            patch("login_probe._debug_port_is_live", return_value=False),
            patch("login_probe._unlink_with_retries") as unlink,
        ):
            prepare_edge_profile_dir(self.root)

        self.assertEqual(
            unlink.call_args_list,
            [
                call(active_port),
                call(self.root / "SingletonCookie"),
                call(self.root / "SingletonLock"),
            ],
        )

    def test_rejects_profile_when_debug_port_is_live(self):
        with patch("login_probe._debug_port_is_live", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "already in use"):
                prepare_edge_profile_dir(self.root)


class LoginProbeLoginButtonTest(unittest.TestCase):
    def test_falls_back_to_visible_submit_button_when_wait_lookup_is_unstable(self):
        class FakeInput:
            def __init__(self, input_type):
                self.rect = {"width": 200, "height": 40}
                self._type = input_type
                self.values = []

            def get_attribute(self, name):
                return self._type if name == "type" else ""

            def clear(self):
                return None

            def send_keys(self, value):
                self.values.append(value)

        class FakeButton:
            def __init__(self):
                self.rect = {"width": 200, "height": 40}
                self.clicked = False

            def click(self):
                self.clicked = True

        class FakeDriver:
            def __init__(self):
                self.inputs = [FakeInput("email"), FakeInput("password")]
                self.button = FakeButton()
                self.script_calls = []

            def find_elements(self, by, selector):
                if selector == "input":
                    return self.inputs
                if selector == "button[type='submit']":
                    return [self.button]
                return []

            def execute_script(self, script, *args):
                self.script_calls.append((script, args))

        driver = FakeDriver()

        with (
            patch.dict(
                "os.environ",
                {"LINE_EMAIL": "user@example.com", "LINE_PASSWORD": "secret"},
                clear=False,
            ),
            patch(
                "login_probe._wait_for_visible_submit_button",
                side_effect=NoSuchElementException("transient lookup"),
            ),
        ):
            from login_probe import maybe_login

            submitted = maybe_login(driver)

        self.assertTrue(submitted)
        self.assertEqual(driver.inputs[0].values, ["user@example.com"])
        self.assertEqual(driver.inputs[1].values, ["secret"])
        self.assertEqual(len(driver.script_calls), 1)
        self.assertIn("arguments[0].click()", driver.script_calls[0][0])


if __name__ == "__main__":
    unittest.main()
