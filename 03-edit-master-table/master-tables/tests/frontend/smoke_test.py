"""Smoke test for 0008 Hide Document Number page (multi-chip + free-text + validate).

Drives the page through every interaction the user added, screenshots at each
step, and prints PASS / FAIL per check.

Run:
    python 03-edit-master-table/0008-hide-document/04tests/smoke_test_0008.py
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
import functools
import http.server
import socketserver
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML_DIR = Path(__file__).resolve().parents[2] / "01frontend"
HTML_FILE = "hide-document.html"
OUT  = Path(__file__).resolve().parents[4] / "verify_0008"
OUT.mkdir(exist_ok=True)


def start_static_server(directory: Path) -> tuple[socketserver.TCPServer, int]:
    """Serve `directory` over HTTP on a random localhost port. Returns (server, port)."""
    Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(directory))
    # SO_REUSEADDR so we don't hit TIME_WAIT issues on rerun
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port

results: list[tuple[str, bool, str]] = []  # (name, passed, detail)


def check(name: str, passed: bool, detail: str = "") -> None:
    results.append((name, passed, detail))
    icon = "PASS" if passed else "FAIL"
    print(f"  [{icon}] {name}  {detail}")


def main() -> None:
    server, port = start_static_server(HTML_DIR)
    page_url = f"http://127.0.0.1:{port}/{HTML_FILE}"
    print(f"Serving page at: {page_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})

        console_errors: list[str] = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        page.on("pageerror", lambda err: console_errors.append(str(err)))

        # Mock ALL backend endpoints — backend is tested via
        # 0003-gl-group/02backend/test_hide_doc_e2e.py against real Fabric SQL DB.
        # Here we just confirm the frontend's request/response wiring is correct.
        import json as _json
        mock_db = []  # server-side rows: [{doc_num, fiscal_year, fiscal_month, period}]

        def mock_list(route):
            route.fulfill(status=200, content_type="application/json",
                          body=_json.dumps(list(mock_db)))

        def mock_save(route):
            body = route.request.post_data_json or {}
            triple = (body.get("doc_num"), body.get("fiscal_year"), body.get("fiscal_month"))
            existing = [(r["doc_num"], r["fiscal_year"], r["fiscal_month"]) for r in mock_db]
            if triple in existing:
                route.fulfill(status=409, content_type="application/json",
                              body=_json.dumps({"code": "DUPLICATE_KEY",
                                                "message_th": "ซ้ำ", "message_en": "duplicate"}))
                return
            mock_db.append({
                "doc_num": triple[0], "fiscal_year": triple[1], "fiscal_month": triple[2],
                "period": f"{triple[1]}-{triple[2]:02d}",
            })
            route.fulfill(status=200, content_type="application/json",
                          body=_json.dumps({"status": "success", "doc_num": triple[0],
                                            "period": f"{triple[1]}-{triple[2]:02d}"}))

        def mock_delete(route):
            body = route.request.post_data_json or {}
            triple = (body.get("doc_num"), body.get("fiscal_year"), body.get("fiscal_month"))
            before = len(mock_db)
            mock_db[:] = [r for r in mock_db if (r["doc_num"], r["fiscal_year"], r["fiscal_month"]) != triple]
            route.fulfill(status=200, content_type="application/json",
                          body=_json.dumps({"status": "deleted", "deleted": before - len(mock_db),
                                            "doc_num": triple[0],
                                            "period": f"{triple[1]}-{triple[2]:02d}"}))

        def mock_validate(route):
            body = route.request.post_data_json or {}
            codes = body.get("codes", [])
            route.fulfill(status=200, content_type="application/json",
                          body=_json.dumps({"valid": codes, "invalid": []}))

        page.route("**/api/master/hide-document/list",          mock_list)
        page.route("**/api/master/hide-document/save",          mock_save)
        page.route("**/api/master/hide-document/delete",        mock_delete)
        page.route("**/api/master/hide-document/validate-docs", mock_validate)

        page.goto(page_url)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(400)  # let init() run
        page.screenshot(path=OUT / "01_load.png", full_page=True)

        # ── 1. Type single doc + Enter ──
        page.locator("#glCodeInput").click()
        page.keyboard.type("5400005042")
        page.keyboard.press("Enter")
        page.wait_for_timeout(200)
        chips_after_1 = page.locator(".doc-chip").count()
        check("Type 5400005042 + Enter → 1 chip", chips_after_1 == 1, f"chips={chips_after_1}")
        page.screenshot(path=OUT / "02_one_chip.png", full_page=True)

        # ── 2. Paste multiple comma-separated ──
        page.evaluate("""
            const inp = document.getElementById('glCodeInput');
            const dt = new DataTransfer();
            dt.setData('text/plain', '5400005043,5400005044,5400005045');
            inp.focus();
            inp.dispatchEvent(new ClipboardEvent('paste', {
                clipboardData: dt, bubbles: true, cancelable: true,
            }));
        """)
        page.wait_for_timeout(200)
        chips_after_paste = page.locator(".doc-chip").count()
        check("Paste 3 comma-separated → 4 chips total", chips_after_paste == 4, f"chips={chips_after_paste}")
        page.screenshot(path=OUT / "03_after_paste.png", full_page=True)

        # ── 3. Type bad format ──
        page.locator("#glCodeInput").click()
        page.keyboard.type("12345")
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)
        helper_text = page.locator("#docInputHelper").inner_text()
        bad_caught = "Format" in helper_text or "ผิด" in helper_text
        check("Type 12345 + Enter → format error shown", bad_caught, f"helper='{helper_text[:60]}'")
        page.screenshot(path=OUT / "04_format_error.png", full_page=True)
        page.wait_for_timeout(1900)  # let error reset

        # ── 4. Clear input via JS then type duplicate ──
        # IMPORTANT: clear via JS to avoid Backspace popping a chip
        page.evaluate("document.getElementById('glCodeInput').value = ''")
        page.locator("#glCodeInput").click()
        page.keyboard.type("5400005042")
        page.keyboard.press("Enter")
        page.wait_for_timeout(100)
        helper_text2 = page.locator("#docInputHelper").inner_text()
        dup_caught = "มีอยู่" in helper_text2 or "list" in helper_text2.lower()
        chips_after_dup = page.locator(".doc-chip").count()
        check("Duplicate → reject + helper warns", dup_caught and chips_after_dup == 4,
              f"helper='{helper_text2[:60]}' chips={chips_after_dup}")
        page.wait_for_timeout(1900)

        # ── 5. Backspace on empty input removes last chip (just ONE) ──
        # Input is already empty (cleared by dup-reject path), so single Backspace pops 1
        page.locator("#glCodeInput").click()
        page.keyboard.press("Backspace")
        page.wait_for_timeout(200)
        chips_after_bs = page.locator(".doc-chip").count()
        check("Backspace on empty → removes last chip", chips_after_bs == 3, f"chips={chips_after_bs}")
        page.screenshot(path=OUT / "05_after_backspace.png", full_page=True)

        # ── 6. Save: 3 chips (5042, 5043, 5044) → backend gets 3 POST, then /list refresh ──
        # mock_db starts empty → masterData empty → 0 chip-cards initially
        cards_before  = page.locator(".chip-card").count()
        state = page.evaluate("({chips: selectedDocs.map(d => d.code)})")
        n = len(state["chips"])

        page.locator("#fiscalYearInput").fill("2026")
        page.locator("#monthInput").fill("3")
        page.locator(".btn-save").click()
        page.wait_for_selector("#noticeModal.open", timeout=5000)
        notice_msg = page.locator("#noticeMsg").inner_text()
        page.screenshot(path=OUT / "06_save_notice.png", full_page=True)
        save_ok = (f"{n} รายการ" in notice_msg) and ("Mar 2026" in notice_msg) and ("สร้าง 3" in notice_msg)
        check(f"Save → notice shows '{n} รายการ Mar 2026 (สร้าง 3)'", save_ok, f"msg='{notice_msg[:120]}'")

        # Close notice and verify list refreshed from mock_db with 3 rows in one period
        page.locator("#noticeModal .btn-back").click()
        page.wait_for_timeout(400)
        cards_after = page.locator(".chip-card").count()
        # Default view 'org' → 1 card per period → 1 new card (Mar 2026) holding 3 doc chips
        check("After save → 1 new Mar 2026 card",
              cards_after == cards_before + 1, f"before={cards_before} after={cards_after}")
        page.screenshot(path=OUT / "07_grid_after_save.png", full_page=True)

        # masterData should reflect server state: 3 rows under 2026-03
        rows_for_mar = page.evaluate("""
            masterData.filter(d => d.glGroup === '2026-03').map(d => d.glCode).sort()
        """)
        for expected in state["chips"]:
            ok = expected in rows_for_mar
            check(f"masterData has ({expected}, 2026-03) from server", ok, f"rows={rows_for_mar}")

        # ── 7. Console error check ──
        check("No console errors", len(console_errors) == 0,
              f"errors={console_errors[:3] if console_errors else '—'}")

        browser.close()
    server.shutdown()
    server.server_close()

    # ── Summary ──
    print()
    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    print(f"=== {passed}/{total} checks passed ===")
    if passed < total:
        print("\nFailures:")
        for name, ok, detail in results:
            if not ok:
                print(f"  - {name}  ({detail})")
    print(f"\nScreenshots: {OUT}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
