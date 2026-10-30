"""CLI: python -m chronovault {scan,digest,serve,demo,reset}"""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_VAULT = ROOT / "vault"
DEFAULT_SOURCES = [ROOT / "samples" / "nas" / "Documents", ROOT / "samples" / "nas" / "Photos"]
DEFAULT_AS_OF = dt.date(2026, 10, 30)


def _parse_date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="ChronoVault local reference prototype")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--source", action="append", type=Path, help="authorized folder (repeatable)")
        sp.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
        sp.add_argument("--as-of", type=_parse_date, default=DEFAULT_AS_OF, help="date used for days remaining")

    sp = sub.add_parser("scan", help="run the three-stage pipeline once")
    add_common(sp)
    sp = sub.add_parser("digest", help="print the Action Digest from the ledger")
    add_common(sp)
    sp = sub.add_parser("serve", help="serve the local dashboard")
    add_common(sp)
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--fresh", action="store_true", help="wipe the vault before serving")
    sp = sub.add_parser("demo", help="fresh vault + dashboard")
    add_common(sp)
    sp.add_argument("--port", type=int, default=8765)
    sp = sub.add_parser("reset", help="delete the vault folder (source files untouched)")
    sp.add_argument("--vault", type=Path, default=DEFAULT_VAULT)

    args = p.parse_args(argv)
    if args.cmd == "reset":
        shutil.rmtree(args.vault, ignore_errors=True)
        print(f"Removed {args.vault}")
        return 0

    sources = args.source or DEFAULT_SOURCES
    if args.source is None and not DEFAULT_SOURCES[0].exists():
        from samples.generate_samples import generate

        generate(ROOT / "samples" / "nas")

    if args.cmd == "scan":
        from .pipeline import run_scan

        rep = run_scan(sources, args.vault, args.as_of, progress=lambda e: print(f"[stage {e['stage']}] {e['msg']}"))
        print(f"Digest: {rep['outputs']['digest']}")
        return 0 if rep["source_unchanged"] else 1
    if args.cmd == "digest":
        from . import ledger
        from .digest import build_state, render_digest

        con = ledger.connect(args.vault / "vault.db")
        sys.stdout.write(render_digest(build_state(con, args.as_of)))
        return 0
    from .server import serve

    if args.cmd == "demo" or getattr(args, "fresh", False):
        shutil.rmtree(args.vault, ignore_errors=True)
    serve(sources, args.vault, args.as_of, args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
