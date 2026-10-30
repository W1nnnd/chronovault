"""Three-stage scan: inventory → extract → rank & save."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Callable

from . import ledger
from .fields import extract_record
from .textract import SUPPORTED_EXT, extract_text
from .digest import write_outputs


Progress = Callable[[dict], None]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _walk(sources: list[Path]) -> list[Path]:
    files: list[Path] = []
    for src in sources:
        src = Path(src)
        if not src.exists():
            continue
        for p in src.rglob("*"):
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXT and not p.name.startswith("."):
                files.append(p.resolve())
    return files


def run_scan(
    sources: list[Path],
    vault: Path,
    as_of: dt.date,
    progress: Progress | None = None,
) -> dict:
    def emit(stage: int, msg: str, **extra):
        event = {"stage": stage, "msg": msg, **extra}
        if progress:
            progress(event)
        log.append(event)

    log: list[dict] = []
    vault = Path(vault)
    vault.mkdir(parents=True, exist_ok=True)
    sources = [Path(s).resolve() for s in sources]
    con = ledger.connect(vault / "vault.db")
    run_id = ledger.start_run(con, as_of.isoformat(), [str(s) for s in sources])

    # ---- Stage 1: inventory ----
    emit(1, "Fingerprinting authorized folders (read-only)…")
    files = _walk(sources)
    before = {str(p): _sha256(p) for p in files}
    by_sha: dict[str, list[Path]] = defaultdict(list)
    for p, sha in before.items():
        by_sha[sha].append(Path(p))

    known = {r["sha256"] for r in con.execute("SELECT sha256 FROM files")}
    new_shas = [s for s in by_sha if s not in known]
    unchanged_shas = [s for s in by_sha if s in known]
    unchanged_paths = sum(len(by_sha[s]) for s in unchanged_shas)
    new_paths = sum(len(by_sha[s]) for s in new_shas)
    emit(1, f"Found {len(files)} files · {len(by_sha)} unique · {new_paths} new · {unchanged_paths} unchanged")

    # Ensure a files row exists before locations (FK), then refresh locations
    for sha, paths in by_sha.items():
        paths_sorted = sorted(paths, key=lambda p: (len(p.parts), str(p)))
        primary = paths_sorted[0]
        if sha not in known:
            con.execute(
                """INSERT OR IGNORE INTO files
                   (sha256, primary_path, name, ext, size, status, first_run, last_run)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (sha, str(primary), primary.name, primary.suffix.lower(),
                 primary.stat().st_size, "pending", run_id, run_id),
            )
        for p in paths_sorted:
            folder = next((str(s) for s in sources if str(p).startswith(str(s))), str(p.parent))
            st = p.stat()
            ledger.upsert_location(con, str(p), sha, folder, st.st_size, st.st_mtime, run_id)
    con.commit()

    # ---- Stage 2: extract ----
    emit(2, f"Extracting fields from {len(new_shas)} new file(s)…")
    new_count = 0
    for sha in new_shas:
        paths_sorted = sorted(by_sha[sha], key=lambda p: (len(p.parts), str(p)))
        primary = paths_sorted[0]
        tr = extract_text(primary)
        rec = extract_record(tr.text or "", is_image=primary.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"},
                             ocr_confidence=tr.ocr_confidence)
        if tr.error and not rec.obligations:
            status, reason = "needs_review", tr.error
        else:
            status, reason = rec.status, rec.review_reason
        row = {
            "sha256": sha,
            "primary_path": str(primary),
            "name": primary.name,
            "ext": primary.suffix.lower(),
            "size": primary.stat().st_size,
            "method": tr.method,
            "doc_type": rec.doc_type,
            "counterparty": rec.counterparty,
            "document_date": rec.document_date.isoformat() if rec.document_date else None,
            "amount": rec.amount,
            "currency": rec.currency,
            "amount_quote": rec.amount_quote,
            "reference_id": rec.reference_id,
            "tax_related": int(rec.tax_related),
            "status": status,
            "review_reason": reason,
            "ocr_confidence": tr.ocr_confidence,
            "text_chars": len(tr.text or ""),
            "text_preview": (tr.text or "")[:2000],
            "obligations": [
                {
                    "kind": o.kind,
                    "obligation_date": o.obligation_date.isoformat(),
                    "notice_days": o.notice_days,
                    "action_date": o.action_date.isoformat(),
                    "derived": o.derived,
                    "confidence": o.confidence,
                    "evidence": o.evidence,
                }
                for o in rec.obligations
            ],
        }
        ledger.upsert_file(con, row, run_id)
        new_count += 1
        emit(2, f"Extracted {primary.name}", sha=sha[:12], status=status)

    # Touch last_run for unchanged
    for sha in unchanged_shas:
        con.execute("UPDATE files SET last_run=? WHERE sha256=?", (run_id, sha))
        paths_sorted = sorted(by_sha[sha], key=lambda p: (len(p.parts), str(p)))
        con.execute("UPDATE files SET primary_path=? WHERE sha256=?", (str(paths_sorted[0]), sha))

    con.commit()

    # ---- Stage 3: rank & save ----
    emit(3, "Computing action dates and writing digest…")
    paths = write_outputs(con, vault, as_of)
    n_ob = con.execute("SELECT COUNT(*) FROM obligations").fetchone()[0]
    n_nr = con.execute("SELECT COUNT(*) FROM files WHERE status='needs_review'").fetchone()[0]

    # Source integrity re-hash
    after = {str(p): _sha256(p) for p in files}
    unchanged = sum(1 for k, v in before.items() if after.get(k) == v)
    emit(3, f"{unchanged}/{len(before)} source files byte-identical after run")

    stats = {
        "files_seen": len(files),
        "files_new": new_count,
        "files_unchanged": unchanged_paths,
        "obligations": n_ob,
        "needs_review": n_nr,
        "source_unchanged": unchanged == len(before),
        "digest_path": paths.get("digest"),
        "log": log,
    }
    ledger.finish_run(con, run_id, stats)
    emit(3, f"Digest ready · {n_ob} obligations · {n_nr} needs review")
    return {
        "run_id": run_id,
        "files_seen": len(files),
        "files_new": new_count,
        "files_unchanged": unchanged_paths,
        "obligations": n_ob,
        "needs_review": n_nr,
        "source_unchanged": unchanged == len(before),
        "log": log,
        "outputs": paths,
    }
