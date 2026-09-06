# D4 — What goes into the UAT pack?

Type: `wayfinder:grilling` · Status: **CLOSED 2026-09-06** · Blocked by: nothing

## Question

Re-run all 61 SIT cases, or a business-acceptance subset plus new cases for everything shipped
after SIT closed?

## What SIT actually covered

61 cases across 11 modules, all Pass except TC-027 (export, out of scope) and TC-042. But it ran
with **one department and three people**, so whole features were never touched:

**Zero coverage:** attachments (the entire feature — upload, reject-extension, >10 MB, download,
delete with its irreversible Thai confirm, the `เอกสาร ฝ่าย/` path guard) · the Admin-mode
toggle and admin overlay · **the department picker with more than one ฝ่าย** · the Approved /
`board_budget` layer · SAP actuals columns and ADR-0026 month masking · the per-diem **baht
figure** (TC-061 asserts no number at all) · year lock / `NOT_OPEN` · the locked-row 🔒 read-only
subform · restricted and hidden GLs · grid filters, column width, fullscreen · deleting a
hand-added grid row · the remark column · the no-scope empty state.

**Now stale:** 15 cases still say `รออนุมัติ` and 11 say `ตีกลับ`, but the whole approval module
went English on 2026-09-05 (`Reject` / `Approve` / `Pending · Step N` / the dept-picker badge
`Pending`). TC-061 expects a 4-row trip table and a greyed-out remark box — both wrong since
2026-09-04. **TC-057 uses seminar GL `6210100150` with a Data & Analytic filler, which the
2026-08-29 restriction now hides from that picker entirely** — that case would fail today, and
it is a live regression risk nobody has retested.

## The delta nobody has ever tested

12 user-visible changes shipped after the last SIT case was executed, all live on both
environments: CI-green repaint · per-diem tier 3 (13→29 countries) · searchable destination
combobox · real English approver titles · the hundreds-rounding legend note · the seminar-GL
restriction · a brand-new toast surface (3 Thai messages, 6 s TTL) · the trip `รายละเอียด` field
becoming editable · the other-travel GL pair leaving the trip form · and the approval module's
full Englishing. A draft of ~25 candidate cases (U-01…U-25) with Thai scenario lines is in
`research/post-sit-changes.md` §7.

## Three known defects in the workbook itself

1. `3. Summary`'s module breakdown has **no row for `Special GL Subform`** — 6 cases are
   silently uncounted.
2. The instructions promise a **Defect ID** column that does not exist.
3. Ranges are hard-coded `$4:$64` with `freeze_panes = I36`; appending rows breaks the Summary
   counts and the autofilter unless every range is extended.

And the sheet has **no `Department` column** — a two-department round needs one.

## Options

- **(a) All 61 re-run and re-worded.** Thorough, heavy for five people in 3–5 days.
- **(b) A business-acceptance subset (~30) plus ~25 new-behaviour cases.** Drop the Security,
  Data Integrity and backend-SQL cases and TC-027; keep what a business user can actually judge.
- **(c) New and changed behaviour only (~25).**

## Recommendation

**(b).** It is the only version that both fits the window and covers the delta. Add the
`Department` column, fix the three workbook defects, and re-word every case that quotes a Thai
string the app no longer renders.

---

## RESOLUTION — CLOSED 2026-09-06

**jakkaritw chose (b): a business-acceptance subset (~30) plus the new-behaviour block (~25).**

What that means concretely for T5:

**Drop from the SIT 61:** the Security module, the Data Integrity module, every case whose
Expected Result can only be judged by reading SQL or backend logs, and TC-027 (export, out of
scope for this version). These are engineering checks, not things five business users can
accept or reject.

**Keep and re-word:** everything a filler or approver can judge on screen. Every case quoting a
Thai string the app no longer renders must be rewritten — 15 cases say `รออนุมัติ`, 11 say
`ตีกลับ`, and the whole approval module went English on 2026-09-05.

**Rewrite outright, because they now assert the wrong thing:**
- **TC-061** — expects a 4-row trip expense table and a greyed-out `รายละเอียด` box. Live: 3
  rows, and the remark is editable and persists to `budget.budget_trip.remark`.
- **TC-057** — has a Data & Analytic filler entering seminar GL `6210100150`. Since `a096e26`
  (2026-08-29) that GL is hidden from the picker for any cost center outside Talent & Culture.
  **The case would fail today.** It becomes the positive test of the restriction instead.
- **TC-013 / TC-035** — decimals and "very large amounts". Live behaviour is integer-only,
  rounded half-up to hundreds, capped at 100,000,000 per cell, each correction narrated by a
  toast.
- **TC-005** — pinned to a 20-minute session that no longer exists anywhere. Re-write against
  whatever D5 settles.

**Add the ~25 new cases** drafted with Thai scenario lines in `research/post-sit-changes.md` §7
(U-01…U-25), covering the 12 uncovered shipped changes plus the two-department switching that
SIT could never test.

**Fix the three inherited workbook defects and add the two missing columns** — the absent
`Special GL Subform` row in the Summary breakdown, the promised-but-missing Defect ID column,
the hard-coded `$4:$64` ranges, a new `Department` column, and a `4. Defects` sheet.
