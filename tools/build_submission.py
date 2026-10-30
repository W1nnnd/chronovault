#!/usr/bin/env python3
"""Build the Round 1 ZIP and proposal PDF."""
from __future__ import annotations

import argparse
import hashlib
import re
import zipfile
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skill" / "chronovault-steward"

PROPOSAL = [
    ("1. One sentence: What does the Skill do?",
     "ChronoVault Steward reads the contracts, bills, receipts and warranty cards in NAS folders the user authorizes and returns a ranked Action Digest of renewal notice windows, warranty expiries, payment due dates and tax dates, each proven by a verbatim quote from the source file."),
    ("2. Who is the target user and problem?",
     "Families, freelancers and small studios who keep years of PDFs, emailed bills and receipt photos on a UGREEN AI NAS. The dates that cost money are buried inside: an auto-renewal needing 30 days notice, a lapsing warranty, a tax instalment. Cloud AI means uploading private financial records; filename search cannot see dates."),
    ("3. What is your proposed solution?",
     "An orchestration Skill that delegates to on-device experts: fingerprint authorized folders read-only, extract obligations with NAS document and OCR capabilities, compute the real action date (renewal minus notice period), and save a digest whose ledger makes reruns incremental. Uncertain items go to Needs Review, never guessed."),
    ("4. What is the Core User Flow?",
     "The user asks \"what is about to expire or renew in my Documents and Receipts folders?\" The Skill confirms the folders; file-agent returns files with SHA-256 and duplicates; document-agent and photo-agent return fields with evidence; the Skill ranks Critical, Upcoming, Planned and Needs Review, shows the digest, and saves it after approval."),
    ("5. What substantive difference does your idea offer?",
     "Generic assistants answer questions about one file; ChronoVault proactively audits a whole archive and does the deadline math people forget. Every date carries its quote, reruns are incremental by hash, originals are never modified, and nothing leaves the NAS."),
    ("6. Which UGREEN AI NAS capabilities will be used, and at which step?",
     "Step 1: ug-filesystem find, stat and sha256sum plus ug-filemgr scan-dedupe (file-agent). Step 2: ug-document extract with contract, invoice and receipt schemas (document-agent) and ug-photo vision-ocr for receipt photos (photo-agent). Step 3: ug-knowledge save-text for the digest (knowledge-agent) and optional ug-filemgr tag-add-file."),
    ("7. What was your technical approach?",
     "The parent Skill only issues delegate commands to registered experts and passes each real result downstream. Inputs: authorized folders, as-of date, horizon, digest folder, previous digest, tagging opt-in. Reading is read-only; saving and tagging require approval. Models are the NAS local document and vision models; no external API. Account numbers are masked. All five delegation states, including waiting_approval, are handled."),
    ("8. What is the current development status?",
     "Implemented: SKILL.md with four linked references, passing the official uliya-skill-kit static check with zero errors and warnings, plus a Python reference prototype of the three stages (OCR, SQLite ledger, dashboard) passing 19 tests on 13 synthetic documents. Pending NAS validation: real expert outputs, tagging, large-folder timing."),
    ("9. What is your final validation plan?",
     "Core case A: a receipt photo with a two-year warranty must yield the derived end date and serial number. Core case B: a contract that renews with 30 days notice must rank the notice date, not the renewal date. Edge case C: a duplicate warranty PDF and an undated scan must be deduplicated or routed to Needs Review while the batch completes."),
    ("10. Are there any known limitations?",
     "Accuracy depends on expert outputs for handwriting and blurry photos. Ambiguous numeric dates go to review. The catalog has no calendar or push capability, so the digest is the deliverable. Large archives run in batches. No external services are used."),
]


def word_count(text: str) -> int:
    # substantive = answers only, whitespace-split
    return len(re.findall(r"\S+", text))


def build_zip(dist: Path) -> Path:
    out = dist / "chronovault-steward-skill.zip"
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(SKILL.rglob("*")):
            if path.is_file() and path.suffix == ".md":
                arc = Path("chronovault-steward") / path.relative_to(SKILL)
                zf.write(path, arc.as_posix())
    data = out.read_bytes()
    print(f"[zip] {out} {len(data)} bytes, "
          f"{sum(1 for p in SKILL.rglob('*.md') if p.is_file())} Markdown files, "
          f"sha256 {hashlib.sha256(data).hexdigest()[:16]}")
    return out


def build_pdf(dist: Path) -> Path:
    out = dist / "ChronoVault_Proposal_Round1.pdf"
    answers = " ".join(a for _, a in PROPOSAL)
    n = word_count(answers)
    styles = getSampleStyleSheet()
    title = ParagraphStyle("T", parent=styles["Heading1"], fontSize=13, leading=16, spaceAfter=4)
    h = ParagraphStyle("H", parent=styles["Heading3"], fontSize=9, leading=11, spaceBefore=5, spaceAfter=1)
    body = ParagraphStyle("B", parent=styles["Normal"], fontSize=8.5, leading=11, spaceAfter=1)
    small = ParagraphStyle("S", parent=styles["Normal"], fontSize=7.5, leading=9, textColor="#333333")
    doc = SimpleDocTemplate(str(out), pagesize=A4,
                            leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm)
    story = [
        Paragraph("ChronoVault Steward: UGREEN Hackathon 2026 on AI NAS, Round 1 Proposal", title),
        Paragraph(
            f"Skill: chronovault-steward | Package: SKILL.md + 4 linked references "
            f"(official static check: pass) | Substantive word count: {n} (limit 500)",
            small),
        Spacer(1, 4),
    ]
    for q, a in PROPOSAL:
        story.append(Paragraph(q, h))
        story.append(Paragraph(a, body))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Entrant: Feng Feng (w1nnnd), solo entry. Signed electronically by Feng Feng on October 30, 2026. "
        "I confirm compliance with the UGREEN Hackathon 2026 Official Rules.", small))
    story.append(Paragraph(
        "Third-party components: the Skill package contains only original Markdown and uses UGOS capabilities "
        "through registered experts; no third-party code, data or external service. The optional reference "
        "prototype (not part of the package) uses pypdf (BSD-3-Clause), RapidOCR (Apache-2.0), ONNX Runtime "
        "(MIT), ReportLab (BSD) and Pillow (MIT-CMU). All sample documents are synthetic. AI coding assistance "
        "was used to draft documentation and tests.", small))
    doc.build(story)
    print(f"[pdf] {out} {out.stat().st_size / 1024:.1f} KB, 1 page(s), {n} substantive words")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = ap.parse_args()
    args.dist.mkdir(parents=True, exist_ok=True)
    build_zip(args.dist)
    build_pdf(args.dist)


if __name__ == "__main__":
    main()
