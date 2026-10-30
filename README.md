# ChronoVault: your deadlines, on your NAS

ChronoVault is a local-first AI steward for **UGREEN AI NAS**. It reads the contracts, bills, receipts, warranty cards and renewal emails in folders you authorize, extracts every deadline **on the device**, and gives you a ranked **Action Digest**: what to do, by when, and the exact sentence that proves it.

It was built for the UGREEN Hackathon 2026 on AI NAS.

- Demo video: https://youtu.be/s_rPAmg7fWw
- Devpost project page: https://devpost.com/software/chronovault-5kyx3s

The repository has two parts:

| Part | What it is |
| :--- | :--- |
| [`skill/chronovault-steward/`](skill/chronovault-steward/SKILL.md) | The **UGOS Skill**: `SKILL.md` plus four linked Markdown references, following the Uliya Skill Development Standard. It delegates the work to the NAS's registered experts (`file-agent`, `document-agent`, `photo-agent`, `knowledge-agent`). It contains no scripts. |
| [`chronovault/`](chronovault/) | A **reference prototype** in Python that runs the same three stages offline on any computer, with a local dashboard. Use it to test the extraction rules and deadline math on the synthetic sample vault without a NAS. |

## Why

The dates that cost money are buried inside documents: an auto-renewal that needed 30 days written notice, a warranty that quietly ended, a broadband bill or a tax instalment. Cloud AI can read them only if you upload your private financial records, and NAS search only sees file names.

ChronoVault does the deadline math people forget. A cloud contract that "renews on 15 December 2026" with "at least thirty (30) days written notice" is ranked as **act by 15 November 2026**, not December.

## How it works

1. **Inventory (read-only).** Fingerprint every document and image in the authorized folders with SHA-256, group duplicates, and skip files already in the ledger.
2. **Extract (on-device).** Read PDFs, emails and text, and run OCR on receipt photos. Pull out document type, counterparty, dates, notice periods, amounts and reference numbers. Every date and amount must come with a verbatim quote, or the item goes to **Needs Review**.
3. **Rank and save.** Action date = obligation date minus notice period. Items are grouped as Critical, Upcoming, Planned and Needs Review. A Markdown digest with an embedded ledger is saved; on the NAS this happens only after the user approves.

| Stage | On the NAS (Skill) | In the prototype |
| :--- | :--- | :--- |
| Inventory | `file-agent`: `ug-filesystem` find, stat, sha256sum; `ug-filemgr` scan-dedupe | `pathlib` walk and `hashlib` |
| Documents | `document-agent`: `ug-document` extract (contract, invoice, receipt) | `pypdf` text and grounded rules in `chronovault/fields.py` |
| Photos | `photo-agent`: `ug-photo` vision-ocr | RapidOCR (ONNX, offline) |
| Digest | `knowledge-agent`: `ug-knowledge` save-text (approval) | SQLite ledger and Markdown digest |
| Tags (optional) | `file-agent`: `ug-filemgr` tag-add-file (opt-in and approval) | not implemented |

## Quick start (prototype)

Requires Python 3.10 or later.

```bash
git clone https://github.com/W1nnnd/chronovault.git
cd chronovault
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python samples/generate_samples.py      # 13 synthetic files under samples/nas (fictional data only)
python -m chronovault scan              # run the pipeline once and print the stage log
python -m chronovault digest            # print the Action Digest
python -m chronovault demo              # fresh vault + dashboard at http://127.0.0.1:8765
pytest -q                               # 19 tests
```

Use your own folders with `--source PATH` (repeatable), set the reference date with `--as-of YYYY-MM-DD`, and choose where the ledger goes with `--vault PATH`. Source folders are opened read-only. After every run the pipeline hashes them again and records the result. `python -m chronovault reset` deletes the vault folder and leaves your documents untouched.

The dashboard binds to `127.0.0.1` only and makes no outbound network calls. The test suite blocks sockets during a scan to prove it.

Demo video (Round 1): https://youtu.be/s_rPAmg7fWw

## The Skill package

```
skill/chronovault-steward/
├── SKILL.md
└── references/
    ├── extraction-and-deadline-rules.md
    ├── digest-format.md
    ├── privacy-and-approval.md
    └── validation-test-cases.md
```

To check it with the official UGOS Skill Creation Tool (`uliya-skill-kit`, from the UGREEN Hackathon Starter Kit):

```bash
node uliya-skill-kit/scripts/check-skill.mjs skill/chronovault-steward
# status: static-pass, 0 errors, 0 warnings
```

`ULIYA_SKILL_KIT=/path/to/uliya-skill-kit pytest` runs the same check as part of the tests. `python tools/build_submission.py --dist dist` builds the submission ZIP and the Round 1 proposal PDF.

A static pass does not prove that the Skill runs on a device. Runtime validation on UGREEN AI NAS hardware is planned for the finalist round.

## Privacy

- The source folders are read-only, and only the folders you name are scanned.
- No cloud API, no API key and no telemetry.
- Account and policy numbers are masked in the digest.
- All sample documents in `samples/` are synthetic. Every company, person and number is fictional.

## Third-party components

| Component | License | Used for |
| :--- | :--- | :--- |
| pypdf | BSD-3-Clause | PDF text extraction |
| RapidOCR (rapidocr-onnxruntime) | Apache-2.0 | Offline OCR |
| ONNX Runtime | MIT | OCR model runtime |
| ReportLab | BSD | Sample and proposal PDFs |
| Pillow | MIT-CMU (HPND) | Sample receipt images |
| Playwright (optional) | Apache-2.0 | Screenshots and video capture |
| Piper TTS (optional, not bundled) | GPL-3.0-or-later | Offline voiceover generation |

The Skill package itself contains only original Markdown.

## License

MIT. See [LICENSE](LICENSE).
