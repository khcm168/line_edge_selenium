from __future__ import annotations

import argparse

from app.config import Settings
from app.response_loop import RESPONSE_CLASSES, record_screenshot_intake


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Record screenshot-backed LINE response evidence."
    )
    parser.add_argument("--draft-id", default="")
    parser.add_argument("--message-id", default="")
    parser.add_argument("--screenshot", required=True)
    parser.add_argument("--response-text", default="")
    parser.add_argument("--response-class", choices=RESPONSE_CLASSES, default="")
    parser.add_argument("--result", required=True)
    parser.add_argument("--next-action", required=True)
    parser.add_argument("--reviewer", required=True)
    args = parser.parse_args(argv)

    settings = Settings.from_env()
    intake = record_screenshot_intake(
        settings.response_dir / "response_intake.jsonl",
        draft_id=args.draft_id,
        message_id=args.message_id,
        screenshot_path=args.screenshot,
        response_text=args.response_text,
        response_class=args.response_class,
        result=args.result,
        next_action=args.next_action,
        reviewer=args.reviewer,
    )
    print(f"intake_id={intake.intake_id}")
    print(f"response_class={intake.response_class}")
    print(f"screenshot_sha256={intake.screenshot_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
