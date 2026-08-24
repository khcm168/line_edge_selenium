from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


FRIEND_CATEGORY_TERMS = ("friend", "friends", "好友", "朋友", "憟賢")
GROUP_CATEGORY_TERMS = ("group", "groups", "群組", "社群", "群")


@dataclass(frozen=True)
class LineCandidate:
    category: str
    display_name: str
    row_index: int
    element: Any = None

    @property
    def normalized_name(self) -> str:
        return normalize_name(self.display_name)

    @property
    def primary_normalized_name(self) -> str:
        first_line = (self.display_name or "").splitlines()[0] if self.display_name else ""
        return normalize_name(first_line)

    @property
    def kind(self) -> str:
        return classify_category(self.category)


@dataclass(frozen=True)
class MatchDecision:
    status: str
    policy: str
    query: str
    selected: LineCandidate | None
    candidates: tuple[LineCandidate, ...]
    detail: str

    @property
    def ok(self) -> bool:
        return self.status == "matched" and self.selected is not None


def normalize_name(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip().casefold()


def classify_category(category: str) -> str:
    normalized = normalize_name(category)
    if any(term.casefold() in normalized for term in GROUP_CATEGORY_TERMS):
        return "group"
    if any(term.casefold() in normalized for term in FRIEND_CATEGORY_TERMS):
        return "friend"
    return "unknown"


def apply_match_policy(
    *,
    query: str,
    candidates: Iterable[LineCandidate],
    policy: str,
    allow_group: bool = False,
    allowed_group_targets: Iterable[str] = (),
) -> MatchDecision:
    rows = tuple(candidates)
    query_norm = normalize_name(query)
    allowed_group_norms = {normalize_name(name) for name in allowed_group_targets}

    if policy == "manual_required":
        return MatchDecision(
            "manual_required",
            policy,
            query,
            None,
            rows,
            "manual selection required by policy",
        )

    if policy == "exact_friend":
        matches = [
            row
            for row in rows
            if row.kind == "friend" and row.primary_normalized_name == query_norm
        ]
    elif policy == "exact_group":
        matches = [
            row
            for row in rows
            if row.kind == "group" and row.primary_normalized_name == query_norm
        ]
    elif policy == "unique_contains_friend":
        matches = [
            row
            for row in rows
            if row.kind == "friend" and query_norm in row.normalized_name
        ]
    elif policy == "unique_contains_group":
        matches = [
            row
            for row in rows
            if row.kind == "group" and query_norm in row.normalized_name
        ]
    elif policy == "unique_contains_any":
        matches = [row for row in rows if query_norm in row.normalized_name]
    elif policy == "all_exact":
        matches = [row for row in rows if row.primary_normalized_name == query_norm]
    else:
        raise ValueError(f"Unsupported match policy: {policy}")

    if not matches:
        return MatchDecision("no_match", policy, query, None, rows, "no matching row")
    if len(matches) > 1 and policy != "all_exact":
        names = ", ".join(
            f"{row.row_index}:{row.display_name}" for row in matches[:5]
        )
        suffix = "..." if len(matches) > 5 else ""
        return MatchDecision(
            "ambiguous",
            policy,
            query,
            None,
            rows,
            f"{len(matches)} candidates matched: {names}{suffix}",
        )

    selected = matches[0]
    if selected.kind == "group":
        group_allowed = (
            allow_group
            and selected.primary_normalized_name in allowed_group_norms
        )
        if not group_allowed:
            return MatchDecision(
                "blocked_group",
                policy,
                query,
                None,
                rows,
                "group match requires task permission and configured allowlist",
            )

    return MatchDecision("matched", policy, query, selected, rows, "matched exactly one row")
