"""Stage 2a: text extraction (stand-in for ug-document extract / ug-photo vision-ocr)."""
from __future__ import annotations

import email
import email.policy
import re
from dataclasses import dataclass
from pathlib import Path

DOC_EXT = {".pdf", ".txt", ".eml", ".md"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
SUPPORTED_EXT = DOC_EXT | IMG_EXT

_OCR_ENGINE = None


@dataclass
class TextResult:
    text: str
    method: str  # pdf-text | plain-text | email | ocr
    error: str | None = None
    ocr_confidence: float | None = None


def _normalize_layout(raw: str) -> str:
    """Join 'Label:' lines with their value and re-flow wrapped sentences."""
    lines = [ln.strip() for ln in raw.replace("\r", "").split("\n")]
    out: list[str] = []
    for ln in lines:
        if not ln:
            out.append("")
            continue
        if out and out[-1].endswith(":") and len(out[-1]) <= 40:
            out[-1] = f"{out[-1]} {ln}"
        elif out and out[-1] and ln[0].islower() and not out[-1].endswith((".", ":", "!", "?")):
            out[-1] = f"{out[-1]} {ln}"
        else:
            out.append(ln)
    return "\n".join(out).strip()


def fix_ocr_confusions(text: str) -> str:
    """Repair common OCR digit/letter swaps inside words (N0V -> NOV, T0TAL -> TOTAL)."""

    def repl(m: re.Match) -> str:
        tok = m.group(0)
        letters = sum(ch.isalpha() for ch in tok)
        return tok.replace("0", "O") if letters >= 1 and letters >= len(tok) - letters else tok

    return re.sub(r"\b[A-Za-z0]*0[A-Za-z0]*\b", repl, text)


def _ocr(path: Path) -> TextResult:
    global _OCR_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR  # optional dependency
    except ImportError:
        return TextResult("", "ocr", "OCR engine not installed (pip install rapidocr-onnxruntime)")
    if _OCR_ENGINE is None:
        _OCR_ENGINE = RapidOCR()
    result, _ = _OCR_ENGINE(str(path))
    if not result:
        return TextResult("", "ocr", "no text recognized in image", 0.0)
    lines = [r[1] for r in result]
    conf = sum(float(r[2]) for r in result) / len(result)
    return TextResult(fix_ocr_confusions("\n".join(lines)), "ocr", None, round(conf, 3))


def extract_text(path: Path) -> TextResult:
    ext = path.suffix.lower()
    try:
        if path.stat().st_size == 0:
            return TextResult("", "none", "empty file")
        if ext == ".pdf":
            from pypdf import PdfReader
            from pypdf.errors import PdfReadError

            try:
                reader = PdfReader(str(path))
                if reader.is_encrypted:
                    return TextResult("", "pdf-text", "password protected PDF")
                raw = "\n".join((p.extract_text() or "") for p in reader.pages)
            except (PdfReadError, ValueError, KeyError, OSError, Exception) as exc:  # noqa: BLE001
                return TextResult("", "pdf-text", f"damaged or encrypted PDF ({type(exc).__name__})")
            text = _normalize_layout(raw)
            if len(text) < 40:
                return TextResult(text, "pdf-text", "PDF has no text layer (scanned page)")
            return TextResult(text, "pdf-text")
        if ext in {".txt", ".md"}:
            return TextResult(_normalize_layout(path.read_text(encoding="utf-8", errors="replace")), "plain-text")
        if ext == ".eml":
            msg = email.message_from_bytes(path.read_bytes(), policy=email.policy.default)
            body = msg.get_body(preferencelist=("plain", "html"))
            content = body.get_content() if body else ""
            header = f"From: {msg.get('From', '')}\nSubject: {msg.get('Subject', '')}\nEmail Date: {msg.get('Date', '')}"
            return TextResult(_normalize_layout(header + "\n\n" + content), "email")
        if ext in IMG_EXT:
            return _ocr(path)
    except OSError as exc:
        return TextResult("", "none", f"cannot read file ({exc.strerror})")
    return TextResult("", "none", "unsupported file type")
