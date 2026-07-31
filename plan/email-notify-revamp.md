# Plan — Email notification workflow revamp (jakkaritw spec 2026-07-31)

**Implementer:** Kimi Code · **Status:** approved spec, implementing
**Tracker:** `email-notify-revamp`

## 1. Target behavior (locked by jakkaritw)

| Event | To | Cc | Repeat |
|---|---|---|---|
| submit | approver1 | — | ถ้าไม่กดอนุมัติ เตือนซ้ำทุก 7 วัน |
| approve (chain ไม่ครบ) | approver ถัดไป | — | ถ้าไม่กดอนุมัติ เตือนซ้ำทุก 7 วัน |
| approve final | sender (submitter) | approver1 | ครั้งเดียว |
| reject (ทุก layer) | sender | approver1 | ครั้งเดียว |
| deadline reminder | filler (แยกเมลต่อฝ่าย) | approver1 | ทุก 7 วัน ตั้งแต่ reminder_date ถึง deadline_date |

Locked via AskUserQuestion / defaults (2026-07-31):
- **cc approver1 สำหรับฝ่ายที่ยังไม่ submit** → derive ด้วย rule เดียวกับ submit: `manager_employee_code` ของ filler จาก `dbo.v_employee_budget_01`, fallback Nipaporn (101032) เหมือน `approval.resolve_chain`.
- **ขอบเขต deadline reminder** → เฉพาะฝ่ายที่บอลอยู่กับ filler: ไม่มี row (DRAFT) หรือ `REJECTED`. ฝ่ายใน chain (PENDING_*) ปล่อยให้ turn reminder ทำงาน — เตือนซ้อนกันไม่ได้.
- **X วันก่อนปิดงบ** → ใช้ `dbo.submission_deadline.reminder_date` / `deadline_date` ที่มีอยู่แล้ว (Nipaporn maintain ผ่าน master) — ไม่สร้าง config ใหม่. ⚠ **แก้ 2026-07-31 หลัง cross-review:** วันปิดจริงอยู่คอลัมน์ `deadline_date` (date) — คอลัมน์ชื่อ `closing_date` เป็น INT เลขวันที่ของเดือน (31) ไม่ใช่วันที่ (ยืนยันกับ live schema + sample row แล้ว); เวอร์ชันแรกของแผน/โค้ดดึงผิดคอลัมน์ จับได้ก่อน deploy.
- **ยังไม่เปิด cron / ยังไม่ flip `NOTIFICATIONS_DRY_RUN`** — implement + test + verify ก่อน, การเปิดยิงเมลจริงเป็น deploy decision แยก (handoff rule: DRY_RUN stays true until Phase-2 verification).

## 2. As-is gap (from exploration, 2026-07-31)

- `notify_approved` / `notify_reject` ส่งหา submitter คนเดียว ไม่มี cc (`backend/app/notifications.py:284-310, 257-281`).
- ไม่มี cc support ใน seam เลย (`send_mail`, `notifications.py:187-206`).
- ไม่มี reminder bookkeeping (ไม่มี column/table เก็บ last-sent) — `jobs/send_reminders.py` ส่งทุกครั้งที่รันหลัง reminder_date.
- `send_reminders.py` รวมทุกฝ่ายของ filler ไว้เมลเดียว (`notify_reminder`, `notifications.py:334-341`).
- cron ใน `.github/workflows/budget-automations.yml` ถูก comment (บรรทัด 13-14).
- 30-day auto-escalate มีอยู่แล้ว (`app/approval.py:796 is_step_stale`) — turn reminder 7 วันต้องใช้ anchor เดียวกัน (turn start = submitted_at / approver{1,2}_actioned_at).

## 3. Changes

### 3.1 `backend/app/notifications.py`
- `send_mail(..., cc: list[str] | None = None)` — เพิ่ม `ccRecipients` ใน Graph payload เมื่อมี cc.
- `notify_approved(..., approver1_empcode)` / `notify_reject(..., approver1_empcode)` — resolve cc = email ของ frozen `approver1_empcode` (reuse `_lookup_email_by_empcode`); **skip cc เมื่อ**: empcode ว่าง / lookup ไม่เจอ / cc == To (กันเมลซ้ำ). cc lookup fail ต้องไม่ทำให้ To หลักไม่ถูกส่ง.
- `notify_turn(..., reminder=False)` — เพิ่มโหมด reminder: subject ขึ้นต้น "[เตือน]" body เพิ่มบรรทัดว่าค้างมา N วัน — ใช้ทั้งตอนเข้าตา (เดิม) และตอนเตือนซ้ำ (ใหม่).
- `notify_deadline_reminder(filler_email, department, fiscal_year, closing_date, cc_emails)` — template ใหม่แบบฝ่ายเดียว พร้อม deep link ของฝ่ายนั้น (ADR-0016).

### 3.2 `backend/app/routers/approval.py`
- `_notify_after_transition` — ส่ง `state.approver1_empcode` เข้า `notify_approved` / `notify_reject` (final + reject เท่านั้น; turn ไม่ cc).
- Admin branches ยังไม่ส่งเมลเหมือนเดิม.

### 3.3 Reminder bookkeeping — ตารางใหม่ `budget.reminder_log`
```sql
CREATE TABLE budget.reminder_log (
  reminder_type  varchar(20)   NOT NULL,  -- 'turn' | 'deadline'
  department     nvarchar(200) NOT NULL,
  fiscal_year    int           NOT NULL,
  recipient      nvarchar(320) NOT NULL,  -- empcode (turn) / email (deadline)
  sent_at        datetime2     NOT NULL,
  CONSTRAINT pk_reminder_log PRIMARY KEY (reminder_type, department, fiscal_year, recipient)
);
```
- DDL ไปที่ `db/ddl/` (+ sync `db/schema.sql` ซึ่ง stale อยู่แล้วให้ตรง live ในส่วนที่แตะ) — **การ CREATE บน Fabric SQL (shared staging/prod DB) ต้องขออนุมัติ jakkaritw แยกต่างหากก่อนรัน**.
- Turn reminder due-check (ทำใน Python, ไม่เพิ่ม column บน approval_status): อ่าน `MAX(sent_at)` ของ (turn, dept, year, current_approver_empcode) — due เมื่อ `last_sent IS NULL AND turn_start <= now-7d` หรือ `last_sent <= now-7d AND last_sent >= turn_start`; ถ้า `last_sent < turn_start` (รอบ chain ก่อนหน้า) ให้ถือว่า NULL.
- Deadline reminder due-check: `MAX(sent_at)` ของ (deadline, dept, year, filler_email) — due เมื่อไม่เคยส่ง (และ today >= reminder_date) หรือ `last_sent <= today-7d`; หยุดเมื่อ today > deadline_date หรือฝ่ายหลุดจาก scope (submit แล้ว).
- บันทึก log **หลังส่งสำเร็จเท่านั้น** (dry-run ไม่เขียน log) — เมล fail ต้องถูกเตือนซ้ำในรอบถัดไป.

### 3.4 `backend/jobs/send_reminders.py` (ขยาย job เดิม ไม่สร้าง job ใหม่)
- Phase A (turn reminders): query `approval_status` ที่ status IN PENDING_APPROVER1/2/3 → คำนวณ turn_start ด้วย logic เดียวกับ `is_step_stale` → due ตาม 3.3 → ส่ง `notify_turn(reminder=True)` หา `current_approver_empcode` → log.
- Phase B (deadline reminders, rework ของเดิม): discovery ฝ่าย DRAFT/REJECTED จาก `cc_filler_map` เทียบ `approval_status` → แยกเมลต่อ (ฝ่าย, filler) → To filler, cc approver1 ที่ derive ด้วย manager-rule (lookup `manager_employee_code` ของ filler → email; fallback Nipaporn) → due ตาม 3.3 → log.
- Per-recipient failure isolation เหมือนเดิม (ฝ่ายหนึ่งพังไม่กระทบฝ่ายอื่น); gate เดิม (`--execute` + DRY_RUN=false) คงไว้ — **ไม่แตะ `common.py`**.
- ลบพฤติกรรมเดิม: grouped email ต่อ filler (`notify_reminder`) — แทนด้วย per-ฝ่าย.

### 3.5 `.github/workflows/budget-automations.yml`
- **ยังไม่ uncomment cron** ใน commit นี้ — เตรียมบรรทัดไว้พร้อม comment บอกขั้นตอน go-live (uncomment cron + ตั้ง `NOTIFICATIONS_DRY_RUN=false` บน Container App หลัง staging verify).

## 4. Tests (TDD, mocked — run `cd backend && pytest tests/<file> -v`)

`tests/test_notifications.py`:
1. `send_mail` ใส่ `ccRecipients` ใน payload เมื่อมี cc / ไม่ใส่ key เมื่อ cc ว่าง.
2. `notify_approved` cc เป็น email ของ approver1_empcode; skip cc เมื่อ == To; ส่ง To ปกติแม้ cc lookup fail.
3. `notify_reject` เช่นเดียวกัน (ทุก layer ใช้ฟังก์ชันเดียว).
4. `notify_turn(reminder=True)` subject/body เป็นโหมดเตือน.
5. `notify_deadline_reminder` ฝ่ายเดียว: To filler, cc ตามที่ส่งเข้ามา, deep link ถูกฝ่าย/ปี label.

`tests/test_approval_router.py`:
6. final approve → `notify_approved` ได้ `approver1_empcode`; reject → `notify_reject` ได้ empcode เดียวกัน (mock assert call args).

`tests/test_jobs_send_reminders.py` (เขียนใหม่เกือบทั้งไฟล์ — พฤติกรรมเดิมเปลี่ยน):
7. turn reminder: ครบ 7 วันส่ง / ยังไม่ครบไม่ส่ง / ส่งแล้ว <7 วันไม่ส่งซ้ำ / ส่งแล้ว >=7 วันส่งซ้ำ / last_sent < turn_start (รอบก่อน) นับเป็นไม่เคยส่ง / ไม่มี current approver ข้าม.
8. deadline: แยกเมลต่อฝ่าย (filler คนเดียว 2 ฝ่าย = 2 เมล) / cc = manager ของ filler (fallback Nipaporn) / เฉพาะ DRAFT+REJECTED (PENDING_*/APPROVED ไม่โดน) / ก่อน reminder_date ไม่ส่ง / หลัง deadline_date ไม่ส่ง / cadence 7 วัน / ฝ่ายละ failure isolation + **เทสเทียบคอลัมน์จริง: query ต้องดึง `deadline_date` ห้ามดึง `closing_date`** (regression ของบั๊กที่ cross-review จับได้ 2026-07-31).
9. dry-run: ไม่ส่ง ไม่เขียน reminder_log; execute: เขียน log เฉพาะที่ส่งสำเร็จ.

## 5. Invariants / never-cut

- เมลพังต้องไม่ทำ business action ล้ม (`notification_warning` pattern เดิม) — ทุก call site catch เหมือนเดิม.
- ADR-0016: ทุกเมลมี deep link ปี label (fiscal_year-1) เหมือนเดิม.
- ไม่เปลี่ยน chain logic / state machine / auto-escalate 30 วัน — turn reminder ใช้ anchor เดียวกับ `is_step_stale` เท่านั้น.
- ไม่ flip `NOTIFICATIONS_DRY_RUN`, ไม่เปิด cron, ไม่ CREATE TABLE บน shared DB โดยไม่ได้อนุมัติ — ทั้ง 3 อย่างเป็น deploy gate แยก.
- `docs/reference/approval-workflow.md` trigger table (บรรทัด 114-128) ต้องอัปเดตให้ตรงพฤติกรรมใหม่ใน commit เดียวกัน.

## 6. Close-out checklist

1. Tests เขียวทั้งหมด (mocked suite) + เก่าไม่แตก.
2. Gate agent รวม (06+07+08) — 07 หนักขึ้นเพราะแตะเมลจริง/recipient resolution.
3. อัปเดต `docs/reference/approval-workflow.md` + `.claude/plan.md` ใน commit เดียวกัน.
4. **ถามอนุมัติก่อน**: CREATE TABLE `budget.reminder_log` บน shared DB.
5. Deploy: staging ก่อน (ต้อง build image ใหม่) — verify job ด้วย manual `workflow_dispatch` (dry-run) อ่าน log ว่า due-check ถูก → ค่อยถามอนุมัติ prd + go-live (cron + DRY_RUN=false).
