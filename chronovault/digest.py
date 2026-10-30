"""Stage 3: deadline math, urgency buckets, Action Digest and JSON outputs."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from pathlib import Path

from .fields import ACTION_LABEL

BUCKETS = [("overdue", None, -1), ("critical", 0, 7), ("upcoming", 8, 30), ("planned", 31, 90)]
BUCKET_TITLE = {
    "overdue": "Overdue",
    "critical": "Critical (0-7 days)",
    "upcoming": "Upcoming (8-30 days)",
    "planned": "Planned (31-90 days)",
    "later": "Later (beyond 90 days)",
}
KIND_TITLE = {
    "renewal": "Auto-renewal",
    "expiry": "Term ends",
    "warranty_end": "Warranty ends",
    "payment_due": "Payment due",
    "filing_due": "Tax due",
    "subscription_renewal": "Plan renews",
}


def bucket_for(days: int) -> str:
    if days < 0:
        return "overdue"
    if days <= 7:
        return "critical"
    if days <= 30:
        return "upcoming"
    if days <= 90:
        return "planned"
    return "later"


def mask_ref(ref: str | None, doc_type: str | None) -> str | None:
    if not ref:
        return None
    if doc_type == "insurance" or (len(ref) >= 8 and ref[-4:].isdigit()):
        return "****" + ref[-4:]
    return ref


def display_path(path: str, sources: list[str] | None = None) -> str:
    p = Path(path)
    parts = p.parts
    for key in ("Documents", "Photos", "Inbox", "Archive", "Receipts"):
        if key in parts:
            i = parts.index(key)
            return str(Path(*parts[i:]))
    return p.name


def build_state(con: sqlite3.Connection, as_of: dt.date) -> dict:
    files = [dict(r) for r in con.execute("SELECT * FROM files ORDER BY name")]
    locs = [dict(r) for r in con.execute("SELECT * FROM locations")]
    obs = [dict(r) for r in con.execute(
        "SELECT o.*, f.name, f.counterparty, f.doc_type, f.primary_path, f.reference_id, f.amount, f.currency, f.text_preview "
        "FROM obligations o JOIN files f ON f.sha256=o.sha256 ORDER BY o.action_date"
    )]
    by_sha_locs: dict[str, list[str]] = {}
    for loc in locs:
        by_sha_locs.setdefault(loc["sha256"], []).append(loc["path"])

    items = []
    for o in obs:
        action = dt.date.fromisoformat(o["action_date"])
        days = (action - as_of).days
        evidence = json.loads(o["evidence_json"] or "[]")
        items.append({
            "id": o["id"],
            "sha256": o["sha256"],
            "kind": o["kind"],
            "kind_title": KIND_TITLE.get(o["kind"], o["kind"]),
            "action_label": ACTION_LABEL.get(o["kind"], "Act by"),
            "obligation_date": o["obligation_date"],
            "action_date": o["action_date"],
            "notice_days": o["notice_days"],
            "derived": bool(o["derived"]),
            "confidence": o["confidence"],
            "evidence": evidence,
            "days_remaining": days,
            "bucket": bucket_for(days),
            "name": o["name"],
            "counterparty": o["counterparty"],
            "doc_type": o["doc_type"],
            "primary_path": o["primary_path"],
            "display_path": display_path(o["primary_path"]),
            "reference_id": mask_ref(o["reference_id"], o["doc_type"]),
            "amount": o["amount"],
            "currency": o["currency"],
            "duplicate_paths": [display_path(p) for p in by_sha_locs.get(o["sha256"], []) if p != o["primary_path"]],
            "text_preview": o["text_preview"],
        })

    review = []
    for f in files:
        if f["status"] == "needs_review":
            review.append({
                "sha256": f["sha256"],
                "name": f["name"],
                "doc_type": f["doc_type"],
                "counterparty": f["counterparty"],
                "reason": f["review_reason"],
                "display_path": display_path(f["primary_path"]),
                "primary_path": f["primary_path"],
                "method": f["method"],
                "text_preview": f["text_preview"],
            })

    buckets = {k: [] for k in ["overdue", "critical", "upcoming", "planned", "later"]}
    for it in items:
        buckets[it["bucket"]].append(it)

    run = con.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "as_of": as_of.isoformat(),
        "counts": {
            "files": len(locs) if locs else len(files),
            "obligations": len(items),
            "needs_review": len(review),
            "critical": len(buckets["critical"]) + len(buckets["overdue"]),
            "upcoming": len(buckets["upcoming"]),
        },
        "buckets": buckets,
        "bucket_titles": BUCKET_TITLE,
        "items": items,
        "review": review,
        "files": [
            {
                **{k: f[k] for k in ("sha256", "name", "ext", "size", "method", "doc_type",
                                     "counterparty", "document_date", "amount", "currency",
                                     "status", "review_reason", "ocr_confidence")},
                "reference_id": mask_ref(f["reference_id"], f["doc_type"]),
                "display_path": display_path(f["primary_path"]),
                "primary_path": f["primary_path"],
                "duplicate_paths": [display_path(p) for p in by_sha_locs.get(f["sha256"], []) if p != f["primary_path"]],
                "text_preview": f["text_preview"],
            }
            for f in files
        ],
        "run": dict(run) if run else None,
    }


def render_digest(state: dict) -> str:
    as_of = state["as_of"]
    lines = [
        f"# ChronoVault Action Digest — {as_of}",
        "",
        f"Scanned **{state['counts']['files']}** files · "
        f"**{state['counts']['obligations']}** obligations · "
        f"**{state['counts']['needs_review']}** needs review.",
        "",
    ]
    for key in ("overdue", "critical", "upcoming", "planned"):
        items = state["buckets"].get(key) or []
        if not items:
            continue
        lines.append(f"## {BUCKET_TITLE[key]}")
        lines.append("")
        for it in items:
            who = it["counterparty"] or it["name"]
            notice = f" (notice {it['notice_days']}d)" if it["notice_days"] else ""
            lines.append(
                f"- **{it['action_date']}** — {it['action_label']} · {who} · "
                f"{it['kind_title']}{notice} · {it['days_remaining']}d · `{it['display_path']}`"
            )
            if it["evidence"]:
                lines.append(f"  - Evidence: “{it['evidence'][0]}”")
        lines.append("")

    if state["review"]:
        lines.append("## Needs Review")
        lines.append("")
        for r in state["review"]:
            lines.append(f"- `{r['display_path']}` — {r['reason']}")
        lines.append("")

    lines.append("## Ledger")
    lines.append("")
    lines.append("| Path | Type | Counterparty | Status | Ref |")
    lines.append("| :--- | :--- | :--- | :--- | :--- |")
    for f in state["files"]:
        lines.append(
            f"| `{f['display_path']}` | {f['doc_type']} | {f['counterparty'] or '—'} | "
            f"{f['status']} | {f['reference_id'] or '—'} |"
        )
    lines.append("")
    lines.append("_Originals were not moved, renamed or edited. Account numbers are masked._")
    return "\n".join(lines) + "\n"


def write_outputs(con: sqlite3.Connection, vault: Path, as_of: dt.date) -> dict[str, str]:
    state = build_state(con, as_of)
    reports = vault / "reports"
    ledger_dir = vault / "ledger"
    reports.mkdir(parents=True, exist_ok=True)
    ledger_dir.mkdir(parents=True, exist_ok=True)
    digest_path = reports / f"ChronoVault_Action_Digest_{as_of.isoformat()}.md"
    digest_path.write_text(render_digest(state), encoding="utf-8")
    alerts = {
        "as_of": as_of.isoformat(),
        "critical": state["buckets"]["critical"] + state["buckets"]["overdue"],
        "upcoming": state["buckets"]["upcoming"],
        "needs_review": state["review"],
    }
    (reports / "alerts.json").write_text(json.dumps(alerts, indent=2), encoding="utf-8")
    with (ledger_dir / "obligations.jsonl").open("w", encoding="utf-8") as f:
        for it in state["items"]:
            f.write(json.dumps(it) + "\n")
    (ledger_dir / "index_manifest.json").write_text(
        json.dumps({"as_of": as_of.isoformat(), "files": state["files"]}, indent=2),
        encoding="utf-8",
    )
    return {
        "digest": str(digest_path),
        "alerts": str(reports / "alerts.json"),
        "obligations": str(ledger_dir / "obligations.jsonl"),
        "manifest": str(ledger_dir / "index_manifest.json"),
    }
