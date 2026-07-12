import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from app.bmp_safety import is_bmp_safe, non_bmp_codepoints, sanitize_bmp_text
from app.task_builder import MessageTask, read_tasks, write_tasks


class BmpSafetyTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_sanitizes_non_bmp_characters(self):
        text = "health red " + chr(0x1F6A8)

        self.assertFalse(is_bmp_safe(text))
        self.assertEqual(sanitize_bmp_text(text), "health red ")
        self.assertEqual(non_bmp_codepoints(text), ("U+1F6A8",))

    def test_task_json_is_written_and_read_as_bmp_safe(self):
        path = self.root / "tasks.json"
        task = MessageTask(
            action="send_message",
            query="P100",
            match_policy="exact_friend",
            message="nightly health " + chr(0x1F6A8),
        )

        write_tasks(path, [task])

        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["message"], "nightly health ")
        self.assertEqual(read_tasks(path)[0].message, "nightly health ")


if __name__ == "__main__":
    unittest.main()
