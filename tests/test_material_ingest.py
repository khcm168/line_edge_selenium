import unittest
from pathlib import Path
from uuid import uuid4

from app.material_catalog import MaterialCatalog, MaterialRecord, load_catalog, write_catalog
from app.material_ingest import (
    _build_cycle_notice,
    build_pending_record,
    discover_new_images,
    ingest_once,
)
from app.material_vision import VisionAnalysis


def analysis():
    return VisionAnalysis(
        visual_summary="血壓衛教圖",
        visible_text="高血壓",
        topic="血壓管理",
        audience="一般成人",
        tags=("高血壓", "血壓管理"),
        risk_level="medium",
        safety_flags=("medical_overclaim_risk",),
        risk_reasons=("含療效敘述",),
        neutral_caption="分享一張血壓管理參考圖，內容請依專業說明判讀。",
    )


class MaterialIngestTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.materials = self.root / "Material"
        self.folder = self.materials / "高血壓"
        self.folder.mkdir(parents=True)
        self.catalog_path = self.root / "catalog.json"
        self.pending_catalog_path = self.root / "material_ingest" / "pending_catalog.json"
        write_catalog(self.catalog_path, [])

    def tearDown(self):
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.root.rmdir()

    def test_discovers_relative_path_and_skips_known_hash(self):
        image = self.folder / "圖1.jpg"
        image.write_bytes(b"new-image")
        catalog = load_catalog(self.catalog_path)

        found = discover_new_images(
            self.materials,
            catalog,
            min_age_seconds=0,
        )
        self.assertEqual(found[0][1], "高血壓/圖1.jpg")

        record = build_pending_record(
            relative_path=found[0][1],
            digest=found[0][2],
            analysis=analysis(),
            model="gemma3:12b",
        )
        write_catalog(self.catalog_path, [record])
        self.assertEqual(
            discover_new_images(
                self.materials,
                load_catalog(self.catalog_path),
                min_age_seconds=0,
            ),
            (),
        )

    def test_discovers_only_one_path_for_duplicate_hashes(self):
        first = self.folder / "圖1.jpg"
        second = self.folder / "圖1複本.jpg"
        first.write_bytes(b"same-image")
        second.write_bytes(b"same-image")

        found = discover_new_images(
            self.materials,
            load_catalog(self.catalog_path),
            min_age_seconds=0,
        )

        self.assertEqual(len(found), 1)

    def test_import_is_always_pending_and_internal_only(self):
        image = self.folder / "圖1.jpg"
        image.write_bytes(b"new-image")

        imported, failed = ingest_once(
            material_root=self.materials,
            catalog_path=self.catalog_path,
            pending_catalog_path=self.pending_catalog_path,
            folder="",
            model="gemma3:12b",
            base_url="http://unused",
            timeout_seconds=1,
            num_gpu=0,
            num_thread=4,
            max_files=1,
            min_age_seconds=0,
            analyzer=lambda *args, **kwargs: analysis(),
        )

        self.assertEqual((imported, failed), (1, 0))
        record = load_catalog(self.catalog_path).records[0]
        self.assertEqual(record.review_status, "pending_review")
        self.assertEqual(record.sendability, "internal_only")
        self.assertFalse(record.is_live_eligible)
        self.assertIn("ai_vision_generated", record.safety_flags)
        self.assertEqual(record.tags, ("高血壓", "血壓管理"))

    def test_prescription_folder_forces_high_risk(self):
        record = build_pending_record(
            relative_path="處方藥/藥品資料.jpg",
            digest="a" * 64,
            analysis=analysis(),
            model="gemma3:12b",
        )

        self.assertEqual(record.risk_level, "high")
        self.assertIn("prescription_drug_content", record.safety_flags)
        self.assertFalse(record.is_live_eligible)

    def test_cycle_notice_exposes_latest_completed_picture(self):
        notice = _build_cycle_notice(
            imported=1,
            failed=0,
            completed_at="2026-06-15T06:30:00+00:00",
            latest_event={
                "path": "高血壓/圖1.jpg",
                "material_id": "MAT-AUTO-ABC123",
            },
        )

        self.assertEqual(notice["result"], "success")
        self.assertEqual(notice["path"], "高血壓/圖1.jpg")
        self.assertEqual(notice["material_id"], "MAT-AUTO-ABC123")

    def test_failed_image_is_quarantined_so_next_image_can_continue(self):
        first = self.folder / "01失敗.jpg"
        second = self.folder / "02成功.jpg"
        first.write_bytes(b"bad-image")
        second.write_bytes(b"good-image")
        failed_path = self.root / "material_ingest" / "failed_images.json"

        imported, failed = ingest_once(
            material_root=self.materials,
            catalog_path=self.catalog_path,
            pending_catalog_path=self.pending_catalog_path,
            folder="",
            model="gemma3:12b",
            base_url="http://unused",
            timeout_seconds=1,
            num_gpu=0,
            num_thread=4,
            max_files=1,
            min_age_seconds=0,
            analyzer=lambda *args, **kwargs: (_ for _ in ()).throw(
                ValueError("invalid JSON")
            ),
            failed_registry_path=failed_path,
        )
        self.assertEqual((imported, failed), (0, 1))

        imported, failed = ingest_once(
            material_root=self.materials,
            catalog_path=self.catalog_path,
            pending_catalog_path=self.pending_catalog_path,
            folder="",
            model="gemma3:12b",
            base_url="http://unused",
            timeout_seconds=1,
            num_gpu=0,
            num_thread=4,
            max_files=1,
            min_age_seconds=0,
            analyzer=lambda *args, **kwargs: analysis(),
            failed_registry_path=failed_path,
        )

        self.assertEqual((imported, failed), (1, 0))
        pending = load_catalog(
            self.pending_catalog_path,
            include_pending=False,
        )
        self.assertEqual(pending.records[0].filename, "高血壓/02成功.jpg")


if __name__ == "__main__":
    unittest.main()
