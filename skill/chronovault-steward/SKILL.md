---
name: chronovault-steward
description: Local-first deadline steward for contracts, invoices, receipts, warranty cards and subscription notices kept on a UGREEN AI NAS. Produces a ranked Action Digest of renewal notice windows, warranty expiries, payment due dates and tax dates, each backed by a verbatim quote from the source file. Use when the user says things like "what is about to expire or renew", "find my warranties and contract renewal dates", "which bills are due this month", or "check my documents folder for deadlines".
---

# Goal

Turn the user's own NAS document folders into a deadline ledger and a prioritized Action Digest, without uploading anything to the cloud and without changing any original file.

The user-visible result is:

1. An **Action Digest** that lists every obligation found, ranked by the real action date (for example "send cancellation notice by 2026-11-15" rather than only "renews on 2026-12-15"), grouped into Critical (0 to 7 days), Upcoming (8 to 30 days), Planned (31 to 90 days) and Needs Review.
2. A **ledger** of each processed file (path, SHA-256, document type, counterparty, dates, amount, verbatim evidence) embedded in the digest, so the next run only processes new or changed files.
3. Optional, only after the user opts in and approves: NAS file tags such as `ChronoVault-Due-30d` on the original files, so they can be filtered in the UGOS file manager.

Supported scope: PDF, Office and text documents, email exports, and photos or scans of receipts and warranty cards that are stored in folders the user explicitly authorizes. Handwritten notes, password-protected files and documents in folders the user did not name are out of scope and are reported, never guessed.

Detailed rules live in these linked references:

- [Extraction fields and deadline rules](references/extraction-and-deadline-rules.md)
- [Action Digest format](references/digest-format.md)
- [Privacy and approval](references/privacy-and-approval.md)
- [Validation test cases](references/validation-test-cases.md)

# Required input

Collect these before Step 1. Ask only for what is missing. Do not invent folder paths.

| Input | Meaning | Default / notes |
| :--- | :--- | :--- |
| `authorized_folders` | Absolute NAS paths the user names for this run | Required. Never scan outside this list. |
| `as_of_date` | Reference date for "days remaining" | Today on the NAS clock |
| `horizon_days` | How far ahead to highlight | 90 |
| `digest_folder` | Folder where the approved Markdown digest will be saved | Ask the user |
| `previous_digest` | Path of the last digest (for incremental runs) | Optional |
| `apply_tags` | Whether to add `ChronoVault-Due-30d` tags after approval | false unless the user opts in |

# Generation-time capability evidence

- `ug-filesystem` → `file-agent`
- `ug-filemgr` → `file-agent`
- `ug-document` → `document-agent`
- `ug-photo` → `photo-agent`
- `ug-knowledge` → `knowledge-agent`

# Workflow

Each step consumes only the real structured result returned by the previous delegation (inventory rows, extract records, OCR text, saved path). Do not restate, invent or substitute those results.

## Step 1 — Inventory (read-only)

Confirm `authorized_folders` with the user. Then:

`delegate --target file-agent --instruction 'In each authorized folder, use ug-filesystem find, ls, stat and sha256sum to list every PDF, Office, text, email (.eml) and image file with its absolute path, size, mtime and SHA-256. Then use ug-filemgr scan-dedupe on the same set and return duplicate groups. Do not move, rename, delete or edit any file. Return a structured inventory.'`

If `previous_digest` is set, read its embedded ledger and mark files whose SHA-256 is unchanged so later steps can skip them.

## Step 2 — Read the previous digest (optional)

If `previous_digest` was provided, open it (read-only) and load the ledger table of path, SHA-256, document type, counterparty, dates, amount and evidence. Carry forward unchanged rows. Only new or changed SHA-256 values continue to Step 3 and Step 4.

## Step 3 — Extract document fields

For each new or changed document file (PDF, Office, text, email):

`delegate --target document-agent --instruction 'For each listed document path, use ug-document extract with the schema that best matches the file (contract, invoice or receipt). Return doc_type, counterparty, document_date, obligations (kind, obligation_date, notice_days), amount, currency, reference_id, and a verbatim evidence quote for every date and amount. If a file is damaged, encrypted or has no readable text, return an error reason for that file and continue with the others. Do not invent dates.'`

Apply the deadline rules in [extraction-and-deadline-rules.md](references/extraction-and-deadline-rules.md). Action date = obligation date minus notice period when a notice period exists.

## Step 4 — Vision OCR for receipt and warranty photos

For each new or changed image in the authorized folders:

`delegate --target photo-agent --instruction 'For each listed image path, use ug-photo vision-ocr and return the OCR text with a confidence score. Prefer printed receipts and warranty cards. If the image is blank, too blurry or handwritten with no readable date, say so and do not guess.'`

Run the same field and deadline rules on the OCR text. Derived warranties (purchase date plus N years) must include both quotes and be marked derived.

## Step 5 — Rank and build the digest

Merge Steps 2 to 4. Deduplicate by SHA-256 (keep the shallowest path as primary; list other paths as duplicates). Compute days remaining from `as_of_date`. Group into Critical (0 to 7 days, plus overdue), Upcoming (8 to 30), Planned (31 to 90) and Needs Review (low confidence, damaged, undated, or missing evidence). Format the Markdown digest as specified in [digest-format.md](references/digest-format.md). Mask account and long policy numbers to the last four characters. Show the digest in chat first. Do not save yet.

## Step 6 — Save the digest (approval required)

Ask the user to approve saving one new Markdown file into `digest_folder`. On approval:

`delegate --target knowledge-agent --instruction 'Use ug-knowledge save-text to write the approved Action Digest Markdown (including the embedded ledger table) into the user-specified digest folder with the agreed file name. Do not overwrite an existing digest unless the user explicitly asked to replace it. Return the saved path.'`

If approval is denied, keep the chat digest and do not retry the write.

## Step 7 — Optional tags (opt-in and approval)

Only if `apply_tags` is true. Propose tags such as `ChronoVault-Due-30d` for items whose action date falls within 30 days. On approval:

`delegate --target file-agent --instruction 'Using ug-filemgr tag-get-by-name, confirm each proposed tag exists. Then use ug-filemgr tag-add-file with exactly that name and add it to the listed file paths only. If a named tag does not exist, report it and do not create it without user approval. Do not move, rename or modify the files themselves. Return each path with the tag result.'`

# Completion and failure

Handle every delegation state explicitly and report states as states, never as success:

- `completed`: use only the returned data. Report counts (files found, new, unchanged, duplicates, obligations, Needs Review) and the saved digest path when Step 6 completed.
- `failed`: report which step failed and why. If Step 1 fails, stop the workflow. If Step 3 or Step 4 fails, keep the results from the other step, mark the affected files as Needs Review, and say the digest is partial.
- `cancelled`: stop dependent steps, keep any digest already shown in chat, and state that nothing was saved or tagged after the cancellation.
- `waiting_user`: ask the one missing question (for example which folders to scan or where to save) and resume only after the answer.
- `waiting_approval`: explain what will change (one new digest file, or tags on the listed files) and wait. If approval is denied, keep the chat digest and do not retry the write.

Empty and partial results: if a folder has no results, say so for that folder; if extraction returns no obligations, report "no deadlines found in N files" instead of inferring dates. A digest built from partial results is labelled partial with the list of files not processed.

The Skill is finished when the user has seen the Action Digest and, if they approved it, the digest file is saved and any approved tags are applied. Original files are never moved, renamed, edited or deleted at any step.

# Disclosures

- **Third-party components in this package:** none. The package is original Markdown only (SKILL.md plus the four linked references). It contains no third-party code, libraries, data, credentials or external service calls.
- **Platform capabilities used:** UGOS CLI capabilities `ug-filesystem`, `ug-filemgr`, `ug-document`, `ug-photo` and `ug-knowledge`, reached only through the registered expert agents `file-agent`, `document-agent`, `photo-agent` and `knowledge-agent`, and the NAS's on-device AI models. These are provided by UGREEN for the Hackathon under the UGREEN Skill Developer Package terms.
- **Optional reference prototype (not part of this package):** a separate offline Python prototype used only to test the extraction and deadline rules on synthetic documents. It uses pypdf (BSD-3-Clause, https://github.com/py-pdf/pypdf), RapidOCR (Apache-2.0, https://github.com/RapidAI/RapidOCR), ONNX Runtime (MIT, https://github.com/microsoft/onnxruntime), ReportLab (BSD, https://www.reportlab.com) and Pillow (MIT-CMU, https://github.com/python-pillow/Pillow). All sample documents are synthetic.
- **Principal functionality developed for this Hackathon:** the read-only inventory and SHA-256 incremental ledger workflow, the evidence-grounded extraction rules, the notice-period deadline math (action date = obligation date minus notice period), the ranked Action Digest format, the approval-gated save and tagging steps, and the validation test cases.
- **AI tools used:** an AI coding assistant was used to help draft this Skill's Markdown, the reference prototype, its tests and the synthetic sample documents. All output was reviewed by the entrant.
