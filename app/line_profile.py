from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class LineProfile:
    customer_id: str
    line_contact: str
    line_message_style: str = ""
    source_row: int = 0


def parse_line_profiles(values: list[list[str]]) -> dict[str, LineProfile]:
    if len(values) < 2:
        return {}
    headers = [_canonical_header(cell) for cell in values[0]]
    profiles: dict[str, LineProfile] = {}
    for row_number, row in enumerate(values[1:], start=2):
        mapped = {
            headers[index]: str(value).strip()
            for index, value in enumerate(row)
            if index < len(headers) and headers[index]
        }
        customer_id = _first(mapped, "customer_id", "code")
        line_contact = _first(mapped, "line_contact")
        if not customer_id:
            continue
        profiles[customer_id] = LineProfile(
            customer_id=customer_id,
            line_contact=line_contact,
            line_message_style=_first(mapped, "line_message_style"),
            source_row=row_number,
        )
    return profiles


def apply_line_profile(
    *,
    customer_id: str,
    fallback_query: str,
    profiles: Mapping[str, LineProfile],
) -> tuple[str, str, str]:
    profile = profiles.get(customer_id)
    if profile is None or not profile.line_contact:
        return fallback_query, "", ""
    return profile.line_contact, profile.line_contact, profile.line_message_style


def is_line_contact_eligible(customer_id: str, line_contact: str) -> bool:
    return bool(customer_id.strip() and line_contact.strip())


def _canonical_header(value: str) -> str:
    text = str(value or "").strip().casefold()
    normalized = (
        text.replace(" ", "_")
        .replace("-", "_")
        .replace("/", "_")
        .replace("\ufeff", "")
    )
    aliases = {
        "customer_id": "customer_id",
        "customerid": "customer_id",
        "customer_code": "customer_id",
        "code": "code",
        "客戶代號": "customer_id",
        "客戶編號": "customer_id",
        "line_contact": "line_contact",
        "line暱稱": "line_contact",
        "line_暱稱": "line_contact",
        "line_nickname": "line_contact",
        "line名稱": "line_contact",
        "line_名稱": "line_contact",
        "line風格": "line_message_style",
        "line_風格": "line_message_style",
        "line_style": "line_message_style",
        "line_message_style": "line_message_style",
        "message_style": "line_message_style",
    }
    return aliases.get(normalized, normalized)


def _first(row: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = row.get(name, "").strip()
        if value:
            return value
    return ""
