import shutil
import unittest
import uuid
from pathlib import Path

from app.line_messaging import (
    ImageUploadResult,
    submit_image_attachment,
    upload_image,
)


class FakeInput:
    def __init__(self):
        self.values = []

    def send_keys(self, value):
        self.values.append(value)


class FakeDriver:
    def __init__(self, inputs=None, states=None):
        self.inputs = list(inputs or [])
        self.states = list(states or [])
        self.script_clicks = 0

    def find_elements(self, _by, _selector):
        return self.inputs

    def execute_script(self, script):
        if "target.click()" in script:
            self.script_clicks += 1
            return True
        if self.states:
            return self.states.pop(0)
        return {"preview": False, "explicitSubmit": False}


class LineImageMessagingTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data/test_tmp") / str(uuid.uuid4())
        self.root.mkdir(parents=True)
        self.image = self.root / "picture.jpg"
        self.image.write_bytes(b"fake-jpeg")

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_upload_uses_file_control_once_and_observes_preview(self):
        file_input = FakeInput()
        driver = FakeDriver(
            inputs=[file_input],
            states=[{"preview": True, "explicitSubmit": True}],
        )

        result = upload_image(driver, self.image, timeout_seconds=0.01)

        self.assertEqual(file_input.values, [str(self.image.resolve())])
        self.assertTrue(result.preview_detected)
        self.assertTrue(result.explicit_submit_required)

    def test_upload_rejects_missing_file_before_browser_action(self):
        driver = FakeDriver()

        with self.assertRaises(FileNotFoundError):
            upload_image(driver, self.root / "missing.jpg", timeout_seconds=0.01)

        self.assertEqual(driver.script_clicks, 0)

    def test_explicit_submit_clicks_once(self):
        driver = FakeDriver(
            states=[{"preview": False, "explicitSubmit": False}]
        )
        result = ImageUploadResult("input[type='file']", True, True)

        method = submit_image_attachment(driver, result, timeout_seconds=0.01)

        self.assertEqual(method, "explicit_attachment_submit")
        self.assertEqual(driver.script_clicks, 1)

    def test_uncertain_submit_is_never_retried(self):
        driver = FakeDriver(
            states=[
                {"preview": True, "explicitSubmit": True},
                {"preview": True, "explicitSubmit": True},
            ]
        )
        result = ImageUploadResult("input[type='file']", True, True)

        with self.assertRaisesRegex(TimeoutError, "was not retried"):
            submit_image_attachment(driver, result, timeout_seconds=0.001)

        self.assertEqual(driver.script_clicks, 1)

    def test_auto_submit_does_not_click_send(self):
        driver = FakeDriver()
        result = ImageUploadResult("input[type='file']", True, False)

        method = submit_image_attachment(driver, result)

        self.assertEqual(method, "file_input_auto_submit")
        self.assertEqual(driver.script_clicks, 0)


if __name__ == "__main__":
    unittest.main()
