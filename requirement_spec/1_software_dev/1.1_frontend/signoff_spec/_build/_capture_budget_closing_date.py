"""Render the Budget Closing Date MODULE page (demo) to screenshots + measure
marker coordinates via live getBoundingClientRect.

No backend/auth needed — page is self-contained (inline data + script; only
Google Fonts external). Source-of-truth = the module path below.

Outputs (into bin/):
  bcd_01_overview.png  (full page)
  bcd_02_editor.png    (add mode, year+date filled)
  bcd_03_records.png   (records table scrolled to top)
  bcd_04_edit.png      (edit mode -> UPDATE, form prefilled)
  bcd_05_save.png      (save success modal)
  bcd_06_delete.png    (delete confirm modal)
  bcd_coords.json      (computed marker lists per state, consumed by builder)
"""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

HTML = Path(
    r"c:\04.budget_management_web\03-edit-master-table\master-tables"
    r"\01frontend\budget-closing-date.html"
).as_uri()
OUT = Path(r"c:\04.budget_management_web") / "bin"
OUT.mkdir(exist_ok=True)

VW, VH = 1280, 860


# ---- marker-placement helpers (deterministic from rects) ------------------ #
def _c(v):
    return int(round(v))


def left(label, r, sy=0, shape=None):
    """Marker at left margin, leader pointing right into element's left edge."""
    cy = r["top"] + sy + r["height"] / 2
    cx = max(40 if shape == "pill" else 16, r["left"] - 44)
    m = {"label": label, "cx": _c(cx), "cy": _c(cy),
         "tx": _c(r["left"] + 8), "ty": _c(cy)}
    if shape:
        m["shape"] = shape
    return m


def leftof(label, r, sy=0, shape=None):
    """Marker sits just left of a right-aligned element."""
    cy = r["top"] + sy + r["height"] / 2
    cx = r["left"] - 40
    m = {"label": label, "cx": _c(cx), "cy": _c(cy),
         "tx": _c(r["left"] + 4), "ty": _c(cy)}
    if shape:
        m["shape"] = shape
    return m


def top(label, r, sy=0, shape=None):
    """Marker above element, leader pointing down into it."""
    cxv = r["left"] + r["width"] / 2
    cy = r["top"] + sy - 28
    ty = r["top"] + sy + min(r["height"] / 2, 14)
    m = {"label": label, "cx": _c(cxv), "cy": _c(cy),
         "tx": _c(cxv), "ty": _c(ty)}
    if shape:
        m["shape"] = shape
    return m


RECTS_JS = """(sels) => {
  const out = {};
  for (const [k, s] of Object.entries(sels)) {
    let el;
    if (s.startsWith('@')) el = document.querySelector(s.slice(1));
    else el = document.querySelector(s);
    if (!el) { out[k] = null; continue; }
    const r = el.getBoundingClientRect();
    out[k] = {left:r.left, top:r.top, width:r.width, height:r.height};
  }
  return out;
}"""


def rects(pg, sels):
    return pg.evaluate(RECTS_JS, sels)


coords = {}

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": VW, "height": VH}, device_scale_factor=1)

    def goto():
        pg.goto(HTML)
        try:
            pg.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        pg.wait_for_timeout(700)

    # 01 — overview (full page)
    goto()
    sy = pg.evaluate("window.scrollY")
    r = rects(pg, {
        "nav": ".nav",
        "head": ".breadcrumb",
        "usage": ".usage-hint",
        "summary": "#summaryStrip",
        "formhead": ".panel-form .panel-head",
        "recordshead": "@.panel:not(.panel-form) .panel-head",
    })
    coords["01"] = [
        left("1", r["nav"], sy),
        left("2", r["head"], sy),
        left("3", r["usage"], sy),
        leftof("4", r["summary"], sy),
        left("5", r["formhead"], sy),
        left("6", r["recordshead"], sy),
    ]
    pg.screenshot(path=str(OUT / "bcd_01_overview.png"), full_page=True)

    # 02 — editor (add mode), year + date filled
    pg.fill("#yearInput", "2028")
    pg.fill("#dateInput", "2027-11-26")
    pg.evaluate("window.scrollTo(0,0)")
    pg.wait_for_timeout(250)
    r = rects(pg, {
        "badge": "#modeBadge",
        "year": "#yearInput",
        "date": "#dateInput",
        "save": ".btn-save",
    })
    coords["02"] = [
        top("1.1", r["badge"], shape="pill"),
        left("1.2", r["year"], shape="pill"),
        left("1.3", r["date"], shape="pill"),
        top("1.4", r["save"], shape="pill"),
    ]
    pg.screenshot(path=str(OUT / "bcd_02_editor.png"))

    # 03 — records (scroll records panel to top)
    pg.fill("#yearInput", "")
    pg.fill("#dateInput", "")
    pg.evaluate("document.querySelectorAll('.panel')[1].scrollIntoView({block:'start'})")
    pg.wait_for_timeout(300)
    r = rects(pg, {
        "search": "#tableSearch",
        "count": ".count-pill",
        "yearhdr": "th[data-col='year']",
        "ratecell": "tbody tr .rate-cell",
        "edit": "tbody tr .action-btn.edit",
        "del": "tbody tr .action-btn.delete",
    })
    coords["03"] = [
        left("2.1", r["search"], shape="pill"),
        leftof("2.2", r["count"], shape="pill"),
        left("2.3", r["yearhdr"], shape="pill"),
        leftof("2.4", r["ratecell"], shape="pill"),
        top("2.5a", r["edit"], shape="pill"),
        top("2.5b", r["del"], shape="pill"),
    ]
    pg.screenshot(path=str(OUT / "bcd_03_records.png"))

    # 04 — edit mode (badge -> UPDATE, form prefilled)
    pg.evaluate("window.scrollTo(0,0)")
    pg.evaluate("editRecord(2026)")
    pg.wait_for_timeout(300)
    r = rects(pg, {"badge": "#modeBadge"})
    coords["04"] = [top("1.1", r["badge"], shape="pill")]
    pg.screenshot(path=str(OUT / "bcd_04_edit.png"))

    # 05 — save success modal
    goto()
    pg.fill("#yearInput", "2028")
    pg.fill("#dateInput", "2027-11-26")
    pg.evaluate("saveRecord()")
    pg.wait_for_timeout(400)
    r = rects(pg, {"title": "#noticeModal .modal-title"})
    coords["05"] = [top("3.1", r["title"], shape="pill")]
    pg.screenshot(path=str(OUT / "bcd_05_save.png"))

    # 06 — delete confirm modal
    goto()
    pg.evaluate("askDelete(2025)")
    pg.wait_for_timeout(300)
    r = rects(pg, {"title": "#confirmModal .modal-title"})
    coords["06"] = [top("3.2", r["title"], shape="pill")]
    pg.screenshot(path=str(OUT / "bcd_06_delete.png"))

    b.close()

(OUT / "bcd_coords.json").write_text(json.dumps(coords, indent=2), encoding="utf-8")

print("CAPTURE_DONE")
for n in ["bcd_01_overview", "bcd_02_editor", "bcd_03_records",
          "bcd_04_edit", "bcd_05_save", "bcd_06_delete"]:
    f = OUT / f"{n}.png"
    print(n, f.exists(), f.stat().st_size if f.exists() else 0)
print("coords:", json.dumps(coords))
