import json
import unittest
from pathlib import Path
from uuid import uuid4

from app.material_catalog import (
    load_catalog,
    resolve_material_path,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "data" / "line_material_catalog.json"


class MaterialCatalogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load_catalog(CATALOG_PATH)
        cls.by_id = cls.catalog.by_id()

    def test_catalog_has_all_legacy_slides(self):
        self.assertGreaterEqual(len(self.catalog.records), 195)
        self.assertEqual(self.catalog.records[0].filename, "投影片1.JPG")
        self.assertEqual(self.by_id["MAT-ACT-195"].filename, "投影片195.JPG")
        self.assertTrue(all(record.customer_caption for record in self.catalog.records))
        self.assertTrue(all(record.internal_comment for record in self.catalog.records))
        self.assertTrue(all(record.visual_summary for record in self.catalog.records))

    def test_known_exact_duplicates_point_to_canonical_material(self):
        expected = {
            "MAT-ACT-039": "MAT-ACT-011",
            "MAT-ACT-081": "MAT-ACT-011",
            "MAT-ACT-092": "MAT-ACT-011",
            "MAT-ACT-121": "MAT-ACT-107",
            "MAT-ACT-122": "MAT-ACT-109",
            "MAT-ACT-134": "MAT-ACT-129",
            "MAT-ACT-186": "MAT-ACT-161",
        }
        self.assertEqual(
            {material_id: self.by_id[material_id].duplicate_of for material_id in expected},
            expected,
        )

    def test_blocked_materials_are_not_live_eligible(self):
        self.assertFalse(self.by_id["MAT-ACT-002"].is_live_eligible)
        self.assertFalse(self.by_id["MAT-ACT-018"].is_live_eligible)
        self.assertFalse(self.by_id["MAT-ACT-020"].is_live_eligible)
        self.assertFalse(self.by_id["MAT-ACT-003"].is_live_eligible)
        self.assertFalse(self.by_id["MAT-ACT-005"].is_live_eligible)

    def test_manually_reviewed_acceptance_material_is_live_eligible(self):
        record = self.by_id["MAT-ACT-006"]

        self.assertTrue(record.is_live_eligible)
        self.assertEqual(record.test_result, "manual_visual_review_2026-06-13")

    def test_supervised_sleep_material_is_live_eligible(self):
        record = self.by_id["MAT-ACT-021"]

        self.assertTrue(record.is_live_eligible)
        self.assertEqual(
            record.test_result,
            "operator_approved_supervised_send_2026-06-14",
        )

    def test_supervised_product_batch_materials_are_live_eligible(self):
        for material_id in ("MAT-ACT-077", "MAT-ACT-082", "MAT-ACT-152"):
            with self.subTest(material_id=material_id):
                record = self.by_id[material_id]
                self.assertTrue(record.is_live_eligible)
                self.assertEqual(
                    record.test_result,
                    "operator_approved_supervised_batch_2026-06-14",
                )

    def test_resolve_material_detects_missing_file(self):
        temp_dir = self._temp_dir()
        try:
            with self.assertRaises(FileNotFoundError):
                resolve_material_path(
                    self.by_id["MAT-ACT-003"],
                    material_root=temp_dir,
                )
        finally:
            temp_dir.rmdir()

    def test_resolve_material_detects_hash_change(self):
        temp_dir = self._temp_dir()
        target = temp_dir / self.by_id["MAT-ACT-003"].filename
        try:
            target.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                resolve_material_path(
                    self.by_id["MAT-ACT-003"],
                    material_root=temp_dir,
                )
        finally:
            if target.exists():
                target.unlink()
            temp_dir.rmdir()

    def test_resolve_material_can_find_sibling_library_folder(self):
        temp_dir = self._temp_dir()
        legacy_root = temp_dir / "行動力"
        sibling = temp_dir / "高血壓"
        legacy_root.mkdir()
        sibling.mkdir()
        target = sibling / "圖1.jpg"
        target.write_bytes(b"picture")
        record = self.by_id["MAT-ACT-003"]
        sibling_record = type(record)(
            **{
                **record.__dict__,
                "filename": "高血壓/圖1.jpg",
                "sha256": sha256_file(target),
            }
        )
        try:
            self.assertEqual(
                resolve_material_path(sibling_record, material_root=legacy_root),
                target.resolve(),
            )
        finally:
            target.unlink()
            sibling.rmdir()
            legacy_root.rmdir()
            temp_dir.rmdir()

    def test_resolve_material_can_find_recursive_hash_match(self):
        temp_dir = self._temp_dir()
        nested = temp_dir / "nested"
        nested.mkdir()
        target = nested / "投影片6.JPG"
        target.write_bytes(b"correct-picture")
        record = self.by_id["MAT-ACT-006"]
        nested_record = type(record)(
            **{
                **record.__dict__,
                "filename": "投影片6.JPG",
                "sha256": sha256_file(target),
            }
        )
        try:
            self.assertEqual(
                resolve_material_path(nested_record, material_root=temp_dir),
                target.resolve(),
            )
        finally:
            target.unlink()
            nested.rmdir()
            temp_dir.rmdir()

    def test_resolve_material_prefers_recursive_hash_match_over_wrong_root_basename(self):
        temp_dir = self._temp_dir()
        wrong = temp_dir / "投影片6.JPG"
        wrong.write_bytes(b"wrong-picture")
        nested = temp_dir / "nested"
        nested.mkdir()
        target = nested / "投影片6.JPG"
        target.write_bytes(b"correct-picture")
        record = self.by_id["MAT-ACT-006"]
        nested_record = type(record)(
            **{
                **record.__dict__,
                "filename": "投影片6.JPG",
                "sha256": sha256_file(target),
            }
        )
        try:
            self.assertEqual(
                resolve_material_path(nested_record, material_root=temp_dir),
                target.resolve(),
            )
        finally:
            wrong.unlink()
            target.unlink()
            nested.rmdir()
            temp_dir.rmdir()

    def test_catalog_json_has_no_absolute_paths(self):
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("C:\\\\", serialized)
        self.assertNotIn("C:/", serialized)

    def test_sha256_helper(self):
        temp_dir = self._temp_dir()
        path = temp_dir / "x.jpg"
        try:
            path.write_bytes(b"abc")
            self.assertEqual(
                sha256_file(path),
                "ba7816bf8f01cfea414140de5dae2223"
                "b00361a396177a9cb410ff61f20015ad",
            )
        finally:
            if path.exists():
                path.unlink()
            temp_dir.rmdir()

    def _temp_dir(self) -> Path:
        target = ROOT / "data" / "test_tmp" / uuid4().hex
        target.mkdir(parents=True)
        return target


if __name__ == "__main__":
    unittest.main()
