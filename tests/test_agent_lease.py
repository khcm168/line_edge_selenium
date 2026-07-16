import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.agent_lease import (
    LeaseExpectation,
    LeaseValidationError,
    lease_filename,
    lease_path,
    read_lease,
    require_line_delivery_leases,
    validate_lease,
    write_lease,
)


class AgentLeaseTest(unittest.TestCase):
    def setUp(self):
        self.root = Path("data") / "test_tmp" / uuid4().hex
        self.root.mkdir(parents=True)
        self.now = datetime(2026, 7, 15, 0, 0, tzinfo=timezone.utc)

    def tearDown(self):
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.root.rmdir()

    def lease(self, **overrides):
        base = {
            "lock_key": "delivery:line:hqming",
            "owner_project": "line_edge_selenium",
            "owner_agent": "delivery",
            "run_id": "nightly-health-2026-07-15",
            "host": "Z13",
            "pid": 22164,
            "started_at": "2026-07-15T00:00:00+00:00",
            "expires_at": "2026-07-15T00:10:00+00:00",
            "scope": "message_delivery",
            "reentrant": False,
            "status": "held",
        }
        base.update(overrides)
        return base

    def test_validates_expected_delivery_lease(self):
        lease = self.lease()

        parsed = validate_lease(
            lease,
            expectation=LeaseExpectation(
                lock_key="delivery:line:hqming",
                owner_project="line_edge_selenium",
                owner_agent="delivery",
                scope="message_delivery",
            ),
            now=self.now,
        )

        self.assertEqual(parsed["lock_key"], "delivery:line:hqming")

    def test_rejects_expired_held_lease(self):
        with self.assertRaisesRegex(LeaseValidationError, "expired"):
            validate_lease(
                self.lease(started_at="2026-07-14T23:50:00+00:00", expires_at="2026-07-14T23:59:00+00:00"),
                expectation=LeaseExpectation(lock_key="delivery:line:hqming"),
                now=self.now,
            )

    def test_rejects_wrong_owner_for_delivery(self):
        with self.assertRaisesRegex(LeaseValidationError, "owner_project"):
            validate_lease(
                self.lease(owner_project="ARM"),
                expectation=LeaseExpectation(
                    lock_key="delivery:line:hqming",
                    owner_project="line_edge_selenium",
                ),
                now=self.now,
            )

    def test_lease_filename_is_filesystem_safe(self):
        self.assertEqual(lease_filename("delivery:line:hqming"), "delivery_line_hqming.json")

    def test_write_and_read_lease(self):
        path = lease_path(self.root, "delivery:line:hqming")
        write_lease(path, self.lease())

        parsed = read_lease(path)

        self.assertEqual(parsed["run_id"], "nightly-health-2026-07-15")

    def test_requires_both_line_delivery_leases(self):
        write_lease(
            lease_path(self.root, "browser:line-primary"),
            self.lease(
                lock_key="browser:line-primary",
                owner_agent="arbiter",
                scope="browser",
            ),
        )
        write_lease(lease_path(self.root, "delivery:line:hqming"), self.lease())

        leases = require_line_delivery_leases(self.root, now=self.now)

        self.assertEqual([lease["lock_key"] for lease in leases], ["browser:line-primary", "delivery:line:hqming"])


if __name__ == "__main__":
    unittest.main()

