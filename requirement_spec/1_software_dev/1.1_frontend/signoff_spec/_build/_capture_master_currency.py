"""Render the Master Currency MODULE page (demo) to screenshots (states).
No backend/auth needed — the page is self-contained (inline data + script;
only Google Fonts external). Page moved 2026-06-11 from the old mockup at
design/mockups/0009master-currency.html into the master-tables module as a DEMO
page (demo notice + 3 bug fixes). Source-of-truth = the module path below.
Output: mc_01..06 PNGs in bin/ for annotation by build_master_currency_spec.py.

NOTE: marker coords inside build_master_currency_spec.py were recomputed from
this page's live getBoundingClientRect via bin/_capture_mc_new.py (2026-06-11).
"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = Path(
    r"c:\04.budget_management_web\03-edit-master-table\master-tables"
    r"\01frontend\master-currency.html"
).as_uri()
OUT = Path(r"c:\04.budget_management_web") / "bin"
OUT.mkdir(exist_ok=True)

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1280, "height": 860}, device_scale_factor=1)

    def goto():
        pg.goto(HTML)
        try:
            pg.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        pg.wait_for_timeout(700)  # let Google fonts settle

    # 01 — overview (full page, seed data 2020-2026)
    goto()
    pg.screenshot(path=str(OUT / "mc_01_overview.png"), full_page=True)

    # 02 — editor with a year + rate filled (shows ฿ prefix / THB/USD suffix)
    pg.fill("#yearInput", "2027")
    pg.fill("#rateInput", "34.50")
    pg.evaluate("window.scrollTo(0,0)")
    pg.wait_for_timeout(250)
    pg.screenshot(path=str(OUT / "mc_02_editor.png"))

    # 03 — records table (scroll the records panel into view)
    pg.fill("#yearInput", "")
    pg.fill("#rateInput", "")
    pg.evaluate("document.querySelectorAll('.panel')[1].scrollIntoView({block:'start'})")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / "mc_03_records.png"))

    # 04 — edit mode (badge -> UPDATE, form prefilled)
    pg.evaluate("window.scrollTo(0,0)")
    pg.evaluate("editRecord(2024)")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / "mc_04_edit.png"))

    # 05 — save success notice modal
    goto()
    pg.fill("#yearInput", "2027")
    pg.fill("#rateInput", "34.50")
    pg.evaluate("saveRecord()")
    pg.wait_for_timeout(400)
    pg.screenshot(path=str(OUT / "mc_05_save.png"))

    # 06 — delete confirm modal
    goto()
    pg.evaluate("askDelete(2022)")
    pg.wait_for_timeout(300)
    pg.screenshot(path=str(OUT / "mc_06_delete.png"))

    b.close()

print("CAPTURE_DONE")
for n in ["mc_01_overview", "mc_02_editor", "mc_03_records", "mc_04_edit", "mc_05_save", "mc_06_delete"]:
    f = OUT / f"{n}.png"
    print(n, f.exists(), f.stat().st_size if f.exists() else 0)
