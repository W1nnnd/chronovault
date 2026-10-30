import datetime as dt
import socket

from chronovault.pipeline import run_scan


AS_OF = dt.date(2026, 10, 30)


def test_end_to_end_on_synthetic_vault(sources, tmp_path):
    rep = run_scan(sources, tmp_path / "vault", AS_OF)
    assert rep["files_seen"] == 13
    assert rep["source_unchanged"] is True
    assert rep["obligations"] >= 5
    assert rep["needs_review"] >= 2
    # Lumora act-by 15 Nov
    digest = open(rep["outputs"]["digest"]).read()
    assert "2026-11-15" in digest
    assert "Lumora" in digest


def test_incremental_second_run_skips_extraction(sources, tmp_path):
    vault = tmp_path / "vault"
    run_scan(sources, vault, AS_OF)
    rep2 = run_scan(sources, vault, AS_OF)
    assert rep2["files_new"] == 0
    assert rep2["files_unchanged"] == 13


def test_duplicate_primary_is_shallowest(sources, tmp_path):
    from chronovault import ledger
    from chronovault.digest import build_state

    vault = tmp_path / "vault"
    run_scan(sources, vault, AS_OF)
    con = ledger.connect(vault / "vault.db")
    row = con.execute(
        "SELECT primary_path FROM files WHERE name='brightfield_washer_warranty.pdf'").fetchone()
    assert "Inbox" in row["primary_path"]
    assert "Archive" not in row["primary_path"]
    st = build_state(con, AS_OF)
    item = next(i for i in st["items"] if "Brightfield" in (i["counterparty"] or "") or "washer" in i["name"])
    assert item["duplicate_paths"]


def test_damaged_pdf_in_needs_review(sources, tmp_path):
    from chronovault import ledger
    from chronovault.digest import build_state

    run_scan(sources, tmp_path / "vault", AS_OF)
    st = build_state(ledger.connect(tmp_path / "vault" / "vault.db"), AS_OF)
    names = [r["name"] for r in st["review"]]
    assert "locked_statement.pdf" in names


def test_scan_makes_no_network_calls(sources, tmp_path):
    real = socket.socket

    class Guard(real):
        def connect(self, *a, **k):  # noqa: ANN001
            raise AssertionError("network connect attempted during scan")

    socket.socket = Guard
    try:
        rep = run_scan(sources, tmp_path / "vault", AS_OF)
        assert rep["files_seen"] == 13
    finally:
        socket.socket = real
