from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from scripts.check_arm_webapp_compatibility import check_compatibility


class ArmWebAppCompatibilityTests(unittest.TestCase):
    def test_matching_shared_spreadsheet_and_contract_pass(self) -> None:
        environment = {
            "ARM_WEBAPP_CANDIDATE_URL": "https://candidate.example/exec",
            "ARM_WEBAPP_EXPECTED_SPREADSHEET_ID": "sheet-1",
            "ARM_WEBAPP_EXPECTED_CONTRACT": "ARM Shared WebApp API",
            "ARM_WEBAPP_EXPECTED_CONTRACT_VERSION": "2.0.0",
            "ARM_WEBAPP_EXPECTED_RELEASE_VERSION": "37",
        }
        health = {
            "ok": True,
            "contract": "ARM Shared WebApp API",
            "contractVersion": "2.0.0",
            "releaseVersion": 37,
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            result = check_compatibility(
                settings=SimpleNamespace(
                    project_name="line_edge_selenium",
                    source_spreadsheet_id="sheet-1",
                ),
                health_fetcher=lambda _url: health,
            )
        self.assertTrue(result["ok"])
        self.assertEqual(result["role"], "shared-spreadsheet observer")

    def test_different_spreadsheet_is_rejected_before_network(self) -> None:
        environment = {
            "ARM_WEBAPP_CANDIDATE_URL": "https://candidate.example/exec",
            "ARM_WEBAPP_EXPECTED_SPREADSHEET_ID": "sheet-1",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            with self.assertRaisesRegex(RuntimeError, "targets another spreadsheet"):
                check_compatibility(
                    settings=SimpleNamespace(
                        project_name="line_edge_selenium",
                        source_spreadsheet_id="sheet-2",
                    ),
                    health_fetcher=lambda _url: self.fail("network should not be called"),
                )


if __name__ == "__main__":
    unittest.main()
