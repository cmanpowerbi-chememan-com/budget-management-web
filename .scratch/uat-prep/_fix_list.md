# FIX LIST — UAT pack repair round (from the completeness audit, 2026-09-07)

The pack at `requirement_spec/5_uat/` passes its validator 9/9, but the completeness critic read
the shipped code in `frontend/src` and `backend/app` and found defects the validator cannot see.
The validator only proves an id is *cited*; it never proves the assertion is *present and
observable*. Everything below is a real defect with evidence. Fix them.

Case data lives in `.scratch/uat-prep/cases/W1.json` … `W8.json`. The workbook, the companion doc
and the traceability table are all GENERATED from those files by
`requirement_spec/5_uat/_build/build_uat_test_cases.py`, so fix the JSON, not the xlsx.

**The case count stays 54.** Do not add or remove cases. Every fix below is a rewrite inside an
existing case, or a change to the generator's sheet-1 / companion-doc content.

---

## A. Would produce a FALSE FAIL on working software — highest priority

### A1 · UAT-37 asks the tester to read a chip the app never renders

UAT-37 Expected item 5 and Test Step 7 tell the approver to read "chip ของขั้นที่ 2 และขั้นที่ 3".
The app renders **exactly one status chip, for the current step only** —
`ApprovalActionBar.tsx:204-206` renders a single `statusChipLabel(status)`, built from
`state.current_position` in `approval/model.ts:48`. At step 1 the chip reads
`Pending · Step 1 (Direct manager)` and nothing else. UAT-37 is a read-only case pinned at
`PENDING_APPROVER1` whose own note forbids pressing Approve or Reject, so the step-2/3 chips
cannot exist while it runs. A tester will hunt, find nothing, and mark a working app **Fail**.

**Fix:** delete Expected item 5 and Test Step 7 from UAT-37, and renumber what follows. Do not
delete the assertion from the pack — it already lives correctly in **UAT-40 items 1 and 3**,
where the chain actually advances through steps 2 and 3 and the chips are observable. Move
U-20 out of UAT-37's `new_refs` and confirm it is in UAT-40's.

### A2 · UAT-12 line 5 tells the tester to do the one thing that wipes the value

Line 5 expects "ช่องไม่รับค่า ค่าเดิมในช่องไม่เปลี่ยน" when letters are typed.
`sanitizeMonthInput` strips non-digits per keystroke, so **appending** `abc` does leave the old
value — but a tester who **clears the cell first** leaves it empty, and `MonthCell.tsx` onBlur
maps `draft === ''` to `typed = 0` and commits **0**, while `pendingAmountNoticeTh(0,0)` returns
`null` so no toast fires. The tester watches the amount get wiped and marks Fail.

**Fix:** the step must say explicitly to **พิมพ์ต่อท้ายค่าเดิม ห้ามลบค่าเดิมออกก่อน**, and the
expected result must say that clearing the cell first commits 0 by design, so the tester knows
which behaviour they are looking at.

### A3 · UAT-12 line 6 describes the negative-value behaviour inaccurately

Entering `-5000`: the minus is stripped, so the cell commits **5,000** — a new value, not the old
one. Expected item 6 currently reads "ใส่ค่าติดลบไม่ได้", which is true but will make a tester
hesitate when 5,000 appears.

**Fix:** state the observable outcome plainly — เครื่องหมายลบถูกตัดทิ้ง ช่องจึงบันทึกเป็น `5,000`
ไม่ใช่ค่าติดลบ และไม่ใช่ค่าเดิม.

### A4 · UAT-15 omits the step that makes the case possible

UAT-15 step 2 tells an admin to select `Data & Analytic`. Nipaporn and Waraporn are **dual-role**
admins, so `BudgetGrid.tsx:122-123` gives them a `โหมด Admin` toggle that **defaults OFF**. With
it off, `GET /scope/departments` runs with `admin_view_enabled=false` and returns only their own
See scope (`routers/reference.py:116-117`). In W2 nothing has been submitted, so the pending
overlay is empty and Data & Analytic is not in their picker at all. The case only asks the tester
to *record* whether the toggle was on.

**Fix:** add an explicit step to turn `โหมด Admin` on before selecting the department, matching
how UAT-42 step 3 already words it.

---

## B. Lost coverage the id bookkeeping hid

### B1 · TC-035's cumulative rounding-drift check disappeared

SIT TC-035's Test Data is literally `33,333.33 x3` — three entries — and its Expected Result is
"ยอดรวมและค่าที่บันทึกไม่คลาดเคลื่อนจากการปัดเศษ": a **cumulative drift** check across several
values. UAT-12 line 4 enters `33333.33` **once** and asserts one cell. The multi-entry sum
assertion is gone. This is a money rule, and money rules are on this project's never-cut list.

**Fix:** UAT-12 line 4 must enter `33333.33` into **three different month cells**, and the
expected result must assert both the per-cell value (`3,333,300` each) **and** that the
`รวมทั้งปี` total equals the exact sum of the three adjusted cells with no drift.

### B2 · TC-013 was retested with a weaker input than SIT asked for

SIT TC-013's input was `999999999999` (12 digits) — the value that actually produced the infinity
symbol, and the one SIT's remark asked to retest. UAT-12 line 3 substitutes `999999999`
(9 digits). Behaviour is identical because `roundPendingAmount` clamps both, but the retest SIT
requested was of the 12-digit input.

**Fix:** use `999999999999` in UAT-12 line 3, and note that this is the exact value that
previously rendered as infinity.

---

## C. Contradictions inside the pack

### C1 · UAT-43 depends on a submission UAT-36 forbids

UAT-43's precondition says Pornthip submitted **both** departments "ตามเคส UAT-36". UAT-36's own
note says **ห้ามกด `Submit`** for Solution Delivery, so it stays `Draft — not submitted`. No other
case among the 54 submits Solution Delivery. UAT-43 steps 2-6 therefore fall through to its
Blocked fallback, and the two-department approver behaviour — which the coverage research calls
"the single biggest behavioural delta from SIT" — goes unproven.

**Fix, and this is the resolution to apply:** keep Solution Delivery in `Draft`. Do NOT submit it.
The reason is real and was flagged at chart time: a mid-chain Solution Delivery locks Suchanya
out of her own live department for the duration of the round, on production. So:
- Rewrite UAT-43's precondition to match reality — only `Data & Analytic` is submitted.
- Narrow UAT-43 to what IS observable with one department submitted: the approver holding two
  departments sees both in the picker, the `Pending` count is correct and counts only the
  submitted one, and the un-submitted department shows no Approve button.
- Add an explicit line to the companion doc's out-of-scope section saying the second half —
  approving two departments independently through the full chain — is **ตั้งใจไม่ทำในรอบนี้**
  because submitting Solution Delivery would lock Suchanya out of her real department, and name
  it as the one behavioural gap the round accepts.

### C2 · UAT-31 uses a tool the companion doc declares out of scope

UAT-31 requires jakkaritw to drive `/sit/impersonate` as `arthids@chememan.com`, while companion
§6 lists `/sit/impersonate` in the out-of-scope table as a developer-only tool.

**Fix:** reconcile in the doc, not the case. The case is correct on the facts — arthids is one of
the six configured targets and the case is read-only. Change §6 so the out-of-scope line reads
that impersonation is **not a tester-facing feature under test**, while noting it IS the
mechanism jakkaritw uses to set up UAT-31, and that any row it writes is signed as the
impersonated person.

### C3 · Sheet 1 states a role the workbook itself refutes

Sheet 1 row 14 says "Role — Observer (ดูอย่างเดียว บนฝ่าย Solution Delivery) | Suchanya".
UAT-31's own note says the opposite, correctly: Suchanya **is** the filler of Solution Delivery
in `dbo.cc_filler_map` (`10IT012000 / Solution Delivery / suchanyay@chememan.com`), so she must
see the upload and delete buttons as normal.

**Fix:** correct sheet 1 to describe Suchanya as the real filler of Solution Delivery whose
department is being borrowed for the round, and say plainly what she is asked to do. Right now
she is named as one of five participants and is the actor in **zero** cases — either give her the
observer checks she can actually perform on her own department, or state that her role this round
is to confirm nothing of hers broke.

### C4 · The PIC column contradicts the fill instructions

Sheet 1 tells the Test Lead to fill `PIC`, but the same sheet and companion §5.1 both say to fill
only the yellow cells, and PIC is not yellow.

**Fix:** either make PIC yellow or reword both instructions so the exception is explicit. Pick one
and apply it consistently in the generator.

---

## D. The execution-order defect — highest severity for the round itself

Sheet 1 and companion §4 both instruct: "ทดสอบเรียงตามคอลัมน์ Wave จาก W1 ไป W8 อย่าข้ามระลอก".
**Nine cases contradict that**, each burying the correction in its own Preconditions where a
tester reads it too late:

| Case | Sits in | Must actually run |
|---|---|---|
| UAT-03 steps 4-6 | W1 | after UAT-32 (W5) |
| UAT-44 | W6, position 44 | **before** UAT-40 (position 40) |
| UAT-41 | W6, position 41 | after UAT-44, before UAT-40 |
| UAT-42 step 5 | W6, position 42 | after UAT-44 |
| UAT-47 | W7 | at the same time as UAT-40 (W6) |
| UAT-53 | W8 | before W5 |
| UAT-54 | W8 | before UAT-40 |

A tester who obeys sheet 1 reaches UAT-40, lands the department in `Approved` — which the pack
itself declares irreversible without a direct database edit — and **UAT-41, UAT-42 step 5 and
UAT-44 become permanently unrunnable**. On production, inside a round, that is unrecoverable.

**Fix:** add a **`ลำดับการรัน` (Run Order)** integer column to `2. Test Cases`, immediately after
`Wave`, carrying the true execution sequence 1…54. Derive it by walking the dependencies above:
everything that must precede `Approved` runs before UAT-40, and UAT-40 runs last for its
department. Then change sheet 1 and companion §4 to say **sort by `ลำดับการรัน`, not by Wave** —
Wave stays as the grouping label and the filter, Run Order is the sequence. Put a one-line warning
next to it: อย่ากด Approve ขั้นที่ 3 (UAT-40) จนกว่าทุกเคสที่ต้องทำก่อนจะเสร็จ เพราะสถานะ
`Approved` ย้อนกลับไม่ได้.

This shifts every column letter after `Wave`. Update the generator, the sheet-1 legend, the
companion doc's fill instructions, **and every column reference inside
`_build/validate_uat_pack.py`** so the validator still checks the right columns.

---

## E. Things that were dropped without being declared

The project rule is that "ตั้งใจไม่ทำ" (chose not to do) and "ยังไม่ทำ" (not done yet) must both
be declared explicitly. These are in neither the 54 cases nor the companion doc's out-of-scope
section, so a returning SIT tester cannot tell which is which:

- **TC-057 — the Training & Seminar subform itself** (course name and Method as separate fields,
  integer-only month input). MAP.md's D4 decision listed TC-057 among the cases to be
  **rewritten**; instead it vanished, and W3 now covers 4 of the 5 special-GL subforms. There is a
  real reason — a Data & Analytic filler can no longer reach that GL since the 2026-08-29
  restriction — but the reason exists only inside UAT-14's note.
  **Resolution to apply:** declare it out of scope with that exact reason, and add one sentence
  saying the subform's field behaviour is structurally covered by the four subforms that are
  tested (UAT-20, 21, 22, 23).
- **TC-003** wrong password — tests the Microsoft login layer, not this app, and needs an
  InPrivate window.
- **TC-009** number format / thousand separators — superseded by UAT-12, which asserts the
  formatted values directly.
- **TC-014** edit a saved draft before submit — covered incidentally by UAT-09 and UAT-13.
- **TC-017** notify approver after submit — same event as UAT-46.
- **TC-018** status agrees on both sides — covered by UAT-32 plus UAT-37.
- **TC-040 / TC-041 / TC-042** reminder emails — these are a CLI job, not a UI control; a
  developer runs `backend/jobs/send_reminders.py`. Note that the "one mail listing N departments"
  aggregation has never been proven for more than one department, and that with two departments in
  this round a single run would prove it — but no tester-driven case exists.
- **§B admin-Submit → straight `APPROVED`** (ADR-0012). UAT-45 covers the admin toggle and the
  admin-wide picker but explicitly forbids admin-Submit. Dropping it on production is defensible;
  it just has to be declared.

**Fix:** add every one of these to the companion doc's out-of-scope section, each with its reason,
in the same voice as the entries already there.

---

## F. Record the deviation the pack got RIGHT

The brief specified UAT-02 as "ตัวเลือกฝ่าย **ไม่เลือกให้อัตโนมัติ เริ่มต้นว่าง**". The pack
asserts the opposite — the first department is auto-selected — and **the pack is correct**:
`picker/model.ts:66-81` documents "the page must NEVER land unselected (2026-07-21 jakkaritw —
supersedes the earlier '>1 ฝ่าย → null' rule)" and returns `all[0].department`.

**Fix:** nothing to change in the case. Add one line to the companion doc's section on where the
cases came from, recording that UAT-02 deliberately departs from the original scope note because
the live rule changed on 2026-07-21, so nobody re-litigates it mid-round.

---

## G. Smaller items

- **UAT-25** hard-codes the domestic destination as `Thailand`. Countries come from the admin
  master `dbo.country_group` and that exact spelling could not be verified live (the database MCP
  server timed out). UAT-24 hedges its destination; UAT-25 should hedge the same way — tell the
  tester to pick whatever domestic entry the dropdown actually offers and write down what they
  picked.
- **UAT-12 line 4** says "ตัดจุดทศนิยมทิ้ง", which reads ambiguously. The app drops the decimal
  *point*, not the decimal digits — `33333.33` becomes `3333333`, then rounds to `3,333,300`.
  Word it so the tester expects that.

---

## Definition of done

- Every fix above applied.
- `python -X utf8 requirement_spec/5_uat/_build/build_uat_test_cases.py` regenerates cleanly and
  is still byte-identical across two consecutive runs.
- `python -X utf8 requirement_spec/5_uat/_build/validate_uat_pack.py` still reports 9 PASS 0 FAIL,
  with its column references updated for the new Run Order column.
- Case count is still exactly 54.
- Nothing committed, nothing uploaded to SharePoint, no mutating `az` command.
