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

---

# §7 Rework — grouped reminders + bulk-send hardening

**สั่งโดย jakkaritw 2026-07-31** (หลัง cross-review commit `e51d38f` + fix `75a0759`)
**Implementer:** Kimi Code · **Tracker:** `email-reminder-grouping`
**Hold ยังอยู่:** ยัง**ไม่** CREATE TABLE / ยัง**ไม่**เปิด cron / ยัง**ไม่** flip `NOTIFICATIONS_DRY_RUN`

> **Status: implemented 2026-07-31** — grouped 1-mail-per-person reminders (turn by approver,
> deadline by filler), `'*'` sentinel cadence keys, token cache + 429/503/504 retry + pacing
> (`reminder_send_delay_seconds` default 2.0) + per-phase cap (`reminder_max_sends_per_run`
> default 150) + per-phase summary line. All §7.4 tests mocked + green (suite 752 passed;
> 4 `tests_data_sync` failures pre-existing, other lane). Holds untouched. Real mails/round
> after grouping ≈ ~99 deadline + ≤48 turn, worst case 1/person.

## 7.1 Decision — กลับไปใช้เมลรวมต่อคน (option 1)

Per-ฝ่าย ทำให้คนเดียวได้เมลทีละหลายสิบฉบับ วัดจากข้อมูลจริง 2026-07-31:

| ชุดเมล | ก่อน (per-ฝ่าย) | worst case ต่อคน 1 รอบ | หลังรวม |
|---|---|---|---|
| deadline (filler) | 253 ฉบับ/รอบ | `khattariyas` 46 | ~99 ฉบับ (1/คน) |
| turn (approver) | ≤114 ฉบับ/รอบ | `bunpotk` 46 · Nipaporn/Waraporn ได้ถึง 114 | ≤48 ฉบับ (1/คน) |

- **Deadline reminder:** 1 เมล/filler — ตารางลิสต์ทุกฝ่ายที่ค้าง แต่ละแถวมี deep link ของฝ่ายนั้น
  (คงข้อดีของ §3.1 ไว้) · cc = manager ของ filler คนนั้น (rule เดิม, 1 address, ไม่ใช่ per-ฝ่าย)
  · filler ที่มีฝ่ายเดียวก็ได้ 1 ฉบับ template เดียวกัน (ไม่มี branch พิเศษ)
- **Turn reminder:** ทำแบบเดียวกัน — 1 เมล/approver ตารางลิสต์ทุกฝ่ายที่รอเขาอยู่ + จำนวนวันที่ค้าง
  ต่อแถว · ไม่มี cc (เหมือนเดิม)
- เมล **ตอนเกิดเหตุ** (submit → approver1, approve → คนถัดไป, final, reject) ยังเป็น per-ฝ่าย
  ทีละฉบับเหมือนเดิม — §7 แตะเฉพาะเมล**เตือนซ้ำ** ที่ job ยิงเป็นชุด

## 7.2 Cadence key เปลี่ยน (`budget.reminder_log`)

ตารางยังไม่ได้สร้างบน DB → แก้ DDL ได้อิสระใน commit เดียวกัน

- deadline: key = (`deadline`, `'*'`, fiscal_year, filler_email) — `department` ถือ sentinel `'*'`
  เพราะเมลไม่ผูกฝ่ายเดียวแล้ว
- turn: key = (`turn`, `'*'`, fiscal_year, approver_empcode)
- **ผลที่ต้องยอมรับและเขียน comment ไว้:** cadence เป็น per-คน-ต่อปี ไม่ใช่ per-ฝ่าย → ฝ่ายใหม่ที่
  เพิ่งค้างกลางสัปดาห์จะไม่ยิงเมลใหม่ทันที แต่ไปรวมในรอบ 7 วันถัดไป (เมลตอนเกิดเหตุยังยิงทันทีอยู่
  แล้ว จึงไม่มีใครพลาดงาน)
- update `db/ddl/budget_reminder_log.sql` comment ให้ตรง (ยังห้ามรัน)

## 7.3 Bulk-send hardening (jakkaritw: "เคยเจอส่งเมลเยอะๆ แล้วค้าง ส่งไม่ได้ในครั้งเดียว")

ปัญหาที่มีอยู่ตอนนี้ใน `app/notifications.py`:

- `send_mail` เรียก `_get_graph_token` **ทุกฉบับ** → 99–367 token request/รอบ
- ไม่มี retry เลย: 429/503 ครั้งเดียว = เมลฉบับนั้นหาย (ยัง retry รอบหน้าได้ แต่ทั้งรอบอาจโดนพร้อมกัน)
- ยิงติดกันไม่มีเว้นจังหวะ — Exchange Online throttle ประมาณ 30 ฉบับ/นาที/mailbox

ต้องทำ:

1. **token ครั้งเดียวต่อรอบ** — cache ใน module (พร้อม expiry) หรือ resolve ครั้งเดียวแล้วส่งต่อ
   ลงไป; ห้ามเปลี่ยน public signature ของ `send_mail` แบบ breaking (ใช้ keyword default)
2. **เว้นจังหวะ** `REMINDER_SEND_DELAY_SECONDS` (default `2.0`) ระหว่างฉบับ — inject `sleep`
   ได้เพื่อให้เทสไม่หลับจริง
3. **retry** เฉพาะ 429 / 503 / 504: เคารพ header `Retry-After` ถ้ามี ไม่มีก็ backoff 2s → 8s → 30s
   สูงสุด 3 ครั้ง; ล้มครบ = ไม่เขียน `reminder_log` (รอบหน้าเตือนซ้ำ ตาม posture เดิม)
4. **cap ต่อรอบ** `REMINDER_MAX_SENDS_PER_RUN` (default `150`, `0` = ไม่จำกัด) — ที่เกิน cap
   ไม่เขียน log และ log บรรทัดว่า `capped N` (ห้าม cap เงียบ)
5. **สรุปท้ายรอบ 1 บรรทัด**: attempted / sent / failed / retried / capped ต่อ phase
6. per-recipient isolation เดิมคงไว้ (คนหนึ่งพังไม่กระทบคนอื่น)

## 7.4 Tests (mocked, ห้ามยิงจริง)

1. filler 46 ฝ่าย → **1 ฉบับ**, body มี 46 แถว + 46 deep link, cc = manager 1 address
2. filler 1 ฝ่าย → 1 ฉบับ template เดียวกัน (ไม่ใช่ path พิเศษ)
3. approver N ฝ่าย → 1 ฉบับ, N แถว, แต่ละแถวมีจำนวนวันค้างของฝ่ายนั้น
4. cadence per-คน: รันซ้ำภายใน 7 วันไม่ส่ง / ครบ 7 วันส่งใหม่ / key ใช้ sentinel `'*'`
5. token: ส่ง N ฉบับ → `_get_graph_token` ถูกเรียก **1 ครั้ง**
6. 429 + `Retry-After: 5` → retry แล้วสำเร็จ, sleep ถูกเรียกด้วย 5
7. 429 ครบ 3 ครั้ง → ไม่เขียน log, นับเป็น failed, ฉบับถัดไปยังถูกส่ง
8. cap: due 200, cap 150 → ส่ง 150, เหลือ 50 ไม่มี log, log บอก capped 50
9. pacing: N ฉบับ → sleep ถูกเรียก N-1 ครั้งด้วย delay ที่ตั้ง
10. regression เดิมต้องไม่แตก: `deadline_date` (ไม่ใช่ `closing_date`), cc-skip 3 เคส,
    log-only-after-real-send, DRY_RUN suppression

## 7.5 Close-out

1. เทสเขียวทั้ง suite (ตอนนี้ baseline = 742 passed; 4 fail ใน `tests_data_sync` เป็นของ lane อื่น)
2. gate รวม 06+07+08 — 07 ดูเรื่อง recipient/cc ถูกคนและ log ไม่รั่ว PII
3. commit เดียวรวม: job + notifications + DDL comment + `db/schema.sql` + plan §7 + docs/reference
4. **ห้ามข้าม hold:** ไม่ CREATE TABLE, ไม่เปิด cron, ไม่ flip `NOTIFICATIONS_DRY_RUN`
   — 3 อย่างนี้รออนุมัติ jakkaritw แยกทีละข้อ
5. รายงาน: จำนวนเมลจริงต่อรอบหลังรวม (คาด ~99 + ≤48) + worst case ต่อคน = 1
