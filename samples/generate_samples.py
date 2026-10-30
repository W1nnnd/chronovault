#!/usr/bin/env python3
"""Generate the synthetic ChronoVault demo vault.

Every company, person, number and address below is fictional and was made up
for this demo. No real personal data is used.

Usage:  python samples/generate_samples.py [output_dir]
Default output: samples/nas  (mimics folders on a UGREEN AI NAS share)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
FIXED_MTIME = 1793318400  # 2026-10-30 00:00 UTC, keeps fingerprints reproducible

MONO_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf",
]
HAND_CANDIDATES = [
    "/usr/share/fonts/truetype/sand-box/google/Caveat/Caveat-VariableFont_wght.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(candidates: list[str], size: int):
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _pdf(path: Path, brand: str, accent: str, title: str, meta: list[tuple[str, str]], body: list[str], footer: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4, invariant=1)
    c.setTitle(title)
    c.setAuthor(brand)
    w, h = A4
    c.setFillColor(colors.HexColor(accent))
    c.rect(0, h - 28 * mm, w, 28 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(18 * mm, h - 16 * mm, brand)
    c.setFont("Helvetica", 10)
    c.drawString(18 * mm, h - 22 * mm, title)
    y = h - 40 * mm
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 11)
    for k, v in meta:
        c.drawString(18 * mm, y, f"{k}:")
        c.setFont("Helvetica", 11)
        c.drawString(55 * mm, y, v)
        c.setFont("Helvetica-Bold", 11)
        y -= 7 * mm
    y -= 4 * mm
    c.setStrokeColor(colors.HexColor("#e5e7eb"))
    c.line(18 * mm, y, w - 18 * mm, y)
    y -= 10 * mm
    c.setFont("Helvetica", 11)
    c.setFillColor(colors.HexColor("#1f2937"))
    for para in body:
        for line in _wrap(para, 90):
            c.drawString(18 * mm, y, line)
            y -= 6 * mm
        y -= 3 * mm
    c.setFont("Helvetica-Oblique", 8)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(18 * mm, 15 * mm, footer)
    c.save()


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) > width and cur:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def _receipt_png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (720, 960), "#f8f5ef")
    d = ImageDraw.Draw(img)
    mono = _font(MONO_CANDIDATES, 28)
    bold = _font(MONO_CANDIDATES, 34)
    d.rectangle([40, 40, 680, 920], outline="#1f2937", width=3)
    d.text((80, 80), "VANTAGE OPTICS", fill="#111827", font=bold)
    d.text((80, 130), "Sample City Optics Boutique (fictional)", fill="#4b5563", font=mono)
    lines = [
        "Date: 20 NOV 2024",
        "Receipt No: VO-58213",
        "Item: 55mm Prime Lens",
        "Serial No: VO-58213",
        "",
        "Subtotal          SGD 1,149.00",
        "Tax               SGD   100.00",
        "TOTAL             SGD 1,249.00",
        "",
        "2-year limited warranty",
        "from date of purchase.",
        "",
        "Thank you for shopping.",
    ]
    y = 220
    for ln in lines:
        d.text((80, y), ln, fill="#111827", font=mono)
        y += 42
    img = img.filter(ImageFilter.GaussianBlur(radius=0.4))
    img.save(path, "PNG")


def _note_png(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (900, 600), "#fff8e7")
    d = ImageDraw.Draw(img)
    hand = _font(HAND_CANDIDATES, 48)
    d.text((60, 80), "Remember to call the plumber", fill="#1f2937", font=hand)
    d.text((60, 180), "about the kitchen tap.", fill="#1f2937", font=hand)
    d.text((60, 320), "(no date on this note)", fill="#9ca3af", font=hand)
    img.save(path, "PNG")


def generate(out: Path | None = None) -> Path:
    out = Path(out) if out else HERE / "nas"
    if out.exists():
        shutil.rmtree(out)
    docs = out / "Documents"
    photos = out / "Photos" / "Receipts"
    for d in [docs / "Contracts", docs / "Bills", docs / "Inbox", docs / "Archive" / "2024", photos]:
        d.mkdir(parents=True, exist_ok=True)

    _pdf(
        docs / "Contracts" / "lumora_cloud_service_agreement.pdf",
        "Lumora Cloud Ltd", "#0f766e",
        "Cloud Service Agreement",
        [("Provider", "Lumora Cloud Ltd"), ("Contract No", "LC-2024-8841"),
         ("Effective", "15 December 2025"), ("Annual fee", "SGD 4,800.00")],
        [
            "This Agreement renews automatically on 15 December 2026 unless either party gives at least thirty (30) days written notice of non-renewal.",
            "Services cover hosted object storage and API access for the Customer's studio workloads.",
            "All notices must be sent to notices@lumora-example.test.",
        ],
        "Fictional sample for ChronoVault demo. Not a real contract.",
    )
    _pdf(
        docs / "Contracts" / "kestrel_home_insurance_policy.pdf",
        "Kestrel Mutual", "#1d4ed8",
        "Home Insurance Policy Schedule",
        [("Insurer", "Kestrel Mutual Insurance Co"), ("Policy No", "KM-445210452"),
         ("Insured", "Sample Residence, Sample City"), ("Premium", "SGD 1,280.00")],
        [
            "The policy period ends on 1 March 2027. Notice of non-renewal must be given 14 days before the end date.",
            "Buildings and contents cover as described in the attached schedule.",
        ],
        "Fictional sample for ChronoVault demo.",
    )
    _pdf(
        docs / "Contracts" / "harbor_lane_tenancy_agreement.pdf",
        "Harbor Lane Estates", "#7c3aed",
        "Residential Tenancy Agreement",
        [("Landlord", "Harbor Lane Estates Pte Ltd"), ("Contract No", "HL-T-2099"),
         ("Tenant", "Demo Tenant"), ("Rent", "SGD 3,200.00 / month")],
        [
            "The lease term ends on 31 August 2027. Either party may end the tenancy earlier by giving sixty (60) days written notice.",
            "The security deposit is SGD 6,400.00.",
        ],
        "Fictional sample for ChronoVault demo.",
    )
    _pdf(
        docs / "Bills" / "orbitel_fiber_invoice_oct2026.pdf",
        "Orbitel Fiber", "#ea580c",
        "Broadband Invoice — October 2026",
        [("Vendor", "Orbitel Fiber Pte Ltd"), ("Invoice No", "OF-77821"),
         ("Billing period", "1 Oct 2026 – 31 Oct 2026"), ("Amount due", "SGD 59.90")],
        [
            "Payment due on 12 November 2026. A late fee of SGD 5.00 applies after the due date.",
            "Service address: Sample Residence, Sample City.",
        ],
        "Fictional sample for ChronoVault demo.",
    )
    _pdf(
        docs / "Bills" / "studio_commons_coworking_invoice.pdf",
        "Studio Commons", "#0891b2",
        "Coworking Membership Invoice",
        [("Vendor", "Studio Commons Co"), ("Invoice No", "SC-44102"),
         ("Member", "Demo Freelancer"), ("Amount due", "SGD 380.00")],
        [
            "Payment due on 5 November 2026 for the November desk membership.",
            "Hot desk access includes meeting room credits.",
        ],
        "Fictional sample for ChronoVault demo.",
    )
    _pdf(
        docs / "Inbox" / "brightfield_washer_warranty.pdf",
        "Brightfield Appliances", "#15803d",
        "Limited Warranty Certificate",
        [("Vendor", "Brightfield Appliances Ltd"), ("Serial No", "BF-WASHER-99102"),
         ("Purchase date", "10 January 2025"), ("Product", "BF-900 Front Load Washer")],
        [
            "This product carries a 2-year limited warranty from date of purchase.",
            "Warranty valid until 10 January 2027 for manufacturing defects under normal household use.",
        ],
        "Fictional sample for ChronoVault demo.",
    )
    # Duplicate of the warranty in Archive
    shutil.copy2(
        docs / "Inbox" / "brightfield_washer_warranty.pdf",
        docs / "Archive" / "2024" / "brightfield_washer_warranty.pdf",
    )

    (docs / "Inbox" / "streamnest_renewal_notice.eml").write_text(
        "From: billing@streamnest.example.com\n"
        "Subject: Your StreamNest Premium plan renews soon\n"
        "Date: Thu, 29 Oct 2026 09:12:00 +0800\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "Hi there,\n\n"
        "Your StreamNest Premium annual plan renews on 3 November 2026.\n"
        "You will be charged USD 119.88. Cancel before the renewal date to avoid the charge.\n\n"
        "StreamNest (fictional service for demonstration purposes)\n",
        encoding="utf-8",
    )
    (docs / "Inbox" / "q4_estimated_tax_reminder.txt").write_text(
        "Sample City Tax Office (fictional)\n"
        "Notice date: 1 October 2026\n\n"
        "Reminder for self-employed taxpayers:\n"
        "Your fourth quarter estimated tax payment is due on 15 January 2027.\n"
        "Estimated amount: SGD 2,150.00\n",
        encoding="utf-8",
    )
    (docs / "Inbox" / "meeting_notes_budget.txt").write_text(
        "Family budget meeting notes\n\n"
        "- Compare electricity plans next quarter\n"
        "- Move old photos to the NAS archive\n",
        encoding="utf-8",
    )
    (docs / "Inbox" / "locked_statement.pdf").write_bytes(
        b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n1 0 obj << /Encrypt 9 0 R >>\n" + bytes(range(256)) * 8
    )

    _receipt_png(photos / "vantage_optics_lens_receipt.png")
    _note_png(photos / "handwritten_note.png")

    for p in out.rglob("*"):
        if p.is_file():
            os.utime(p, (FIXED_MTIME, FIXED_MTIME))
    return out


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "nas"
    generate(target)
    files = sorted(p for p in target.rglob("*") if p.is_file())
    print(f"Generated {len(files)} synthetic files under {target}")
    for p in files:
        print("  ", p.relative_to(target))
