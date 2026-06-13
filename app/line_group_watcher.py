from __future__ import annotations

import argparse
from typing import Any

from app.audit import SnapshotWriter
from app.config import Settings
from app.line_client import LineClient
from app.line_messaging import open_chat, resolve_match
from app.response_loop import (
    ObservationLedger,
    ObservedMessage,
    classify_response,
    response_draft_from_observation,
)
from app.sheet_gateway import SheetGateway


def observe_recent_messages(
    driver: Any,
    *,
    group_name: str,
    limit: int = 10,
) -> tuple[ObservedMessage, ...]:
    raw = driver.execute_script(
        """
        const selectors = [
          '[data-message-id]',
          '[class*="message"]',
          '[class*="chatItem"]',
          '[role="listitem"]'
        ];
        const visible = (el) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden'
            && rect.width > 0 && rect.height > 0;
        };
        const seen = new Set();
        const rows = [];
        for (const selector of selectors) {
          for (const el of document.querySelectorAll(selector)) {
            if (!visible(el) || seen.has(el)) continue;
            seen.add(el);
            const text = (el.innerText || '').trim();
            if (!text || text.length > 2000) continue;
            const authorEl = el.querySelector(
              '[class*="author"], [class*="name"], [data-author]'
            );
            const timeEl = el.querySelector('time, [class*="time"]');
            rows.push({
              messageId: el.getAttribute('data-message-id') || el.id || '',
              author: authorEl ? (authorEl.innerText || '').trim() : '',
              text,
              observedAt: timeEl
                ? (timeEl.getAttribute('datetime') || timeEl.innerText || '').trim()
                : ''
            });
          }
        }
        return rows.slice(-arguments[0]);
        """,
        limit,
    )
    return tuple(
        ObservedMessage(
            group_name=group_name,
            author=str(item.get("author") or ""),
            text=str(item.get("text") or ""),
            observed_at=str(item.get("observedAt") or ""),
            message_id=str(item.get("messageId") or ""),
        )
        for item in (raw or [])
    )


def run_once(
    *,
    client: LineClient,
    gateway: SheetGateway,
    settings: Settings,
    max_messages: int = 5,
) -> int:
    if not settings.response_watcher_enabled:
        raise RuntimeError(
            "LINE response watcher is disabled. Set "
            "LINE_RESPONSE_WATCHER_ENABLED=true to run it."
        )
    if not settings.response_watch_groups:
        raise RuntimeError("LINE_RESPONSE_WATCH_GROUPS has no allowlisted groups")

    ledger = ObservationLedger(settings.response_dir / "watcher_observations.jsonl")
    snapshots = SnapshotWriter(settings.snapshot_dir / "watcher")
    written = 0
    for group_name in settings.response_watch_groups:
        decision = resolve_match(
            client.driver,
            query=group_name,
            policy="unique_contains_group",
            allow_group=True,
            allowed_group_targets=settings.response_watch_groups,
        )
        if not decision.ok:
            continue
        open_chat(client.driver, decision)
        observations = observe_recent_messages(
            client.driver,
            group_name=group_name,
            limit=max_messages,
        )
        unseen = ledger.unseen(
            observations,
            allowed_groups=settings.response_watch_groups,
        )
        for observation in unseen:
            response_class = classify_response(observation.text)
            draft = response_draft_from_observation(
                observation,
                response_class=response_class,
            )
            evidence = snapshots.write(
                label=f"watch_{group_name}_{observation.observation_hash[:10]}",
                payload={
                    "observation": observation,
                    "observation_hash": observation.observation_hash,
                    "response_class": response_class,
                    "note": "Draft-only watcher. No reply was sent.",
                },
                driver=client.driver,
            )
            appended = gateway.append_drafts([draft])
            ledger.record(
                observation,
                evidence_snapshot=evidence,
                response_class=response_class,
                draft_id=draft.draft_id,
            )
            written += appended
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Allowlisted LINE group watcher that creates drafts only."
    )
    parser.add_argument("--attach-existing", action="store_true")
    parser.add_argument("--max-messages", type=int, default=5)
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args(argv)

    settings = Settings.from_env(require_google=True)
    client = (
        LineClient.attach_existing()
        if args.attach_existing
        else LineClient.open()
    )
    try:
        client.driver.maximize_window()
        client.ensure_friends()
        gateway = SheetGateway.from_settings(settings)
        written = run_once(
            client=client,
            gateway=gateway,
            settings=settings,
            max_messages=args.max_messages,
        )
    finally:
        if not args.keep_open:
            client.close()
    print(f"response_drafts_written={written}")
    print("auto_reply=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
