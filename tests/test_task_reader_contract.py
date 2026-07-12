import json
import shutil
import unittest
from pathlib import Path
from uuid import uuid4

from app.task_builder import MessageTask, read_tasks


def _task_payload(**overrides):
    payload = {
        "action": "send_message",
        "query": "nightly_project_health",
        "match_policy": "exact_friend",
        "message": "nightly project health OK",
        "source": {"automation": "nightly_project_health"},
        "reminder_type": "nightly_project_health",
    }
    payload.update(overrides)
    return payload


class TaskReaderContractTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_reads_2026_06_25_bom_task_fixture(self):
        path = self.root / "nightly_project_health_2026-06-25_bom.json"
        path.write_text(json.dumps([_task_payload()], ensure_ascii=False), encoding="utf-8-sig")

        tasks = read_tasks(path)

        self.assertEqual(len(tasks), 1)
        self.assertIsInstance(tasks[0], MessageTask)
        self.assertEqual(tasks[0].query, "nightly_project_health")

    def test_reads_2026_06_29_object_shape_task_fixture(self):
        path = self.root / "nightly_project_health_2026-06-29_object_shape.json"
        path.write_text(
            json.dumps({"tasks": [_task_payload(message="object shape OK")]}, ensure_ascii=False),
            encoding="utf-8",
        )

        tasks = read_tasks(path)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].message, "object shape OK")

    def test_reads_single_task_object_shape_fixture(self):
        path = self.root / "world_cup_briefing_single_task_object.json"
        path.write_text(
            json.dumps(_task_payload(query="world_cup_briefing"), ensure_ascii=False),
            encoding="utf-8",
        )

        tasks = read_tasks(path)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].query, "world_cup_briefing")

    def test_reads_non_bmp_message_fixture_as_bmp_safe(self):
        path = self.root / "nightly_project_health_non_bmp.json"
        path.write_text(
            json.dumps([_task_payload(message="health red " + chr(0x1F6A8))], ensure_ascii=False),
            encoding="utf-8",
        )

        tasks = read_tasks(path)

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].message, "health red ")

    def test_rejects_unknown_object_shape_with_clear_error(self):
        path = self.root / "nightly_project_health_bad_object.json"
        path.write_text(json.dumps({"created_at": "2026-06-29", "payload": []}), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "MessageTask object"):
            read_tasks(path)


if __name__ == "__main__":
    unittest.main()
