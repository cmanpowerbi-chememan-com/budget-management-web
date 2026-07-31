# Reference — Approval Workflow

Operational reference for the budget approval workflow: the people, the special cases, the
exclusion rules, and the email triggers. This is a **lookup sheet of stable facts** (who,
what, when) — not a decision record. The *why* and the routing/unit/lock rules live in the
ADRs; this file links them rather than restating rationale.

- **Decisions** (approval unit, routing, admin override, approve-on-main-page, status
  machine): see the linked ADRs. Do not duplicate the rationale here.
- **Term definitions** (Cost Center, ฝ่าย, Submitter, See/Fill scope, orgcode): see
  `CONTEXT.md`.
- **Source of truth for the chain + special cases:**
  `requirement_spec/3_approval_workflow/approval_workflow_spec.md`; canonical actor table:
  `docs/12budget_actors_full.csv` (275 rows, 254 submitters).

---

## The chain (one approval unit)

```
L3/L4 Submit → approver1 (managerempcode ตรงๆ) → นิภาพร ทองกิ่ง (approver2) → วราพร ติรสิทธิ์ (approver3) → APPROVED
```

- approver1 = the **last submitter's** `managerempcode` (no walk-up / no level-derive).
- approver2 = นิภาพร ทองกิ่ง (Nipaporn Tongking, empcode `101032`, Budget Staff).
- approver3 = วราพร ติรสิทธิ์ (Waraporn Tirasit, empcode `100427`, Budget Manager — final).
- Status enum (neutral): `DRAFT / PENDING_APPROVER1 / PENDING_APPROVER2 / PENDING_APPROVER3 /
  APPROVED / REJECTED`.

**Rules — see ADRs (don't restate why):**
- Approval unit = `(ฝ่าย/department, fiscal_year)`, one record per dept per year covering all
  its CCs — **ADR-0008** (supersedes the earlier per-CC unit).
- See-scope vs Fill-scope (broad union see; ฝ่าย-gated fill) — **ADR-0007**.
- Routing, snapshot-at-submit, invalid-approver fallback to Nipaporn, 30-day step
  auto-escalate, reject → back to `PENDING_APPROVER1` — **ADR-0006**.
- Editing a number never changes status (in-flight PENDING locked; APPROVED admin-editable) —
  **ADR-0013**.
- Approval happens **inline on the main budget page** (`รออนุมัติ` badge + step-gated inline
  Approve/Reject) — there is **NO separate approver inbox** — **ADR-0016**.
- Admin Submit goes straight to `APPROVED` (orphan ฝ่าย in-cycle, anything post-deadline);
  admin powers gated behind an opt-in "โหมด Admin" toggle — **ADR-0012**, **ADR-0014**.

---

## Special-case people (self-review / dual role)

นิภาพร and วราพร are both approvers AND submitters of their own ฝ่าย. When they submit their
own budget, the chain skips their own approver step.

| Submitter | Chain |
|-----------|-------|
| **นิภาพร** (101032, L4 submitter orgcode 1142402 + Budget Staff approver2) | Submit → **วราพร** (approver1 = direct mgr) → END (skip self as approver2) |
| **วราพร** (100427, Budget Manager + final approver3) | Submit → **ปิยะดา ดวงพลจันทร์** (approver1) → END (she IS final approver) |
| anyone else | Submit → managerempcode → นิภาพร → วราพร |

> "Warapornt" in code/`.env` = Waraporn **T**irasit (`warapornt@chememan.com`) — not a typo.

Other intentional special cases:
- **ฐานิยา** fills อภิชัย's budget + อภิชัย approves = self-review — intentional.
- **แพรวทิพย์** fills for 2 CEOs + approves 2 subordinates = 3 roles.
- L2 → L1 submitters (3): ปรัชญา, ปิยะนุช → เลิศศักดิ์; ธนกฤษณ์ → ปรีด์.

---

## C-Level → ผู้กรอกแทน (proxy filler) mapping (confirmed 2026-05-27)

C-Level executives do not fill their own budget; a proxy fills on their behalf.

| C-Level | empcode | ผู้กรอกแทน | empcode |
|---------|---------|-----------|---------|
| อดิศักดิ์ เหล่าจันทร์ (CEO) | 100001 | แพรวทิพย์ ลิ้มจิระวัฒนา | 101300 |
| จันทรจุฑา จันทรทัต (CEO-Int) | 10T018 | แพรวทิพย์ ลิ้มจิระวัฒนา | 101300 |
| อภิชัย สมบูรณ์ปกรณ์ (CTO) | 101875 | ฐานิยา วิจิตรพนมศิลป์ | 101905 |
| เลิศศักดิ์ บุญส่งทรัพย์ (CSO) | 101632 | ปรัชญา เทพวรชัย + ปิยะนุช ปิยะนีรนาท | 100164 + 101801 |
| ปรีด์ สุวิมลธีระบุตร (CCO) | 101754 | ธนกฤษณ์ ศรีอนุชาต | 101429 |

- **C-Level who must log in (they are approver1 of a submitter):** อภิชัย, เลิศศักดิ์, ปรีด์ only.
- **C-Level who never log in (no direct submitter reports):** อดิศักดิ์, จันทรจุฑา.

---

## Subsidiary / L5 exclusion rules

Excluded entirely from the system (no fill, no approve, no email). `setup/sync_employees.py`
applies these at sync time, so they are already absent from `mas_employee_data` — no need to
re-filter in queries.

```python
empcode    LIKE '4%'      # Gritsman subsidiary
orgcode    LIKE '117%'    # Office of Affiliate (Vietnam)
hr_status  != 'Active'    # only Active synced
joblevelnameen IN ('Operator 1', 'Operator 2', 'Operator 3', 'Driver', 'Maid')  # L5
```

- **L5 (Operator / Driver / Maid)** do not use this system at any step.
- Budget actors = **L2–L4** only.

**Acceptable email domains** (can log in via Entra ID): `@chememan.com`, `@cman…`,
`@gritsman.com` (subsidiary — accepted). Personal email (gmail/hotmail/…) cannot log in.

---

## Workflow applies to which templates

| Template | Approval workflow | เหตุผล |
|----------|------------------|--------|
| **1.1 + 1.2 (รวมกัน)** | **Yes — full chain** | 1.2 is detail of 1.1 → submitted as one package |
| **Template 2** (งบประมาณกำหนดเอง) | **No** — Budget dept (วราพร) confirms it; admin import lane, no chain | Budget dept fills it themselves; นิภาพร should not approve her own dept's |

See `docs/reference/budget-templates.md` for template structures.

---

## Email notification triggers

(Revamped 2026-07-31 — `plan/email-notify-revamp.md`.) Mechanism, sender, and failure
handling = decision; see `.claude/project-context.md` ("Email notifications") — FastAPI →
Microsoft Graph `sendMail` direct, approval is source of truth (email failure never rolls back).
Repeat reminders are sent by `jobs/send_reminders.py` and tracked in `budget.reminder_log`
(7-day cadence per stream).

| Event | To | Cc | Repeat |
|-------|----|----|--------|
| User submits | approver1 (managerempcode of last submitter — trace up to VP/AVP) | — | ถ้าไม่กดอนุมัติ เตือนซ้ำทุก 7 วัน — เมลเตือน**รวม 1 ฉบับ/คน** ลิสต์ทุกฝ่ายที่รออยู่ (§7) |
| approver อนุมัติ (chain ยังไม่ครบ) | approver ถัดไป (นิภาพร → วราพร) | — | ถ้าไม่กดอนุมัติ เตือนซ้ำทุก 7 วัน — เมลเตือน**รวม 1 ฉบับ/คน** (§7) |
| วราพร approves (final) | User (submitter) ✅ | approver1 | ครั้งเดียว |
| reject (ทุก layer) | User (submitter) | approver1 | ครั้งเดียว |
| deadline reminder (ฝ่ายยังไม่ submit / REJECTED) | filler — **เมลรวม 1 ฉบับ/คน** ลิสต์ทุกฝ่ายที่ค้าง แต่ละแถวมี deep link ของฝ่ายนั้น (§7) | approver1 ที่ derive จาก manager ของ filler (fallback นิภาพร) | ทุก 7 วัน ตั้งแต่ `reminder_date` ถึง `closing_date` |

cc is skipped when it cannot be resolved or equals the To address; a cc failure never blocks
the main send. Turn reminders reuse the same turn-start anchor as the 30-day auto-escalate.
Reminder cadence is tracked per PERSON (sentinel `'*'` in `budget.reminder_log.department`,
§7.2) — a ฝ่าย that goes pending mid-week rides the person's next 7-day round; event mails
always fire instantly. Bulk sends are paced (`REMINDER_SEND_DELAY_SECONDS`), capped per phase
(`REMINDER_MAX_SENDS_PER_RUN`), retried on 429/503/504, and use one cached Graph token per round.
Special-case routing (นิภาพร/วราพร self-submit, C-Level) follows the same chain with the
self-skip above.
