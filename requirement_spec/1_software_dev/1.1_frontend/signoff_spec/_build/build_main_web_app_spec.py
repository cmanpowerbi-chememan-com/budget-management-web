# -*- coding: utf-8 -*-
"""
Generator — Main Budget Web App page · User Sign-off Specification (.docx).

ส่วน A · Module 01 — หน้าหลักของระบบงบประมาณ (OPEX Data Management).
ตารางงบประมาณรายเดือน: ส่วน SAP (Actuals) + ส่วน Pending (รออนุมัติ กรอกมือ)
พร้อม toolbar Export / Import approved budget (admins only).

DRAFT (ฉบับร่าง) — "ร่างตามนี้ก่อน" รายละเอียดเพิ่มเติมจะตามมา.

Reuses the OOXML + Pillow + Playwright pattern from build_special_gl_subform_spec.py
VERBATIM (OOXML helpers copied, capture()/annotate()/build_body()/main() shape kept).
New here: capture step targets the MAIN table page (not the modal) and computes gold
marker coordinates from live DOM getBoundingClientRect — no hand-tuned pixels.

HARD CONSTRAINTS:
  - NO package installation. stdlib + Pillow + Playwright (all installed).
  - .docx built by hand as WordprocessingML. Thai uses Leelawadee UI, szCs==sz.
  - Mockup source: design/mockups/0002claude design/0002budget-export.html
Re-runnable: overwrites screenshots (bin/, prefix main_), assets, and the .docx each run.
"""

import os, io, sys, zipfile, html, pathlib
from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

# Console may be cp1252 on Windows; PROOF lines print ①②③ — force UTF-8 stdout.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = r"c:\04.budget_management_web"
SIGNOFF_DIR = os.path.join(PROJECT_ROOT, "requirement_spec", "1_software_dev", "1.1_frontend", "signoff_spec")
ASSETS_DIR = os.path.join(SIGNOFF_DIR, "assets")
BIN_DIR = os.path.join(PROJECT_ROOT, "bin")
DOCX_PATH = os.path.join(SIGNOFF_DIR, "01_main_web_app_spec.docx")
MOCKUP = pathlib.Path(PROJECT_ROOT, "design", "mockups", "0002claude design", "0002.1budget-export.html")
# Master Currency edit page (Module 09) — separate master-tables HTML, self-contained demo
# data (FY2025 = 35.00, matches the OPEX read-only FX chip). Captured for §15 as the place
# where Master FX is actually edited.
MC_PAGE = pathlib.Path(PROJECT_ROOT, "03-edit-master-table", "master-tables", "01frontend", "master-currency.html")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(BIN_DIR, exist_ok=True)

GOLD = (201, 150, 61); GOLD_DARK = (140, 100, 35); WHITE = (255, 255, 255)
# Per-marker accent colors (FIX A — SAP markers only; everything else stays GOLD).
RED = (211, 47, 47); RED_DARK = (142, 27, 27)        # SAP status badge   (marker ①)
GREEN = (46, 125, 50); GREEN_DARK = (27, 94, 32)     # SAP green value     (marker ②)
NUM_FONT_PATH = r"C:\Windows\Fonts\arialbd.ttf"
THAI_FONT = "Leelawadee UI"
SCALE = 2  # device_scale_factor


# --------------------------------------------------------------------------- #
# CAPTURE — screenshot the main page + read element rects for gold markers.
# Returns {key: (img_path, markers)} where markers are in image-pixel space.
# --------------------------------------------------------------------------- #
def _markers_from_rects(points, rects, base_box, colors=None):
    """Convert page rects -> image-pixel markers relative to a screenshotted box.

    colors (optional): list parallel to `points`; each item is a (fill, outline)
    tuple OR None. None / missing -> default GOLD (so every other illustration is
    unchanged). FIX A passes RED for the SAP status marker and GREEN for the SAP
    value marker only. Each marker also records the rect box it anchors to
    (ex/ey/ew/eh) so the proof step can assert the leader endpoint lands inside it.
    """
    markers = []
    for i, ((label, _), r) in enumerate(zip(points, rects)):
        if not r:
            continue
        ex = (r["x"] - base_box["x"]) * SCALE; ey = (r["y"] - base_box["y"]) * SCALE
        ew = r["w"] * SCALE; eh = r["h"] * SCALE
        if ex > 70:  # place circle to the LEFT of the element
            cx, cy, tx, ty = ex - 30, ey + eh / 2, ex, ey + eh / 2
        elif ey > 70:  # place ABOVE
            cx, cy, tx, ty = ex + ew / 2, ey - 28, ex + ew / 2, ey
        else:  # too close to both edges -> place BELOW
            cx, cy, tx, ty = ex + ew / 2, ey + eh + 28, ex + ew / 2, ey + eh
        # Pull the leader endpoint a few px INSIDE the element box (clamped) so the
        # dot visibly touches the cell and the proof's inside-box check is exact.
        ins = 4
        tx = min(max(tx, ex + ins), ex + ew - ins)
        ty = min(max(ty, ey + ins), ey + eh - ins)
        col = (colors[i] if colors and i < len(colors) and colors[i] else (GOLD, GOLD_DARK))
        markers.append({"label": label, "cx": cx, "cy": cy, "tx": tx, "ty": ty,
                        "fill": col[0], "dark": col[1],
                        "ex": ex, "ey": ey, "ew": ew, "eh": eh})
    return markers


RECT_JS = """(sels)=>sels.map(s=>{const e=document.querySelector(s);
    if(!e)return null;const r=e.getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};})"""


def capture():
    out = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1700, "height": 1180}, device_scale_factor=SCALE)
        pg.goto(MOCKUP.as_uri()); pg.wait_for_selector(".data-table tbody tr")
        pg.wait_for_timeout(300)
        # Pin the year filter to the SEED data year (2025) for capture only — the mockup's REAL
        # default is FY2026 (current year), but the demo transactions are seeded in 2025, so the
        # illustration rows (txn ids the markers anchor to) only render when the view = 2025.
        # This does NOT change the documented default (2026); it just makes screenshots non-empty.
        pg.select_option("#yearFilter", "2025"); pg.wait_for_timeout(200)

        # ── helpers (NEW 2026-06-13) — drive the new wired mockup ──
        #   The page locks to ONE ฝ่าย (department) = the approval unit (ADR-0008) via the
        #   ฝ่าย-picker (#faiPicker — NOT a <select>). Lock programmatically with pickDept().
        #   Overlay admins (นิภาพร/วราพร) default to their base role; the 🛡️ "โหมด Admin" toggle
        #   (#adminModeChk → onAdminModeToggle()) switches them into admin powers (sees-all, FX
        #   display, admin-zone). Pure admin jakkaritw is always admin (no toggle).
        def use_user(key):
            pg.evaluate(f"switchUser('{key}')"); pg.wait_for_timeout(150)
        def admin_on():
            pg.evaluate("var c=document.getElementById('adminModeChk'); if(c){c.checked=true; onAdminModeToggle();}")
            pg.wait_for_timeout(150)
        def lock_dept(dept):
            pg.evaluate(f"pickDept({dept!r})"); pg.wait_for_timeout(150)
        def set_status(dept, status):  # drive edit-lock states for the locked-pending capture
            pg.evaluate(f"DEPT_STATUS[{dept!r}]={status!r}; renderTable();"); pg.wait_for_timeout(150)

        # ── 0) LOGIN BAR — two role views (V3 hierarchy) ──
        #     <section id="userBar"> shows WHO is logged in and the scope (avatar, name,
        #     ADMIN/USER/APPROVER badge, สายงาน › ฝ่าย(n) › Cost Centers(n), email in the
        #     switcher). Captured twice: an admin (jakkaritw — always sees all CC) and a
        #     normal submitter (suchanya — scoped to her own ฝ่าย). No markers (annotate []).
        #     The real app has NO user-switcher — the demo switcher only shows both views here.
        # LOGIN BAR — admin (sees all CC) = jakkaritw (pure admin, always-on)
        use_user("jakkaritw")
        ub = pg.locator("#userBar").first
        la_path = os.path.join(BIN_DIR, "main_login_admin.png")
        ub.screenshot(path=la_path)
        out["login_admin"] = (la_path, [])
        # LOGIN BAR — normal submitter (suchanya · L3 Solution Delivery, scoped to own ฝ่าย)
        use_user("suchanya")
        ub2 = pg.locator("#userBar").first
        lu_path = os.path.join(BIN_DIR, "main_login_user.png")
        ub2.screenshot(path=lu_path)
        out["login_user"] = (lu_path, [])

        # remaining table captures stay as submitter suchanya, locked to her own ฝ่าย
        # "Solution Delivery" (status DRAFT → Pending cells editable, special row shows the
        # detail button). All txn-ids used below (1/5) belong to that ฝ่าย so they render.
        use_user("suchanya")
        lock_dept("Solution Delivery")

        # ── 1) OVERVIEW — whole table panel (SAP + Approved + Pending rows) ──
        #     All markers anchor to ONE row group (data-txn-id="1" = Solution Delivery /
        #     10IT012000 / GL 6211800030 Office expenses — a NORMAL GL with SAP + Approved +
        #     Pending data), except marker 4 which points at the Jan Pending input cell of the
        #     SAME normal row (editable because suchanya = submitter, ฝ่าย status DRAFT).
        #     Labels travel WITH the selector via zip(), so marker "N" == the Nth selector.
        #       1 = SAP green value     (.month-value.sap, txn 1) — Actuals read-only
        #       2 = APPROVED blue value (.month-value.approved-ro, txn 1) — read-only, Import-only
        #       3 = PENDING input cell  (.month-value.pending-input, txn 1 — Aug has a value) — normal GL, user types
        #       4 = PENDING input cell  (.month-value.pending-input, txn 1 Jan) — leftmost editable cell
        panel = pg.locator(".table-panel").first
        pbox = panel.bounding_box()
        ov_points = [
            ("1", 'tr[data-status="sap"][data-txn-id="1"] .month-value.sap'),
            ("2", 'tr[data-status="approved"][data-txn-id="1"] .month-value.approved-ro'),
            ("3", 'tr[data-status="pending"][data-txn-id="1"] .month-value.pending-input[data-i="7"]'),
            # marker 4: leftmost editable Pending cell (Jan, data-i="0") of the same normal row.
            ("4", 'tr[data-status="pending"][data-txn-id="1"] .month-value.pending-input[data-i="0"]'),
        ]
        ov_rects = pg.evaluate(RECT_JS, [s for _, s in ov_points])
        ov_path = os.path.join(BIN_DIR, "main_overview.png")
        panel.screenshot(path=ov_path)
        out["overview"] = (ov_path, _markers_from_rects(ov_points, ov_rects, pbox))

        # ── 2) TOOLBAR — filters + user-action buttons (NEW DOM 2026-06-13) ──
        #     The old <select id="divisionFilter"> is GONE — replaced by the custom ฝ่าย-picker
        #     (#faiPicker, see capture 2c). The toolbar now holds: year filter, ฝ่าย-picker
        #     trigger, + เพิ่ม Transaction, and แนบไฟล์ (attach to SharePoint per ฝ่าย/ปี).
        #     Export/Import Approved live in a separate admin-zone (capture 2b).
        #       ① #yearFilter · ② #faipTrig (ฝ่าย-picker trigger) · ③ .btn-add · ④ .btn-attach
        tb = pg.locator(".toolbar").first
        tbox = tb.bounding_box()
        tb_points = [("1", "#yearFilter"), ("2", "#faipTrig"), ("3", ".btn-add"), ("4", ".btn-attach")]
        tb_rects = pg.evaluate(RECT_JS, [s for _, s in tb_points])
        tb_path = os.path.join(BIN_DIR, "main_toolbar.png")
        tb.screenshot(path=tb_path)
        out["toolbar"] = (tb_path, _markers_from_rects(tb_points, tb_rects, tbox))

        # ── 2b) ADMIN ZONE — Approved board_budget Import/Export + READ-ONLY Master FX ──
        #     Separate bar above the table, admin-only (hidden for normal users). Carries the
        #     warning that Import/Export act on the WHOLE year / company per the CSV file — NOT
        #     scoped by the view filters — plus the READ-ONLY Master FX display (owned by
        #     Module 09, recompute-on-read, ADR-0015). Switch to an admin to make it visible.
        #       ① .btn-import · ② .btn-export · ③ #fxDisplay (read-only Master FX)
        use_user("jakkaritw")   # pure admin → admin-zone + FX visible without a toggle
        az = pg.locator(".admin-zone").first
        azbox = az.bounding_box()
        az_points = [("1", ".admin-zone .btn-import"), ("2", ".admin-zone .btn-export"), ("3", "#fxDisplay")]
        az_rects = pg.evaluate(RECT_JS, [s for _, s in az_points])
        az_path = os.path.join(BIN_DIR, "main_admin_zone.png")
        az.screenshot(path=az_path)
        out["admin_zone"] = (az_path, _markers_from_rects(az_points, az_rects, azbox))

        # ── 2b-2) MASTER FX (read-only) — TIGHT crop for §15 ──
        #     The whole FX chip "💱 Master FX (USD→THB · FY2025): 35.00 (read-only)" — i.e. the
        #     .admin-zone-note span that WRAPS #fxDisplay (USD→THB read-only, owned by Module 09,
        #     recompute-on-read · ADR-0015). #fxDisplay alone is only the bold number, and there
        #     are TWO .admin-zone-note spans (warning + FX) so we anchor via closest() on the
        #     unique #fxDisplay. Admin-only — jakkaritw (pure admin) is still active from 2b. No
        #     markers: §15 uses bullet points, not a numbered table (matches login-bar captures).
        fx_rect = pg.evaluate(
            "()=>{const e=document.getElementById('fxDisplay').closest('.admin-zone-note');"
            "const r=e.getBoundingClientRect();return {x:r.left,y:r.top,w:r.width,h:r.height};}")
        fxpad = 16
        fx_box = {"x": fx_rect["x"] - fxpad, "y": fx_rect["y"] - fxpad,
                  "w": fx_rect["w"] + fxpad * 2, "h": fx_rect["h"] + fxpad * 2}
        fx_path = os.path.join(BIN_DIR, "main_fx_only.png")
        pg.screenshot(path=fx_path, clip={"x": fx_box["x"], "y": fx_box["y"],
                                          "width": fx_box["w"], "height": fx_box["h"]})
        out["fx_only"] = (fx_path, [])

        # ── 2c) ฝ่าย-PICKER (open) — approver view with รออนุมัติ / อนุมัติแล้ว badges (NEW) ──
        #     The ฝ่าย-picker replaces the division filter (ADR-0008). For approvers each ฝ่าย
        #     carries a รออนุมัติ (wait) / อนุมัติแล้ว (done) badge + a "เฉพาะที่รออนุมัติ" toggle to
        #     trim to their queue. We open the panel as approver นิภาพร (base approver role, no
        #     admin hat) and seed one ฝ่าย into PENDING_APPROVER2 so a wait badge shows.
        #       ① #faipPanel (the open picker) · ② #faipOnlyWait (queue toggle)
        use_user("nipaporn")    # base role = approver (step 2); admin hat OFF
        set_status("Solution Delivery", "PENDING_APPROVER2")   # → นิภาพร's turn (wait badge)
        pg.evaluate("toggleFaiPanel()"); pg.wait_for_timeout(250)
        # The panel is position:absolute (overflows the #faiPicker wrapper) → screenshot the
        # PANEL element itself and anchor markers to its children: ① ฝ่าย list · ② queue toggle.
        fp = pg.locator("#faipPanel").first
        fpbox = fp.bounding_box()
        fp_points = [("1", "#faipList"), ("2", "#faipOnlyWait")]
        fp_rects = pg.evaluate(RECT_JS, [s for _, s in fp_points])
        fp_path = os.path.join(BIN_DIR, "main_fai_picker.png")
        fp.screenshot(path=fp_path)
        out["fai_picker"] = (fp_path, _markers_from_rects(fp_points, fp_rects, fpbox))
        pg.evaluate("toggleFaiPanel()"); pg.wait_for_timeout(120)   # close panel

        # ── 2d) ACTION BAR — approver (อนุมัติ / ตีกลับ) ──
        #     #actionBar buttons depend on the SELECTED ฝ่าย, not the role: อนุมัติ/ตีกลับ show
        #     when the ฝ่าย is at the current user's approval step. นิภาพร + Solution Delivery
        #     (seeded PENDING_APPROVER2 above) = นิภาพร's turn → both buttons visible.
        #       ① #approveBtn · ② #rejectBtn
        lock_dept("Solution Delivery"); pg.wait_for_timeout(120)
        abar = pg.locator("#actionBar").first
        abbox = abar.bounding_box()
        ab_points = [("1", "#approveBtn"), ("2", "#rejectBtn")]
        ab_rects = pg.evaluate(RECT_JS, [s for _, s in ab_points])
        ab_path = os.path.join(BIN_DIR, "main_action_approver.png")
        abar.screenshot(path=ab_path)
        out["action_approver"] = (ab_path, _markers_from_rects(ab_points, ab_rects, abbox))

        # ── 2e) ADMIN-MODE toggle (overlay admin) — base role ↔ admin hat (ADR-0014) ──
        #     นิภาพร is an overlay admin: defaults to her approver role, switches into admin
        #     powers via the 🛡️ "โหมด Admin" toggle in the nav. Captured as a tight crop of the
        #     nav actions so the toggle reads large.   ① #adminModeWrap (the toggle)
        use_user("nipaporn"); pg.wait_for_timeout(120)   # reset to base role (toggle OFF, visible)
        amw_rect = pg.evaluate(RECT_JS, ["#adminModeWrap"])[0]
        pad = 18
        amw_box = {"x": amw_rect["x"] - pad, "y": amw_rect["y"] - pad,
                   "w": amw_rect["w"] + pad * 2, "h": amw_rect["h"] + pad * 2}
        amw_path = os.path.join(BIN_DIR, "main_admin_mode.png")
        pg.screenshot(path=amw_path, clip={"x": amw_box["x"], "y": amw_box["y"],
                                           "width": amw_box["w"], "height": amw_box["h"]})
        out["admin_mode"] = (amw_path, _markers_from_rects(
            [("1", "#adminModeWrap")], [amw_rect], amw_box))

        # ── 2f) EDIT-LOCK — a locked Pending row after Submit (ADR-0013 × role) ──
        #     A submitter (suchanya) viewing her ฝ่าย once it has entered the chain
        #     (PENDING_APPROVER1) sees the Pending cells LOCKED (read-only) with a 🔒 hint —
        #     editing never changes status; status only moves via Submit/Approve/Reject.
        #       ① status-cell.pending (carries the 🔒 lock hint) · ② .month-value.pending-readonly (Jan)
        use_user("suchanya")
        set_status("Solution Delivery", "PENDING_APPROVER1")   # submitter → locked
        lock_dept("Solution Delivery"); pg.wait_for_timeout(150)
        lock_points = [
            ("1", 'tr[data-status="pending"][data-txn-id="1"] .status-cell.pending'),
            ("2", 'tr[data-status="pending"][data-txn-id="1"] .month-value.pending-readonly[data-i="0"]'),
        ]
        # the locked normal-GL pending cell has no data-i attr; fall back to first readonly cell
        lock_points[1] = ("2", 'tr[data-status="pending"][data-txn-id="1"] .month-value.pending-readonly')
        lock_rects = pg.evaluate(RECT_JS, [s for _, s in lock_points])
        lock_main = pg.locator(".table-panel").first
        lkbox = lock_main.bounding_box()
        lock_path = os.path.join(BIN_DIR, "main_edit_lock.png")
        lock_main.screenshot(path=lock_path)
        out["edit_lock"] = (lock_path, _markers_from_rects(lock_points, lock_rects, lkbox))
        set_status("Solution Delivery", "DRAFT")   # restore for the captures below

        # back to submitter suchanya, DRAFT (editable) for the SAP / Approved / Pending / detail captures
        use_user("suchanya")
        lock_dept("Solution Delivery")

        # ── 3) SAP COLUMNS (Actuals) — tight crop so the two markers read large ──
        #     base_box = union of the SAP status badge + the SAP first month value cell of
        #     txn-id 1 (Solution Delivery, normal GL, has SAP actuals), padded, single row.
        #       ① = SAP status badge (.status-cell.sap, txn 1) → RED   (status colour)
        #       ② = SAP green value  (.month-value.sap,  txn 1) → GREEN (value colour)
        sap_points = [
            ("1", 'tr[data-status="sap"][data-txn-id="1"] .status-cell.sap'),
            ("2", 'tr[data-status="sap"][data-txn-id="1"] .month-value.sap'),
        ]
        sap_rects = pg.evaluate(RECT_JS, [s for _, s in sap_points])
        rs, rv = sap_rects[0], sap_rects[1]   # status rect, value rect
        # Union box of the two anchors + padding; clamp height to a single SAP row.
        pad = 26
        clip_x = min(rs["x"], rv["x"]) - pad
        clip_y = min(rs["y"], rv["y"]) - pad
        clip_r = max(rs["x"] + rs["w"], rv["x"] + rv["w"]) + pad
        clip_b = max(rs["y"] + rs["h"], rv["y"] + rv["h"]) + pad
        sap_box = {"x": clip_x, "y": clip_y, "w": clip_r - clip_x, "h": clip_b - clip_y}
        sap_path = os.path.join(BIN_DIR, "main_sap_columns.png")
        pg.screenshot(path=sap_path, clip={"x": sap_box["x"], "y": sap_box["y"],
                                           "width": sap_box["w"], "height": sap_box["h"]})
        out["sap"] = (sap_path, _markers_from_rects(
            sap_points, sap_rects, sap_box, colors=[(RED, RED_DARK), (GREEN, GREEN_DARK)]))

        # ── 3b) APPROVED · งบ (สีฟ้า · READ-ONLY) + Import path — UPDATED 2026-06-12 ──
        #     Approved is now READ-ONLY on the web (board_budget). It is NEVER typed in
        #     the grid and has NO per-cell submit — the ONLY write path is Import Approved
        #     Budget (whole-year CSV, Replace-by-Year) in the admin-zone. So this image
        #     pairs the read-only Approved cell with the Import button that sets it.
        #       ① = APPROVED read-only cell (.month-value.approved-ro, txn 1, blue, no input)
        #       ② = Import Approved Budget button (.admin-zone .btn-import) — the write path.
        #     NB: .admin-zone is hidden for the submitter suchanya (admin-only). We flip the
        #     pure-admin jakkaritw on temporarily so BOTH the read-only cell AND the Import
        #     button render in the SAME <main> screenshot, then switch back. jakkaritw sees all
        #     CC, so we lock to Solution Delivery again to keep txn-id 1 in view.
        use_user("jakkaritw"); lock_dept("Solution Delivery"); pg.wait_for_timeout(150)
        appr_points = [
            ("1", 'tr[data-status="approved"][data-txn-id="1"] .month-value.approved-ro'),
            ("2", ".admin-zone .btn-import"),
        ]
        appr_rects = pg.evaluate(RECT_JS, [s for _, s in appr_points])
        appr_main = pg.locator("main.wrap").first
        ambox = appr_main.bounding_box()
        appr_path = os.path.join(BIN_DIR, "main_approved_submit.png")
        appr_main.screenshot(path=appr_path)
        out["approved"] = (appr_path, _markers_from_rects(appr_points, appr_rects, ambox))
        # back to submitter suchanya · DRAFT for the editable Pending + detail captures
        use_user("suchanya"); lock_dept("Solution Delivery")

        # ── 4) PENDING input cells + Submit button ──
        #     Pending row of a NORMAL GL (txn id 1, Solution Delivery) has editable
        #     .pending-input fields because suchanya = submitter and the ฝ่าย is DRAFT. The
        #     #submitBtn is visible (ฝ่าย ∈ her fill-scope). Pinned to txn-id 1 for determinism.
        #       ① status-cell.pending · ② first .month-value.pending-input (Jan) · ③ #submitBtn
        pend_points = [
            ("1", 'tr[data-status="pending"][data-txn-id="1"] .status-cell.pending'),
            ("2", 'tr[data-status="pending"][data-txn-id="1"] .month-value.pending-input[data-i="0"]'),
            ("3", "#submitBtn"),
        ]
        pend_rects = pg.evaluate(RECT_JS, [s for _, s in pend_points])
        # screenshot the <main> region so both pending row and submit button fit
        main_el = pg.locator("main.wrap").first
        mbox = main_el.bounding_box()
        pend_path = os.path.join(BIN_DIR, "main_pending_submit.png")
        main_el.screenshot(path=pend_path)
        out["pending"] = (pend_path, _markers_from_rects(pend_points, pend_rects, mbox))

        # ── 5) SPECIAL GL — "+ ใส่รายละเอียดงบทำการ" detail entry button (ref to doc 02) ──
        #     Both detail markers on the SAME special-GL row = txn-id 5 · 10IT012000 /
        #     GL 6210700030 / group 'Professional & Legal Fee' (Solution Delivery, visible to
        #     suchanya). It is a Special GL group, so its Pending <tr> renders the .btn-detail
        #     button THEN twelve grey .month-value.pending-readonly cells (isSpec branch). The
        #     button is the editable form (suchanya = submitter, ฝ่าย DRAFT → not the 🔒 variant).
        #       ① = .btn-detail ("+ ใส่รายละเอียดงบทำการ") → RED   (opens subform — doc 02)
        #       ② = leftmost .month-value.pending-readonly cell (the grey "–" box right
        #           of the button = ม.ค./Jan, document order) → GREEN (read-only sum back).
        #     querySelector on the row returns the FIRST pending-readonly cell = Jan
        #     deterministically (the 12 cells follow the button td in document order).
        det_points = [
            ("1", 'tr[data-status="pending"].special[data-txn-id="5"] .btn-detail'),
            ("2", 'tr[data-status="pending"].special[data-txn-id="5"] .month-value.pending-readonly'),
        ]
        det_rects = pg.evaluate(RECT_JS, [s for _, s in det_points])
        det_path = os.path.join(BIN_DIR, "main_special_detail.png")
        panel.screenshot(path=det_path)
        out["detail"] = (det_path, _markers_from_rects(
            det_points, det_rects, pbox, colors=[(RED, RED_DARK), (GREEN, GREEN_DARK)]))

        # ── 15-ref) MASTER CURRENCY PAGE (Module 09) — where Master FX is actually edited ──
        #     Companion to the read-only FX crop (§15). Separate self-contained HTML (master-
        #     tables module) — seed FY2025 = 35.00 matches the OPEX chip. Screenshot the
        #     <main class="wrap"> content (header + edit form + records table), no nav chrome,
        #     no markers. Last capture: it navigates AWAY from the OPEX mockup, so keep it here.
        pg.goto(MC_PAGE.as_uri()); pg.wait_for_selector(".data-table tbody tr")
        pg.wait_for_timeout(300)
        mc_main = pg.locator("main.wrap").first
        mc_path = os.path.join(BIN_DIR, "main_master_currency_page.png")
        mc_main.screenshot(path=mc_path)
        out["mc_page"] = (mc_path, [])

        b.close()
    return out


# ---------------- Pillow annotation (verbatim from reference) ---------------- #
def _num_font(s):
    try: return ImageFont.truetype(NUM_FONT_PATH, s)
    except Exception: return ImageFont.load_default()

def _leader(draw, cx, cy, tx, ty, radius, fill=GOLD, dark=GOLD_DARK):
    import math
    dx, dy = tx-cx, ty-cy; dist = math.hypot(dx, dy)
    if dist < 1: return
    ux, uy = dx/dist, dy/dist; sx, sy = cx+ux*(radius+1), cy+uy*(radius+1)
    draw.line([(sx+1, sy+1), (tx+1, ty+1)], fill=dark, width=2)
    draw.line([(sx, sy), (tx, ty)], fill=fill, width=2)
    draw.ellipse([tx-3, ty-3, tx+3, ty+3], fill=fill, outline=dark)

def _circle(draw, label, cx, cy, tx, ty, radius=18, fill=GOLD, dark=GOLD_DARK):
    _leader(draw, cx, cy, tx, ty, radius, fill=fill, dark=dark)
    draw.ellipse([cx-radius+2, cy-radius+2, cx+radius+2, cy+radius+2], fill=(0, 0, 0, 60))
    draw.ellipse([cx-radius, cy-radius, cx+radius, cy+radius], fill=fill, outline=dark, width=2)
    f = _num_font(radius+4); bb = draw.textbbox((0, 0), label, font=f)
    tw, th = bb[2]-bb[0], bb[3]-bb[1]
    draw.text((cx-tw/2-bb[0], cy-th/2-bb[1]), label, fill=WHITE, font=f)

def annotate(src_path, out_name, markers):
    im = Image.open(src_path).convert("RGBA")
    ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); dr = ImageDraw.Draw(ov)
    for m in markers:
        _circle(dr, m["label"], m["cx"], m["cy"], m["tx"], m["ty"],
                fill=m.get("fill", GOLD), dark=m.get("dark", GOLD_DARK))
    out = Image.alpha_composite(im, ov).convert("RGB")
    op = os.path.join(ASSETS_DIR, out_name); out.save(op, "PNG")
    return op, out.size


# ---------------- OOXML helpers (verbatim from reference) ---------------- #
EMU_PER_IN = 914400; TARGET_WIDTH_IN = 6.3
def esc(t): return html.escape(str(t), quote=True)
def run_props(sz, bold=False, color=None, italic=False):
    p = ['<w:rPr>', f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>']
    if bold: p.append('<w:b/><w:bCs/>')
    if italic: p.append('<w:i/><w:iCs/>')
    if color: p.append(f'<w:color w:val="{color}"/>')
    p.append(f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/></w:rPr>'); return "".join(p)
def run(t, sz=22, bold=False, color=None, italic=False):
    return f'<w:r>{run_props(sz, bold, color, italic)}<w:t xml:space="preserve">{esc(t)}</w:t></w:r>'
def para(rx, align=None, space_before=0, space_after=120, shading=None, keep_next=False):
    pp = ['<w:pPr>', f'<w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>',
          f'<w:spacing w:before="{space_before}" w:after="{space_after}"/>']
    if align: pp.append(f'<w:jc w:val="{align}"/>')
    if shading: pp.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{shading}"/>')
    if keep_next: pp.append('<w:keepNext/>')
    pp.append('</w:pPr>'); return f'<w:p>{"".join(pp)}{rx}</w:p>'
def heading(t, sz=30, color="2F6B3F", space_before=240, space_after=120):
    return para(run(t, sz=sz, bold=True, color=color), space_before=space_before, space_after=space_after, keep_next=True)
def body_para(t, sz=22, space_after=120): return para(run(t, sz=sz), space_after=space_after)
def bullet(t, sz=22): return para(run("•  "+t, sz=sz), space_after=60)
def image_para(rid, px_w, px_h, doc_pr_id, name, width_in=None):
    cx = int((width_in or TARGET_WIDTH_IN)*EMU_PER_IN); cy = int(cx*(px_h/px_w))
    d = f'''<w:r><w:rPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/></w:rPr><w:drawing>
<wp:inline distT="0" distB="0" distL="0" distR="0" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
<wp:extent cx="{cx}" cy="{cy}"/><wp:effectExtent l="0" t="0" r="0" b="0"/><wp:docPr id="{doc_pr_id}" name="{esc(name)}"/>
<wp:cNvGraphicFramePr><a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/></wp:cNvGraphicFramePr>
<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="{doc_pr_id}" name="{esc(name)}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>'''
    pp = (f'<w:pPr><w:rFonts w:ascii="{THAI_FONT}" w:hAnsi="{THAI_FONT}" w:cs="{THAI_FONT}"/>'
          f'<w:spacing w:before="80" w:after="80"/><w:jc w:val="center"/><w:keepNext/></w:pPr>')
    return f'<w:p>{pp}{d}</w:p>'
def tcell(cx, width_dxa=None, fill=None):
    t = ['<w:tcPr>']
    t.append(f'<w:tcW w:w="{width_dxa}" w:type="dxa"/>' if width_dxa else '<w:tcW w:w="0" w:type="auto"/>')
    if fill: t.append(f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>')
    t.append('<w:tcMar><w:top w:w="40" w:type="dxa"/><w:bottom w:w="40" w:type="dxa"/><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tcMar>')
    t.append('<w:vAlign w:val="center"/></w:tcPr>'); return f'<w:tc>{"".join(t)}{cx}</w:tc>'
def cell_para(t, bold=False, color=None, sz=18, align=None):
    return para(run(t, sz=sz, bold=bold, color=color), align=align, space_after=20, space_before=20)
def table(rows, widths, header_fill="E8F0E8"):
    t = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>',
         '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:left w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:right w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/></w:tblBorders>',
         '<w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>']
    for w in widths: t.append(f'<w:gridCol w:w="{w}"/>')
    t.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        hdr = ri == 0; tr = ['<w:tr>']
        if hdr: tr.append('<w:trPr><w:tblHeader/></w:trPr>')
        for ci, c in enumerate(row):
            tr.append(tcell(cell_para(c, bold=hdr, color=("1E3A24" if hdr else None), sz=(18 if hdr else 17)),
                            width_dxa=widths[ci], fill=(header_fill if hdr else None)))
        tr.append('</w:tr>'); t.append("".join(tr))
    t.append('</w:tbl>'); t.append(para(run("", sz=8), space_after=80)); return "".join(t)

DESC = [620, 1700, 2600, 4440]
SRC = [3200, 6160]
SIGN = [1900, 3000, 2460, 2000]
META = [2700, 6660]
CTRL = [2400, 6560]

def _sign_table(rows, widths):
    t = ['<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/>',
         '<w:tblBorders><w:top w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:left w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:bottom w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/><w:right w:val="single" w:sz="4" w:space="0" w:color="9AB59A"/>'
         '<w:insideH w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/><w:insideV w:val="single" w:sz="4" w:space="0" w:color="C7D6C7"/></w:tblBorders><w:tblLayout w:type="fixed"/></w:tblPr><w:tblGrid>']
    for w in widths: t.append(f'<w:gridCol w:w="{w}"/>')
    t.append('</w:tblGrid>')
    for ri, row in enumerate(rows):
        hdr = ri == 0; tr = ['<w:tr><w:trPr>']
        tr.append('<w:tblHeader/>' if hdr else '<w:trHeight w:val="900" w:hRule="atLeast"/>')
        tr.append('</w:trPr>')
        for ci, c in enumerate(row):
            tr.append(tcell(cell_para(c, bold=hdr, color=("1E3A24" if hdr else None), sz=18),
                            width_dxa=widths[ci], fill=("E8F0E8" if hdr else None)))
        tr.append('</w:tr>'); t.append("".join(tr))
    t.append('</w:tbl>'); t.append(para(run("", sz=8), space_after=80)); return "".join(t)


# ---------------- Body ---------------- #
def build_body(meta, rids):
    P = []
    P.append(para(run("Chememan — ระบบบริหารงบประมาณ (Budget Management Web)", sz=18, color="6B7280"), space_after=40))
    P.append(para(run("เอกสารข้อกำหนดเพื่อขออนุมัติ (User Sign-off Specification)", sz=40, bold=True, color="2F6B3F"), space_after=40))
    P.append(para(run("ส่วน A — หน้าหลักของระบบ · Module 01: หน้าจัดการข้อมูลงบประมาณ (Main Budget Web App)",
                      sz=24, bold=True, color="1E3A24"), space_after=160))
    P.append(table([["รายการ", "รายละเอียด"], ["เวอร์ชัน", "v0.7 (ฉบับร่าง · Draft)"], ["วันที่", "14 มิถุนายน 2569 (2026-06-14)"],
                    ["ผู้จัดทำ", "ทีม Data Analytics"], ["สถานะ", "รออนุมัติจากผู้ใช้"],
                    ["แก้ไขล่าสุด", "v0.7 — แก้ขอบเขต RLS SEE-scope ให้ตรงกับ ADR-0007 (union model: orgcode ∪ ฝ่าย ∪ admin overlay)"]], META))

    # ── 0. Login & role-based visibility (Points 1 + 8) ──
    P.append(heading("0) การเข้าสู่ระบบ & สิทธิ์การเห็นข้อมูล (Login & Role)"))
    P.append(body_para(
        "ทั้งผู้ใช้ทั่วไป (User) และผู้ดูแลระบบ (Admin) เข้าสู่หน้าหลักนี้เหมือนกัน — เมื่อ login เข้ามา "
        "ระบบจะ\"แสดงข้อมูลของผู้ใช้คนนั้นทันที\" (ตามสิทธิ์ของตัวเอง) ไม่มีการสลับผู้ใช้ · ด้านบนของหน้ามี "
        "\"แถบผู้ใช้ (Login bar)\" บอกว่ากำลัง login เป็นใคร และเห็นข้อมูลในขอบเขตใด โดยจัดเรียงเป็น "
        "ลำดับชั้นอ่านซ้าย→ขวา: รูปย่อ (avatar) + ชื่อผู้ใช้ + อีเมล + ป้ายบทบาท ADMIN/USER  ›  สายงาน (Division)  ›  "
        "ฝ่าย (Department) พร้อมจำนวนฝ่าย และป้ายชื่อแต่ละฝ่าย  ›  จำนวน Cost Center ที่ดูแล — "
        "จำนวนทั้งหมดวางอยู่ในบรรทัดเดียวติดกับสิ่งที่นับ เพื่อให้เห็นลำดับชั้นชัด"))
    P.append(bullet("User / ผู้กรอก (Submitter · L3/L4): เห็น Cost Center ตามขอบเขต SEE แบบ union (orgcode∪ฝ่าย — ดู RLS chain ด้านล่าง · เอกสาร 10)"))
    P.append(bullet("Approver (ผู้อนุมัติ · L1/L2): เห็นฝ่ายในคิวอนุมัติของตน — ตรวจและกดอนุมัติ/ตีกลับบนหน้าหลักนี้เลย (ไม่มีหน้า inbox แยก · ดูข้อ 12)"))
    P.append(bullet("Admin (ผู้ดูแลระบบ · 4 คน): เห็นทุก Cost Center ทั้งบริษัท · แก้ Pending ได้ทุก CC"))
    P.append(bullet("บทบาทซ้อน (overlay admin): บางคน (วราพร/นิภาพร/ปิยะดา) เป็นทั้ง approver/submitter และ admin — "
                    "ปกติทำงานในบทบาทฐานของตน แล้วสลับเป็นบทบาท admin ผ่านปุ่ม \"🛡️ โหมด Admin\" (ดูข้อ 14) · "
                    "Admin แท้ (jakkaritw) เป็น admin ตลอด ไม่มีปุ่มสลับ"))
    P.append(bullet("หมายเหตุ: ภาพประกอบ 2 ภาพด้านล่าง (มุมมอง Admin / มุมมอง Submitter) มาจากตัวสลับผู้ใช้ใน "
                    "\"แบบเดโม่ (mockup)\" เพื่อให้เห็นทั้งสองมุมมองในที่เดียวเท่านั้น — ระบบจริงไม่มีปุ่มสลับผู้ใช้"))
    P.append(para(run("ภาพประกอบ: Admin (jakkaritw) — เห็นทุก Cost Center", sz=21, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["login_admin"], *meta["login_admin"][1], 106, "main_login_admin", width_in=5.6))
    P.append(para(run("ภาพประกอบ: Submitter (สุชัญญา · L3 Solution Delivery) — เห็นเฉพาะ Cost Center ของตน", sz=21, bold=True, color="1E3A24"),
                  space_before=40, space_after=40))
    P.append(image_para(rids["login_user"], *meta["login_user"][1], 107, "main_login_user", width_in=5.6))
    P.append(para(run("RLS chain — สายการ trace สิทธิ์ SEE แบบ union (ADR-0007 · รายละเอียดเต็มในเอกสาร 10):",
                      sz=21, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(table([
        ["ขั้น", "ตาราง / แหล่ง", "เชื่อมด้วย"],
        ["1", "login email → dbo.mas_employee_data (Fabric SQL DB · ทั้ง Primary และ Acting)", "empcode ↔ orgcode"],
        ["2a", "cfg_master.orgcode_costcenter_map (file 09)", "orgcode → cost_center (many-to-many)"],
        ["2b", "ฝ่าย (Department) → cost center master (file 02)", "ฝ่าย → cost_center (ขอบเขตกรอก/fill)"],
        ["3", "SEE = ผล 2a ∪ 2b ∪ overlay ของ Admin", "→ cost_center ที่ผู้ใช้ \"เห็น\""],
        ["4", "FILL ⊆ SEE — กรอกได้เฉพาะ CC ในฝ่ายของตน (2b)", "→ กำหนดสิทธิ์ \"กรอก\""],
    ], [800, 5500, 2860]))
    P.append(bullet("SEE-scope = union (ADR-0007): ขอบเขตเห็น = CC จาก orgcode (file 09 · many-to-many) ∪ CC จากฝ่ายของตน (file 02) ∪ overlay ของ Admin "
                    "— ต้อง union ไม่งั้นบางคนกรอกได้แต่มองไม่เห็น · orgcode lookup ใช้ทั้ง Primary และ Acting", sz=20))
    P.append(bullet("FILL-scope = ตามฝ่าย (file 02) เท่านั้น และ FILL ⊆ SEE เสมอ — กรอก/แก้ได้เฉพาะ CC ในฝ่ายของตน · Admin overlay เห็น/แก้ได้ทุก CC", sz=20))

    # ── 0b. Point 8 — login "cc name" == department (ฝ่าย), NOT Description ──
    P.append(para(run("ชื่อที่แถบ login แสดงคืออะไร? (ข้อ 8 — แสดง สายงาน/ฝ่าย ไม่ใช่ Description)",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(body_para(
        "แถบ login แสดงลำดับชั้น 2 ระดับจากไฟล์ master docs/02cost center & department (master).xlsx "
        "(sheet 'Cost center (Update 18 Mar 26)' · คอลัมน์: Cost Ctr | Description | C Level | สายงาน[Division] | ฝ่าย[Department]) "
        "คือ สายงาน (Division) เป็นหัวข้อหลัก และ ฝ่าย (Department) เป็นป้าย chips — ทั้งคู่ใช้คอลัมน์ "
        "สายงาน / ฝ่าย จาก master ไม่ใช่ Description (ชื่อ CC จริง):", sz=21))
    P.append(table([
        ["Cost Ctr", "chips ที่ระบบแสดง (= ฝ่าย/Department)", "Description (ชื่อ CC จริง)", "สายงาน (Division)"],
        ["10IT012000", "Solution Delivery", "Solution Delivery", "Digital Technology Division"],
        ["10AC020000", "Budgeting and Management Accounting", "Budget&Cost Acc Div", "Budgeting and Cost Accounting Division"],
        ["10GE000000", "General (orphan)", "General", "General"],
    ], [1500, 3100, 3100, 1860]))
    P.append(bullet("สถิติจากไฟล์จริง: Description ตรงกับ ฝ่าย เพียง 37% ของ 210 แถว → Description โดยทั่วไป "
                    "ไม่ใช่ชื่อฝ่าย ระบบจึงเลือกใช้คอลัมน์ ฝ่าย เป็นป้ายชื่อที่อ่านง่ายแทน", sz=20))
    P.append(bullet("เหตุผล: 1 คนผูกได้หลาย Cost Center ที่รวมขึ้นเป็น 1 ฝ่าย → แสดงชื่อฝ่ายอ่านง่ายกว่า · "
                    "รหัส CC แสดงเป็นข้อมูลละเอียดรอง", sz=20))
    P.append(para(run(
        "ข้อสรุป (ตัดสินแล้ว): แถบ login แสดงลำดับ สายงาน (Division) › ฝ่าย (Department) › จำนวน Cost Center "
        "เป็นขอบเขตที่อ่านง่าย — ใช้คอลัมน์ สายงาน/ฝ่าย ไม่ใช่ Description · อีเมลแสดงในแถบผู้ใช้ของคนที่ login",
        sz=21, bold=True, color="8C6423"), space_before=60, space_after=120))

    # ── 1. Overview ──
    P.append(heading("1) ภาพรวม (Overview)"))
    P.append(body_para(
        "หน้านี้คือหน้าหลัก (Main App Web) ของระบบบริหารงบประมาณ ทั้งผู้ใช้ทั่วไป (User) และผู้ดูแลระบบ (Admin) "
        "เข้ามาที่หน้านี้เพื่อดู (View) และกรอกข้อมูล (Fill data) งบประมาณรายเดือน ต่อ Cost Center / GL Code / ปีงบประมาณ"))
    P.append(body_para(
        "ตารางแสดงข้อมูล 3 ชั้นต่อรายการ (Transaction): SAP · ใช้จริง (Actuals), Approved · งบที่อนุมัติแล้ว, "
        "และ Pending · งบรออนุมัติ (กรอกมือ) — แต่ละชั้นมีแถบสีและสถานะกำกับชัดเจน", sz=21))
    P.append(para(run("เปลี่ยนแปลงจาก mockup (สรุปสั้น — รายละเอียด GL กลุ่มพิเศษอยู่ในเอกสาร 02):",
                      sz=21, bold=True, color="8C6423"), space_before=60, space_after=40))
    P.append(bullet("เพิ่มแถบ Login bar (เวอร์ชันใหม่ V3) แสดงลำดับชั้น สายงาน › ฝ่าย(จำนวน) › Cost Center(จำนวน) "
                    "พร้อมอีเมลผู้ใช้ · กรองตาราง/สรุป/submit ตามบทบาท (ระบบจริงไม่มีปุ่มสลับผู้ใช้ — login แล้วเห็นของตัวเองทันที)", sz=20))
    P.append(bullet("อนุมัติบนหน้าหลักเลย — ไม่มีหน้า inbox แยก: ผู้อนุมัติตรวจและกด อนุมัติ/ตีกลับ บนหน้าเดียวกับผู้กรอก (ดูข้อ 12)", sz=20))
    P.append(bullet("เปลี่ยนตัวกรองสายงาน (Division) เป็น \"ตัวเลือกฝ่าย (ฝ่าย-picker)\": ล็อกหน้าให้เหลือ 1 (ฝ่าย, ปี) = "
                    "หน่วยอนุมัติ (ADR-0008) · จัดกลุ่มตามสายงาน · ผู้อนุมัติเห็นป้าย รออนุมัติ/อนุมัติแล้ว ต่อฝ่าย + toggle "
                    "\"เฉพาะที่รออนุมัติ\" · ผู้กรอกถูกล็อกที่ฝ่ายของตนอัตโนมัติ (ดูข้อ 13)", sz=20))
    P.append(bullet("ตัวกรองปี: เอาตัวเลือก \"ทุกปี (all)\" ออก — เหลือเฉพาะ FY2024 / FY2025 / FY2026 (ค่าเริ่มต้น 2026 = ปีปัจจุบัน)", sz=20))
    P.append(bullet("Cost Center / GL ใช้ข้อมูลจริง (Solution Delivery · Budgeting · General orphan) · GL กลุ่มพิเศษจริง "
                    "(รวม Travelling Expense 8 GL) — ดูฟอร์มย่อย/per-diem engine ในเอกสาร 02", sz=20))
    P.append(bullet("Approved · งบ เป็น read-only บนเว็บ (แก้ในตารางไม่ได้) — แก้ได้ทาง Import .csv ทั้งปีเท่านั้น · "
                    "ปุ่ม Export/Import + Master FX (read-only) อยู่ \"แถบ งบอนุมัติ (Approved) · Admin\" แยกจาก toolbar (ดูข้อ 4–5, 15)", sz=20))
    P.append(bullet("เพิ่มปุ่ม \"🛡️ โหมด Admin\": overlay admin สลับระหว่างบทบาทฐาน ↔ บทบาท admin (ดูข้อ 14) · "
                    "ล็อกการแก้ไขตามสถานะ × บทบาท (edit-lock — ดูข้อ 16)", sz=20))
    P.append(bullet("ป้ายปีในวงเล็บที่ทุกแถว/legend: ยืนปีปัจจุบัน Y → SAP (Y) · Approved (Y) · Pending (Y+1) "
                    "เปลี่ยนตามตัวกรองปี — กรอกงบปีหน้า เทียบ actual/งบอนุมัติปีนี้", sz=20))
    P.append(bullet("ตารางเรียงตามกลุ่ม GL (GL group) · ป้ายกลุ่ม GL พิเศษเป็นสีเฉพาะกลุ่ม (Entertainment เหลือง · "
                    "Lease ชมพู · Professional ม่วง · Public Relation ส้ม · Training ฟ้า · Travelling เขียว)", sz=20))
    P.append(bullet("ปุ่ม \"+ เพิ่ม Transaction\" (เพิ่มแถว CC×GL เอง — เลือกจาก master, CC กรองตามฝ่าย) และปุ่ม "
                    "\"แนบไฟล์\" (เก็บเอกสาร pdf/excel/รูป เข้า SharePoint ตามฝ่าย+ปี) อยู่ใน toolbar (ดูข้อ 11)", sz=20))
    P.append(image_para(rids["overview"], *meta["overview"][1], 100, "main_overview", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ยอด Actuals จาก SAP (สีเขียว · read-only)", "ดึงจาก Lakehouse gold_sap_gl_trans · คอลัมน์ company_curr_amount (อธิบายข้อ 3)"],
        ["②", "APPROVED · งบ (สีฟ้า · read-only)", "งบที่อนุมัติแล้ว — แสดงอ่านอย่างเดียว แก้ในตารางไม่ได้ · ตั้งค่าได้ทาง Import .csv ทั้งปี (แถบ Admin) ไม่ผ่าน approval loop"],
        ["③", "ช่อง Pending · รออนุมัติ (GL ปกติ · มียอด)", "ผู้ใช้กรอกยอด Pending มือโดยตรง — แก้ได้เมื่อสถานะ DRAFT/REJECTED เท่านั้น (edit-lock — ดูข้อ 16)"],
        ["④", "ช่อง Pending · รออนุมัติ (เดือน ม.ค.)", "ช่องกรอกตัวซ้ายสุด (ม.ค.) ของแถว GL ปกติ — กรอกได้รายเดือน · GL กลุ่มพิเศษกรอกผ่าน subform แทน (ข้อ 2)"],
    ], [620, 3400, 5340]))

    # ── 2. RLS ──
    P.append(heading("2) การมองเห็นข้อมูล (RLS — Row Level Security ตาม Login)"))
    P.append(body_para(
        "ผู้ใช้แต่ละคนเห็นเฉพาะข้อมูลของตัวเอง โดยขอบเขตการเห็น (SEE-scope) เป็น \"union\" ตาม ADR-0007 — "
        "ตัวกำหนดสุดท้ายว่าใครเห็นข้อมูลอะไรได้บ้างคือ cost_center ที่ได้จากการรวม (union) ของ 2 เส้นทาง + overlay ของ Admin"))
    P.append(table([
        ["ขั้น", "ตาราง / แหล่ง", "เชื่อมด้วย"],
        ["1", "dbo.mas_employee_data (Fabric SQL DB · ทั้ง Primary และ Acting)", "empcode ↔ orgcode"],
        ["2a", "cfg_master.orgcode_costcenter_map (file 09)", "orgcode → cost_center (many-to-many)"],
        ["2b", "ฝ่าย (Department) → cost center master (file 02)", "ฝ่าย → cost_center (= ขอบเขตกรอก)"],
        ["3", "SEE = ผล 2a ∪ 2b ∪ overlay ของ Admin", "→ cost_center ที่ผู้ใช้ \"เห็น\""],
    ], [800, 5500, 2860]))
    P.append(para(run("สรุปกฎการเห็นข้อมูล (ADR-0007):", sz=22, bold=True, color="1E3A24"), space_before=60, space_after=40))
    P.append(bullet("SEE-scope = union: CC จาก orgcode (file 09 · many-to-many) ∪ CC จากฝ่ายของตน (file 02) ∪ overlay ของ Admin — "
                    "1 CC ถูกหลาย orgcode/ฝ่ายอ้างถึงได้ จึงแชร์การเห็นข้ามฝ่าย/สายงานได้"))
    P.append(bullet("ทำไมต้อง union: file 09 (orgcode↔CC) กับ file 02 (ฝ่าย↔CC) เป็น mapping คนละชุด — ถ้าไม่ union บางคน (≈29 ราย) จะกรอกได้แต่มองไม่เห็น CC ของตัวเอง"))
    P.append(bullet("orgcode lookup ใช้ทั้ง Primary และ Acting (ตาม RLS decision 2026-05-27) — บทบาท Acting ก็ให้สิทธิ์เห็น CC ของ orgcode นั้น"))
    P.append(bullet("FILL-scope = ตามฝ่าย (file 02) เท่านั้น · FILL ⊆ SEE เสมอ — กรอก/แก้ได้เฉพาะ CC ในฝ่ายของตน (ขอบเขตเห็นกว้างกว่าหรือเท่ากับขอบเขตกรอกเสมอ)"))
    P.append(bullet("User เห็นเฉพาะข้อมูลในขอบเขต SEE ของตัวเอง (ตาม cost_center ที่ trace ได้)"))
    P.append(bullet("Admin มี 4 คน — เห็นและแก้ไขได้ทุกอย่าง (ทุก cost_center · overlay เหนือ SEE)"))
    P.append(bullet("ใครเข้าถึง (เห็น) อะไร → กรอก/แก้ได้แค่นั้น ทั้งหน้าหลักและการ \"ใส่รายละเอียดงบทำการ\" (subform ย่อย — ดูเอกสาร 02) · ยกเว้น Admin เห็นและแก้ทุกอย่าง"))
    P.append(bullet("กรณี Cost Center ในสิทธิ์ที่ยังไม่มีแถวในตาราง (ยังไม่เคยกรอก): ผู้ใช้กดปุ่ม \"+ เพิ่ม Transaction\" "
                    "เพื่อเพิ่มแถวเองได้ — dropdown Cost Center จำกัดเฉพาะฝ่ายที่ตนกรอกได้ (fill-scope) เท่านั้น "
                    "จึงยังอยู่ในขอบเขตสิทธิ์เดิม (เห็น/กรอกได้แค่ของตน)"))
    P.append(para(run("จุดเข้าฟอร์มย่อย \"+ ใส่รายละเอียดงบทำการ\" (Special GL Group) — รายละเอียดเต็มอยู่ในเอกสาร 02:",
                      sz=21, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["detail"], *meta["detail"][1], 104, "main_special_detail", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ปุ่ม \"+ ใส่รายละเอียดงบทำการ\" (Special GL)", "เปิดฟอร์มย่อย (subform) กรอกรายละเอียด — ดูเอกสาร 02"],
        ["②", "ช่อง Pending (read-only)", "ยอดรวมจาก subform แสดงกลับที่ช่องนี้ (กรอกตรงไม่ได้)"],
    ], [620, 3700, 5040]))

    # ── 3. Data sources in table ──
    P.append(heading("3) แหล่งข้อมูลในตาราง (3 ส่วน)"))
    P.append(body_para(
        "ข้อมูลในตารางมาจาก 3 ส่วน — แต่ละส่วนมีแถบสีกำกับตรงกับภาพประกอบ: "
        "SAP (เขียว) · Approved (ฟ้า) · Pending (ดำ)"))
    P.append(table([
        ["ส่วน (สี)", "แหล่งข้อมูล / ใครกรอก", "การทำงาน"],
        ["1. SAP · ใช้จริง (Actuals) — สีเขียว",
         "ดึงจาก Lakehouse gold_sap_gl_trans · คอลัมน์ company_curr_amount",
         "อ่านอย่างเดียว (read-only) · ดึงอัตโนมัติ"],
        ["2. Approved · งบ — สีฟ้า (read-only)",
         "Admin import .csv ทั้งปีเท่านั้น (แถบ Admin) — แก้ในตารางไม่ได้",
         "Import → เข้า DB เลย (Replace-by-Year) ไม่ผ่าน approval loop"],
        ["3. Pending · รออนุมัติ — สีดำ",
         "User (L3/L4) กรอกมือ (Admin แก้ส่วนนี้ด้วยมือได้)",
         "กด submit → เข้า approval loop: Submitter (L3/L4) → managerempcode → นิภาพร → วราพร "
         "(มี special case เช่น นิภาพร/วราพร กรอกเอง, C-Level — ดูรายละเอียดในเอกสาร approval workflow)"],
    ], [2600, 3300, 3000]))
    P.append(para(run("ภาพประกอบ: คอลัมน์ส่วน SAP (Actuals)", sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["sap"], *meta["sap"][1], 101, "main_sap_columns", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สถานะแถว SAP · ใช้จริง (วงสีแดง)", "บอกว่าแถวนี้เป็นยอด Actuals จาก SAP"],
        ["②", "ยอดรายเดือน (SAP · สีเขียว)", "ค่าจาก gold_sap_gl_trans.company_curr_amount — read-only"],
    ], [620, 3400, 5340]))
    # ── 3 · Approved illustration (FIX B — between SAP and Pending) ──
    P.append(para(run("ภาพประกอบ: Approved · งบ (สีฟ้า · read-only) + ทางตั้งค่า = Import .csv",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["approved"], *meta["approved"][1], 105, "main_approved_submit", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ช่อง Approved · งบ (สีฟ้า · read-only)", "แสดงอ่านอย่างเดียว — กรอก/แก้ในตารางไม่ได้"],
        ["②", "ปุ่ม Import Approved Budget (แถบ Admin)", "ทางเดียวที่ตั้งค่า Approved — Import .csv ทั้งปี (Replace-by-Year) เข้า DB ตรง ไม่ผ่าน approval loop"],
    ], [620, 3400, 5340]))
    P.append(para(run("ภาพประกอบ: ช่องกรอก Pending · รออนุมัติ + ปุ่มส่ง/อนุมัติ", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["pending"], *meta["pending"][1], 102, "main_pending_submit", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สถานะแถว Pending · รออนุมัติ", "งบที่ผู้ใช้กรอกมือ รอเข้าอนุมัติ"],
        ["②", "ช่องกรอกยอดรายเดือน (Pending)", "ผู้ใช้กรอกมือ — กรอกได้เฉพาะ cost_center ที่ตัวเองเห็น"],
        ["③", "ปุ่มส่ง/อนุมัติ (Submit to Database)", "ยืนยันส่งข้อมูล Pending เข้ากระบวนการอนุมัติ"],
    ], [620, 3700, 5040]))

    # ── Data sources summary (3 sources — moved into section 3) ──
    P.append(heading("สรุปแหล่งข้อมูล (Data sources — 3 ส่วน)"))
    P.append(body_para("ข้อมูลในตารางมาจาก 3 ส่วน (SAP เขียว · Approved ฟ้า · Pending ดำ) + ตาราง RLS ที่ใช้กำหนดสิทธิ์การเห็น", sz=21))
    P.append(table([
        ["แหล่ง / ตาราง", "บทบาท"],
        ["1. gold_sap_gl_trans (Lakehouse) · company_curr_amount",
         "SAP · ใช้จริง (สีเขียว) — Actuals อ่านอย่างเดียว"],
        ["2. Approved · งบ (สีฟ้า · read-only) — Admin Import .csv ทั้งปี",
         "งบที่อนุมัติแล้ว — Import เข้า DB เลย (Replace-by-Year) ไม่ผ่าน approval loop · แก้ในตารางไม่ได้"],
        ["3. Pending · รออนุมัติ (สีดำ) — User กรอกมือ / Admin แก้ได้",
         "งบรออนุมัติ — submit เข้า approval loop (มี routing การส่งต่อ)"],
        ["dbo.mas_employee_data + cfg_master.orgcode_costcenter_map (file 09) + cost center master (file 02)",
         "RLS chain (ADR-0007): SEE = (orgcode→file 09) ∪ (ฝ่าย→file 02) ∪ Admin overlay · FILL ⊆ SEE (กรอกตามฝ่าย) — กำหนดสิทธิ์เห็น/กรอกข้อมูล"],
    ], SRC))

    # ── 3c. See / Fill / Submit matrix per data part × role (Point 2 — centerpiece) ──
    P.append(heading("3.1) ใครเห็น / ใครกรอก / การ Submit (แยกตามส่วนข้อมูล × บทบาท)"))
    P.append(body_para(
        "ตารางสรุปสิทธิ์ต่อข้อมูล 3 ส่วน — User เห็น/กรอกได้เฉพาะ Cost Center ของตน (RLS) · "
        "Admin เห็นทุก CC และแก้ Pending ได้ทุก CC · หน่วยส่ง = ฝ่าย และปุ่มส่งของ Admin มี 2 โหมด (ดูข้อ 8, 16.1):", sz=21))
    P.append(table([
        ["ส่วนข้อมูล (สี)", "ใครเห็น", "ใครกรอก + วิธีกรอก", "การ Submit"],
        ["SAP · ใช้จริง (เขียว)",
         "ทุกคนตาม RLS scope (User = CC ตน · Admin = ทุก CC)",
         "ไม่มีใครกรอก — auto จาก Lakehouse gold_sap_gl_trans.company_curr_amount (read-only)",
         "ไม่มี"],
        ["Approved · งบ (ฟ้า · read-only)",
         "ตาม scope",
         "Admin เท่านั้น — Import .csv ทั้งปี (read-only ในตาราง แก้มือไม่ได้)",
         "Import → เข้า DB ตรง (Replace-by-Year) · ไม่ผ่าน approval loop"],
        ["Pending · รออนุมัติ (ดำ)",
         "ตาม scope",
         "User (L3/L4) กรอก CC ของตน (รายเดือน ม.ค.–ธ.ค. หรือผ่าน subform สำหรับ special GL) · Admin แก้ของ CC ใดก็ได้",
         "Submit ทั้งฝ่าย → เข้า approval loop · Admin: orphan/หลัง deadline → APPROVED ตรงๆ"],
    ], [2100, 1900, 3300, 1600]))

    # Point 3 — Admin editing a normal user's Pending
    P.append(para(run("(ข้อ 3) สิทธิ์ Admin ในการแก้ Pending ของ User",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(bullet("Admin แก้ไขงบ Pending ของ Cost Center ใดก็ได้ ทุกสถานะ (บันทึกเป็นฉบับร่างของเจ้าของ CC นั้น) — edit-lock ข้อ 16"))
    P.append(bullet("ข้อจำกัดการส่ง (ADR-0012 · ดูข้อ 16.1): รอบปกติ Admin ส่งได้เฉพาะฝ่าย orphan → APPROVED ตรงๆ · หลัง deadline ส่งฝ่ายใดก็ได้แทน → APPROVED ตรงๆ"))
    P.append(bullet("กันยอดซ้ำ (ข้อ 4): คีย์ = (cost_center, fiscal_year, gl_account, month) ไม่มี empcode → 1 CC = ชุดงบเดียว · last-write-wins"))

    # Point 4 — How a normal user fills Pending
    P.append(para(run("(ข้อ 4) ขั้นตอน User กรอกงบ Pending",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("(1) เลือก Cost Center (ของตนเท่านั้น) → (2) เลือก GL Code → (3) กรอกยอด ม.ค.–ธ.ค."))
    P.append(bullet("ยอดรวมทั้งปี auto-sum · division / department / GL name / GL group auto-fill อัตโนมัติ"))
    P.append(bullet("GL กลุ่มพิเศษ → กดปุ่ม \"+ ใส่รายละเอียดงบทำการ\" เปิด subform (เอกสาร 02) แล้วยอดรวมเด้งกลับช่อง Pending (read-only)"))
    P.append(bullet("ปุ่ม Save = บันทึกฉบับร่าง (DRAFT) · ปุ่ม Submit = ส่งเข้า approval loop"))

    # ── 4. Export ──
    P.append(heading("4) ปุ่ม Export Approved Budget (เฉพาะ Admin)"))
    P.append(body_para(
        "ปุ่มนี้สำหรับ Admin เท่านั้น — ใช้ส่งออกข้อมูลงบที่อนุมัติแล้วเป็นไฟล์ ใครเห็นอะไร (ตาม RLS) "
        "จะ export ออกมาตามหน้านั้น แต่ปุ่ม Export จะแสดงเฉพาะ Admin"))
    P.append(bullet("ตำแหน่งปุ่ม (2026-06-12): Export/Import ย้ายออกจาก toolbar ไปอยู่ \"แถบ งบอนุมัติ (Approved) · Admin\" "
                    "แยกต่างหากเหนือตาราง — กันเข้าใจผิดว่าตัวกรองปี/ฝ่ายมีผลกับการ import", sz=20))
    P.append(bullet("แถบนี้แสดงเฉพาะ Admin — ผู้ใช้ทั่วไป (User) ไม่เห็นทั้งแถบ (ซ่อนทั้งก้อน)", sz=20))
    P.append(bullet("Export ใช้ \"ตัวกรองปี\" กำหนดปีในชื่อไฟล์ (เช่น เลือก FY2025 → approved_budget_2025.csv) · "
                    "ส่วน Import จะยึดปีจากตัวไฟล์เอง ไม่ขึ้นกับตัวกรอง (ดูข้อ 5)", sz=20))
    P.append(table([
        ["#", "หัวข้อ", "รายละเอียด"],
        ["1", "สิทธิ์", "Admin เท่านั้น (4 คน)"],
        ["2", "ขอบเขตข้อมูล", "Export ตามที่ผู้ใช้นั้นเห็น (ตาม RLS / cost_center)"],
        ["3", "Filter", "กรองตามปีที่เลือก (2024 / 2025 / 2026) — ไม่มีตัวเลือก \"ทุกปี\" แล้ว"],
        ["4", "ชื่อไฟล์", "ปีกำหนดชื่อไฟล์ เช่น approved_budget_2025.csv (เปลี่ยนตามปีที่เลือก)"],
        ["5", "รูปแบบไฟล์", ".csv (UTF-8 มี BOM · คั่นด้วย ,)"],
        ["6", "ค่ายอดที่ export", "ยอดของ \"Approved · งบ\" (สีฟ้า) รายเดือน jan–dec"],
    ], [620, 2600, 6140]))
    P.append(para(run(
        "คอลัมน์ของไฟล์ .csv ที่ระบบ export ออกมาจริง (จากฟังก์ชัน exportApprovedCSV ใน mockup) "
        "เรียงตามลำดับ 21 คอลัมน์ดังนี้:", sz=21, bold=True, color="1E3A24"),
        space_before=80, space_after=40))
    P.append(table([
        ["#", "ชื่อคอลัมน์", "ความหมาย"],
        ["1", "cost_center", "รหัส Cost Center"],
        ["2", "gl_code", "รหัส GL"],
        ["3", "gl_name", "ชื่อ GL (auto จาก master)"],
        ["4", "gl_group", "กลุ่ม GL (auto จาก master)"],
        ["5", "remark", "หมายเหตุ (แก้ไขได้)"],
        ["6", "c_level", "ระดับผู้บริหาร (auto จาก cost center)"],
        ["7", "division", "สายงาน (auto จาก cost center)"],
        ["8", "department", "หน่วยงาน (auto จาก cost center)"],
        ["9–20", "jan, feb, mar, apr, may, jun, jul, aug, sep, oct, nov, dec",
         "ยอดงบ Approved รายเดือน 12 คอลัมน์ (ยอดของแถวสีฟ้า)"],
        ["21", "year", "ปีงบประมาณของรายการ"],
    ], [620, 3400, 5340]))
    P.append(para(run("หมายเหตุสำคัญ — เรื่องชื่อไฟล์ vs ชื่อคอลัมน์:", sz=21, bold=True, color="8C6423"),
                  space_before=80, space_after=40))
    P.append(bullet("ชื่อไฟล์ที่ export = approved_budget_<ปี>.csv (เช่น approved_budget_2025.csv) — <ปี> เปลี่ยนตามปีที่เลือก", sz=20))
    P.append(bullet("ยอดงบที่อนุมัติแล้ว → เก็บอยู่ใน 12 คอลัมน์รายเดือน jan–dec", sz=20))

    # ── 5. Import ──
    P.append(heading("5) ปุ่ม Import Approved Budget (เฉพาะ Admin)"))
    P.append(body_para(
        "นำไฟล์ที่ได้จากข้อ 4 (Export) มาแก้ไขข้อมูล แล้วใส่กลับเข้าระบบผ่านปุ่ม Import นี้ "
        "ข้อมูลที่ใส่เข้ามาจะวิ่งไปเก็บหลังบ้าน และเพิ่ม control column ตอนเก็บ ด้วย streaming mode batch"))
    P.append(para(run("สำคัญ — Import ไม่ขึ้นกับตัวกรองปี/ฝ่าย:", sz=21, bold=True, color="8C6423"),
                  space_before=60, space_after=40))
    P.append(bullet("ขอบเขตการ import กำหนดโดย \"ไฟล์ CSV\" เท่านั้น — ปีจากชื่อไฟล์ + คอลัมน์ year (ต้องตรงกัน) · "
                    "แทนที่ทั้งปี/ทั้งบริษัท (Replace-by-Year) ไม่ใช่เฉพาะปี/ฝ่ายที่กำลังกรองดูบนจอ", sz=20))
    P.append(bullet("ตัวกรองปี/ฝ่ายบนหน้าเป็นแค่ \"มุมมอง\" ไม่ตัดขอบเขตข้อมูลที่ import — จึงย้ายปุ่มออกจาก toolbar "
                    "มาอยู่แถบ Admin แยก พร้อมข้อความเตือนกำกับ", sz=20))
    P.append(body_para("ภาพประกอบ: แถบ งบอนุมัติ (Approved) · Admin — ปุ่ม Import / Export + ข้อความเตือน + Master FX (read-only)", sz=21))
    P.append(image_para(rids["admin_zone"], *meta["admin_zone"][1], 103, "main_admin_zone", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ปุ่ม Import Approved Budget", "นำไฟล์ .csv ทั้งปีกลับเข้าระบบ (Replace-by-Year) — ข้อ 5"],
        ["②", "ปุ่ม Export Approved Budget", "ส่งออกงบอนุมัติเป็น .csv (Admin) — ข้อ 4"],
        ["③", "Master FX (USD→THB · read-only)", "อัตราแลกเปลี่ยน — แสดงอย่างเดียว · แก้ที่หน้า Master Currency (Module 09) เท่านั้น (ดูข้อ 15)"],
    ], [620, 3700, 5040]))
    P.append(bullet("แถบนี้มีเส้นขอบฟ้า+ ข้อความ \"⚠ ทั้งปี/ทั้งบริษัท ตามไฟล์ CSV — ไม่ขึ้นกับตัวกรองปี/ฝ่าย\" กำกับชัด", sz=20))
    P.append(bullet("แถบนี้แสดงเฉพาะ Admin — ถ้า login เป็นผู้ใช้ทั่วไป (ไม่ใช่ Admin) จะไม่เห็นแถบนี้เลย (ซ่อนทั้งก้อน)", sz=20))

    # ── 6. Control columns ──
    P.append(heading("6) Control Columns (เพิ่มตอน Import เก็บหลังบ้าน)"))
    P.append(body_para("เมื่อ Import ระบบจะเพิ่มคอลัมน์ควบคุม (control column) เก็บไว้หลังบ้านอัตโนมัติ ด้วย streaming mode batch:"))
    P.append(table([
        ["Column", "ค่า"],
        ["_load_dt", "current_date() → 2026-05-04"],
        ["_load_dttm", "current_timestamp()"],
        ["_user", "ex. jakkaritw@chememan.com (ผู้ upload หรือ fill data)"],
    ], CTRL))
    P.append(bullet("ไม่เก็บ control column ที่เกี่ยวกับไฟล์ (_file_name / _file_path / _file_size / _file_mod) "
                    "เพราะ import เป็นแบบ direct-to-table (overwrite) — ไม่ได้เก็บไฟล์ไว้", sz=20))

    # ── 7. Confirmed design decisions ──
    P.append(heading("7) ข้อสรุปการออกแบบ"))

    P.append(para(run("(1) วิธีเก็บข้อมูลหลัง import .csv → เขียนลง table ตรงๆ (direct-to-table)",
                      sz=22, bold=True, color="1E3A24"), space_before=40, space_after=40))
    P.append(bullet("parse .csv แล้ว insert ลง table เลย — ไม่เก็บไฟล์ลง landing / Volume"))
    P.append(bullet("control columns ที่เก็บ = เฉพาะ _load_dt, _load_dttm, _user เท่านั้น"))
    P.append(bullet("control columns ที่เกี่ยวกับไฟล์ (_file_name / _file_path / _file_size / _file_mod) "
                    "ไม่เก็บ — เพราะ import เป็นแบบ direct-to-table (overwrite) ไม่ได้เก็บไฟล์ไว้"))

    P.append(para(run("(2) อัปโหลดซ้ำปีเดิม → Replace by Year",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("DELETE WHERE year = X (เช่น 2025) แล้ว INSERT ข้อมูลใหม่ทั้งก้อนของปีนั้น"))
    P.append(bullet("จับปีจาก ชื่อไฟล์ และ คอลัมน์ year — สองค่านี้ต้องตรงกัน "
                    "(validate ก่อน import; ถ้าไม่ตรง → reject)"))
    P.append(bullet("ขอบเขตการทับ = ทั้งปี (เฉพาะ part Approved งบ) · row ในไฟล์ระบุตัวด้วย cost_center + gl_code + ปี (year)"))

    # ── 8. Submit loop + admin special condition (Point 6) ──
    P.append(heading("8) การส่งข้อมูล (Submit)"))
    P.append(body_para("การ \"ส่ง\" มี 2 เส้นทางต่างกันชัดเจนตามส่วนข้อมูล:", sz=21))
    P.append(table([
        ["ส่วน", "เส้นทางหลังกดส่ง"],
        ["Pending · รออนุมัติ (User กรอก)",
         "เข้า approval chain: ผู้กรอก (L3/L4) → managerempcode → นิภาพร ทองกิ่ง → วราพร ติรสิทธิ์ "
         "(มี special case: นิภาพร/วราพร กรอกเอง, C-Level — ดูเอกสาร 10 + เอกสาร approval workflow)"],
        ["Approved · งบ (Admin · read-only)",
         "ตั้งค่าทาง Import .csv ทั้งปีเท่านั้น (Replace-by-Year) → เข้า DB ตรง ไม่ผ่าน approval loop · ไม่มีการกรอก/ส่งราย cell"],
    ], [3000, 6200]))
    P.append(para(run("Special condition (สำคัญ) — หน่วยส่ง + ขอบเขตปุ่มส่งของ Admin (ปรับปรุง 2026-06-13):",
                      sz=22, bold=True, color="8C6423"), space_before=80, space_after=40))
    P.append(bullet("หน่วยส่ง = ฝ่าย (Department) — กด Submit 1 ครั้ง = ส่งทั้งฝ่าย (ทุก CC) เป็นก้อนเดียว ตามปีงบประมาณ "
                    "(หน่วยอนุมัติ = (ฝ่าย, ปี) · ADR-0008) · ปุ่มขึ้นกับ \"ฝ่ายที่เลือก\" ไม่ใช่บทบาท (ดูข้อ 13.1)"))
    P.append(bullet("Admin เห็นทุก CC และแก้ Pending ได้ทุก CC · แต่ปุ่มส่งของ Admin มี 2 โหมด (ADR-0012 · ดูข้อ 16.1): "
                    "รอบปกติ = ส่งได้เฉพาะฝ่าย orphan → APPROVED ตรงๆ · หลัง deadline = ส่งฝ่ายใดก็ได้แทน → APPROVED ตรงๆ (log ADMIN_OVERRIDE)"))

    # ── 9. Other suggestions (Point 7) ──
    P.append(heading("9) ข้อเสนอแนะเพิ่มเติม / ประเด็นควรตัดสิน"))
    P.append(bullet("Concurrency (ตัดสินแล้ว — ไม่ทำอะไร): หลายคนใน dept เดียวกันกรอก CC คนละตัว — ใช้ last-write-wins "
                    "ตามคีย์ (cost_center, year, gl, month) · ไม่ทำ lock/indicator (โอกาสชน CC+GL+เดือนเดียวกันต่ำมาก) · "
                    "ยอมรับความเสี่ยงเขียนทับเงียบ แลกความ lean · control column _user/_updated_at ใช้ตรวจย้อนหลังได้ · "
                    "ทางถอย: ถ้าเกิดจริงค่อยเพิ่ม optimistic warn (เช็ค _updated_at ตอน save) ภายหลัง — ไม่ต้องรื้อ schema"))
    P.append(bullet("Deadline lock: ถึงวันปิดรับ form ปิดอัตโนมัติ (GET /api/deadline)"))
    P.append(bullet("Validation ก่อน submit แบบ lean — เตือน (warn) ไม่บล็อก"))
    P.append(bullet("Audit ผ่าน control column _user / _updated_at — ไม่ต้องมี audit table แยก"))
    P.append(bullet("Admin act-as: มีตัวระบุ \"CC ที่กำลังแก้แทน\" ให้ชัดว่ากำลังแก้ของใคร"))

    # ── 10. Performance when Admin sees all CC (Point 9) ──
    P.append(heading("10) ประสิทธิภาพเมื่อ Admin เห็นทุก CC (~1000+ รายการ)"))
    P.append(body_para(
        "ตอบตรงประเด็น: เว็บ \"ไม่ error\" — ทำงานได้ปกติ แต่ถ้า render ทุกแถวฝั่ง client พร้อมกันที่ "
        "~1000+ แถวจะเริ่มหน่วง (เรื่อง UX/ความเร็ว ไม่ใช่ error). ตัวที่แก้จริงคือ \"เลือก scope ก่อนดู\" (scope-picker-first):", sz=21))
    P.append(para(run("ทางแก้ที่ตัดสิน + ทำในแบบ (mockup) แล้ว:", sz=22, bold=True, color="1E3A24"),
                  space_before=60, space_after=40))
    P.append(bullet("ตัวเลือกฝ่าย (ฝ่าย-picker) — บังคับล็อก 1 ฝ่ายเสมอ (ไม่มี \"ทุกฝ่าย\") → ตาราง render เฉพาะแถวของ "
                    "ฝ่ายนั้น ไม่มีทางแสดงทุก CC พร้อมกัน = แก้ที่ต้นเหตุ · ฝ่าย = หน่วยอนุมัติด้วย (ADR-0008 · ดูข้อ 13)"))
    P.append(bullet("กรอบของปัญหา: ความหน่วงเกิดเฉพาะมุมมอง Admin เห็นทุก CC เท่านั้น · "
                    "หน้ากรอกของ User = 1 CC เสมอ → ชุดข้อมูลเล็ก ไม่เคยโดน"))
    P.append(para(run("ทางแก้ฝั่งหลังบ้าน (ทำควบคู่):", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(bullet("ใส่ index (cost_center, fiscal_year, gl_account) บนตาราง Pending/Approved ใน Fabric SQL DB — ของฟรี ทำเลย"))
    P.append(bullet("SAP actuals มาจาก Lakehouse gold ผ่าน datawarehouse endpoint (อ่านอย่างเดียว · schema = dbo · "
                    "aggregate มาแล้ว) → ไม่ join หนักฝั่ง client"))
    P.append(bullet("ถ้ากรองสายงานเดียวแล้วยังได้แถวเยอะ ค่อยเพิ่ม server-side pagination + virtualized table ภายหลัง — "
                    "ไม่ทำตั้งแต่แรก (เลี่ยง over-engineer ตาม lean)"))
    P.append(para(run(
        "สรุป: ไม่ใช่ปัญหา error · แก้ที่ \"เลือกสายงานก่อนดู\" (ทำแล้วในแบบ) + index หลังบ้าน · "
        "pagination/virtualization เป็นทางสำรองเพิ่มทีหลังถ้าจำเป็น",
        sz=21, bold=True, color="8C6423"), space_before=80, space_after=120))

    # ── 11. Toolbar tools + year labels + GL color/sort (NEW 2026-06-12) ──
    P.append(heading("11) เครื่องมือบน toolbar · ป้ายปี · สี/การเรียงกลุ่ม GL (ปรับปรุง 2026-06-12)"))
    P.append(body_para(
        "หลังย้าย Export/Import ไปแถบ Admin (ข้อ 4–5) toolbar เหลือเครื่องมือสำหรับผู้ใช้: ตัวกรองปี, "
        "ตัวเลือกฝ่าย (ฝ่าย-picker), ปุ่ม \"+ เพิ่ม Transaction\" และปุ่ม \"แนบไฟล์\"", sz=21))
    P.append(image_para(rids["toolbar"], *meta["toolbar"][1], 108, "main_toolbar", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ตัวกรองปี (Year filter)", "FY2024 / 2025 / 2026 — เป็นมุมมอง · กำหนดปีในป้ายวงเล็บ + ชื่อไฟล์ Export"],
        ["②", "ตัวเลือกฝ่าย (ฝ่าย-picker)", "ปุ่มเปิดแผงเลือกฝ่าย — ล็อกหน้าเหลือ 1 (ฝ่าย, ปี) = หน่วยอนุมัติ (ดูข้อ 13) · แทนตัวกรองสายงานเดิม"],
        ["③", "ปุ่ม + เพิ่ม Transaction", "เพิ่มแถว Cost Center × GL เอง (CC จำกัดตามฝ่ายที่ผู้ใช้กรอกได้)"],
        ["④", "ปุ่ม แนบไฟล์", "เก็บเอกสารประกอบเข้า SharePoint ตามฝ่าย+ปี"],
    ], [620, 3700, 5040]))

    P.append(para(run("(11.1) ตารางแสดงแถวไหน + ปุ่ม \"+ เพิ่ม Transaction\"",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(body_para(
        "ตารางไม่ได้แสดง GL ทุกตัว — แถว (Cost Center × GL × ปี) ที่โผล่มาจาก 3 แหล่งรวมกัน โดยมี "
        "\"SAP · ใช้จริง เป็นตัวนำ\": GL ที่เคยมียอดจริงใน SAP ปีนั้นจะโผล่ก่อน (Approved/Pending แสดงข้างกันรอกรอก) · "
        "นอกจากนี้ยังโผล่ถ้ามีข้อมูลใน Approved (เช่น GL/CC ใหม่จากการ import) หรือ Pending (ที่กรอกไว้)", sz=21))
    P.append(bullet("กฎการแสดงแถว = SAP actual (ตัวนำ) ∪ มี Approved ∪ มี Pending — มีข้อมูลแหล่งใดก็โผล่ · "
                    "พอมีแล้วจะ \"ค้างถาวร\" โผล่ทุกครั้ง (งบที่กรอก/import ไม่หาย) — ดู ADR-0010", sz=20))
    P.append(bullet("GL ที่ไม่เคยมี actual และยังไม่มีงบ → ไม่โผล่ตอนแรก · ถ้าจะใช้ปีนี้ ให้กด \"+ เพิ่ม Transaction\" "
                    "(ไม่ใช่ระบบเสีย — แค่ยังไม่มีข้อมูลแหล่งใดเลย)", sz=20))
    P.append(bullet("ปุ่ม + เพิ่ม Transaction: เลือก Cost Center + GL Code จาก dropdown ที่ดึงจาก master — "
                    "รายการ CC กรองเฉพาะฝ่ายที่ผู้ใช้กรอกได้ (fill-scope)", sz=20))
    P.append(bullet("ถ้า GL ที่เลือกเป็นกลุ่มพิเศษ → แถวเข้าโหมด subform อัตโนมัติ (ช่องรายเดือน read-only + ปุ่มใส่รายละเอียด) "
                    "เหมือนแถวพิเศษทั่วไป · Travelling → เปิด Trip Manager → กรอกเสร็จ ยอดรวมโผล่หน้าหลักเหมือน GL อื่น (ดูเอกสาร 02)", sz=20))
    P.append(bullet("เลือก CC+GL ซ้ำของเดิม = ลงที่แถวเดิม (ไม่เพิ่มซ้ำ)", sz=20))

    P.append(para(run("(11.2) ปุ่ม \"แนบไฟล์\" — เก็บเอกสารเข้า SharePoint ตามฝ่าย + ปี",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("รองรับ pdf / xlsx / xls / png / jpg · เก็บเข้าโฟลเดอร์ปลายทางตามรูปแบบ <ฝ่าย> / <ปี> / (เช่น Solution Delivery / 2026 /)", sz=20))
    P.append(bullet("ฝ่าย + ปี ของปลายทาง \"ล้อตามตัวกรองหน้าหลัก\" — แสดงแบบอ่านอย่างเดียวใน modal (ไม่มี dropdown ให้เลือกซ้ำ)", sz=20))
    P.append(bullet("เก็บที่ SharePoint (ไม่เก็บใน DB) — โฟลเดอร์ = ดัชนี (ฝ่าย+ปี) · ผู้แนบ/วันที่ได้จาก metadata ของ SharePoint", sz=20))
    P.append(bullet("รากโฟลเดอร์ (SharePoint root) อยู่ระหว่างกำหนด — ในแบบยังเป็น placeholder", sz=20))

    P.append(para(run("(11.3) ป้ายปีในวงเล็บ — SAP (Y) · Approved (Y) · Pending (Y+1)",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("ทุกแถว + legend แสดงปีในวงเล็บ · ยืนปีปัจจุบัน Y → SAP/Approved = ปีปัจจุบัน (Y) · Pending = ปีที่วางแผน (Y+1)", sz=20))
    P.append(bullet("เปลี่ยนตามตัวกรองปี เช่น เลือก 2026 → SAP (2026) · Approved (2026) · Pending (2027) — กรอกงบปีหน้า เทียบของปีนี้", sz=20))

    P.append(para(run("(11.4) สีกลุ่ม GL พิเศษ + เรียงตามกลุ่ม",
                      sz=22, bold=True, color="1E3A24"), space_before=120, space_after=40))
    P.append(bullet("ตารางเรียงตามกลุ่ม GL (gl_group) แล้วตามรหัส GL — กลุ่มเดียวกันอยู่ติดกัน", sz=20))
    P.append(bullet("ป้ายกลุ่ม GL พิเศษเป็นสีเฉพาะกลุ่ม (เดิมเป็นสีรุ้ง): Entertainment = เหลือง · Lease & Rental = ชมพู · "
                    "Professional & Legal Fee = ม่วง · Public Relation & Donation = ส้ม · Training & Seminar = ฟ้า · Travelling Expense = เขียว", sz=20))

    # ── 12. Approve on the main page — no separate inbox ──
    P.append(heading("12) อนุมัติบนหน้าหลัก — ไม่มีหน้า inbox แยก"))
    P.append(body_para(
        "ผู้อนุมัติ (Approver) ตรวจและอนุมัติบน \"หน้าหลักเดียวกัน\" กับที่ผู้กรอกใช้ — ไม่มีหน้า inbox แยกอีกต่อไป "
        "(หน้า approver-inbox เดิมถูกยกเลิก) · เลือกฝ่ายที่จะตรวจจากตัวเลือกฝ่าย (ดูข้อ 13) แล้วกด อนุมัติ/ตีกลับ ที่แถบล่าง", sz=21))
    P.append(bullet("ปุ่มอนุมัติ/ตีกลับ จะโผล่เมื่อ \"ฝ่ายที่เลือก\" อยู่ที่ขั้นการอนุมัติของผู้ใช้คนนั้นพอดี (ดูข้อ 13.1)", sz=20))
    P.append(bullet("กดอนุมัติ = ส่งต่อขั้นถัดไป (PENDING_APPROVER1→2→3→APPROVED) · กดตีกลับ = ทั้งฝ่ายกลับเป็น REJECTED + แจ้งผู้ส่งล่าสุด", sz=20))
    P.append(bullet("อนุมัติ/ตีกลับ ทำทั้งฝ่ายเป็นก้อนเดียว (ทุก CC ในฝ่าย) — ไม่ใช่ราย CC หรือราย GL (หน่วยอนุมัติ = ฝ่าย)", sz=20))
    P.append(para(run("ภาพประกอบ: แถบ Action (ผู้อนุมัติ — อนุมัติ/ตีกลับ)", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["action_approver"], *meta["action_approver"][1], 109, "main_action_approver", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "ปุ่ม อนุมัติทั้งฝ่าย", "ส่งต่อขั้นถัดไป — โผล่เมื่อฝ่ายอยู่ที่ขั้นของผู้อนุมัติคนนี้พอดี"],
        ["②", "ปุ่ม ตีกลับทั้งฝ่าย", "ตีกลับทั้งฝ่าย → REJECTED + แจ้งผู้ส่งล่าสุด (ต้องระบุเหตุผล)"],
    ], [620, 3700, 5040]))

    # ── 13. ฝ่าย-picker — the approval unit ──
    P.append(heading("13) ตัวเลือกฝ่าย (ฝ่าย-picker) = หน่วยอนุมัติ (ADR-0008)"))
    P.append(body_para(
        "ตัวเลือกฝ่ายแทนตัวกรองสายงานเดิม · ล็อกหน้าให้เหลือ 1 (ฝ่าย/Department, ปีงบประมาณ) ซึ่งเป็น "
        "\"หน่วยอนุมัติ\" (1 ฝ่าย/ปี = 1 ก้อนอนุมัติ) · รายการฝ่ายจัดกลุ่มตามสายงาน (Division)", sz=21))
    P.append(bullet("ผู้กรอก (Submitter): ถูกล็อกที่ฝ่ายของตนอัตโนมัติ — กรอกได้เฉพาะฝ่ายของตน", sz=20))
    P.append(bullet("ผู้อนุมัติ (Approver): แต่ละฝ่ายมีป้าย \"รออนุมัติ\" (ถึงคิวฉัน) / \"อนุมัติแล้ว\" (ผ่านขั้นฉันแล้ว) + "
                    "toggle \"เฉพาะที่รออนุมัติ\" เพื่อกรองเหลือเฉพาะคิวของตน", sz=20))
    P.append(para(run("ภาพประกอบ: ตัวเลือกฝ่าย (เปิด) — มุมมองผู้อนุมัติ พร้อมป้ายสถานะ", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["fai_picker"], *meta["fai_picker"][1], 110, "main_fai_picker", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "แผงเลือกฝ่าย (จัดกลุ่มตามสายงาน)", "เลือก 1 ฝ่าย → ล็อกหน้า (ฝ่าย, ปี) · แต่ละฝ่ายมีป้าย รออนุมัติ/อนุมัติแล้ว สำหรับผู้อนุมัติ"],
        ["②", "toggle เฉพาะที่รออนุมัติ", "กรองเหลือเฉพาะฝ่ายที่ถึงคิวอนุมัติของผู้ใช้คนนี้ (ผู้อนุมัติเท่านั้น)"],
    ], [620, 3700, 5040]))
    P.append(para(run("(13.1) แถบ Action — ปุ่มขึ้นกับ \"ฝ่ายที่เลือก\" ไม่ใช่บทบาท",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(bullet("ปุ่ม Submit โผล่เมื่อ ฝ่ายที่เลือก ∈ ขอบเขตการกรอก (fill-scope) ของผู้ใช้", sz=20))
    P.append(bullet("ปุ่ม อนุมัติ/ตีกลับ โผล่เมื่อ ฝ่ายที่เลือก อยู่ที่ขั้นการอนุมัติของผู้ใช้พอดี", sz=20))

    # ── 14. Admin-mode toggle (overlay admin) ──
    P.append(heading("14) ปุ่ม 🛡️ โหมด Admin (overlay admin · ADR-0014)"))
    P.append(body_para(
        "ผู้ที่มีบทบาทซ้อน (overlay admin — วราพร/นิภาพร/ปิยะดา) ปกติทำงานในบทบาทฐานของตน (approver/submitter) "
        "แล้วสลับเข้าสู่บทบาท admin (เห็นทุก CC · แก้ Pending ทุก CC · เห็นแถบ Admin/Import + Master FX) ผ่านปุ่ม "
        "\"🛡️ โหมด Admin\" ที่มุมขวาบน · Admin แท้ (jakkaritw) เป็น admin ตลอดเวลา ไม่มีปุ่มสลับ", sz=21))
    P.append(bullet("ปิดโหมด Admin → กลับสู่บทบาทฐาน (เช่น นิภาพรกลับเป็นผู้อนุมัติขั้นที่ 2) · เปิด → ได้บทบาท admin ทันที", sz=20))
    P.append(bullet("เหตุผล: คนชุดเดียวกันทำหลายบทบาท — แยก \"หมวก\" ให้ชัด กันเผลอใช้บทบาท admin ตอนทำงานปกติ", sz=20))
    P.append(para(run("ภาพประกอบ: ปุ่ม โหมด Admin (overlay admin · นิภาพร)", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["admin_mode"], *meta["admin_mode"][1], 111, "main_admin_mode", width_in=3.4))

    # ── 15. Master FX read-only here (owned by Module 09) ──
    P.append(heading("15) Master FX เป็น read-only ที่หน้านี้ (เป็นของ Module 09 · ADR-0015)"))
    P.append(body_para(
        "อัตราแลกเปลี่ยน USD→THB (Master FX) แสดงในแถบ Admin แบบ \"อ่านอย่างเดียว\" — แก้ไขได้ที่หน้า "
        "Master Currency (Module 09) เท่านั้น · หน้า OPEX นี้แค่อ่านค่ามาแสดง และใช้คำนวณเบี้ยเลี้ยงเดินทาง "
        "ต่างประเทศ (per-diem) ใหม่ทุกครั้งที่อ่าน (recompute-on-read)", sz=21))
    P.append(bullet("ค่า FX ผูกตามปีงบประมาณ (เช่น FY2025 = 35.00) — ตัวกรองปีเปลี่ยน → FX ที่แสดงเปลี่ยนตาม", sz=20))
    P.append(bullet("แบบเดโม่ sync ค่าระหว่างหน้าผ่าน localStorage (cm.masterFX) — แก้ที่ Module 09 แล้วหน้านี้คิด per-diem ใหม่อัตโนมัติ", sz=20))
    P.append(bullet("เฉพาะ Admin เห็นแถบนี้ (รวม Master FX) — ผู้ใช้ทั่วไปไม่เห็น", sz=20))
    P.append(para(run("ภาพประกอบ: แถบ Master FX (USD→THB · อ่านอย่างเดียว) ในแถบ Admin", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["fx_only"], *meta["fx_only"][1], 113, "main_fx_only", width_in=3.4))
    P.append(para(run("ภาพประกอบ: หน้า Master Currency (Module 09) — ที่แก้ไขอัตรา FX จริง (ฟอร์มแก้ปี/อัตรา + ตารางรายปี · FY2025 = 35.00)",
                      sz=22, bold=True, color="1E3A24"), space_before=80, space_after=40))
    P.append(image_para(rids["mc_page"], *meta["mc_page"][1], 114, "main_master_currency_page", width_in=6.3))

    # ── 16. Edit-lock by status × role ──
    P.append(heading("16) การล็อกการแก้ไข ตามสถานะ × บทบาท (edit-lock · ADR-0013)"))
    P.append(body_para(
        "การแก้ไขช่อง Pending ขึ้นกับ \"สถานะของฝ่าย\" และ \"บทบาทของผู้ใช้\" · การแก้ไขไม่เคยเปลี่ยนสถานะ — "
        "สถานะเลื่อนได้ทาง Submit/Approve/Reject เท่านั้น · มี 6 สถานะ: "
        "DRAFT / PENDING_APPROVER1 / PENDING_APPROVER2 / PENDING_APPROVER3 / APPROVED / REJECTED", sz=21))
    P.append(table([
        ["บทบาท", "สถานะที่แก้ Pending ได้", "หมายเหตุ"],
        ["ผู้กรอก (Submitter)", "DRAFT, REJECTED เท่านั้น", "PENDING_* / APPROVED → ล็อก (อ่านอย่างเดียว · มีป้าย 🔒)"],
        ["ผู้อนุมัติ (Approver)", "— (ไม่แก้)", "ดูเพื่อตรวจอย่างเดียว → read-only"],
        ["Admin", "ทุกสถานะ", "แก้ Pending ได้ทุก CC ทุกสถานะ (รวม APPROVED)"],
    ], [2400, 3000, 3800]))
    P.append(para(run("ภาพประกอบ: แถว Pending ที่ถูกล็อก (หลัง Submit · มุมมองผู้กรอก)", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(image_para(rids["edit_lock"], *meta["edit_lock"][1], 112, "main_edit_lock", width_in=6.3))
    P.append(table([
        ["#", "จุด", "ความหมาย"],
        ["①", "สถานะแถว Pending (มีป้าย 🔒)", "สถานะ PENDING_APPROVER1 — ผู้กรอกแก้ไม่ได้ (รออนุมัติ)"],
        ["②", "ช่องรายเดือน (อ่านอย่างเดียว)", "ช่องกรอกถูกล็อกเป็น read-only — ปลดล็อกเมื่อถูกตีกลับ (REJECTED)"],
    ], [620, 3700, 5040]))
    P.append(para(run("(16.1) Admin submit — 2 โหมด (ADR-0012)", sz=22, bold=True, color="1E3A24"),
                  space_before=80, space_after=40))
    P.append(bullet("ในรอบปกติ: Admin Submit ได้เฉพาะ \"ฝ่าย orphan\" (ไม่มีผู้กรอก) → APPROVED ตรงๆ ไม่ผ่าน chain (log ADMIN_OVERRIDE)", sz=20))
    P.append(bullet("หลัง deadline: Admin override-edit + Submit ฝ่ายใดก็ได้แทน (ผู้ใช้ถูกล็อก) → APPROVED ตรงๆ · มี toggle ทดสอบ \"🔒 หลัง deadline\"", sz=20))
    P.append(bullet("ทั้ง 2 โหมด Submit/Approve ทำทั้งก้อน (ฝ่าย, ปี) เสมอ แม้แก้แค่ CC เดียว", sz=20))

    # ── Closing note ──
    P.append(heading("หมายเหตุท้ายเอกสาร"))
    P.append(para(run(
        "เอกสารฉบับร่าง (Draft · v0.7) — ข้อสรุปการออกแบบทั้งหมดดูได้ในข้อ 7 · "
        "ภาพประกอบ render จากแบบ (mockup) ตัวเลข/ชื่อเป็นข้อมูลตัวอย่าง · "
        "วงกลมสีทองคือจุดอ้างอิงในตารางคำอธิบายของแต่ละหัวข้อ",
        sz=20, italic=True, color="8C6423"), space_before=40, space_after=120))

    P.append(heading("ช่องลงนามอนุมัติ (Sign-off)"))
    P.append(_sign_table([["บทบาท", "ชื่อ-นามสกุล", "ลายเซ็น", "วันที่"], ["ผู้จัดทำ", "", "", ""],
                          ["ผู้ตรวจสอบ", "", "", ""], ["ผู้อนุมัติ", "", "", ""]], SIGN))
    return "".join(P)


def content_types_xml():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="png" ContentType="image/png"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
def root_rels_xml():
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
def document_rels_xml(image_rels):
    r = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for rid, fn in image_rels:
        r.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{fn}"/>')
    r.append('</Relationships>'); return "".join(r)
def document_xml(body):
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
            'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
            'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
            'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>'
            f'{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
            '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="708" w:footer="708" w:gutter="0"/>'
            '</w:sectPr></w:body></w:document>')


def main():
    print("[1/4] Capturing main-page screenshots + DOM rects (Playwright) ...")
    shots = capture()
    print("[2/4] Annotating with gold markers (Pillow) ...")
    meta = {}
    # login_admin/login_user carry NO markers (login-bar views near top). New 2026-06-13:
    # fai_picker / action_approver / admin_mode / edit_lock document the wired approve-on-
    # main-page flow (ฝ่าย-picker, action bar, admin-mode toggle, edit-lock by status×role).
    order = ["login_admin", "login_user", "overview", "sap", "approved", "pending",
             "toolbar", "admin_zone", "fai_picker", "action_approver", "admin_mode",
             "edit_lock", "detail", "fx_only", "mc_page"]
    for k in order:
        src, markers = shots[k]
        meta[k] = annotate(src, os.path.basename(src), markers)
        print(f"      {k}: {meta[k][0]}  {meta[k][1]}  markers={len(markers)}")

    # ---- PROOF (computed only — no PNG viewing) ---------------------------- #
    def _inside(m):
        return (m["ex"] <= m["tx"] <= m["ex"] + m["ew"]
                and m["ey"] <= m["ty"] <= m["ey"] + m["eh"])
    print("[PROOF] per-image marker counts:",
          {k: len(shots[k][1]) for k in ("sap", "approved", "pending")})
    sap_m = shots["sap"][1]
    print(f"[PROOF] SAP ①: leader=({sap_m[0]['tx']:.0f},{sap_m[0]['ty']:.0f}) "
          f"in status box[{sap_m[0]['ex']:.0f},{sap_m[0]['ey']:.0f},"
          f"{sap_m[0]['ew']:.0f},{sap_m[0]['eh']:.0f}] inside={_inside(sap_m[0])} "
          f"fill={sap_m[0]['fill']} (RED={sap_m[0]['fill']==RED})")
    print(f"[PROOF] SAP ②: leader=({sap_m[1]['tx']:.0f},{sap_m[1]['ty']:.0f}) "
          f"in value  box[{sap_m[1]['ex']:.0f},{sap_m[1]['ey']:.0f},"
          f"{sap_m[1]['ew']:.0f},{sap_m[1]['eh']:.0f}] inside={_inside(sap_m[1])} "
          f"fill={sap_m[1]['fill']} (GREEN={sap_m[1]['fill']==GREEN})")
    ap_m = shots["approved"][1]
    print(f"[PROOF] APPROVED ① (read-only cell): leader=({ap_m[0]['tx']:.0f},{ap_m[0]['ty']:.0f}) "
          f"in cell  box[{ap_m[0]['ex']:.0f},{ap_m[0]['ey']:.0f},"
          f"{ap_m[0]['ew']:.0f},{ap_m[0]['eh']:.0f}] inside={_inside(ap_m[0])} "
          f"fill={ap_m[0]['fill']} (GOLD={ap_m[0]['fill']==GOLD})")
    print(f"[PROOF] APPROVED ② (Import btn): leader=({ap_m[1]['tx']:.0f},{ap_m[1]['ty']:.0f}) "
          f"in import box[{ap_m[1]['ex']:.0f},{ap_m[1]['ey']:.0f},"
          f"{ap_m[1]['ew']:.0f},{ap_m[1]['eh']:.0f}] inside={_inside(ap_m[1])} "
          f"fill={ap_m[1]['fill']} (GOLD={ap_m[1]['fill']==GOLD})")
    # DETAIL image: both markers on the SAME Professional & Legal Fee row (data-txn-id=5,
    # Solution Delivery). ① = .btn-detail → RED · ② = leftmost pending-readonly → GREEN.
    det_m = shots["detail"][1]
    det_txn = "5"  # the data-txn-id both detail selectors are pinned to
    print(f"[PROOF] DETAIL anchored to data-txn-id={det_txn} (both markers, Professional & Legal Fee)")
    print(f"[PROOF] DETAIL ① (btn-detail): leader=({det_m[0]['tx']:.0f},{det_m[0]['ty']:.0f}) "
          f"in button box[{det_m[0]['ex']:.0f},{det_m[0]['ey']:.0f},"
          f"{det_m[0]['ew']:.0f},{det_m[0]['eh']:.0f}] inside={_inside(det_m[0])} "
          f"fill={det_m[0]['fill']} (RED={det_m[0]['fill']==RED})")
    print(f"[PROOF] DETAIL ② (pending-readonly): leader=({det_m[1]['tx']:.0f},{det_m[1]['ty']:.0f}) "
          f"in cell  box[{det_m[1]['ex']:.0f},{det_m[1]['ey']:.0f},"
          f"{det_m[1]['ew']:.0f},{det_m[1]['eh']:.0f}] inside={_inside(det_m[1])} "
          f"fill={det_m[1]['fill']} (GREEN={det_m[1]['fill']==GREEN})")
    for k in ("overview", "toolbar", "pending", "admin_zone",
              "fai_picker", "action_approver", "admin_mode", "edit_lock"):
        ms = shots[k][1]
        allgold = all(m["fill"] == GOLD for m in ms)
        print(f"[PROOF] {k}: markers={len(ms)} default GOLD = {allgold}")
    # ----------------------------------------------------------------------- #

    media = {k: f"image{i+1}.png" for i, k in enumerate(order)}
    rids = {k: f"rId{i+10}" for i, k in enumerate(order)}
    image_rels = [(rids[k], media[k]) for k in order]
    print("[3/4] Building OOXML ...")
    doc = document_xml(build_body(meta, rids))
    print("[4/4] Writing .docx ...")
    if os.path.exists(DOCX_PATH): os.remove(DOCX_PATH)
    with zipfile.ZipFile(DOCX_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml())
        z.writestr("_rels/.rels", root_rels_xml())
        z.writestr("word/document.xml", doc.encode("utf-8"))
        z.writestr("word/_rels/document.xml.rels", document_rels_xml(image_rels))
        for k in order:
            with open(meta[k][0], "rb") as f:
                z.writestr(f"word/media/{media[k]}", f.read())
    print(f"DONE: {DOCX_PATH}  ({os.path.getsize(DOCX_PATH)} bytes)")


if __name__ == "__main__":
    main()
