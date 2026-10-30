# Extraction fields and deadline rules

Linked from [SKILL.md](../SKILL.md). Read this before Step 3, Step 4 and Step 5.

## 1. Fields requested for each file

| Field | Meaning | Rule |
| :--- | :--- | :--- |
| `doc_type` | contract, subscription, invoice, receipt, warranty, insurance, lease, tax_notice | Taken from the document title or body; `other` if unclear |
| `counterparty` | Vendor, landlord, insurer or agency | As printed; never shortened into a brand guess |
| `document_date` | Issue, signing or purchase date | Normalized to YYYY-MM-DD |
| `obligations[]` | One entry per date that needs action | See section 2 |
| `amount`, `currency` | Total amount and ISO currency code | Keep the printed currency; do not convert |
| `reference_id` | Contract, policy, invoice or serial number | Mask to the last four characters in the digest when it is an account or card number |
| `evidence[]` | Verbatim sentence for every date and amount | Mandatory; an item without evidence goes to Needs Review |
| `confidence` | 0.0 to 1.0 | Below 0.75 goes to Needs Review |

## 2. Obligation kinds

| Kind | Typical wording | Obligation date | Notice period |
| :--- | :--- | :--- | :--- |
| `renewal` | "renews automatically on", "initial term ends" | renewal date | "written notice at least N days before" |
| `expiry` | "policy period ends", "lease term ends" | end date | "notice of non-renewal N days" |
| `warranty_end` | "warranty valid until", "N-year limited warranty from date of purchase" | end date, or purchase date plus N years (marked `derived`) | none |
| `payment_due` | "payment due", "due date" | due date | none |
| `filing_due` | "estimated tax payment due", "filing deadline" | due date | none |
| `subscription_renewal` | "your plan renews on", "next billing date" | renewal date | cancel-before wording if present |

## 3. Action date math

```
action_date = obligation_date - notice_days   (when notice_days is present)
action_date = obligation_date                 (otherwise)
```

Example: renews on 15 December 2026 with thirty days written notice → act by 15 November 2026.

## 4. Needs Review (never guess)

Route to Needs Review when any of these are true:

- No verbatim evidence quote for a date or amount
- Confidence below 0.75, or OCR confidence below 0.60
- Damaged, encrypted or empty file
- Undated scan or handwritten note with no readable date
- Ambiguous numeric date (for example 01/02/03 without a locale cue)

Continue the batch for the other files. Never invent a date to make the digest look complete.
