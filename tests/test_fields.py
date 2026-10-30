import datetime as dt

from chronovault.fields import classify, extract_record, find_dates
from chronovault.textract import fix_ocr_confusions


def test_date_formats_and_impossible_dates():
    got = [d for d, _, _ in find_dates(
        "on 15 December 2026, by December 1, 2026 or 2027-01-05; not 31 June 2026")]
    assert got == [dt.date(2026, 12, 15), dt.date(2026, 12, 1), dt.date(2027, 1, 5), None]


def test_notice_period_moves_the_action_date():
    rec = extract_record(
        "Service Agreement\nProvider: Acme Example Ltd\nThis Agreement renews automatically on "
        "15 December 2026 unless either party gives at least thirty (30) days written notice.")
    assert rec.doc_type == "contract"
    (o,) = rec.obligations
    assert (o.kind, o.obligation_date, o.notice_days, o.action_date) == (
        "renewal", dt.date(2026, 12, 15), 30, dt.date(2026, 11, 15))
    assert "renews automatically on 15 December 2026" in o.evidence[0]


def test_warranty_derived_from_purchase_date_on_ocr_text():
    text = fix_ocr_confusions(
        "VANTAGE OPTICS\nDate: 20 N0V 2024\nT0TAL SGD 1,249.00\n2-year limited warranty\nfrom date of purchase.")
    rec = extract_record(text, is_image=True, ocr_confidence=0.86)
    (o,) = rec.obligations
    assert o.kind == "warranty_end" and o.derived and o.obligation_date == dt.date(2026, 11, 20)


def test_late_fee_amount_is_skipped():
    rec = extract_record(
        "Invoice\nVendor: Orbitel Fiber\nAmount due SGD 59.90. Payment due on 12 November 2026. "
        "A late fee of SGD 5.00 applies after the due date.")
    assert rec.amount == 59.90
    assert rec.obligations and rec.obligations[0].action_date == dt.date(2026, 11, 12)


def test_insurance_policy_expiry_with_notice():
    rec = extract_record(
        "Home Insurance Policy Schedule\nInsurer: Kestrel Mutual\nPolicy No: KM-445210452\n"
        "The policy period ends on 1 March 2027. Notice of non-renewal must be given 14 days before the end date.")
    assert rec.doc_type == "insurance"
    (o,) = rec.obligations
    assert o.kind == "expiry" and o.action_date == dt.date(2027, 2, 15)


def test_undated_note_goes_to_needs_review():
    rec = extract_record("Remember to call the plumber about the kitchen tap.", is_image=True)
    assert rec.status == "needs_review"


def test_other_doc_without_dates_is_no_deadline():
    rec = extract_record("Family budget meeting notes\n- Compare electricity plans next quarter\n")
    assert rec.doc_type == "other" and rec.status == "no_deadline" and rec.counterparty is None


def test_classify_lease_and_tax():
    assert classify("Residential Tenancy Agreement lease term") == "lease"
    assert classify("estimated tax payment due") == "tax_notice"
