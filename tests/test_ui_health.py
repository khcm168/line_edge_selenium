import unittest

from app.ui_health import UiHealth, check_login_state, infer_login_state


class FakeElement:
    def __init__(self, *, width=10, height=10, text=""):
        self.rect = {"width": width, "height": height}
        self.text = text


class FakeDriver:
    def __init__(self, mapping):
        self.mapping = mapping

    def find_elements(self, by, selector):
        return list(self.mapping.get(selector, []))

    def find_element(self, by, selector):
        if selector == "body":
            return self.mapping.get("body", FakeElement(text=""))
        raise LookupError(selector)


class FakeClient:
    def __init__(self, *, exc=None, driver=None):
        self.exc = exc
        self.driver = driver or FakeDriver({})

    def ensure_friends(self):
        if self.exc is not None:
            raise self.exc


class UiHealthTest(unittest.TestCase):
    def test_infer_login_state_prefers_visible_search_box(self):
        driver = FakeDriver({".searchInput-module__input__ekGp7": [FakeElement()]})

        health = infer_login_state(driver)

        self.assertEqual(
            health,
            UiHealth(True, "friends_view_visible", "LINE friends view appears reachable"),
        )

    def test_infer_login_state_detects_password_prompt(self):
        driver = FakeDriver({"input[type='password']": [FakeElement()]})

        health = infer_login_state(driver)

        self.assertEqual(health.status, "login_prompt_visible")

    def test_check_login_state_returns_fallback_classification(self):
        driver = FakeDriver({"input[type='password']": [FakeElement()]})
        client = FakeClient(exc=RuntimeError("submit button missing"), driver=driver)

        health = check_login_state(client)

        self.assertFalse(health.ok)
        self.assertEqual(health.status, "login_prompt_visible")
        self.assertIn("original=RuntimeError: submit button missing", health.detail)


if __name__ == "__main__":
    unittest.main()
