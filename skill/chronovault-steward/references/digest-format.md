# Action Digest format

Linked from [SKILL.md](../SKILL.md). Used in Step 5 and Step 6.

## Filename

`ChronoVault_Action_Digest_YYYY-MM-DD.md` using `as_of_date`.

## Body

1. Title line with the as-of date.
2. One-line summary: files scanned, new, unchanged, obligations, Needs Review.
3. Sections in order: Overdue, Critical (0-7 days), Upcoming (8-30 days), Planned (31-90 days), Needs Review.
4. Each obligation line: action date, action label, counterparty, kind, notice period if any, days remaining, display path.
5. Under each obligation: the first evidence quote in quotation marks.
6. A Markdown ledger table of every processed file: path, type, counterparty, status, masked reference.
7. Footer: "Originals were not moved, renamed or edited. Account numbers are masked."

## Incremental ledger

Embed enough of the ledger (path, SHA-256, document type, counterparty, dates, amount, evidence) that the next run can skip unchanged SHA-256 values without re-extracting. Pass the real inventory from Step 1 and the real extract results from Steps 3 and 4 into this table; do not reconstruct them from memory.
