-- ============================================================================
-- Trip-subform traveler picker — dept-scoped roster views (2026-07-19)
-- Target: [fabric_sql_database].[dbo]  (Fabric SQL DB, cman-dw-ws — ADR-0022/0023)
-- Base:   dbo.v_employee_primary (612-row Primary-row dedup roster; the SAME
--         source the old full-roster picker + write_model._lookup_traveler use,
--         so every pickable traveler stays save-able).
--
-- Why not cc_filler_map.department: cross-system name matching fails (matches
-- org_name_en for only 35/114 ฝ่าย). dept_key here is derived from ONE source
-- (v_employee_primary) for BOTH filler and traveler → join always resolves.
--
-- Org semantics verified live 2026-07-19:
--   area_code/sub_area_code = LOCATION (Bangkok…), NOT org units — ignore.
--   org_code 7 digits: 1-2 company group, 3 = สาย (division family),
--   4 = dept group, 5 = seat level (0/1 Division, 2 Department, 3 Section,
--   4 = member org where 540/612 employees sit). Org units repeat per manager
--   position (same name, many codes) → department = 4-digit prefix + name with
--   Division/Department/Section suffix stripped (121 groups, no cross-division
--   collision; ~114 matches the cc_filler_map ฝ่าย vocabulary in magnitude).
--
-- Validation vs all 99 distinct cc_filler_map.filler_email (2026-07-19):
--   99/99 resolve to an employee row; mgr1+mgr2 resolve 100%;
--   picker size min=3 median=7 p75=9 max=46 (3 legs below).
--   24 fillers sit in head-seat orgs whose team lives in differently-named
--   orgs (e.g. 'Fleet Management Department' vs 'Fleet Management Finished
--   Product') → leg 3 (direct reports) covers them; the 10 genuinely tiny
--   teams (≤2 people, no reports) still get ≥3 rows (self + mgr1 + mgr2).
--
-- Run order: view 1 then view 2 (v_traveler_picker depends on
-- v_employee_orgmap). No GO batch separators — Fabric portal query editor
-- runs one statement at a time. Reversible: DROP VIEW both.
-- ============================================================================

-- VIEW 1 — one row per employee: normalized dept key + resolved manager chain.
CREATE OR ALTER VIEW dbo.v_employee_orgmap AS
WITH norm AS (
    SELECT e.employee_code, LOWER(e.email) AS email, e.full_name_th, e.full_name_en,
           e.job_level_name_en, e.org_code, e.org_name_en,
           LEFT(e.org_code, 4) AS dept_prefix,
           CASE WHEN e.org_name_en LIKE '% Division'   THEN LEFT(e.org_name_en, LEN(e.org_name_en)-9)
                WHEN e.org_name_en LIKE '% Department' THEN LEFT(e.org_name_en, LEN(e.org_name_en)-11)
                WHEN e.org_name_en LIKE '% Section'    THEN LEFT(e.org_name_en, LEN(e.org_name_en)-8)
                ELSE e.org_name_en END AS dept_name,
           e.manager_employee_code
    FROM dbo.v_employee_primary e
)
SELECT n.employee_code, n.email, n.full_name_th, n.full_name_en, n.job_level_name_en,
       n.org_code, n.org_name_en,
       n.dept_prefix + '|' + n.dept_name AS dept_key,   -- prefix guards future same-name depts across divisions
       n.dept_name,
       LEFT(n.org_code, 3) AS division_key,
       n.manager_employee_code,
       m1.employee_code AS mgr1_empcode, m1.full_name_th AS mgr1_name, LOWER(m1.email) AS mgr1_email,
       m2.employee_code AS mgr2_empcode, m2.full_name_th AS mgr2_name, LOWER(m2.email) AS mgr2_email
FROM norm n
LEFT JOIN dbo.v_employee_primary m1 ON m1.employee_code = n.manager_employee_code
LEFT JOIN dbo.v_employee_primary m2 ON m2.employee_code = m1.manager_employee_code;

-- VIEW 2 — pairs grain (filler_email × pickable traveler); the app filters
-- WHERE filler_email = @login. One row per traveler: a person matching
-- several legs (e.g. a direct report who is also a same-dept colleague)
-- would surface once per leg since pick_reason differs — ROW_NUMBER keeps
-- exactly one row, priority manager > skip_manager > direct_report >
-- same_department.
CREATE OR ALTER VIEW dbo.v_traveler_picker AS
WITH u AS (
    -- leg 1: same department
    SELECT f.email AS filler_email, f.dept_name AS filler_department, f.division_key AS filler_division,
           t.employee_code AS traveler_empcode, t.full_name_th AS traveler_name,
           t.job_level_name_en AS traveler_position, t.email AS traveler_email,
           'same_department' AS pick_reason
    FROM dbo.v_employee_orgmap f
    JOIN dbo.v_employee_orgmap t ON t.dept_key = f.dept_key
    UNION ALL
    -- leg 2: direct manager + manager's manager (always, even outside the dept)
    SELECT f.email, f.dept_name, f.division_key,
           m.employee_code, m.full_name_th, m.job_level_name_en, m.email,
           CASE WHEN m.employee_code = f.mgr1_empcode THEN 'manager' ELSE 'skip_manager' END
    FROM dbo.v_employee_orgmap f
    JOIN dbo.v_employee_orgmap m ON m.employee_code IN (f.mgr1_empcode, f.mgr2_empcode)
    UNION ALL
    -- leg 3: direct reports (covers head-seat fillers whose team sits in
    -- differently-named orgs — 24/99 fillers live-verified)
    SELECT f.email, f.dept_name, f.division_key,
           r.employee_code, r.full_name_th, r.job_level_name_en, r.email,
           'direct_report'
    FROM dbo.v_employee_orgmap f
    JOIN dbo.v_employee_orgmap r ON r.manager_employee_code = f.employee_code
),
ranked AS (
    SELECT u.*,
           ROW_NUMBER() OVER (
               PARTITION BY filler_email, traveler_empcode
               ORDER BY CASE pick_reason WHEN 'manager'        THEN 1
                                         WHEN 'skip_manager'   THEN 2
                                         WHEN 'direct_report'  THEN 3
                                         ELSE 4 END
           ) AS rn
    FROM u
)
SELECT filler_email, filler_department, filler_division,
       traveler_empcode, traveler_name, traveler_position, traveler_email, pick_reason
FROM ranked
WHERE rn = 1;

-- ============================================================================
-- Verify (expected: 612 / 8 rows for suchanyay):
--   SELECT COUNT(*) FROM dbo.v_employee_orgmap;
--   SELECT traveler_name, traveler_position, traveler_email, pick_reason
--   FROM dbo.v_traveler_picker
--   WHERE filler_email = 'suchanyay@chememan.com'
--   ORDER BY pick_reason, traveler_name;
-- ============================================================================
