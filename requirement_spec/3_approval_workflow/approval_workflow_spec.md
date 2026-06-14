# Approval Workflow Specification

**Status:** Confirmed ✅  
**Last updated:** 2026-05-27  
**Confirmed by:** Jakkarit (Product Owner)

---

## 1. Overview

Budget submissions go through a **3-level approval chain** before being finalized.

```
Submitter (L3/L4)
  → Level 1: Direct Manager (managerempcode from HR)
  → Level 2: Budget Staff (Nipaporn Tongking — fixed)
  → Level 3: Budget Manager (Waraporn Tirasit — fixed)
```

---

## 2. Submitters

- **Who:** L3 (Department Head / Asst Dept Head) + L4 (Supervisor / Senior Supervisor) only
- **Excluded:** L1 (C-Level), L2 (VP/AVP), L5 (Operator/Driver/Maid)
- **Excluded orgs:**
  - `empcode LIKE '4%'` — Gritsman subsidiary
  - `orgcode LIKE '117%'` — Office of Affiliate (Vietnam)
  - L5 job levels: Operator 1/2/3, Driver, Maid

**L3 note:** L3 role = Confirm only (ไม่ submit) — no role conflict.  
**Why not L3 submit:** ถ้า L3 submit → role conflict 149/240 คน (ต้อง submit เอง + confirm L4 ด้วย)

---

## 3. Approval Chain

### 3.1 Standard Chain

```
Submit → approver1 (managerempcode) → approver2 (Nipaporn) → approver3 (Waraporn)
```

**approver1 rule:** Use `managerempcode` field from `mas_employee_data` directly — do NOT derive from level or walk up the hierarchy. HR data is authoritative.

**Valid combinations (all confirmed ✅):**

| Submitter Level | approver1 Level | Count |
|----------------|----------------|-------|
| L4 → L4 | Senior Supervisor is direct manager of Supervisor | 42 |
| L4 → L3 | Normal Dept Head manages Supervisors | 103 |
| L3 → L2 | VP/AVP manages Department Head | 43 |
| L3 → L1 | C-Level is direct manager (2 special cases) | 2 |
| L2 → L1 | VP/AVP submitter, C-Level is manager | 3 |

### 3.2 Fixed Approvers

| Role | Name (TH) | empcode | Email env var |
|------|-----------|---------|---------------|
| approver2 (Budget Staff) | นิภาพร ทองกิ่ง | 101032 | `NIPAPORNT_EMAIL` |
| approver3 (Budget Manager) | วราพร ติรสิทธิ์ | 100427 | `WARAPORNT_EMAIL` |

> **Note:** "Warapornt" in code/env = Waraporn **T**irasit (email: warapornt@chememan.com) — not a typo.

---

## 4. Special Cases

All confirmed ✅ by product owner.

### 4.1 Nipaporn submits her own budget

Nipaporn (101032) has 2 roles: L4 submitter (orgcode 1142402) + Budget Staff approver.

```
Nipaporn submits → Waraporn (approver1 = her direct manager) → END
                   (skip herself as approver2)
```

### 4.2 Waraporn submits her own budget

Waraporn (100427) is the final approver. When she submits:

```
Waraporn submits → Piyada Duangpolchan (approver1 = her direct manager) → END
                   (she IS the final approver — loop ends at approver1)
```

### 4.3 C-Level approves in the system themselves

C-Level people who are approver1 click approve themselves in the system — no PA approves on their behalf.

Applies to: อภิชัย สมบูรณ์ปกรณ์ (CTO), เลิศศักดิ์ บุญส่งทรัพย์ (CSO), ปรีด์ สุวิมลธีระบุตร (CCO)

### 4.4 Approver approves a package that contains their own CC

When a submission contains the approver's own CC (filled by an assigned subordinate), the approver is reviewing their own budget — this is **intentional by design** and requires no special handling in the system.

Applies to all `approver1_only` users (VP/AVP/C-Level) whose CC budget is filled by their direct report as part of the same division submission package.

> Example: ฐานิยา (101905) is assigned to fill CTO's CC. When ฐานิยา submits, the package goes to อภิชัย (101875) as approver1. อภิชัย approves a package that includes his own CC — intentional.

---

## 5. C-Level → Assigned Submitters

C-Level executives do not fill their own budget. Assigned staff fill on their behalf.

| C-Level | empcode | Assigned Submitter | empcode | Notes |
|---------|---------|-------------------|---------|-------|
| อดิศักดิ์ เหล่าจันทร์ (CEO) | 100001 | แพรวทิพย์ ลิ้มจิระวัฒนา | 101300 | — |
| จันทรจุฑา จันทรทัต (CEO-Int'l) | 10T018 | แพรวทิพย์ ลิ้มจิระวัฒนา | 101300 | Same person as above |
| อภิชัย สมบูรณ์ปกรณ์ (CTO) | 101875 | ฐานิยา วิจิตรพนมศิลป์ | 101905 | ฐานิยา fills + อภิชัย approves |
| เลิศศักดิ์ บุญส่งทรัพย์ (CSO) | 101632 | ปรัชญา เทพวรชัย + ปิยะนุช ปิยะนีรนาท | 100164 + 101801 | 2 submitters |
| ปรีด์ สุวิมลธีระบุตร (CCO) | 101754 | ธนกฤษณ์ ศรีอนุชาต | 101429 | — |

**แพรวทิพย์ has 3 roles:** fills for CEO + CEO-Int'l + approver1 for her 2 L4 subordinates.

**C-Level who must login (are approver1):** อภิชัย, เลิศศักดิ์, ปรีด์  
**C-Level who do NOT need to login:** อดิศักดิ์, จันทรจุฑา (no direct submitters)

---

## 6. Approval Unit (Granularity)

**1 Submission = 1 approval unit per Division + Fiscal Year**

- User fills Template 1.1 (all GLs) + Template 1.2 (all sub-templates) → Submit once as 1 package
- Approver sees "Budget of Division X, Year 2026" → approve/reject the whole package
- `approval_status` table tracks at submission level (division + fiscal_year), NOT per row or per GL

---

## 7. Approval Status Flow

```
DRAFT
  → PENDING_L1        (after submitter clicks Submit)
  → PENDING_L2        (after approver1 approves)
  → APPROVED          (after approver2/Waraporn approves)

Rejection paths:
  PENDING_L1 → REJECTED_BY_L1     (approver1 rejects)
  PENDING_L2 → REJECTED_BY_L2     (Nipaporn rejects)
  APPROVED   → REJECTED_BY_L3     (Waraporn rejects — rare)
```

> **DB field:** `approval_status` column in `approval_status` table.

---

## 8. Workflow Applies To Which Templates

| Template | Approval Workflow | Reason |
|----------|-----------------|--------|
| 1.1 Main + 1.2 (all sub-templates) | ✅ Full 3-level workflow | Submitted as 1 package |
| Template 2 (Budget dept) | ❌ Waraporn confirms directly | Budget dept fills it; Nipaporn should not approve her own data |

---

## 9. Email Notification Triggers

| Event | Notify |
|-------|--------|
| Submitter clicks Submit | approver1 (direct manager) |
| approver1 Approves | Nipaporn |
| approver1 Rejects | Submitter |
| Nipaporn Approves | Waraporn |
| Nipaporn Rejects | Submitter + approver1 |
| Waraporn Approves | Submitter (final confirmation ✅) |
| Waraporn Rejects | Submitter + approver1 + Nipaporn |
| Deadline reminder | All users who have not submitted |

---

## 10. User Count Summary

| Role | Count |
|------|-------|
| submitter only | 177 |
| submitter + approver1 | 73 |
| approver1 only (L1/L2 who are managers but don't submit) | 21 |
| submitter + approver2 (Nipaporn) | 1 |
| submitter + approver3 (Waraporn) | 1 |
| **Total users** | **273** |

Full table: `docs/budget_actors_full.csv` (273 rows, 16 columns)

---

## 11. L3→L1 Direct Chain (Special Cases — 2 people)

| Submitter | empcode | managerempcode | Manager |
|-----------|---------|----------------|---------|
| Yuan-Ming Huang | (L3) | ปรีด์ สุวิมลธีระบุตร (CCO/L1) | Direct to C-Level |
| ฐานิยา วิจิตรพนมศิลป์ | 101905 (L3) | อภิชัย สมบูรณ์ปกรณ์ (CTO/L1) | Direct to C-Level |

Both valid per HR `managerempcode` — no special handling needed in code beyond using managerempcode as-is.

---

## 12. Implementation Notes

- **approver1 lookup:** `SELECT managerempcode FROM mas_employee_data WHERE empcode = :submitter_empcode AND posstatus = 'Primary'`
- **Nipaporn special case:** `IF submission.submitter_empcode = '101032' THEN skip approver2, end at approver1`
- **Waraporn special case:** `IF submission.submitter_empcode = '100427' THEN end at approver1 (Piyada)`
- **No level-walk logic** — never traverse up the org tree; always use managerempcode directly
- **Resubmit after rejection:** submitter can edit and resubmit → status resets to PENDING_L1
