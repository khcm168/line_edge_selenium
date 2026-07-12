from __future__ import annotations


def is_bmp_safe(text: str) -> bool:
    return all(ord(character) <= 0xFFFF for character in text)


def sanitize_bmp_text(text: str) -> str:
    return "".join(character for character in text if ord(character) <= 0xFFFF)


def non_bmp_codepoints(text: str) -> tuple[str, ...]:
    return tuple(f"U+{ord(character):X}" for character in text if ord(character) > 0xFFFF)
