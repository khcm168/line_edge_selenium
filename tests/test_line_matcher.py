import unittest

from app.line_matcher import LineCandidate, apply_match_policy


class LineMatcherTest(unittest.TestCase):
    def test_exact_friend_match(self):
        decision = apply_match_policy(
            query="洪啓明",
            policy="exact_friend",
            candidates=[
                LineCandidate(category="好友", display_name="洪啓明", row_index=0),
                LineCandidate(category="群組", display_name="001N1備份區", row_index=1),
            ],
        )

        self.assertTrue(decision.ok)
        self.assertEqual(decision.selected.display_name, "洪啓明")

    def test_exact_group_requires_allowance(self):
        blocked = apply_match_policy(
            query="001N1備份區",
            policy="exact_group",
            candidates=[LineCandidate(category="群組", display_name="001N1備份區\n(2)", row_index=0)],
        )
        allowed = apply_match_policy(
            query="001N1備份區",
            policy="exact_group",
            candidates=[LineCandidate(category="群組", display_name="001N1備份區\n(2)", row_index=0)],
            allow_group=True,
            allowed_group_targets=("001N1備份區",),
        )

        self.assertEqual(blocked.status, "blocked_group")
        self.assertTrue(allowed.ok)

    def test_ambiguous_contains_is_skipped(self):
        decision = apply_match_policy(
            query="P104062",
            policy="unique_contains_friend",
            candidates=[
                LineCandidate(category="好友", display_name="雅涵媽，賢 生泉 P104062", row_index=0),
                LineCandidate(category="好友", display_name="另一位 P104062", row_index=1),
            ],
        )

        self.assertEqual(decision.status, "ambiguous")
        self.assertFalse(decision.ok)

    def test_unique_contains_group_accepts_count_suffix(self):
        decision = apply_match_policy(
            query="001N1備份區",
            policy="unique_contains_group",
            candidates=[
                LineCandidate(category="群組", display_name="001N1備份區\n(2)", row_index=0)
            ],
            allow_group=True,
            allowed_group_targets=("001N1備份區",),
        )

        self.assertTrue(decision.ok)
        self.assertEqual(decision.selected.primary_normalized_name, "001n1備份區")

    def test_group_task_permission_cannot_bypass_allowlist(self):
        decision = apply_match_policy(
            query="100分的自己",
            policy="exact_group",
            candidates=[
                LineCandidate(
                    category="群組",
                    display_name="100分的自己\n(8)",
                    row_index=0,
                )
            ],
            allow_group=True,
            allowed_group_targets=("001N1備份區",),
        )

        self.assertEqual(decision.status, "blocked_group")

    def test_allowlisted_group_still_requires_task_permission(self):
        decision = apply_match_policy(
            query="100分的自己",
            policy="exact_group",
            candidates=[
                LineCandidate(
                    category="群組",
                    display_name="100分的自己\n(8)",
                    row_index=0,
                )
            ],
            allowed_group_targets=("100分的自己",),
        )

        self.assertEqual(decision.status, "blocked_group")

    def test_duplicate_exact_group_rows_are_ambiguous(self):
        decision = apply_match_policy(
            query="100分的自己",
            policy="exact_group",
            candidates=[
                LineCandidate("群組", "100分的自己\n(8)", 0),
                LineCandidate("群組", "100分的自己\n(3)", 1),
            ],
            allow_group=True,
            allowed_group_targets=("100分的自己",),
        )

        self.assertEqual(decision.status, "ambiguous")

    def test_no_match(self):
        decision = apply_match_policy(
            query="Ya.ping",
            policy="exact_friend",
            candidates=[LineCandidate(category="好友", display_name="洪啓明", row_index=0)],
        )

        self.assertEqual(decision.status, "no_match")


if __name__ == "__main__":
    unittest.main()
