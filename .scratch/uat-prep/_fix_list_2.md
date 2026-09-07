# FIX LIST 2 — final repair round (from the re-audit, 2026-09-07)

The pack at `requirement_spec/5_uat/` now passes its validator 10/10, the column shift is clean,
the out-of-scope accounting reconciles 61/61 SIT ids, and the build is deterministic. The
re-auditor's verdict is nevertheless **NOT READY**, for four reasons. Fix those four, fold in the
six smaller ones, and the round is runnable.

Case data is `.scratch/uat-prep/cases/W1.json` … `W8.json`. The workbook and the companion doc are
GENERATED from those by `requirement_spec/5_uat/_build/build_uat_test_cases.py`. Fix the JSON and
the generator, never the xlsx. **The case count stays 54.**

Cell references below are into the generated `2. Test Cases` sheet, given so you can confirm you
are editing the right case: column J = Preconditions, K = Test Steps, L = Test Data,
M = Expected Result.

---

## GATING — these four block the round

### 1 · HIGH — UAT-12's drift total is arithmetically impossible, guaranteeing a false Fail

UAT-12 is the only case carrying the money rules, and its line-4 cumulative-drift assertion is
anchored to the wrong baseline.

- `J14` tells the tester to record the row's `รวมทั้งปี` **before starting**.
- `K14` step 7 and `M14` item 5 then assert the total equals **that pre-case baseline + 9,999,900**.

But lines 1-3 run first **in the same row**, and line 3 leaves the main test cell at
`100,000,000`. `รวมทั้งปี` is a per-row year total (`frontend/src/grid/GridTable.tsx:1259`), so by
the time line 4 runs the real total is `baseline − X + 100,000,000`, where X is that cell's
original value. The tester's calculator says `baseline + 9,999,900`; the screen says roughly
**100 million THB more**. Item 5 orders them to mark Fail.

The pack already contradicts itself here: `L14` line 4 and companion §5.3 both correctly say the
total **เพิ่มขึ้น 9,999,900** (a delta); only `K14` step 7 and `M14` item 5 anchor to the stale
baseline.

**Fix:** make the baseline a **fresh reading taken immediately before line 4**. Reword `K14`
step 7 and `M14` item 5 so the tester records `รวมทั้งปี` right before entering the three
`33333.33` values, and asserts that it rose by exactly `9,999,900` from *that* reading. Keep the
"Fail if it drifts even slightly" instruction — that is the point of the case.

### 2 · MEDIUM-HIGH — UAT-46 sits where its precondition is false, and blocks the chain

Walking the printed Run Order for Data & Analytic: pos 34 UAT-32 → `Pending Step 1`; 43 UAT-38 →
`Rejected`; 44 UAT-39 → `Pending Step 1`; 45 UAT-44 → `Pending Step 2`; 46 UAT-41 → `Rejected`;
**47 = UAT-46**.

- `J48` requires `Draft — not submitted` and a Submit to press. At position 47 the department is
  `Rejected`. The precondition is false as printed.
- UAT-41's note is the only place saying a re-submit must happen at all, and that re-submit has no
  Run Order position of its own.
- `K48` step 2 actively tells the tester **ห้ามกดซ้ำ** if they already submitted — so an obedient
  tester leaves the department `Rejected`, and UAT-47 (pos 49) and UAT-40 (pos 50) both stall.

**Fix:** reword `J48` and `K48` step 2 so position 47 **is** the re-submit after UAT-41's reject —
a `Rejected → Submit` counts as the observed Submit event that generates the approver-1 mail — and
narrow the "ห้ามกดซ้ำ" clause so it only applies when the department is already `Pending`.

### 3 · MEDIUM — the `UAT-42 step 5 → after UAT-44` dependency was never encoded

`W6.json` gives UAT-42 only `runs_after: ["UAT-32"]`, so it lands at position 41 while UAT-44 is at
45. But `K44` step 5 needs the budget at **step 2**, and the only step-2 windows in the round are
between position 45 (UAT-44 moves it to step 2) and 46 (UAT-41 rejects out of it), or inside UAT-40
at position 50.

Note for whoever reads the validator: **Check 10 passing is not evidence the round is runnable.**
It only proves the sheet agrees with the edges written in the JSON. A dependency nobody wrote down
is invisible to it.

**Fix:** the case genuinely spans two states and cannot occupy two positions, so signpost it —
add to **UAT-44's note**: `หยุด — กลับไปทำ UAT-42 ข้อ 5 ตอนนี้ ก่อนเริ่ม UAT-41`, and to
**UAT-42 step 5**: `ทำทันทีหลัง UAT-44 ก่อนเริ่ม UAT-41`. Mirror the same pointer into the
companion doc's §4.1 within-W6 bullet, which currently says only "UAT-44 · UAT-41 ทำก่อน UAT-40".

### 4 · MEDIUM — UAT-44 expected item 4 has a half that is unobservable where it is printed

`K46` step 4 asks the tester to check the admin-override restriction at **both** step 2 and step 3.
At position 45 the budget only reaches step 2; it never reaches step 3 until inside UAT-40 at
position 50. UAT-44's note says nothing about deferring the step-3 half, so a tester finds no
step-3 state and either Fails it or improvises.

**Fix:** split step 4 and its expected item into **4a** (do it here, at step 2) and **4b**
(`ทำระหว่างเคส UAT-40 หลังข้อ 4 ก่อนข้อ 5`), and add the matching pointer to **UAT-40's note** so
the tester is told to come back for it at the moment the state exists.

---

## FOLD IN — not gating, but fix while the files are open

### 5 · UAT-52 has no editable trip left at position 54

`J54` needs at least one editable trip for its negative-days check. Every trip is created in W3
(positions 19-25) on Data & Analytic, which is `Approved` and locked from position 50. UAT-52's
only edge is `UAT-32`. Both escape hatches in its note are dead: Solution Delivery has 0 rows, and
only FY2027 has a `submission_deadline` row so every other year is `NOT_OPEN`. The negative-days
validation is silently lost.

**Fix:** add a `runs_after` edge that places UAT-52 **before UAT-40** (its other precondition, a
submitted department, holds from position 34), so an editable trip still exists.

### 6 · UAT-48's precondition describes a state that ended five positions earlier

`J50` says the department is `Pending · Step 1`, but UAT-38's reject happened at position 43 and
UAT-48 sits at 48. As a mailbox check it still works. **Fix:** reword to
`ตรวจอีเมลที่เกิดจากการกด Reject ในเคส UAT-38`.

### 7 · The Summary's `Not Run` row always reads 0

All 54 Status cells ship empty while sheet 1 and companion §5.2 both call `Not Run` the default, so
`3. Summary!C10` counts 0 and day one reads Total 54 / Pass 0 / … / Not Run 0. **Fix:** pre-fill
`Not Run` in the Status column, or compute C10 as `C6 − (Pass+Fail+Blocked+N/A)`. Pick one.

### 8 · Two incompatible Severity vocabularies

`2. Test Cases` Severity DV is `Critical,High,Medium,Low,-`; `4. Defects` Severity DV is
`Blocker,Major,Minor`. Companion §5.4 tells the tester to carry a case's severity onto the defect
row, where the second dropdown will reject it. **Fix:** make them one vocabulary, or state the
mapping explicitly in both places.

### 9 · `Wave` and `ลำดับการรัน` are painted purple, which the legend says means "edit freely"

Sheet 1 defines purple as AI-drafted text the tester may correct, while companion §5.1 says both
columns must never be edited because the program computes them. **Fix:** take those two columns out
of the purple range, or carve out the exception in the legend.

### 10 · jakkaritw runs UAT-31 but has no row in §3 "ใครทำอะไร"

He is the actor for UAT-31, one of the three real admins, and the named decision-maker in §2 and
§6, but a first-day reader has no row saying who he is. **Fix:** add him to the role table.

### 11 · Two leftovers from the pre-Run-Order draft

- **UAT-03** `J5` still describes the old split ("ข้อ 1-3 ทำในระลอก W1, ข้อ 4-6 กลับมาทำหลัง
  UAT-32"). Run Order now places the whole case at 35, after UAT-32, so it runs in one sitting.
- Companion §3 tells Suchanya to do her confirmation "หลังจบระลอก W4" — wave language in a document
  that has otherwise switched to Run Order.

---

## Definition of done

- All eleven items applied.
- The generator regenerates cleanly and is byte-identical across two consecutive runs.
- `validate_uat_pack.py` still reports 10 PASS 0 FAIL.
- Case count still exactly 54.
- Nothing committed, nothing uploaded, no mutating `az` command.
