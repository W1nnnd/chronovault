# Validation test cases

Linked from [SKILL.md](../SKILL.md). All company, person and number values below are fictional.

## Core case A: receipt photo with a derived warranty

- **Input**: a phone photo of a printed receipt from "Vantage Optics" dated 20 Nov 2024 that says "2-year limited warranty from date of purchase", serial VO-58213, placed in a receipts photo folder.
- **Expected**: Step 4 returns OCR text; the digest shows a derived warranty end of 2026-11-20 (21 days, Upcoming) with both quotes and the serial number.

## Core case B: contract renewal with a notice period

- **Input**: a PDF service agreement with "Lumora Cloud Ltd" that renews on 15 December 2026 and requires thirty days written notice, annual fee SGD 4,800.00.
- **Expected**: the action date is 2026-11-15 (16 days, Upcoming), not 2026-12-15; the evidence quote contains the renewal sentence. Step 5 must use the real extract result from Step 3 for that file.

## Edge case C: duplicates, unreadable and undated files

- **Input**: a second copy of a warranty PDF in another subfolder, a damaged PDF named locked_statement.pdf, and a scanned note with no date.
- **Expected**: the duplicate is processed once and listed under `duplicate_paths`; the damaged file appears in Needs Review with the reason returned by `document-agent`; the undated note appears in Needs Review with "no date found"; the rest of the batch completes.

## Incremental re-run

- **Input**: run again with `previous_digest` set to the digest saved in case A and B, with no file changes.
- **Expected**: every file is reported as unchanged by SHA-256 and no extraction is requested; the digest is rebuilt from the ledger.

## Pass criteria

1. Every reported date and amount has a verbatim evidence quote.
2. No original file has a changed SHA-256 or modification time after the run.
3. The only new file is the approved digest.
