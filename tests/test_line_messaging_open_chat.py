import unittest

from selenium.webdriver.common.by import By

from app.line_matcher import LineCandidate, MatchDecision
from app.line_messaging import open_chat


class FakeElement:
    def __init__(self, *, text="", width=100, height=30):
        self.text = text
        self.rect = {"width": width, "height": height}
        self.clicks = 0

    def find_element(self, by, selector):
        return self

    def get_attribute(self, name):
        return ""

    def click(self):
        self.clicks += 1


class FakeDriver:
    def __init__(self):
        self.profile_visible = False
        self.chat_ready = False
        self.row_button = FakeElement(text="Abbie Jessica")
        self.profile_button = FakeElement(text="聊天")
        self.script_clicks = []

    def execute_script(self, script, *args):
        if script.startswith("arguments[0].click();"):
            target = args[0]
            self.script_clicks.append(target)
            target.click()
            if target is self.row_button:
                self.profile_visible = True
            if target is self.profile_button:
                self.chat_ready = True
            return None
        if "chatroomHeader-module__button_name" in script:
            return ["Abbie Jessica"] if self.chat_ready else []
        return None

    def find_elements(self, by, selector):
        if selector in {"button", "[role='button']", "a"}:
            if self.profile_visible and not self.chat_ready:
                return [self.profile_button]
            return []
        if selector == "textarea, [contenteditable='true'], [role='textbox']":
            return []
        if by == By.CSS_SELECTOR and "chatroomHeader" in selector and self.chat_ready:
            return [FakeElement(text="Abbie Jessica")]
        return []


class OpenChatTest(unittest.TestCase):
    def test_clicks_profile_chat_button_before_declaring_chat_ready(self):
        driver = FakeDriver()
        candidate = LineCandidate(
            category="friend",
            display_name="Abbie Jessica",
            row_index=0,
            element=driver.row_button,
        )
        decision = MatchDecision(
            status="matched",
            policy="unique_contains_friend",
            query="abb",
            selected=candidate,
            candidates=(candidate,),
            detail="matched exactly one row",
        )

        open_chat(driver, decision)

        self.assertEqual(driver.row_button.clicks, 1)
        self.assertEqual(driver.profile_button.clicks, 1)
        self.assertTrue(driver.chat_ready)


if __name__ == "__main__":
    unittest.main()
