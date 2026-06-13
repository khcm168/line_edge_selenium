import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

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


class FakeButton:
    def __init__(self, on_click=None):
        self.on_click = on_click
        self.clicks = 0

    @property
    def text(self):
        return ""

    def get_attribute(self, name):
        return "Send file" if name == "aria-label" else ""

    def click(self):
        self.clicks += 1
        if self.on_click:
            self.on_click()


class FakeMessageField:
    def __init__(self):
        self.clicks = 0
        self.keys = []

    def click(self):
        self.clicks += 1

    def send_keys(self, *keys):
        self.keys.append(keys)


class FakeBidiInput:
    def __init__(self):
        self.callback = None
        self.files = []

    def add_file_dialog_handler(self, callback):
        self.callback = callback
        return 1

    def remove_file_dialog_handler(self, _handler_id):
        self.callback = None

    def set_files(self, *, context, element, files):
        self.files.append((context, element, files))


class FakeDriver:
    def __init__(
        self,
        inputs=None,
        states=None,
        buttons=None,
        bidi_input=None,
        baseline_sources=None,
        one_shot_supported=False,
        message_image_counts=None,
        auto_send_states=None,
    ):
        self.inputs = list(inputs or [])
        self.states = list(states or [])
        self.buttons = list(buttons or [])
        self.input = bidi_input
        self.baseline_sources = list(baseline_sources or [])
        self.one_shot_supported = one_shot_supported
        self.one_shot_status = ""
        self.message_image_counts = list(message_image_counts or [0])
        self.auto_send_states = list(
            auto_send_states
            or [{"imageCount": 0, "uploadInProgress": False}]
        )
        self.picker_cleanups = 0
        self.script_clicks = 0

    def find_elements(self, _by, selector):
        if selector == "input[type='file']":
            return self.inputs
        return self.buttons

    def execute_script(self, script, *_args):
        if "codex-one-shot-file-picker" in script:
            if self.one_shot_supported:
                self.one_shot_status = "armed"
            return self.one_shot_supported
        if "__codexOneShotFilePicker?.status" in script:
            return self.one_shot_status
        if "delete window.__codexOneShotFilePicker" in script:
            self.picker_cleanups += 1
            self.one_shot_status = ""
            return None
        if "attachment-baseline" in script:
            return self.baseline_sources
        if "auto-sent-image-state" in script:
            if len(self.auto_send_states) > 1:
                return self.auto_send_states.pop(0)
            return self.auto_send_states[0]
        if "imageMessageContent-module__button_view" in script:
            if len(self.message_image_counts) > 1:
                return self.message_image_counts.pop(0)
            return self.message_image_counts[0]
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

    def test_upload_uses_bidi_file_dialog_when_no_dom_input_exists(self):
        bidi_input = FakeBidiInput()
        dialog = type(
            "Dialog",
            (),
            {"context": "context-1", "element": {"sharedId": "file-1"}},
        )()
        button = FakeButton(
            on_click=lambda: bidi_input.callback(dialog)
        )
        driver = FakeDriver(
            buttons=[button],
            bidi_input=bidi_input,
            states=[{"preview": True, "explicitSubmit": False}],
        )

        result = upload_image(driver, self.image, timeout_seconds=0.01)

        self.assertEqual(button.clicks, 1)
        self.assertEqual(
            bidi_input.files,
            [
                (
                    "context-1",
                    {"sharedId": "file-1"},
                    [str(self.image.resolve())],
                )
            ],
        )
        self.assertTrue(result.preview_detected)

    def test_upload_uses_one_shot_show_open_file_picker(self):
        driver = FakeDriver(
            one_shot_supported=True,
            states=[
                {
                    "preview": True,
                    "explicitSubmit": False,
                    "editorPreview": False,
                }
            ],
            auto_send_states=[
                {"imageCount": 1, "uploadInProgress": False},
            ],
        )
        button = FakeButton(
            on_click=lambda: setattr(
                driver,
                "one_shot_status",
                "consumed",
            )
        )
        driver.buttons = [button]

        result = upload_image(driver, self.image, timeout_seconds=0.01)

        self.assertEqual(button.clicks, 1)
        self.assertEqual(result.picker_method, "show_open_file_picker")
        self.assertTrue(result.auto_send_verified)
        self.assertFalse(result.composer_submit_required)
        self.assertEqual(driver.picker_cleanups, 1)
        self.assertEqual(
            submit_image_attachment(driver, result),
            "show_open_file_picker_auto_send_verified",
        )

    def test_bidi_event_without_dom_element_uses_native_dialog_once(self):
        bidi_input = FakeBidiInput()
        dialog = type(
            "Dialog",
            (),
            {"context": "context-1", "element": None},
        )()
        button = FakeButton(
            on_click=lambda: bidi_input.callback(dialog)
        )
        driver = FakeDriver(
            buttons=[button],
            bidi_input=bidi_input,
            states=[{"preview": True, "explicitSubmit": False}],
        )

        with patch(
            "app.line_messaging._select_file_in_native_dialog"
        ) as native_select:
            upload_image(driver, self.image, timeout_seconds=0.01)

        native_select.assert_called_once_with(
            self.image.resolve(),
            timeout_seconds=0.01,
        )
        self.assertEqual(button.clicks, 1)
        self.assertEqual(bidi_input.files, [])

    def test_explicit_submit_clicks_once(self):
        driver = FakeDriver(
            states=[{"preview": False, "explicitSubmit": False}]
        )
        result = ImageUploadResult("input[type='file']", True, True)

        method = submit_image_attachment(driver, result, timeout_seconds=0.01)

        self.assertEqual(method, "explicit_attachment_submit")
        self.assertEqual(driver.script_clicks, 1)

    def test_editor_preview_submits_enter_once_and_verifies_new_image(self):
        field = FakeMessageField()
        driver = FakeDriver(
            states=[
                {
                    "preview": False,
                    "explicitSubmit": False,
                    "editorPreview": False,
                }
            ],
            message_image_counts=[2],
        )
        result = ImageUploadResult(
            "input[type='file']",
            True,
            True,
            composer_submit_required=True,
            baseline_message_image_count=1,
        )

        with patch(
            "app.line_messaging.shadow_message_field",
            return_value=(field, {}, ""),
        ):
            method = submit_image_attachment(
                driver,
                result,
                timeout_seconds=0.01,
            )

        self.assertEqual(method, "composer_enter_verified")
        self.assertEqual(field.clicks, 1)
        self.assertEqual(len(field.keys), 1)

    def test_editor_preview_uncertain_send_is_not_retried(self):
        field = FakeMessageField()
        driver = FakeDriver(
            states=[
                {
                    "preview": True,
                    "explicitSubmit": True,
                    "editorPreview": True,
                }
            ],
            message_image_counts=[1],
        )
        result = ImageUploadResult(
            "input[type='file']",
            True,
            True,
            composer_submit_required=True,
            baseline_message_image_count=1,
        )

        with patch(
            "app.line_messaging.shadow_message_field",
            return_value=(field, {}, ""),
        ):
            with self.assertRaisesRegex(TimeoutError, "not retried"):
                submit_image_attachment(
                    driver,
                    result,
                    timeout_seconds=0.001,
                )

        self.assertEqual(len(field.keys), 1)

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

    def test_existing_chat_image_is_not_attachment_verification(self):
        file_input = FakeInput()
        driver = FakeDriver(
            inputs=[file_input],
            baseline_sources=["blob:old-chat-image"],
            states=[{"preview": False, "explicitSubmit": False}],
        )

        with self.assertRaisesRegex(TimeoutError, "no new attachment state"):
            upload_image(driver, self.image, timeout_seconds=0.001)

        self.assertEqual(file_input.values, [str(self.image.resolve())])


if __name__ == "__main__":
    unittest.main()
