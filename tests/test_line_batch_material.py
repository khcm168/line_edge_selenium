import shutil
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace

from app.line_batch import _resolve_task_material
from app.material_catalog import MaterialRecord, sha256_file, write_catalog
from app.task_builder import MessageTask


class LineBatchMaterialTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data/test_tmp") / str(uuid.uuid4())
        self.material_root = self.root / "materials"
        self.material_root.mkdir(parents=True)
        self.image = self.material_root / "approved.jpg"
        self.image.write_bytes(b"approved-picture")
        self.record = MaterialRecord(
            material_id="MAT-TEST-001",
            filename=self.image.name,
            sha256=sha256_file(self.image),
            duplicate_of="",
            product="test",
            topic="test",
            audience="internal",
            visual_summary="safe test material",
            internal_comment="test",
            customer_caption="test caption",
            risk_level="low",
            safety_flags=(),
            sendability="sendable",
            review_status="approved",
            test_result="unit_test",
        )
        self.catalog_path = self.root / "catalog.json"
        write_catalog(self.catalog_path, [self.record])
        self.settings = SimpleNamespace(
            material_root=self.material_root,
            material_catalog_path=self.catalog_path,
        )

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def task(self, **overrides):
        values = {
            "action": "send_message",
            "query": "001N1備份區",
            "match_policy": "unique_contains_group",
            "message": "caption",
            "allow_group": True,
            "material_id": self.record.material_id,
            "image_path": self.record.filename,
            "message_kind": "image_text",
            "material_sha256": self.record.sha256,
        }
        values.update(overrides)
        return MessageTask(**values)

    def test_resolves_approved_material_and_verifies_hash(self):
        resolved = _resolve_task_material(self.task(), self.settings)

        self.assertEqual(resolved["material_id"], self.record.material_id)
        self.assertEqual(resolved["sha256"], self.record.sha256)
        self.assertEqual(Path(resolved["resolved_path"]), self.image.resolve())

    def test_rejects_task_hash_mismatch(self):
        with self.assertRaisesRegex(ValueError, "Task hash"):
            _resolve_task_material(
                self.task(material_sha256="0" * 64),
                self.settings,
            )

    def test_rejects_changed_external_file(self):
        self.image.write_bytes(b"changed")

        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            _resolve_task_material(self.task(), self.settings)

    def test_rejects_unapproved_material(self):
        blocked = MaterialRecord(
            **{
                **self.record.__dict__,
                "review_status": "pending_review",
            }
        )
        write_catalog(self.catalog_path, [blocked])

        with self.assertRaisesRegex(ValueError, "not approved"):
            _resolve_task_material(self.task(), self.settings)


if __name__ == "__main__":
    unittest.main()
