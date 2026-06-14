"""
Generate Approval Workflow Spec PDF (sign-off version)
Usage: python requirement_spec/3_approval_workflow/generate_pdf.py
"""
from fpdf import FPDF

FONT_PATH = r"C:\Windows\Fonts\tahoma.ttf"
FONT_BOLD_PATH = r"C:\Windows\Fonts\tahomabd.ttf"
OUT_PATH = r"c:\04.budget_management_web\requirement_spec\3_approval_workflow\approval_workflow_spec.pdf"

BLUE   = (31, 73, 125)
LGRAY  = (245, 245, 245)
DGRAY  = (80, 80, 80)
BLACK  = (0, 0, 0)
WHITE  = (255, 255, 255)
GREEN  = (0, 112, 68)

class PDF(FPDF):
    def header(self):
        self.set_fill_color(*BLUE)
        self.rect(0, 0, 210, 16, "F")
        self.set_font("th", "B", 10)
        self.set_text_color(*WHITE)
        self.set_xy(10, 4)
        self.cell(0, 8, "CHEMEMAN PUBLIC COMPANY LIMITED  |  Budget Management Web", align="L")
        self.set_xy(0, 4)
        self.cell(200, 8, f"Page {self.page_no()}", align="R")
        self.set_text_color(*BLACK)
        self.ln(14)

    def footer(self):
        self.set_y(-12)
        self.set_font("th", "", 8)
        self.set_text_color(*DGRAY)
        self.cell(0, 6, "Approval Workflow Specification  |  Confidential  |  2026-05-27", align="C")
        self.set_text_color(*BLACK)

    def section_title(self, text):
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font("th", "B", 10)
        self.cell(0, 8, f"  {text}", fill=True, ln=True)
        self.set_text_color(*BLACK)
        self.ln(2)

    def subsection(self, text):
        self.set_font("th", "B", 9)
        self.set_text_color(*BLUE)
        self.cell(0, 6, text, ln=True)
        self.set_text_color(*BLACK)
        self.set_font("th", "", 9)

    def body(self, text, indent=0):
        self.set_font("th", "", 9)
        self.set_x(10 + indent)
        self.multi_cell(0, 5.5, text)

    def bullet(self, text, indent=4):
        self.set_font("th", "", 9)
        self.set_x(10 + indent)
        self.cell(5, 5.5, "•", ln=False)
        self.multi_cell(0, 5.5, text)

    def note(self, text):
        self.set_fill_color(*LGRAY)
        self.set_font("th", "", 8.5)
        self.set_text_color(*DGRAY)
        self.set_x(10)
        self.multi_cell(0, 5, f"  {text}", fill=True)
        self.set_text_color(*BLACK)
        self.ln(1)

    def table_header(self, cols, widths):
        self.set_fill_color(*BLUE)
        self.set_text_color(*WHITE)
        self.set_font("th", "B", 8.5)
        for col, w in zip(cols, widths):
            self.cell(w, 7, f" {col}", border=1, fill=True)
        self.ln()
        self.set_text_color(*BLACK)

    def table_row(self, cells, widths, fill=False):
        self.set_fill_color(*LGRAY)
        self.set_font("th", "", 8.5)
        for cell, w in zip(cells, widths):
            self.cell(w, 6.5, f" {cell}", border=1, fill=fill)
        self.ln()

    def hline(self):
        self.set_draw_color(200, 200, 200)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(3)


def build():
    pdf = PDF(orientation="P", unit="mm", format="A4")
    pdf.add_font("th", "", FONT_PATH, uni=True)
    pdf.add_font("th", "B", FONT_BOLD_PATH, uni=True)
    pdf.set_margins(10, 18, 10)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()

    # ── Title block ──────────────────────────────────────────────────────────
    pdf.set_font("th", "B", 16)
    pdf.set_text_color(*BLUE)
    pdf.cell(0, 10, "Approval Workflow Specification", ln=True, align="C")
    pdf.set_font("th", "", 9)
    pdf.set_text_color(*DGRAY)
    pdf.cell(0, 5, "Budget Management Web  |  Version 1.0  |  2026-05-27  |  Status: Confirmed", ln=True, align="C")
    pdf.set_text_color(*BLACK)
    pdf.ln(5)

    # ── Section 1: Overview ───────────────────────────────────────────────────
    pdf.section_title("1. Overview")
    pdf.body("Budget submissions follow a 3-level approval chain:")
    pdf.ln(2)
    pdf.set_fill_color(*LGRAY)
    pdf.set_font("th", "B", 9)
    pdf.set_x(20)
    chain = [
        ("[1]  Submitter (L3/L4)",        "กรอกงบประมาณ และกด Submit"),
        ("[2]  approver1 — Direct Manager", "managerempcode จาก HR (อัตโนมัติ)"),
        ("[3]  approver2 — Budget Staff",   "นิภาพร ทองกิ่ง (101032) — fixed"),
        ("[4]  approver3 — Budget Manager", "วราพร ติรสิทธิ์ (100427) — fixed"),
    ]
    for step, desc in chain:
        pdf.set_font("th", "B", 9)
        pdf.set_x(18)
        pdf.cell(70, 7, step, border=0)
        pdf.set_font("th", "", 9)
        pdf.cell(0, 7, desc, ln=True)
    pdf.ln(3)

    # ── Section 2: Submitters ─────────────────────────────────────────────────
    pdf.section_title("2. Submitters")
    pdf.bullet("L3: Department Head, Assistant Department Head (all variants)")
    pdf.bullet("L4: Supervisor 1/2, Senior Supervisor 1/2 (all variants)")
    pdf.ln(1)
    pdf.subsection("Excluded from system:")
    pdf.bullet("L1 (C-Level), L2 (VP/AVP) — approvers only, do not submit")
    pdf.bullet("L5: Operator 1/2/3, Driver, Maid — not in budget system")
    pdf.bullet("empcode LIKE '4%' — Gritsman subsidiary")
    pdf.bullet("orgcode LIKE '117%' — Office of Affiliate (Vietnam)")
    pdf.ln(2)

    pdf.subsection("Valid approver1 level combinations:")
    pdf.table_header(["Submitter Level", "approver1 Level", "Count", "Example"],
                     [42, 50, 20, 78])
    rows = [
        ("L4", "L4 (Senior Supervisor)", "42", "Senior Supervisor manages Supervisor"),
        ("L4", "L3 (Dept Head)", "103", "Normal chain"),
        ("L3", "L2 (VP/AVP)", "43", "Normal chain"),
        ("L3", "L1 (C-Level)", "2",  "Yuan-Ming, ฐานิยา — direct to C-Level"),
        ("L2", "L1 (C-Level)", "3",  "ปรัชญา, ปิยะนุช, ธนกฤษณ์"),
    ]
    for i, r in enumerate(rows):
        pdf.table_row(r, [42, 50, 20, 78], fill=(i % 2 == 1))
    pdf.ln(3)

    # ── Section 3: approver1 Rule ─────────────────────────────────────────────
    pdf.section_title("3. approver1 Lookup Rule")
    pdf.body("Use managerempcode field from mas_employee_data directly — do NOT derive from level or walk up the hierarchy.")
    pdf.note("SQL: SELECT managerempcode FROM mas_employee_data WHERE empcode = :submitter AND posstatus = 'Primary'")
    pdf.ln(2)

    # ── Section 4: Special Cases ──────────────────────────────────────────────
    pdf.section_title("4. Special Cases (all confirmed)")
    cases = [
        ("นิภาพร submits own budget",
         "Submit → วราพร (approver1 = direct manager) → END  (skip herself as approver2)"),
        ("วราพร submits own budget",
         "Submit → ปิยะดา ดวงพลจันทร์ (approver1) → END  (she IS final approver)"),
        ("C-Level approves in the system",
         "อภิชัย, เลิศศักดิ์, ปรีด์ click approve themselves — no PA"),
        ("ฐานิยา fills อภิชัย’s budget",
         "Self-review — intentional design. ฐานิยา fills, CTO approves."),
    ]
    for title, desc in cases:
        pdf.set_font("th", "B", 9)
        pdf.set_x(12)
        pdf.cell(0, 6, f">>  {title}", ln=True)
        pdf.set_font("th", "", 9)
        pdf.set_x(18)
        pdf.multi_cell(0, 5.5, desc)
        pdf.ln(1)
    pdf.ln(1)

    # ── Section 5: C-Level Map ────────────────────────────────────────────────
    pdf.section_title("5. C-Level → Assigned Submitters")
    pdf.table_header(["C-Level", "empcode", "Assigned Submitter", "empcode"],
                     [60, 22, 72, 22])
    clevel = [
        ("อดิศักดิ์ เหล่าจันทร์ (CEO)", "100001",
         "แพรวทิพย์ ลิ้มจิระวัฒนา", "101300"),
        ("จันทรจุฑา จันทรทัต (CEO-Int’l)", "10T018",
         "แพรวทิพย์ ลิ้มจิระวัฒนา", "101300"),
        ("อภิชัย สมบูรณ์ปกรณ์ (CTO)", "101875",
         "ฐานิยา วิจิตรพนมศิลป์", "101905"),
        ("เลิศศักดิ์ บุญส่งทรัพย์ (CSO)", "101632",
         "ปรัชญา + ปิยะนุช", "100164+101801"),
        ("ปรีด์ สุวิมลธีระบุตร (CCO)", "101754",
         "ธนกฤษณ์ ศรีอนุชาต", "101429"),
    ]
    for i, r in enumerate(clevel):
        pdf.table_row(r, [60, 22, 72, 22], fill=(i % 2 == 1))
    pdf.ln(3)

    # ── Section 6: Approval Unit ──────────────────────────────────────────────
    pdf.section_title("6. Approval Unit (Granularity)")
    pdf.body("1 Submission = 1 approval unit per Division + Fiscal Year")
    pdf.bullet("User fills Template 1.1 + all 1.2 sub-templates → Submit once as 1 package")
    pdf.bullet("Approver sees entire division budget → approve/reject the whole package")
    pdf.bullet("approval_status table tracks at (division, fiscal_year) level — NOT per row or GL")
    pdf.ln(2)

    # ── Section 7: Status Flow ────────────────────────────────────────────────
    pdf.section_title("7. Approval Status Flow")
    pdf.set_font("th", "", 9)
    pdf.set_fill_color(*LGRAY)
    flow = [
        ("DRAFT", "submitter saves without submitting", LGRAY),
        ("PENDING_L1", "after submitter clicks Submit", (255, 243, 205)),
        ("PENDING_L2", "after approver1 approves", (255, 243, 205)),
        ("APPROVED", "after Waraporn approves — final [APPROVED]", (209, 231, 221)),
        ("REJECTED_BY_L1", "approver1 rejects", (248, 215, 218)),
        ("REJECTED_BY_L2", "Nipaporn rejects", (248, 215, 218)),
        ("REJECTED_BY_L3", "Waraporn rejects (rare)", (248, 215, 218)),
    ]
    for status, desc, color in flow:
        pdf.set_fill_color(*color)
        pdf.set_font("th", "B", 9)
        pdf.set_x(12)
        pdf.cell(52, 6.5, f"  {status}", border=1, fill=True)
        pdf.set_font("th", "", 9)
        pdf.set_fill_color(*LGRAY)
        pdf.cell(0, 6.5, f"  {desc}", border=1, fill=True, ln=True)
    pdf.ln(3)

    # ── Section 8: Which Templates ────────────────────────────────────────────
    pdf.section_title("8. Workflow Applies To")
    pdf.table_header(["Template", "Approval Workflow", "Reason"], [70, 42, 78])
    pdf.table_row(["1.1 Main + 1.2 sub-templates", "[YES] Full 3-level workflow", "Submitted as 1 package"], [70, 42, 78], False)
    pdf.table_row(["Template 2 (Budget dept)", "[NO] Waraporn confirms directly", "Budget dept fills; no self-approval"], [70, 42, 78], True)
    pdf.ln(3)

    # ── Section 9: Email Triggers ─────────────────────────────────────────────
    pdf.section_title("9. Email Notification Triggers")
    pdf.table_header(["Event", "Notify"], [90, 100])
    emails = [
        ("Submitter clicks Submit", "approver1 (direct manager)"),
        ("approver1 Approves", "นิภาพร ทองกิ่ง (Budget Staff)"),
        ("approver1 Rejects", "Submitter"),
        ("นิภาพร Approves", "วราพร ติรสิทธิ์ (Budget Manager)"),
        ("นิภาพร Rejects", "Submitter + approver1"),
        ("วราพร Approves", "Submitter — final confirmation [APPROVED]"),
        ("วราพร Rejects", "Submitter + approver1 + นิภาพร"),
        ("Deadline reminder", "All users who have not submitted"),
    ]
    for i, (ev, notify) in enumerate(emails):
        pdf.table_row([ev, notify], [90, 100], fill=(i % 2 == 1))
    pdf.ln(3)

    # ── Section 10: User Summary ──────────────────────────────────────────────
    pdf.section_title("10. User Count Summary")
    pdf.table_header(["Role", "Count"], [140, 30])
    usrs = [
        ("submitter only", "177"),
        ("submitter + approver1", "73"),
        ("approver1 only (L1/L2 direct managers who don’t submit)", "21"),
        ("submitter + approver2 (นิภาพร)", "1"),
        ("submitter + approver3 (วราพร)", "1"),
        ("Total", "273"),
    ]
    for i, (r, c) in enumerate(usrs):
        fill = (i % 2 == 1)
        if i == len(usrs) - 1:
            pdf.set_font("th", "B", 9)
        pdf.table_row([r, c], [140, 30], fill=fill)
    pdf.ln(3)

    # ── Signature Block ───────────────────────────────────────────────────────
    pdf.add_page()
    pdf.section_title("Sign-off & Approval")
    pdf.body("This document has been reviewed and agreed upon by the following parties.")
    pdf.ln(6)

    sig_cols = [60, 60, 60]
    headers  = ["Prepared by", "Reviewed by", "Approved by"]
    names    = ["Jakkarit T.", "________________", "________________"]
    roles    = ["Developer", "Budget Staff", "Budget Manager"]
    dates    = ["2026-05-27", "____________", "____________"]

    pdf.set_font("th", "B", 9)
    for h, w in zip(headers, sig_cols):
        pdf.cell(w, 7, h, align="C")
    pdf.ln()

    pdf.set_font("th", "", 9)
    for n, w in zip(names, sig_cols):
        pdf.set_fill_color(*LGRAY)
        pdf.cell(w, 22, "", border=1)
    pdf.ln()

    pdf.set_font("th", "B", 9)
    for n, w in zip(names, sig_cols):
        pdf.cell(w, 6, n, align="C")
    pdf.ln()

    pdf.set_font("th", "", 9)
    for r, w in zip(roles, sig_cols):
        pdf.cell(w, 5.5, r, align="C")
    pdf.ln()
    pdf.set_text_color(*DGRAY)
    for d, w in zip(dates, sig_cols):
        pdf.cell(w, 5.5, f"Date: {d}", align="C")
    pdf.ln(10)
    pdf.set_text_color(*BLACK)

    pdf.note("Full user list: docs/budget_actors_full.csv (273 rows, 16 columns)")

    pdf.output(OUT_PATH)
    print(f"PDF saved: {OUT_PATH}")


if __name__ == "__main__":
    build()
