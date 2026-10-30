#!/usr/bin/env python3
"""Capture 1500x1000 gallery PNGs from the dashboard and static slides."""
from __future__ import annotations

import argparse
import datetime as dt
import shutil
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chronovault.pipeline import run_scan
from chronovault.server import App, make_handler
from samples.generate_samples import generate


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=ROOT / "dist" / "media" / "gallery")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    nas = generate(ROOT / "samples" / "nas")
    vault = ROOT / "vault_gallery"
    shutil.rmtree(vault, ignore_errors=True)
    sources = [nas / "Documents", nas / "Photos"]
    as_of = dt.date(2026, 10, 30)
    run_scan(sources, vault, as_of)

    app = App(sources, vault, as_of)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    port = httpd.server_address[1]
    base = f"http://127.0.0.1:{port}"

    media = ROOT / "tools" / "media"
    shots = [
        ("00_cover.png", media / "cover.html", None),
        ("09_architecture.png", media / "architecture.html", None),
        ("01_overview.png", f"{base}/", "overview"),
        ("03_deadline_math.png", f"{base}/", "overview-drawer"),
        ("04_receipt_ocr.png", f"{base}/", "receipt"),
        ("05_timeline.png", f"{base}/", "timeline"),
        ("06_privacy.png", f"{base}/", "privacy"),
        ("07_vault.png", f"{base}/", "vault"),
        ("08_needs_review.png", f"{base}/", "review"),
        ("02_scan_pipeline.png", f"{base}/", "scan"),
    ]

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1500, "height": 1000}, device_scale_factor=1)
        for name, target, mode in shots:
            out = args.out / name
            if str(target).endswith(".html"):
                page.goto(target.as_uri() if isinstance(target, Path) else target)
                page.wait_for_timeout(200)
                page.screenshot(path=str(out), type="png")
            else:
                page.goto(target)
                page.wait_for_selector(".card, .empty, table")
                if mode == "timeline":
                    page.click('button[data-view="timeline"]')
                    page.wait_for_timeout(300)
                elif mode == "privacy":
                    page.click('button[data-view="privacy"]')
                    page.wait_for_timeout(300)
                elif mode == "vault":
                    page.click('button[data-view="vault"]')
                    page.wait_for_timeout(300)
                elif mode == "review":
                    page.click('button[data-view="review"]')
                    page.wait_for_timeout(300)
                elif mode == "overview-drawer":
                    # open Lumora / earliest upcoming with notice
                    page.wait_for_selector(".item")
                    page.evaluate("""() => {
                      const items = [...document.querySelectorAll('.item')];
                      const hit = items.find(el => /notice/i.test(el.innerText)) || items[0];
                      hit.click();
                    }""")
                    page.wait_for_selector("#drawer:not([hidden]) .math, #drawer:not([hidden]) h2")
                    page.wait_for_timeout(200)
                elif mode == "receipt":
                    page.click('button[data-view="vault"]')
                    page.wait_for_timeout(200)
                    page.evaluate("""() => {
                      const rows = [...document.querySelectorAll('tr[data-sha]')];
                      const hit = rows.find(r => /vantage|receipt|png/i.test(r.innerText)) || rows[0];
                      hit.click();
                    }""")
                    page.wait_for_selector("#drawer:not([hidden])")
                    page.wait_for_timeout(400)
                elif mode == "scan":
                    page.evaluate("window.SCAN_PACE = 800")
                    page.click("#btnScan")
                    page.wait_for_selector("#modal:not([hidden])")
                    page.wait_for_timeout(900)
                page.screenshot(path=str(out), type="png")
            print(f"wrote {out} ({out.stat().st_size} bytes)")
        browser.close()
    httpd.shutdown()
    shutil.rmtree(vault, ignore_errors=True)
    # copy key shots into docs/
    docs = ROOT / "docs"
    docs.mkdir(exist_ok=True)
    for src, dst in [("01_overview.png", "overview.png"),
                     ("03_deadline_math.png", "deadline-math.png"),
                     ("09_architecture.png", "architecture.png")]:
        shutil.copy(args.out / src, docs / dst)


if __name__ == "__main__":
    main()
