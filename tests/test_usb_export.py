import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from app.material_catalog import MaterialRecord, sha256_file, write_catalog
from tools.export_usb_kit import build_usb_kit, is_exportable_source


class UsbExportTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data/test_tmp") / str(uuid.uuid4())
        self.source = self.root / "source_repo"
        self.materials = self.root / "external_materials"
        self.source.mkdir(parents=True)
        self.materials.mkdir(parents=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_secret_and_runtime_paths_are_excluded(self):
        blocked = (
            ".env",
            ".env.local",
            "credentials.json",
            "secrets/service_account.json",
            "edge-profile/Default/Cookies",
            "data/logs/send.jsonl",
            "data/snapshots/a.png",
            "data/responses/intake.jsonl",
            "data/customer_export_2026.csv",
            "private.key",
        )
        for path in blocked:
            self.assertFalse(is_exportable_source(path), path)
        self.assertTrue(is_exportable_source(".env.example"))
        self.assertTrue(is_exportable_source("app/line_batch.py"))

    def test_builds_checksums_and_copies_external_materials(self):
        (self.source / "app").mkdir()
        source_file = self.source / "app" / "sample.py"
        source_file.write_text("print('ok')\n", encoding="utf-8")
        (self.source / "data").mkdir()
        image = self.materials / "001.jpg"
        image.write_bytes(b"picture")
        record = MaterialRecord(
            material_id="MAT-001",
            filename=image.name,
            sha256=sha256_file(image),
            duplicate_of="",
            product="test",
            topic="test",
            audience="test",
            visual_summary="test",
            internal_comment="test",
            customer_caption="test",
            risk_level="low",
            safety_flags=(),
            sendability="sendable",
            review_status="approved",
            test_result="test",
        )
        write_catalog(
            self.source / "data" / "line_material_catalog.json",
            [record],
        )
        portable = self.source / "portable"
        portable.mkdir()
        for name in (
            "setup_second_pc.ps1",
            "doctor_second_pc.py",
            "README.md",
            "portable.env.example",
        ):
            (portable / name).write_text(name, encoding="utf-8")

        destination = self.root / "kit"
        tracked = (
            source_file,
            self.source / "data" / "line_material_catalog.json",
        )
        with patch("tools.export_usb_kit.tracked_source_files", return_value=tracked):
            result = build_usb_kit(
                destination,
                material_root=self.materials,
                source_root=self.source,
            )

        self.assertEqual(result, destination.resolve())
        self.assertTrue((destination / "source/app/sample.py").is_file())
        self.assertTrue((destination / "materials/行動力/001.jpg").is_file())
        checksums = (destination / "SHA256SUMS.txt").read_text(encoding="utf-8")
        self.assertIn("source/app/sample.py", checksums)
        self.assertIn("materials/", checksums)
        manifest = json.loads(
            (destination / "kit_manifest.json").read_text(encoding="utf-8")
        )
        self.assertFalse(manifest["credentials_included"])
        self.assertEqual(manifest["material_file_count"], 1)

    def test_refuses_to_merge_into_existing_destination(self):
        destination = self.root / "existing"
        destination.mkdir()

        with self.assertRaises(FileExistsError):
            build_usb_kit(
                destination,
                material_root=self.materials,
                source_root=self.source,
            )


if __name__ == "__main__":
    unittest.main()
