/* ============================================================================
   01-approval-flow-inspect.sql        READ-ONLY — safe to run on prd
   ----------------------------------------------------------------------------
   PURPOSE : answer "ข้อมูลของ 2 อีเมล (รออนุมัติ / อนุมัติครบทุกขั้น) เก็บไว้ที่ไหน
             และดูย้อนหลังตามลำดับได้อย่างไร"
   TARGET  : Fabric SQL Database (Azure-SQL engine, T-SQL) — env
             FABRIC_SQL_SERVER / FABRIC_SQL_DATABASE. Paste into the Fabric SQL
             query editor (or SSMS) and run one block at a time.
             NOTE: prd + stg share this SAME database.
   SAFETY  : SELECT only. No DDL, no DML. Nothing here changes data.

   YEAR MAPPING (the trap) --------------------------------------------------
     email  : "ปีงบประมาณ 2027"
     stored : budget.*.fiscal_year = 2027       <-- filter on THIS
     screen : YearPicker label = fiscal_year - 1 = 2026
     (frontend/src/grid/YearPicker.tsx, backend/app/notifications.py:_year_phrase)

   WHERE THE DATA LIVES ------------------------------------------------------
     budget.approval_status        1 row per (ฝ่าย × fiscal_year) = CURRENT state.
                                   Overwritten on every action + on re-submit
                                   (last-submitter-wins). No history here.
     budget.approval_log           APPEND-ONLY history, 1 row per action
                                   (SUBMIT/APPROVE/REJECT/RESUBMIT/ADMIN_*).
                                   log_id IDENTITY = the true sequence.
     budget.pending_budget         the money: 1 row per (cost_center, gl_account,
                                   fiscal_year), 12 monthly cols + total_year.
                                   NO status column — status lives on
                                   approval_status (ฝ่าย-level, ADR-0008).
     budget.pending_budget_detail  subform lines of special GL groups.
     budget.budget_trip            travel trip headers (per-diem source).
     budget.reminder_log           dedup ledger of REMINDER mails only.
     NOT in the DB: the approval/reject/approved e-mails themselves (Graph
     sendMail, no send-log table) and the attachments (SharePoint).
   ============================================================================ */


/* == Q1. สถานะปัจจุบันของฝ่าย+ปี ที่อีเมลอ้างถึง =============================
   Email 2 ("อนุมัติครบทุกขั้นแล้ว") => status = 'APPROVED' and all three
   approverN_actioned_at filled.
   Email 1 ("รอการอนุมัติจากท่าน" ส่งถึง Waraporn) => status was
   'PENDING_APPROVER3' at that moment.                                        */
SELECT  department, fiscal_year, status,
        submitter_empcode, submitter_email, submitted_at,
        approver1_empcode, approver1_actioned_at,   -- ผู้จัดการสายตรง (frozen at submit)
        approver2_actioned_at,                      -- Nipaporn (Budget Staff)
        approver3_actioned_at,                      -- Waraporn (Budget Manager, ขั้นสุดท้าย)
        reject_reason, rejected_by_empcode, _updated_at
FROM    budget.approval_status
WHERE   department  = N'Budgeting and Management'
  AND   fiscal_year = 2027;


/* == Q2. ประวัติทุก action ตามลำดับจริง (คำตอบหลักของ "ตามลำดับ") ===========
   log_id = IDENTITY = ลำดับที่เขียนลง DB จริง; ใช้ ORDER BY log_id ไม่ใช่
   action_at (สอง action ใน DATETIME2 เดียวกันเกิดขึ้นได้)                    */
SELECT  ROW_NUMBER() OVER (ORDER BY log_id)               AS seq,
        log_id, action_at, action,
        action_by_email, action_by_empcode,
        previous_status, new_status, comment
FROM    budget.approval_log
WHERE   department  = N'Budgeting and Management'
  AND   fiscal_year = 2027
ORDER BY log_id;


/* == Q3. ไทม์ไลน์ทั้งปี ทุกฝ่าย เรียงตามเวลา (ล่าสุดอยู่บน) =================
   ใช้ตรวจว่าอีเมลฉบับไหนตรงกับ action ไหน                                    */
SELECT  TOP 200
        action_at, department, action, previous_status, new_status,
        action_by_email, log_id
FROM    budget.approval_log
WHERE   fiscal_year = 2027
ORDER BY action_at DESC, log_id DESC;


/* == Q4. กระดานสถานะทั้งปี เรียงตามลำดับขั้นของ workflow ====================
   ลำดับขั้น: DRAFT -> PENDING_APPROVER1 -> 2 -> 3 -> APPROVED (REJECTED แยก) */
SELECT  CASE status
            WHEN N'DRAFT'              THEN 0
            WHEN N'PENDING_APPROVER1'  THEN 1
            WHEN N'PENDING_APPROVER2'  THEN 2
            WHEN N'PENDING_APPROVER3'  THEN 3
            WHEN N'APPROVED'           THEN 4
            WHEN N'REJECTED'           THEN 5
            ELSE 9 END                                    AS stage_no,
        status, department, submitted_at,
        approver1_actioned_at, approver2_actioned_at, approver3_actioned_at,
        _updated_at
FROM    budget.approval_status
WHERE   fiscal_year = 2027
ORDER BY stage_no, department;


/* == Q5. ตัวเงินของฝ่ายนั้น เรียงตาม cost center + GL ========================
   grain = (cost_center, gl_account, fiscal_year) — 1 แถวต่อ 1 ช่องในกริด      */
SELECT  cost_center, gl_account, gl_name, gl_group, template,
        m01, m02, m03, m04, m05, m06, m07, m08, m09, m10, m11, m12,
        total_year, remark, _user, _updated_at
FROM    budget.pending_budget
WHERE   department  = N'Budgeting and Management'
  AND   fiscal_year = 2027
ORDER BY cost_center, gl_account;


/* == Q6. control total + parity check (กฎการเงิน: ห้าม DISTINCT) ============
   total_year เป็นค่า STORED ที่ app คำนวณไว้ ไม่ใช่ computed column
   => diff ต้องเป็น 0.00 เสมอ ถ้าไม่ 0 คือข้อมูลเพี้ยน                        */
SELECT  COUNT(*)                                                  AS row_cnt,
        SUM(total_year)                                           AS sum_total_year,
        SUM(m01+m02+m03+m04+m05+m06+m07+m08+m09+m10+m11+m12)      AS sum_months,
        SUM(total_year)
          - SUM(m01+m02+m03+m04+m05+m06+m07+m08+m09+m10+m11+m12)  AS diff_must_be_zero
FROM    budget.pending_budget
WHERE   department  = N'Budgeting and Management'
  AND   fiscal_year = 2027;


/* == Q7. subform lines (special GL groups) เรียงตาม GL แล้วตามลำดับที่กรอก ==
   detail ไม่มีคอลัมน์ department -> join กลับ pending_budget เพื่อกรองฝ่าย
   is_auto_calc = 1 คือบรรทัด per-diem ที่ m01..m12 ถูกคำนวณตอนอ่าน
   (ADR-0015) ค่าที่เก็บใน DB ของบรรทัดนั้นไม่ใช่ค่าจริงที่แสดงบนจอ           */
SELECT  d.cost_center, d.gl_account, d.gl_group,
        d.detail_id, d.line_label, d.trip_id, d.is_auto_calc,
        d.total_year, d.meta_json, d._user, d._updated_at
FROM    budget.pending_budget_detail AS d
JOIN    budget.pending_budget        AS p
        ON  p.cost_center = d.cost_center
        AND p.gl_account  = d.gl_account
        AND p.fiscal_year = d.fiscal_year
WHERE   p.department   = N'Budgeting and Management'
  AND   d.fiscal_year  = 2027
ORDER BY d.cost_center, d.gl_account, d.detail_id;


/* == Q8. trip headers ของปีนั้น เรียงตามลำดับที่สร้าง ======================= */
SELECT  t.trip_id, t.cost_center, t.traveler_name, t.position, t.destination,
        t.country_group, t.days, t.travel_months, t.side, t.purpose, t.project,
        t._user, t._updated_at
FROM    budget.budget_trip AS t
WHERE   t.fiscal_year = 2027
  AND   EXISTS (SELECT 1 FROM budget.pending_budget AS p
                WHERE p.cost_center = t.cost_center
                  AND p.fiscal_year = t.fiscal_year
                  AND p.department  = N'Budgeting and Management')
ORDER BY t.trip_id;


/* == Q9. อีเมลเตือน (reminder) ที่ระบบเคยส่ง — ตารางกันส่งซ้ำ ================
   เก็บแค่ reminder ('turn' = เตือนผู้อนุมัติ, 'deadline' = เตือนคนกรอก)
   อีเมล submit/approve/reject ไม่มี log ในตารางนี้                            */
SELECT  reminder_type, department, fiscal_year, recipient, sent_at
FROM    budget.reminder_log
WHERE   fiscal_year = 2027
ORDER BY sent_at DESC;


/* == Q10. ไทม์ไลน์รวม action + reminder ในสายเดียว เรียงตามเวลา ============= */
SELECT  event_at, source, department, detail
FROM (
    SELECT  action_at                                             AS event_at,
            'approval_log'                                        AS source,
            department,
            CONCAT(action, N' : ', ISNULL(previous_status, N'-'), N' -> ',
                   ISNULL(new_status, N'-'), N' by ', action_by_email) AS detail
    FROM    budget.approval_log
    WHERE   fiscal_year = 2027
      AND   department = N'Budgeting and Management'
    UNION ALL
    SELECT  sent_at, 'reminder_log', department,
            CONCAT(N'REMINDER ', reminder_type, N' -> ', recipient)
    FROM    budget.reminder_log
    WHERE   fiscal_year = 2027
) AS x
ORDER BY event_at, source;


/* == Q11. คอลัมน์จริงในฐานข้อมูล (ตรวจก่อนเชื่อสเปกทุกครั้ง) ================ */
SELECT  TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE,
        CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
FROM    INFORMATION_SCHEMA.COLUMNS
WHERE   TABLE_SCHEMA = 'budget'
ORDER BY TABLE_NAME, ORDINAL_POSITION;

/* ============================================================================
   END — 11 read-only blocks. เปลี่ยนได้แค่ 2 ค่า:
         N'Budgeting and Management'  (ฝ่าย)  และ  2027  (fiscal_year = ปีบนอีเมล)
   ============================================================================ */
