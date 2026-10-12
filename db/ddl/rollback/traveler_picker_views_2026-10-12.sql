-- ============================================================================
-- ROLLBACK for the 2026-10-12 traveler-picker widening
-- (db/ddl/traveler_picker_views.sql, view 2 only: legs 4-6 'peer',
-- 'skip_report', 'peer_report' were added).
--
-- Running the statement below restores dbo.v_traveler_picker to its
-- PRE-change text (3 legs: same_department, manager / skip_manager,
-- direct_report). A view holds no data, so rolling back is instant and
-- lossless. dbo.v_employee_orgmap (view 1) was NOT changed by the widening
-- and needs no rollback.
--
-- Source: the statement is copied byte-for-byte from the committed
-- db/ddl/traveler_picker_views.sql (last changed in commit 47d00ab, i.e. the
-- text that was live before the widening).
--
-- Live-text verification: the pre-deploy measure script compares
-- OBJECT_DEFINITION('dbo.v_traveler_picker') with this statement (comments and
-- whitespace stripped, case-folded, 'create view' = 'create or alter view').
-- Result: MATCH (pre-deploy measure run 2026-10-12 22:19 BKK; live state was
-- PRE-CHANGE, i.e. live == this statement).
--
-- Fabric portal query editor runs one statement at a time; no GO separators.
-- ============================================================================

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
