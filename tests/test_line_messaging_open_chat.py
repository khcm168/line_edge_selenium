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
    def __init__(
        self,
        *,
        row_opens_chat=False,
        profile_button_visible=True,
        header_text="Abbie Jessica",
    ):
        self.profile_visible = False
        self.chat_ready = False
        self.row_opens_chat = row_opens_chat
        self.profile_button_visible = profile_button_visible
        self.header_text = header_text
        self.row_button = FakeElement(text="Abbie Jessica")
        self.profile_button = FakeElement(text="聊天")
        self.composer = FakeElement(text="Aa")
        self.script_clicks = []

    def execute_script(self, script, *args):
        if script.startswith("arguments[0].click();"):
            target = args[0]
            self.script_clicks.append(target)
            target.click()
            if target is self.row_button:
                if self.row_opens_chat:
                    self.chat_ready = True
                else:
                    self.profile_visible = True
            if target is self.profile_button:
                self.chat_ready = True
            return None
        if "chatroomHeader-module__button_name" in script:
            return [self.header_text] if self.chat_ready else []
        return None

    def find_elements(self, by, selector):
        if selector in {"button", "[role='button']", "a"}:
            if self.profile_visible and not self.chat_ready and self.profile_button_visible:
                return [self.profile_button]
            return []
        if selector == "textarea, [contenteditable='true'], [role='textbox']":
            return [self.composer] if self.chat_ready else []
        if by == By.CSS_SELECTOR and "chatroomHeader" in selector and self.chat_ready:
            return [FakeElement(text="Abbie Jessica")]
        return []


class OpenChatTest(unittest.TestCase):
    def decision(self):
        candidate = LineCandidate(
            category="friend",
            display_name="Abbie Jessica",
            row_index=0,
            element=self.driver.row_button,
        )
        return MatchDecision(
            status="matched",
            policy="unique_contains_friend",
            query="abb",
            selected=candidate,
            candidates=(candidate,),
            detail="matched exactly one row",
        )

    def test_row_click_can_open_chat_without_profile_fallback(self):
        self.driver = FakeDriver(row_opens_chat=True)

        result = open_chat(self.driver, self.decision())

        self.assertEqual(result.status, "chat_ready")
        self.assertEqual(self.driver.row_button.clicks, 1)
        self.assertEqual(self.driver.profile_button.clicks, 0)
        self.assertTrue(self.driver.chat_ready)

    def test_clicks_profile_chat_button_before_declaring_chat_ready(self):
        self.driver = FakeDriver()
        stages = []

        result = open_chat(
            self.driver,
            self.decision(),
            profile_fallback_snapshot=lambda stage: stages.append(stage) or f"{stage}.json",
        )

        self.assertEqual(result.status, "opened_profile_chat_button")
        self.assertEqual(self.driver.row_button.clicks, 1)
        self.assertGreaterEqual(self.driver.profile_button.clicks, 1)
        self.assertTrue(self.driver.chat_ready)
        self.assertEqual(
            result.evidence,
            {
                "before_profile_chat_button": "before_profile_chat_button.json",
                "after_profile_chat_button": "after_profile_chat_button.json",
            },
        )
        self.assertEqual(stages, ["before_profile_chat_button", "after_profile_chat_button"])

    def test_profile_fallback_blocks_unverified_chat_header(self):
        self.driver = FakeDriver(header_text="Wrong Person")

        with self.assertRaisesRegex(RuntimeError, "unexpected chat"):
            open_chat(self.driver, self.decision())

    def test_profile_fallback_blocks_when_chat_button_is_missing(self):
        self.driver = FakeDriver(profile_button_visible=False)

        with self.assertRaisesRegex(RuntimeError, "did not expose a visible chat button"):
            open_chat(self.driver, self.decision(), timeout_seconds=0.01)


if __name__ == "__main__":
    unittest.main()
