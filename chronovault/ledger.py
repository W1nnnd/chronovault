"""SQLite ledger: the vault's memory between runs (idempotent by SHA-256)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    sha256 TEXT PRIMARY KEY,
    primary_path TEXT NOT NULL,
    name TEXT NOT NULL,
    ext TEXT NOT NULL,
    size INTEGER NOT NULL,
    method TEXT,
    doc_type TEXT,
    counterparty TEXT,
    document_date TEXT,
    amount REAL,
    currency TEXT,
    amount_quote TEXT,
    reference_id TEXT,
    tax_related INTEGER DEFAULT 0,
    status TEXT NOT NULL,
    review_reason TEXT,
    ocr_confidence REAL,
    text_chars INTEGER DEFAULT 0,
    text_preview TEXT,
    first_run INTEGER,
    last_run INTEGER
);
CREATE TABLE IF NOT EXISTS locations (
    path TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL REFERENCES files(sha256),
    folder TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    last_run INTEGER
);
CREATE TABLE IF NOT EXISTS obligations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sha256 TEXT NOT NULL REFERENCES files(sha256) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    obligation_date TEXT NOT NULL,
    notice_days INTEGER,
    action_date TEXT NOT NULL,
    derived INTEGER DEFAULT 0,
    confidence REAL,
    evidence_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    as_of TEXT NOT NULL,
    sources_json TEXT NOT NULL,
    files_seen INTEGER DEFAULT 0,
    files_new INTEGER DEFAULT 0,
    files_unchanged INTEGER DEFAULT 0,
    obligations INTEGER DEFAULT 0,
    needs_review INTEGER DEFAULT 0,
    source_unchanged INTEGER DEFAULT 0,
    digest_path TEXT,
    log_json TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA)
    return con


def upsert_file(con: sqlite3.Connection, row: dict, run_id: int) -> None:
    existing = con.execute("SELECT sha256 FROM files WHERE sha256=?", (row["sha256"],)).fetchone()
    if existing:
        con.execute(
            """UPDATE files SET primary_path=?, name=?, ext=?, size=?, method=?, doc_type=?,
               counterparty=?, document_date=?, amount=?, currency=?, amount_quote=?,
               reference_id=?, tax_related=?, status=?, review_reason=?, ocr_confidence=?,
               text_chars=?, text_preview=?, last_run=? WHERE sha256=?""",
            (
                row["primary_path"], row["name"], row["ext"], row["size"], row["method"],
                row["doc_type"], row["counterparty"], row["document_date"], row["amount"],
                row["currency"], row["amount_quote"], row["reference_id"], row["tax_related"],
                row["status"], row["review_reason"], row["ocr_confidence"], row["text_chars"],
                row["text_preview"], run_id, row["sha256"],
            ),
        )
        con.execute("DELETE FROM obligations WHERE sha256=?", (row["sha256"],))
    else:
        con.execute(
            """INSERT INTO files (sha256, primary_path, name, ext, size, method, doc_type,
               counterparty, document_date, amount, currency, amount_quote, reference_id,
               tax_related, status, review_reason, ocr_confidence, text_chars, text_preview,
               first_run, last_run)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                row["sha256"], row["primary_path"], row["name"], row["ext"], row["size"],
                row["method"], row["doc_type"], row["counterparty"], row["document_date"],
                row["amount"], row["currency"], row["amount_quote"], row["reference_id"],
                row["tax_related"], row["status"], row["review_reason"], row["ocr_confidence"],
                row["text_chars"], row["text_preview"], run_id, run_id,
            ),
        )
    for o in row.get("obligations", []):
        con.execute(
            """INSERT INTO obligations (sha256, kind, obligation_date, notice_days, action_date,
               derived, confidence, evidence_json) VALUES (?,?,?,?,?,?,?,?)""",
            (
                row["sha256"], o["kind"], o["obligation_date"], o["notice_days"],
                o["action_date"], int(o["derived"]), o["confidence"],
                json.dumps(o["evidence"]),
            ),
        )


def upsert_location(con: sqlite3.Connection, path: str, sha: str, folder: str,
                    size: int, mtime: float, run_id: int) -> None:
    con.execute(
        """INSERT INTO locations (path, sha256, folder, size, mtime, last_run)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(path) DO UPDATE SET sha256=excluded.sha256, folder=excluded.folder,
           size=excluded.size, mtime=excluded.mtime, last_run=excluded.last_run""",
        (path, sha, folder, size, mtime, run_id),
    )


def start_run(con: sqlite3.Connection, as_of: str, sources: list[str]) -> int:
    cur = con.execute(
        "INSERT INTO runs (started_at, as_of, sources_json) VALUES (datetime('now'), ?, ?)",
        (as_of, json.dumps(sources)),
    )
    con.commit()
    return int(cur.lastrowid)


def finish_run(con: sqlite3.Connection, run_id: int, stats: dict) -> None:
    con.execute(
        """UPDATE runs SET finished_at=datetime('now'), files_seen=?, files_new=?,
           files_unchanged=?, obligations=?, needs_review=?, source_unchanged=?,
           digest_path=?, log_json=? WHERE id=?""",
        (
            stats.get("files_seen", 0), stats.get("files_new", 0),
            stats.get("files_unchanged", 0), stats.get("obligations", 0),
            stats.get("needs_review", 0), int(stats.get("source_unchanged", False)),
            stats.get("digest_path"), json.dumps(stats.get("log", [])), run_id,
        ),
    )
    con.commit()
