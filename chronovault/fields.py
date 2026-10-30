"""Stage 2b: grounded field and obligation extraction.

A deterministic, rule-based stand-in for the on-device `ug-document extract`
call. It follows the same contract as the Skill: every date and amount must be
backed by a verbatim quote, uncertain items are routed to Needs Review, and
nothing is estimated.
"""
from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1)}
_MON = r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\.?"
DATE_PATTERNS = [
    re.compile(rf"\b(\d{{1,2}})\s+{_MON},?\s+(\d{{4}})\b", re.I),
    re.compile(rf"\b{_MON}\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]
NUMBER_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
                "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40, "sixty": 60,
                "ninety": 90}
CURRENCY = {"SGD": "SGD", "S$": "SGD", "USD": "USD", "US$": "USD", "EUR": "EUR",
            "€": "EUR", "GBP": "GBP", "£": "GBP", "CNY": "CNY", "JPY": "JPY"}
AMOUNT_RE = re.compile(
    r"(SGD|USD|EUR|GBP|CNY|JPY|S\$|US\$|€|£)\s?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)"
)
REF_RE = re.compile(
    r"\b(Contract No|Policy No|Serial No|Invoice No|Receipt No|Account No|Policy Number)\s*[:#]?\s*([A-Z0-9][A-Z0-9-]{2,})",
    re.I,
)
PARTY_LABELS = re.compile(
    r"^(Provider|Vendor|Seller|Insurer|Landlord|Merchant|From|Issuer)\s*:\s*(.+)$",
    re.I | re.M,
)

DOC_TYPE_RULES = [
    ("lease", r"\b(tenancy|lease)\b"),
    ("insurance", r"\binsurance\b|\bpolicy schedule\b"),
    ("warranty", r"\bwarranty\b"),
    ("tax_notice", r"\b(estimated tax|tax payment|tax office|inland revenue)\b"),
    ("invoice", r"\binvoice\b|\bbill\b|\bamount due\b"),
    ("receipt", r"\breceipt\b|\bpurchase\b"),
    ("subscription", r"\b(subscription|plan renews|premium plan)\b"),
    ("contract", r"\b(agreement|contract|service agreement)\b"),
]

ACTION_LABEL = {
    "renewal": "Send notice / cancel by",
    "expiry": "Act before term ends",
    "warranty_end": "Warranty ends",
    "payment_due": "Payment due",
    "filing_due": "File / pay by",
    "subscription_renewal": "Cancel or change by",
}


@dataclass
class Obligation:
    kind: str
    obligation_date: dt.date
    notice_days: int | None
    derived: bool
    confidence: float
    evidence: list[str] = field(default_factory=list)

    @property
    def action_date(self) -> dt.date:
        if self.notice_days:
            return self.obligation_date - dt.timedelta(days=self.notice_days)
        return self.obligation_date


@dataclass
class Record:
    doc_type: str
    counterparty: str | None
    document_date: dt.date | None
    amount: float | None
    currency: str | None
    amount_quote: str | None
    reference_id: str | None
    tax_related: bool
    obligations: list[Obligation]
    status: str
    review_reason: str | None


def _safe_date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None


def _parse_match(m: re.Match) -> tuple[dt.date | None, str]:
    g = m.groups()
    quote = m.group(0)
    if len(g) == 3 and g[0].isdigit() and len(g[0]) == 4:
        return _safe_date(int(g[0]), int(g[1]), int(g[2])), quote
    if len(g) == 3 and g[1][:3].lower() in MONTHS:
        # day MON year
        return _safe_date(int(g[2]), MONTHS[g[1][:3].lower()], int(g[0])), quote
    if len(g) == 3 and g[0][:3].lower() in MONTHS:
        # MON day year
        return _safe_date(int(g[2]), MONTHS[g[0][:3].lower()], int(g[1])), quote
    return None, quote


def find_dates(text: str) -> list[tuple[dt.date | None, str, int]]:
    """Return (date_or_None_if_impossible, quote, start_index) in order of appearance."""
    hits: list[tuple[int, dt.date | None, str]] = []
    for pat in DATE_PATTERNS:
        for m in pat.finditer(text):
            d, q = _parse_match(m)
            hits.append((m.start(), d, q))
    hits.sort(key=lambda x: x[0])
    # de-dupe overlapping starts
    out: list[tuple[dt.date | None, str, int]] = []
    used: set[int] = set()
    for start, d, q in hits:
        if any(abs(start - u) < 3 for u in used):
            continue
        used.add(start)
        out.append((d, q, start))
    return out


def classify(text: str) -> str:
    low = text.lower()
    for name, pat in DOC_TYPE_RULES:
        if re.search(pat, low):
            return name
    return "other"


def _sentence_around(text: str, idx: int, quote: str) -> str:
    start = text.rfind(".", 0, idx)
    start = 0 if start < 0 else start + 1
    end = text.find(".", idx + len(quote))
    end = len(text) if end < 0 else end + 1
    snip = text[start:end].strip()
    return snip or quote


def _notice_days(text: str) -> tuple[int | None, str | None]:
    patterns = [
        r"(?:at least|minimum of|no less than)?\s*"
        r"(?:(\d+)|(" + "|".join(NUMBER_WORDS) + r"))\s*"
        r"\(?\d*\)?\s*days?\s+(?:prior\s+)?(?:written\s+)?notice",
        r"(?:written\s+)?notice\s+(?:of\s+(?:non-renewal\s+)?)?(?:must be )?(?:given\s+)?"
        r"(?:at\s+least\s+)?"
        r"(?:(\d+)|(" + "|".join(NUMBER_WORDS) + r"))\s*\(?\d*\)?\s*days?",
        r"(?:given|give)\s+(?:at\s+least\s+)?"
        r"(?:(\d+)|(" + "|".join(NUMBER_WORDS) + r"))\s*\(?\d*\)?\s*days?\s+before",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.I)
        if m:
            raw = (m.group(1) or m.group(2) or "").lower()
            days = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)
            if days:
                return days, m.group(0)
    return None, None


def _warranty_years(text: str) -> tuple[int | None, str | None]:
    m = re.search(
        r"(\d+|one|two|three|four|five)\s*[- ]\s*year(?:s)?\s+(?:limited\s+)?warranty",
        text, re.I,
    )
    if not m:
        return None, None
    raw = m.group(1).lower()
    years = int(raw) if raw.isdigit() else NUMBER_WORDS.get(raw)
    return years, m.group(0)


def _find_amount(text: str) -> tuple[float | None, str | None, str | None]:
    for m in AMOUNT_RE.finditer(text):
        window = text[max(0, m.start() - 40): m.end() + 20].lower()
        if "late fee" in window or "penalty" in window:
            continue
        cur = CURRENCY.get(m.group(1), m.group(1))
        val = float(m.group(2).replace(",", ""))
        return val, cur, m.group(0)
    return None, None, None


def extract_record(text: str, *, is_image: bool = False,
                   ocr_confidence: float | None = None) -> Record:
    doc_type = classify(text)
    party_m = PARTY_LABELS.search(text)
    counterparty = party_m.group(2).strip() if party_m else None
    if counterparty is None:
        # first ALLCAPS or Title line that looks like a brand
        for ln in text.splitlines()[:8]:
            s = ln.strip()
            if 2 <= len(s) <= 48 and re.match(r"^[A-Z][A-Za-z0-9 &.'-]{1,}$", s):
                if s.lower() not in {"service agreement", "invoice", "receipt", "warranty"}:
                    counterparty = s
                    break
    if doc_type == "other":
        counterparty = None

    dates = find_dates(text)
    impossible = [q for d, q, _ in dates if d is None]
    valid = [(d, q, i) for d, q, i in dates if d is not None]

    document_date = valid[0][0] if valid else None
    doc_date_quote = valid[0][1] if valid else None

    amount, currency, amount_quote = _find_amount(text)
    ref_m = REF_RE.search(text)
    ref = ref_m.group(2) if ref_m else None

    tax_related = doc_type == "tax_notice" or bool(re.search(r"\btax\b", text, re.I))

    notice, notice_quote = _notice_days(text)
    years, years_quote = _warranty_years(text)
    obligations: list[Obligation] = []
    conf_penalty = 0.0 if (ocr_confidence is None or ocr_confidence >= 0.8) else 0.1

    low = text.lower()

    # Renewals / subscriptions
    for d, q, idx in valid:
        snip = _sentence_around(text, idx, q).lower()
        if re.search(r"renews?\s+(automatically\s+)?on|auto-?renew|plan renews|next billing", snip):
            kind = "subscription_renewal" if doc_type == "subscription" or "plan" in snip else "renewal"
            ev = [_sentence_around(text, idx, q)]
            if notice_quote:
                ev.append(notice_quote)
            obligations.append(Obligation(kind, d, notice, False, round(0.92 - conf_penalty, 2), ev))
        elif re.search(r"(policy period ends|lease term ends|term ends|expires? on|valid until)", snip):
            obligations.append(Obligation(
                "expiry", d, notice, False, round(0.9 - conf_penalty, 2),
                [_sentence_around(text, idx, q)] + ([notice_quote] if notice_quote else []),
            ))
        elif re.search(r"(payment due|due date|amount due|is due on)", snip) and doc_type in {
            "invoice", "tax_notice", "other", "subscription"
        }:
            kind = "filing_due" if tax_related or doc_type == "tax_notice" else "payment_due"
            obligations.append(Obligation(
                kind, d, None, False, round(0.9 - conf_penalty, 2),
                [_sentence_around(text, idx, q)],
            ))
        elif re.search(r"warranty valid until|warranty ends|warranty expir", snip):
            obligations.append(Obligation(
                "warranty_end", d, None, False, round(0.9 - conf_penalty, 2),
                [_sentence_around(text, idx, q)],
            ))

    # Derived warranty from purchase date + N years
    if years and document_date and not any(o.kind == "warranty_end" for o in obligations):
        if "warranty" in low or doc_type in {"receipt", "warranty"}:
            try:
                end = document_date.replace(year=document_date.year + years)
            except ValueError:
                end = _safe_date(document_date.year + years, document_date.month, 28)
            if end:
                obligations.append(Obligation(
                    "warranty_end", end, None, True, round(0.82 - conf_penalty, 2),
                    [doc_date_quote or "", years_quote or ""],
                ))

    # Deduplicate by (kind, date)
    seen: set[tuple[str, dt.date]] = set()
    uniq: list[Obligation] = []
    for o in obligations:
        key = (o.kind, o.obligation_date)
        if key in seen:
            continue
        seen.add(key)
        uniq.append(o)
    obligations = uniq

    status, reason = "tracked", None
    if impossible and not obligations:
        status, reason = "needs_review", impossible[0]
    elif not obligations:
        if is_image or doc_type != "other":
            status, reason = "needs_review", "no deadline date found in " + (
                "scanned image" if is_image else "document")
        else:
            status = "no_deadline"
    elif min(o.confidence for o in obligations) < 0.75:
        status, reason = "needs_review", "low confidence extraction"
    if is_image and ocr_confidence is not None and ocr_confidence < 0.6:
        status, reason = "needs_review", f"low OCR confidence ({ocr_confidence:.2f})"

    return Record(doc_type, counterparty, document_date, amount, currency, amount_quote, ref,
                  tax_related, obligations, status, reason)
