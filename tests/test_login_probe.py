import unittest

from login_probe import find_login_submit_button


class FakeElement:
    def __init__(self, *, text="", aria_label="", title="", button_type="", width=10, height=10):
        self._text = text
        self._aria_label = aria_label
        self._title = title
        self._button_type = button_type
        self.rect = {"width": width, "height": height}

    @property
    def text(self):
        return self._text

    def get_attribute(self, name):
        return {
            "aria-label": self._aria_label,
            "title": self._title,
            "type": self._button_type,
        }.get(name, "")


class FakeDriver:
    def __init__(self, mapping):
        self.mapping = mapping

    def find_elements(self, by, selector):
        return list(self.mapping.get(selector, []))


class LoginProbeTest(unittest.TestCase):
    def test_find_login_submit_button_prefers_submit_type(self):
        submit = FakeElement(button_type="submit")
        driver = FakeDriver({"button[type='submit']": [submit]})

        self.assertIs(find_login_submit_button(driver), submit)

    def test_find_login_submit_button_falls_back_to_label(self):
        labeled = FakeElement(text="Log in")
        driver = FakeDriver(
            {
                "button[type='submit']": [],
                "button": [labeled],
                "[role='button']": [],
            }
        )

        self.assertIs(find_login_submit_button(driver), labeled)


if __name__ == "__main__":
    unittest.main()
