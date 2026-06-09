# LINE_Drafts June 7 Duplicate Cleanup Plan

## Scope

Clean only duplicated `LINE_Drafts` rows that match all of these conditions:

- `Created_At` is on `2026-06-07` Taipei time.
- `Status` is `pending_review`.
- `Draft_ID` appears more than once in the matching row set.

Do not delete or edit rows with `Status` of `approved`, `sent`, `rejected`, or `error`.

## Backup First

1. Duplicate the `LINE_Drafts` worksheet to a temporary tab named `LINE_Drafts_backup_2026-06-07_dedupe`.
2. Confirm the backup row count matches the original `LINE_Drafts` row count.
3. Freeze any scheduled draft-builder run until cleanup is complete, or run only after the idempotent writer fix is deployed.

## Identify Duplicates

1. Filter `LINE_Drafts` to `Created_At` beginning with `2026-06-07` and `Status=pending_review`.
2. Group the filtered rows by `Draft_ID`.
3. For each group where count is greater than 1, choose the keeper row:
   - Prefer a row with nonblank `Draft_Message`.
   - If messages differ, keep the row with the most complete review fields.
   - If rows are equivalent, keep the earliest sheet row number.

## Delete Safely

1. Build a deletion list containing only the non-keeper row numbers from duplicate groups.
2. Sort row numbers descending before deletion so row shifts do not invalidate later deletes.
3. Delete only those duplicate pending-review rows.
4. Record the deleted row numbers, kept row numbers, and `Draft_ID` values in the cleanup note or audit log.

## Verify

1. Recount duplicate groups for `2026-06-07` + `pending_review`; expected duplicate count is zero.
2. Confirm approved/sent/rejected/error rows still have the same row data as the backup.
3. Rerun the draft builder once for `2026-06-07`; expected result is `draft_count=0` for already-present drafts.
4. Re-enable the scheduled workday run after the verification pass.
