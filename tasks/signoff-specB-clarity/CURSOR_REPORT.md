# CURSOR_REPORT — TASK-001 SpecB clarity polish

**Date:** 2026-06-26  
**Target:** `requirement_spec/1_software_dev/1.1_frontend/signoff_spec/version2/SpecB_GL_Subform_v3.docx`

## Summary

- **Paragraphs rewritten:** 40 (collapse-rewrite via `apply_paras.py`)
- **Method:** `extract_paras.py` → `edits_specB_clarity.json` → `check_paras.py` → `apply_paras.py`
- **Document stats:** 447 paragraphs total, 382 rewritable, 65 skip (unchanged)

## Version + changelog

| Para | Before | After |
|------|--------|-------|
| 28 | `v0.4 (ฉบับร่าง)` | `v0.4.1 (ฉบับร่าง)` |
| 36 | single-line colon chain | bullet changelog with new v0.4.1 entry + v0.4 + v0.3 lines preserved |

## check_paras output

```
=== 40 edits | preservation flags: 0 | overlap flags: 0 ===
PASS
```

## Before / after samples

### Para 94 — read-only trigger (colon chain → bullets)

**Before:**
> ฟอร์มย่อยจะเปิดในโหมด "อ่านอย่างเดียว" เมื่อฝ่ายนั้นแก้ไขไม่ได้สำหรับผู้ใช้ปัจจุบัน: เกิดใน 3 กรณี: (1) ส่งเข้าอนุมัติแล้ว (สถานะ PENDING_*): (2) อนุมัติแล้ว (APPROVED): (3) ผู้ใช้เป็นผู้อนุมัติ (เปิดเพื่อตรวจ)

**After:**
> ฟอร์มย่อยเปิดโหมด "อ่านอย่างเดียว" เมื่อฝ่ายนั้นแก้ไขไม่ได้สำหรับผู้ใช้ปัจจุบัน — 3 กรณี:
> • (1) ส่งเข้าอนุมัติแล้ว (สถานะ PENDING_*)
> • (2) อนุมัติแล้ว (APPROVED)
> • (3) ผู้ใช้เป็นผู้อนุมัติ (เปิดเพื่อตรวจ)

### Para 324 — per-diem formula (long colon chain → bullets)

**Before:**
> สูตรเบี้ยเลี้ยง: ในประเทศ(ไทย) = วัน × อัตรา ฿ (ไม่คูณ FX): ต่างประเทศ = วัน × อัตรา $ × อัตราแลกเปลี่ยน (Master FX ของปีงบประมาณนั้น เช่น ภาพตัวอย่างปี 2025 = 35.00): อัตรา...

**After:**
> สูตรเบี้ยเลี้ยง:
> • ในประเทศ(ไทย) = วัน × อัตรา ฿ (ไม่คูณ FX)
> • ต่างประเทศ = วัน × อัตรา $ × อัตราแลกเปลี่ยน (Master FX ของปีงบประมาณนั้น เช่น ภาพตัวอย่างปี 2025 = 35.00)
> • อัตราตาม [ตำแหน่ง × กลุ่มประเทศ] จากชีต เบี้ยเลี้ยง ...

### Para 389 — Trip Manager read-only (371 chars → structured bullets)

**Before:** single dense paragraph covering fieldset disabled, hidden buttons, header lock.

**After:** same facts split into 3 bullets (fieldset rule, button changes, header 🔒).

## Pre-commit checks

| Check | Result |
|-------|--------|
| `apply_paras.py --selftest` | SELFTEST OK (447 paragraphs, well-formed) |
| `check_paras.py` | **PASS** (0 DROP, 0 OVERLAP) |
| Post-apply `extract_paras.py` | OK (447 paragraphs) |
| Spot-check facts | All PASS: `11 ชนิด`, 8 GL, FX 2025/FY2026, `L2 3 คน`, markers ①–⑤, `recompute-on-read`, `Module 02`, `Trip Manager` |
| `v0.4.1` present | Yes (para 28 + changelog) |

## Untouched (confirmed)

- **65 skip paragraphs** (images / hyperlinks / mixed-bold / empty): 0 text changes
- **Para 82** `"+ เพิ่ม Transaction"`: verbatim unchanged

## Paragraph indices edited

28, 36, 39, 40, 90, 91, 94, 96, 97, 98, 99, 140, 152, 175, 194, 259, 260, 262, 263, 264, 265, 289, 298, 306, 310, 314, 324, 326, 328, 329, 365, 386, 389, 390, 403, 410, 412, 413, 421, 425
