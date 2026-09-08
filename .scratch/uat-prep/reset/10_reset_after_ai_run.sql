/* ============================================================================
   10_reset_after_ai_run.sql   —   THE UNDO.
   Run AFTER the AI UAT round, BEFORE the human round.
   ----------------------------------------------------------------------------
   Target DB : the PRODUCTION Fabric SQL Database behind cman-budget-web-prd.
               staging and production share THIS ONE database.

   NOTHING IN THIS FILE MUTATES ANYTHING AS SHIPPED.
   Every DELETE and INSERT is commented out.  Each one sits directly beneath
   the SELECT that shows precisely which rows it would touch, and a blank line
   where you write that SELECT's row count.  Uncomment a statement only after
   reading its SELECT's output and writing the number down.

   ---------------------------------------------------------------------------
   THREE RULES THAT ARE NOT NEGOTIABLE
   ---------------------------------------------------------------------------
   RULE 1 — NEVER DELETE ON "SHOULD BE EMPTY".
       On 2026-08-18 a cleanup on this system assumed an empty baseline and
       deleted a trip a real user had created.  No predicate here is allowed
       to mean "everything in scope".  A row is deleted only when it is BOTH
       absent from the pre-round manifest AND present on the AI's own write
       journal.  A row on neither list is somebody else's work: it is
       REPORTED for a human to decide, never deleted by this script.

   RULE 2 — EVERY TIMESTAMP IN THESE TABLES IS UTC.
       write_model.py:300 and approval.py:276 both write
       datetime.now(timezone.utc) into DATETIME2 columns, which carry no
       offset.  Bangkok is UTC+7.  Paste the UTC value that section 0 of the
       baseline script printed.  A Bangkok timestamp selects the wrong seven-
       hour band and will look entirely plausible while being wrong.

   RULE 3 — THIS SCRIPT CANNOT UNDO EMAILS, SHAREPOINT FILES, OR THE FX MASTER.
       See the tail of this file.  A clean run here does NOT mean the round
       left no trace.

   ---------------------------------------------------------------------------
   WHAT YOU NEED IN FRONT OF YOU BEFORE STARTING
   ---------------------------------------------------------------------------
   a) out\07b_baseline_pk_inserts.sql   — pasted into #baseline_pk in PHASE 0
   b) the AI round's write journal      — pasted into #journal in PHASE 0
   c) out\08a..08d_restore_*.sql        — the generated restore blocks
   d) out\06_counts_totals_fingerprints_BEFORE.csv
      out\06b_department_totals_BEFORE.csv   — to diff against in PHASE 4
   e) the run-start UTC timestamp and MAX(log_id) from baseline sections 0 and 5

   If (b) does not exist — if the AI did not journal every row it wrote —
   STOP.  Without it this script can only guess, and guessing is exactly what
   caused the 2026-08-18 incident.  Reconstruct the journal from the AI's own
   transcript before going any further.  The AI must record, for every write:
   the table, the primary key, the UAT case id, and whether it created or
   modified the row.

   ---------------------------------------------------------------------------
   ABOUT WRAPPING THIS IN A TRANSACTION
   ---------------------------------------------------------------------------
   You may wrap PHASE 2 and PHASE 3 in an explicit transaction:
       BEGIN TRANSACTION;   ... mutations ...   -- verify, then
       COMMIT TRANSACTION;  -- or ROLLBACK TRANSACTION;
   Do so only if you can finish inside a minute.  An open transaction holds
   row locks on live production tables while cman-budget-web-prd is serving
   real users.  The commented-out mutations are the primary safety mechanism;
   the transaction is a second belt, not a licence to leave the script open
   while you go away and think about it.

   ---------------------------------------------------------------------------
   SESSION NOTE
   ---------------------------------------------------------------------------
   #params, #cc, #baseline_pk and #journal are session-scoped temp tables.
   Run PHASE 0 first and DO NOT RECONNECT until you are finished.  If the
   connection drops, start again from PHASE 0.
   ============================================================================ */


/* ===========================================================================
   PHASE 0 — parameters, scope, and the two lists this whole script rests on
   =========================================================================== */

/* ---- 0.1 Parameters.  FILL THESE IN.  One place, so nothing can drift. -- */
DROP TABLE IF EXISTS #params;
CREATE TABLE #params (
    fy                 INT           NOT NULL,
    dept_a             NVARCHAR(150) NOT NULL,
    dept_b             NVARCHAR(150) NOT NULL,
    run_start_utc      DATETIME2     NOT NULL,
    run_end_utc        DATETIME2     NOT NULL,
    max_log_id_before  BIGINT        NOT NULL
);
INSERT INTO #params (fy, dept_a, dept_b, run_start_utc, run_end_utc, max_log_id_before) VALUES (
    2027,
    N'Data & Analytic',
    N'Solution Delivery',
    '2026-01-01T00:00:00.0000000',   -- <== PASTE the UTC run start from baseline section 0
    '2099-01-01T00:00:00.0000000',   -- <== SYSUTCDATETIME() at the moment the AI stopped
    0                                 -- <== PASTE MAX(log_id) from baseline section 5
);

/* ---- 0.2 Scope: the cost centers of the two departments ---------------- */
DROP TABLE IF EXISTS #cc;
CREATE TABLE #cc (cost_center NVARCHAR(20) NOT NULL PRIMARY KEY);
INSERT INTO #cc (cost_center)
SELECT DISTINCT m.cost_center
FROM dbo.cc_filler_map m CROSS JOIN #params p
WHERE m.department IN (p.dept_a, p.dept_b);

-- ASSERTION.  A typo in a department name makes every predicate below match
-- nothing, and the script then reports a reassuring "0 rows" everywhere while
-- doing nothing at all.  All three counts must be > 0.  STOP if any is 0.
SELECT N'scope resolved' AS assertion,
       (SELECT COUNT(*) FROM #cc) AS cost_centers,
       (SELECT COUNT(*) FROM dbo.cc_filler_map m CROSS JOIN #params p WHERE m.department = p.dept_a) AS rows_dept_a,
       (SELECT COUNT(*) FROM dbo.cc_filler_map m CROSS JOIN #params p WHERE m.department = p.dept_b) AS rows_dept_b,
       (SELECT CONVERT(varchar(33), run_start_utc, 126) FROM #params) AS run_start_utc,
       (SELECT CONVERT(varchar(33), run_end_utc, 126)   FROM #params) AS run_end_utc;
GO


/* ---- 0.3 THE PRE-ROUND MANIFEST -- paste out\07b_baseline_pk_inserts.sql
   Anything ON this list existed before the round and must be RESTORED.
   Anything in scope but NOT on this list was created during the round.
   pk format, exactly as the baseline emitted it:
       pending_budget         'costcenter|glaccount|fiscalyear'
       pending_budget_detail  the detail_id, as text
       budget_trip            the trip_id, as text
       approval_status        'department|fiscalyear'
   Omitting a table's rows tells this script that table was empty before the
   round.  For Solution Delivery's approval_status that is the true, verified
   answer.  For anything else, check it against out\07 before accepting it —
   RULE 1.
   ---------------------------------------------------------------------- */
DROP TABLE IF EXISTS #baseline_pk;
CREATE TABLE #baseline_pk (tbl NVARCHAR(40) NOT NULL, pk NVARCHAR(200) NOT NULL,
                           PRIMARY KEY (tbl, pk));

-- <== PASTE out\07b_baseline_pk_inserts.sql BETWEEN THE NEXT TWO LINES.
--     (Remove the trailing comma on the last tuple and end with a semicolon.)
-- INSERT INTO #baseline_pk (tbl, pk) VALUES
--   (N'pending_budget',        N'10IT011300|6210700020|2027'),
--   (N'pending_budget_detail', N'12345'),
--   (N'budget_trip',           N'678'),
--   (N'approval_status',       N'Data & Analytic|2027');

SELECT tbl, COUNT(*) AS baseline_rows FROM #baseline_pk GROUP BY tbl ORDER BY tbl;
-- Cross-check these counts against out\07_baseline_pk_manifest.csv before
-- continuing.  A short paste here silently converts pre-existing rows into
-- "created by the round", which is how real data gets deleted.
GO


/* ---- 0.4 THE AI'S WRITE JOURNAL -- paste from the round's own log
   One row per row the AI created or modified, in the same pk format.
   This is the ONLY thing that separates a row the AI wrote from a row a real
   colleague wrote in the same window under the same name: impersonation
   rewrites the identity completely, and budget.approval_log has no
   real-caller column, so the database itself cannot tell them apart.

   THE JOURNAL MUST INCLUDE ROWS THE AI NEVER TYPED.  One user action writes
   more rows than it looks like:
     · Saving a special-GL subform line writes the detail row AND creates or
       updates the pending_budget PARENT CELL for that (cost_center, gl_account,
       fiscal_year) — write_model `_recompute_parent_cell` inserts the parent
       when none exists.  A journal listing only the detail row leaves that
       parent behind after the reset.
     · Saving a trip writes budget_trip AND an is_auto_calc=1 per-diem detail
       line AND that line's parent cell (`_upsert_trip_detail_line`).
     · Flipping a trip's COST/SGA side moves its detail lines to the other
       side's GL accounts and creates parent cells there
       (`_rehome_trip_detail_lines`, `_delete_trip_detail_line`).
     · Deleting the last detail line of a cell also deletes the now-empty
       parent row (`_delete_parent_if_orphaned`) — so a BASELINE parent can
       disappear through an action that looks like a detail-only delete.  The
       restore in PHASE 3 puts it back; that is why the manifest matters as
       much as the journal.
   The safest way to build the journal is to diff the tables against the
   baseline capture immediately after the round and confirm every difference
   against the AI's transcript — not to trust a hand-kept list.
   ---------------------------------------------------------------------- */
DROP TABLE IF EXISTS #journal;
CREATE TABLE #journal (tbl NVARCHAR(40) NOT NULL, pk NVARCHAR(200) NOT NULL,
                       uat_case NVARCHAR(20) NULL, note NVARCHAR(400) NULL,
                       PRIMARY KEY (tbl, pk));

-- <== PASTE THE AI WRITE JOURNAL HERE.  Shape (these examples are illustrative
--     — delete them):
-- INSERT INTO #journal (tbl, pk, uat_case, note) VALUES
--   (N'pending_budget',        N'10IT011300|6210700020|2027', N'UAT-09', N'created'),
--   (N'pending_budget_detail', N'99001',                      N'UAT-21', N'created'),
--   (N'budget_trip',           N'4021',                       N'UAT-24', N'created'),
--   (N'approval_status',       N'Solution Delivery|2027',     N'UAT-36', N'created');

SELECT tbl, COUNT(*) AS journalled_rows FROM #journal GROUP BY tbl ORDER BY tbl;
GO


/* ===========================================================================
   PHASE 1 — PREVIEW ONLY.  Read every one of these before PHASE 2.
   =========================================================================== */

/* ---- 1.1 THE ADJUDICATION LIST — read this one first --------------------
   In-scope rows that are NOT in the baseline manifest and NOT in the journal.
   Every row here was created either by SOMEBODY ELSE, or by the AI without
   being journalled.  THIS SCRIPT NEVER DELETES THEM.  Decide each one by
   hand: look at who wrote it and when, and check the AI transcript.
   EXPECTED: zero rows.  Anything here means the journal is incomplete, or a
   real colleague was working in these departments during the round.
   ---------------------------------------------------------------------- */
SELECT N'pending_budget' AS [table],
       pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year) AS pk,
       pb.department, pb.total_year AS amount, pb._user AS who,
       CONVERT(varchar(33), pb._updated_at, 126) AS updated_at_utc,
       CASE WHEN pb._updated_at BETWEEN p.run_start_utc AND p.run_end_utc
            THEN N'written during the round' ELSE N'written outside the round window' END AS window_check
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget'
                    AND b.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year))
  AND NOT EXISTS (SELECT 1 FROM #journal j WHERE j.tbl = N'pending_budget'
                    AND j.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year))

UNION ALL
SELECT N'pending_budget_detail', CONVERT(nvarchar(40), d.detail_id), NULL, d.total_year, d._user,
       CONVERT(varchar(33), d._updated_at, 126),
       CASE WHEN d._updated_at BETWEEN p.run_start_utc AND p.run_end_utc
            THEN N'written during the round' ELSE N'written outside the round window' END
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget_detail' AND b.pk = CONVERT(nvarchar(40), d.detail_id))
  AND NOT EXISTS (SELECT 1 FROM #journal    j WHERE j.tbl = N'pending_budget_detail' AND j.pk = CONVERT(nvarchar(40), d.detail_id))

UNION ALL
SELECT N'budget_trip', CONVERT(nvarchar(40), t.trip_id), NULL, NULL, t._user,
       CONVERT(varchar(33), t._updated_at, 126),
       CASE WHEN t._updated_at BETWEEN p.run_start_utc AND p.run_end_utc
            THEN N'written during the round' ELSE N'written outside the round window' END
FROM budget.budget_trip t CROSS JOIN #params p
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'budget_trip' AND b.pk = CONVERT(nvarchar(40), t.trip_id))
  AND NOT EXISTS (SELECT 1 FROM #journal    j WHERE j.tbl = N'budget_trip' AND j.pk = CONVERT(nvarchar(40), t.trip_id))

UNION ALL
SELECT N'approval_status', s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year), s.department,
       NULL, s.submitter_email, CONVERT(varchar(33), s._updated_at, 126),
       CASE WHEN s._updated_at BETWEEN p.run_start_utc AND p.run_end_utc
            THEN N'written during the round' ELSE N'written outside the round window' END
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'approval_status'
                    AND b.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year))
  AND NOT EXISTS (SELECT 1 FROM #journal    j WHERE j.tbl = N'approval_status'
                    AND j.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year))
ORDER BY 1, 2;

-- ADJUDICATION ROWS FOUND: ______      (must be 0 to proceed unattended)
GO


/* ---- 1.2 Rows that will be DELETED — created by the round --------------
   In scope, absent from the baseline manifest, present on the journal.
   window_check is a cross-examination of the journal, not a filter: a row the
   AI claims to have written but whose timestamp falls outside the run window
   is a contradiction and must be investigated before anything is deleted.
   ---------------------------------------------------------------------- */
SELECT N'pending_budget' AS [table],
       pb.cost_center, pb.gl_account, pb.fiscal_year, pb.department,
       pb.total_year, pb.remark, pb._user,
       CONVERT(varchar(33), pb._updated_at, 126) AS updated_at_utc,
       j.uat_case,
       CASE WHEN pb._updated_at BETWEEN p.run_start_utc AND p.run_end_utc
            THEN N'in run window'
            ELSE N'*** OUTSIDE THE RUN WINDOW — INVESTIGATE BEFORE DELETING ***' END AS window_check
FROM budget.pending_budget pb
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'pending_budget'
               AND j.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year)
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget'
                    AND b.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year))
ORDER BY pb.cost_center, pb.gl_account;

-- pending_budget rows to delete: ______


SELECT N'pending_budget_detail' AS [table], d.detail_id, d.cost_center, d.gl_account, d.trip_id,
       d.gl_group, d.line_label, d.total_year, d.is_auto_calc, d._user,
       CONVERT(varchar(33), d._updated_at, 126) AS updated_at_utc, j.uat_case,
       CASE WHEN d._updated_at BETWEEN p.run_start_utc AND p.run_end_utc
            THEN N'in run window'
            ELSE N'*** OUTSIDE THE RUN WINDOW — INVESTIGATE BEFORE DELETING ***' END AS window_check
FROM budget.pending_budget_detail d
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'pending_budget_detail' AND j.pk = CONVERT(nvarchar(40), d.detail_id)
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget_detail' AND b.pk = CONVERT(nvarchar(40), d.detail_id))
ORDER BY d.detail_id;

-- pending_budget_detail rows to delete: ______


SELECT N'budget_trip' AS [table], t.trip_id, t.cost_center, t.traveler_name, t.destination,
       t.side, t.days, t.travel_months, t._user,
       CONVERT(varchar(33), t._updated_at, 126) AS updated_at_utc, j.uat_case,
       (SELECT COUNT(*) FROM budget.pending_budget_detail d2 WHERE d2.trip_id = t.trip_id) AS detail_lines_attached
FROM budget.budget_trip t
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'budget_trip' AND j.pk = CONVERT(nvarchar(40), t.trip_id)
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'budget_trip' AND b.pk = CONVERT(nvarchar(40), t.trip_id))
ORDER BY t.trip_id;

-- budget_trip rows to delete: ______


SELECT N'approval_status' AS [table], s.*
FROM budget.approval_status s
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'approval_status' AND j.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year)
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'approval_status'
                    AND b.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year));

-- approval_status rows to delete: ______
-- EXPECTED = 1, and it should be Solution Delivery|2027.  That department had
-- no approval_status row at all before the round — never submitted, in any
-- year.  UAT-36 creates one; UAT-43 leaves it REJECTED.  Restoring it to
-- DRAFT would be WRONG: "never submitted" is the ABSENCE of a row, and the
-- app synthesizes DRAFT from that absence (approval.get_approval_status).
GO


/* ---- 1.3 Rows that will be RESTORED — they existed before the round ----
   For each manifest key, whether it is still present (the round modified it,
   or left it alone) or gone (the round deleted it, and the restore block
   re-inserts it).
   ---------------------------------------------------------------------- */
SELECT b.tbl, b.pk,
       CASE
         WHEN b.tbl = N'pending_budget' THEN
           CASE WHEN EXISTS (SELECT 1 FROM budget.pending_budget pb
                             WHERE pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year) = b.pk)
                THEN N'present — will be overwritten with the baseline values'
                ELSE N'*** DELETED BY THE ROUND — will be re-inserted ***' END
         WHEN b.tbl = N'pending_budget_detail' THEN
           CASE WHEN EXISTS (SELECT 1 FROM budget.pending_budget_detail d WHERE CONVERT(nvarchar(40), d.detail_id) = b.pk)
                THEN N'present — will be overwritten with the baseline values'
                ELSE N'*** DELETED BY THE ROUND — re-insert needs IDENTITY_INSERT ***' END
         WHEN b.tbl = N'budget_trip' THEN
           CASE WHEN EXISTS (SELECT 1 FROM budget.budget_trip t WHERE CONVERT(nvarchar(40), t.trip_id) = b.pk)
                THEN N'present — will be overwritten with the baseline values'
                ELSE N'*** DELETED BY THE ROUND — re-insert needs IDENTITY_INSERT ***' END
         WHEN b.tbl = N'approval_status' THEN
           CASE WHEN EXISTS (SELECT 1 FROM budget.approval_status s
                             WHERE s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year) = b.pk)
                THEN N'present — will be overwritten with the baseline values'
                ELSE N'*** DELETED BY THE ROUND — will be re-inserted ***' END
       END AS current_state
FROM #baseline_pk b
ORDER BY b.tbl, b.pk;

-- rows to restore: ______

-- The money question, in one row.  Compare with out\06, IN SCOPE / pending_budget.
SELECT N'IN SCOPE, right now, before the reset' AS ring,
       COUNT(*) AS pending_budget_rows,
       CONVERT(DECIMAL(38,2), ISNULL(SUM(pb.total_year), 0)) AS total_thb
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc));

-- Last verified baseline: Data & Analytic FY2027 = 3 rows, 42,040.00 THB,
-- approval_status REJECTED.  Solution Delivery FY2027 = 0 rows, no approval
-- row at all, never submitted in any year.  Confirm those against out\02 and
-- out\05a — they are a last-known state, not something this script may assume.
GO


/* ---- 1.4 approval_log rows the round appended -------------------------
   Append-only by design (ADR-0006).  Verified: nothing in backend/ or
   frontend/ ever SELECTs from budget.approval_log, so these rows have zero
   effect on how the application behaves.  Deleting them is purely a choice
   about the audit trail.

   RECOMMENDATION: KEEP THEM.  They are the only record that an AI acted under
   colleagues' names on this date — the table stores the IMPERSONATED person
   and has no real-caller column, so once these rows go, that fact is gone
   from the database entirely.  The human round's own entries simply sit on
   top of them.
   ---------------------------------------------------------------------- */
SELECT l.log_id, l.department, l.fiscal_year, l.action, l.action_by_empcode, l.action_by_email,
       CONVERT(varchar(33), l.action_at, 126) AS action_at_utc,
       l.previous_status, l.new_status, l.comment
FROM budget.approval_log l CROSS JOIN #params p
WHERE l.fiscal_year = p.fy AND l.department IN (p.dept_a, p.dept_b)
  AND l.log_id > p.max_log_id_before
ORDER BY l.log_id;

-- approval_log rows appended by the round: ______
--
-- ONLY IF you have decided to erase the round from the audit trail:
-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE:
-- DELETE l
-- FROM budget.approval_log l
-- CROSS JOIN #params p
-- WHERE l.fiscal_year = p.fy AND l.department IN (p.dept_a, p.dept_b)
--   AND l.log_id > p.max_log_id_before;
GO


/* ---- 1.5 budget.reminder_log -----------------------------------------
   Should be untouched: the nightly Budget Automations workflow runs with
   DRY_RUN='true' and no --execute, so it writes nothing.  A non-empty result
   means somebody ran that workflow manually with execute=true during the
   round — which also means reminder emails went out.
   ---------------------------------------------------------------------- */
SELECT r.*
FROM budget.reminder_log r CROSS JOIN #params p
WHERE r.fiscal_year = p.fy AND r.sent_at BETWEEN p.run_start_utc AND p.run_end_utc
ORDER BY r.reminder_type, r.recipient;

-- reminder_log rows written during the round: ______      (expected 0)
GO


/* ===========================================================================
   PHASE 2 — DELETE the rows the round created.
   Children first: detail lines, then trips, then parent budget rows, then the
   approval record.  Every statement is commented out.  Uncomment one at a
   time, after writing down the count its preview returned.
   =========================================================================== */

/* ---- 2.1 pending_budget_detail ---------------------------------------
   The preview is repeated here on purpose: the count you approve must be the
   count that exists at the moment you run the DELETE, not the one from five
   minutes ago.
   ---------------------------------------------------------------------- */
SELECT COUNT(*) AS will_delete_detail,
       CONVERT(DECIMAL(38,2), ISNULL(SUM(d.total_year), 0)) AS thb_in_those_lines
FROM budget.pending_budget_detail d
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'pending_budget_detail' AND j.pk = CONVERT(nvarchar(40), d.detail_id)
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget_detail' AND b.pk = CONVERT(nvarchar(40), d.detail_id));

-- expected rows: ______   (must equal "pending_budget_detail rows to delete" from 1.2)
-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE:
-- DELETE d
-- FROM budget.pending_budget_detail d
-- CROSS JOIN #params p
-- JOIN #journal j ON j.tbl = N'pending_budget_detail' AND j.pk = CONVERT(nvarchar(40), d.detail_id)
-- WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
--   AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget_detail' AND b.pk = CONVERT(nvarchar(40), d.detail_id));
GO


/* ---- 2.2 budget_trip --------------------------------------------------
   Trips go after their detail lines, mirroring the app's own order
   (write_model._delete_one_trip deletes the trip, then every detail row
   carrying that trip_id).  The second column refuses to leave an orphan: if
   any detail line still points at a trip about to be deleted, it is > 0 and
   you must go back to 2.1.
   ---------------------------------------------------------------------- */
SELECT COUNT(*) AS will_delete_trips,
       (SELECT COUNT(*)
        FROM budget.pending_budget_detail d2
        WHERE d2.trip_id IN (
            SELECT t2.trip_id
            FROM budget.budget_trip t2
            CROSS JOIN #params p2
            JOIN #journal j2 ON j2.tbl = N'budget_trip' AND j2.pk = CONVERT(nvarchar(40), t2.trip_id)
            WHERE t2.fiscal_year = p2.fy AND t2.cost_center IN (SELECT cost_center FROM #cc)
              AND NOT EXISTS (SELECT 1 FROM #baseline_pk b2 WHERE b2.tbl = N'budget_trip' AND b2.pk = CONVERT(nvarchar(40), t2.trip_id)))
       ) AS orphaned_details_that_would_remain
FROM budget.budget_trip t
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'budget_trip' AND j.pk = CONVERT(nvarchar(40), t.trip_id)
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'budget_trip' AND b.pk = CONVERT(nvarchar(40), t.trip_id));

-- expected rows: ______   ·   orphaned_details_that_would_remain MUST be 0
-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE:
-- DELETE t
-- FROM budget.budget_trip t
-- CROSS JOIN #params p
-- JOIN #journal j ON j.tbl = N'budget_trip' AND j.pk = CONVERT(nvarchar(40), t.trip_id)
-- WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
--   AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'budget_trip' AND b.pk = CONVERT(nvarchar(40), t.trip_id));
GO


/* ---- 2.3 pending_budget ----------------------------------------------- */
SELECT COUNT(*) AS will_delete_pending_budget,
       CONVERT(DECIMAL(38,2), ISNULL(SUM(pb.total_year), 0)) AS thb_being_removed
FROM budget.pending_budget pb
CROSS JOIN #params p
JOIN #journal j ON j.tbl = N'pending_budget'
               AND j.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year)
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget'
                    AND b.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year));

-- expected rows: ______   ·   THB being removed: ______
-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE:
-- DELETE pb
-- FROM budget.pending_budget pb
-- CROSS JOIN #params p
-- JOIN #journal j ON j.tbl = N'pending_budget'
--                AND j.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year)
-- WHERE pb.fiscal_year = p.fy
--   AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
--   AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'pending_budget'
--                     AND b.pk = pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year));
GO


/* ---- 2.4 approval_status — the row the round created ------------------
   Expected: exactly one row, Solution Delivery|2027.  DELETE it; do not
   update it to DRAFT.  "Never submitted" is the absence of a row, which the
   app renders as DRAFT.
   ---------------------------------------------------------------------- */
SELECT s.department, s.fiscal_year, s.status, s.submitter_email,
       CONVERT(varchar(33), s._updated_at, 126) AS updated_at_utc
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
  AND EXISTS (SELECT 1 FROM #journal j WHERE j.tbl = N'approval_status'
                AND j.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year))
  AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'approval_status'
                    AND b.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year));

-- expected rows: ______      (expected 1: Solution Delivery|2027)
-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE:
-- DELETE s
-- FROM budget.approval_status s
-- CROSS JOIN #params p
-- WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
--   AND EXISTS (SELECT 1 FROM #journal j WHERE j.tbl = N'approval_status'
--                 AND j.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year))
--   AND NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = N'approval_status'
--                     AND b.pk = s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year));
GO


/* ===========================================================================
   PHASE 3 — RESTORE the pre-round rows, exactly.
   ---------------------------------------------------------------------------
   Paste the blocks generated by baseline section 8, in this order:
       3.1  out\08a_restore_pending_budget.sql
       3.2  out\08b_restore_budget_trip.sql            (trips before details)
       3.3  out\08c_restore_pending_budget_detail.sql
       3.4  out\08d_restore_approval_status.sql
   Each generated statement is a DELETE for one primary key followed by an
   INSERT of the baseline values.  That is what makes the restore correct
   whether the round modified the row, deleted it, or never touched it.

   _updated_at is restored to its baseline value ON PURPOSE.  The application
   uses it as an optimistic-lock token — write_model sends it back as
   expected_updated_at and refuses the write when it does not match.  A
   restore that stamped "now" would leave every open browser tab holding a
   token that no longer exists, and the next real save would 409 against a
   value the user never saw.
   =========================================================================== */

/* ---- 3.1 pending_budget ----------------------------------------------- */
SELECT COUNT(*) AS pending_budget_in_scope_now,
       CONVERT(DECIMAL(38,2), ISNULL(SUM(pb.total_year), 0)) AS thb_now
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc));
-- after the restore this must equal out\06, IN SCOPE / pending_budget: ______ rows, ______ THB

-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE, then paste the file:
-- <<< PASTE out\08a_restore_pending_budget.sql HERE >>>
GO

/* ---- 3.2 budget_trip -------------------------------------------------- */
SELECT COUNT(*) AS trips_in_scope_now
FROM budget.budget_trip t CROSS JOIN #params p
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc);
-- after the restore this must equal out\06, IN SCOPE / budget_trip: ______ rows

-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE, then paste the file between these:
-- SET IDENTITY_INSERT budget.budget_trip ON;
-- <<< PASTE out\08b_restore_budget_trip.sql HERE >>>
-- SET IDENTITY_INSERT budget.budget_trip OFF;
GO

/* ---- 3.3 pending_budget_detail ---------------------------------------- */
SELECT COUNT(*) AS detail_in_scope_now,
       CONVERT(DECIMAL(38,2), ISNULL(SUM(d.total_year), 0)) AS thb_now
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc);
-- after the restore this must equal out\06, IN SCOPE / pending_budget_detail: ______ rows, ______ THB

-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE, then paste the file between these:
-- SET IDENTITY_INSERT budget.pending_budget_detail ON;
-- <<< PASTE out\08c_restore_pending_budget_detail.sql HERE >>>
-- SET IDENTITY_INSERT budget.pending_budget_detail OFF;
GO

/* ---- 3.4 approval_status ----------------------------------------------
   For Data & Analytic FY2027 this is the statement that undoes APPROVED.
   UAT-40 walks the department through all three approval steps, and APPROVED
   is terminal — the application offers no reopen, no un-approve, and no admin
   bypass out of it.  A direct database write is the ONLY way back, and it
   must restore every column together: status, all three approver_actioned_at
   stamps, submitter, reject_reason, rejected_by_empcode and _updated_at.
   Setting status alone would leave the record internally inconsistent — a
   REJECTED row still carrying approver2 and approver3 action timestamps.
   ---------------------------------------------------------------------- */
SELECT s.department, s.fiscal_year, s.status,
       CONVERT(varchar(33), s.approver1_actioned_at, 126) AS approver1_actioned_at,
       CONVERT(varchar(33), s.approver2_actioned_at, 126) AS approver2_actioned_at,
       CONVERT(varchar(33), s.approver3_actioned_at, 126) AS approver3_actioned_at,
       s.reject_reason, s.rejected_by_empcode
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b);
-- current state: ______
-- after the restore this must match out\05a_approval_status_rows.csv exactly:
-- Data & Analytic back to REJECTED with its original reject_reason, and
-- Solution Delivery absent entirely.

-- UNCOMMENT AFTER REVIEWING THE SELECT ABOVE, then paste the file:
-- <<< PASTE out\08d_restore_approval_status.sql HERE >>>
GO


/* ===========================================================================
   PHASE 4 — PROVE IT.  All SELECT.  Nothing below changes anything.
   =========================================================================== */

/* ---- 4.1 Re-run baseline SECTION 6 verbatim and diff it against
   out\06_counts_totals_fingerprints_BEFORE.csv.
     IN SCOPE rows   must MATCH the before-file.
     BLAST RING rows must ALSO match.  A moved blast-ring number means the
     reset reached outside the two departments — stop, and work out what it
     touched before anyone else uses the system.
   SAVE AS: out\06_counts_totals_fingerprints_AFTER.csv
   ---------------------------------------------------------------------- */
--  >>> paste baseline SECTION 6 here verbatim and run it <<<

/* ---- 4.2 Re-run baseline SECTION 6b (per-department FY2027 totals).
   Every department other than the two under test must show an identical row
   count and THB total.  This is the clearest single piece of evidence that
   nobody else's budget was harmed.
   SAVE AS: out\06b_department_totals_AFTER.csv
   ---------------------------------------------------------------------- */
--  >>> paste baseline SECTION 6b here verbatim and run it <<<

/* ---- 4.3 Round-trip and integrity checks — every value MUST be 0 ------ */
SELECT N'baseline rows now missing' AS check_name, COUNT(*) AS value
FROM #baseline_pk b
WHERE (b.tbl = N'pending_budget'        AND NOT EXISTS (SELECT 1 FROM budget.pending_budget pb WHERE pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year) = b.pk))
   OR (b.tbl = N'pending_budget_detail' AND NOT EXISTS (SELECT 1 FROM budget.pending_budget_detail d WHERE CONVERT(nvarchar(40), d.detail_id) = b.pk))
   OR (b.tbl = N'budget_trip'           AND NOT EXISTS (SELECT 1 FROM budget.budget_trip t WHERE CONVERT(nvarchar(40), t.trip_id) = b.pk))
   OR (b.tbl = N'approval_status'       AND NOT EXISTS (SELECT 1 FROM budget.approval_status s WHERE s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year) = b.pk))

UNION ALL
SELECT N'round-created rows still present', COUNT(*)
FROM #journal j
WHERE NOT EXISTS (SELECT 1 FROM #baseline_pk b WHERE b.tbl = j.tbl AND b.pk = j.pk)
  AND ( (j.tbl = N'pending_budget'        AND EXISTS (SELECT 1 FROM budget.pending_budget pb WHERE pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year) = j.pk))
     OR (j.tbl = N'pending_budget_detail' AND EXISTS (SELECT 1 FROM budget.pending_budget_detail d WHERE CONVERT(nvarchar(40), d.detail_id) = j.pk))
     OR (j.tbl = N'budget_trip'           AND EXISTS (SELECT 1 FROM budget.budget_trip t WHERE CONVERT(nvarchar(40), t.trip_id) = j.pk))
     OR (j.tbl = N'approval_status'       AND EXISTS (SELECT 1 FROM budget.approval_status s WHERE s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year) = j.pk)) )

UNION ALL
SELECT N'orphan detail lines pointing at a missing trip', COUNT(*)
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
  AND d.trip_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM budget.budget_trip t WHERE t.trip_id = d.trip_id)

UNION ALL
SELECT N'parent cell not equal to SUM(its detail lines)', COUNT(*)
FROM (
    SELECT pb.total_year,
           (SELECT ISNULL(SUM(d.total_year), 0)
            FROM budget.pending_budget_detail d
            WHERE d.cost_center = pb.cost_center AND d.gl_account = pb.gl_account
              AND d.fiscal_year = pb.fiscal_year) AS detail_sum
    FROM budget.pending_budget pb CROSS JOIN #params p
    WHERE pb.fiscal_year = p.fy AND pb.cost_center IN (SELECT cost_center FROM #cc)
      AND EXISTS (SELECT 1 FROM budget.pending_budget_detail d2
                  WHERE d2.cost_center = pb.cost_center AND d2.gl_account = pb.gl_account
                    AND d2.fiscal_year = pb.fiscal_year)
) x
WHERE x.total_year <> x.detail_sum

UNION ALL
SELECT N'total_year not equal to SUM(m01..m12), in scope', COUNT(*)
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
  AND pb.total_year <> (pb.m01+pb.m02+pb.m03+pb.m04+pb.m05+pb.m06+pb.m07+pb.m08+pb.m09+pb.m10+pb.m11+pb.m12);
GO


/* ---- 4.4 Final eyeball: the two departments exactly as a human will find
   them when the human UAT round starts.
   SAVE AS: out\09_final_state.csv
   ---------------------------------------------------------------------- */
SELECT pb.department, pb.cost_center, pb.gl_account, pb.gl_name, pb.total_year, pb.remark,
       pb._user, CONVERT(varchar(33), pb._updated_at, 126) AS updated_at_utc
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
ORDER BY pb.department, pb.cost_center, pb.gl_account;

SELECT s.*
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b);
GO


DROP TABLE IF EXISTS #cc;
DROP TABLE IF EXISTS #baseline_pk;
DROP TABLE IF EXISTS #journal;
DROP TABLE IF EXISTS #params;
GO


/* ============================================================================
   WHAT THIS SCRIPT CANNOT UNDO — the honest list
   ============================================================================

   1. THE EMAILS.  Roughly thirteen real Thai notification mails, unlabelled,
      from the shared cmanpowerbi mailbox, cc'd to the audit mailbox, sent to
      Laddawan / Nipaporn / Waraporn / Pornthip / Suchanya as the round moves
      the two departments through submit, reject, approve, resubmit, admin
      step-override and final approval.  Each says a real colleague submitted
      or approved a real budget — because under impersonation that is exactly
      what the application believed.  No recall exists, and no row in any
      table records that it was an AI.
      This is the ONE item that can be PREVENTED before the round rather than
      undone after it: see the end of 00_capture_baseline.sql for the two
      Container App env vars that redirect and label every mail.

   2. THE SHAREPOINT ATTACHMENTS.  There is no database table for attachments
      at all — the folder IS the index (backend/app/attachments.py).  UAT-27
      uploads two files into the real library at "Budgeting and Management >
      เอกสาร ฝ่าย/Data & Analytic/2027/", and UAT-30 permanently deletes one
      of them through the app.  Leftovers must be removed by hand in
      SharePoint; a wrongly-deleted file returns only from the SharePoint
      recycle bin, and only a SharePoint admin can retrieve it.  Before the
      human round, open that folder — and Solution Delivery's — and confirm
      the contents match what was there before.

   3. dbo.master_currency_rate (UAT-54).  A global master, edited in the
      SharePoint workbook and synced daily, feeding per-diem for EVERY
      department — not just the two under test.  Changed and not changed back,
      every foreign trip in the company reprices on its next save.  UAT-54's
      own note documents an approved way to avoid this: skip its steps 2 to 6
      and do only step 7.  Do that.

   4. budget.approval_log, IF you choose to delete it (section 1.4).
      Append-only by design, never read by the application, and the only place
      the round's actions are recorded at all.  The recommendation is to keep it.

   5. ANY WRITE BY A REAL COLLEAGUE DURING THE ROUND.  Section 1.1 surfaces
      these as the adjudication list.  This script will not touch them.  They
      are not the AI's to undo.

   ---------------------------------------------------------------------------
   ALSO REVERT — not database state, but part of returning production to normal
   ---------------------------------------------------------------------------
     APP_ENV                          back to 'production'  (this is what kills
                                      /sit/impersonate — auth.py `_sit_guard_ok`
                                      refuses impersonation outright when
                                      app_env is "production")
     SIT_IMPERSONATE                  removed
     NOTIFICATIONS_REDIRECT_ALL_TO    removed, if set for the round
     NOTIFICATIONS_ENVIRONMENT_LABEL  removed, if set for the round
   Tracker tasks prd-appenv-uat-revert-after-uat and
   prd-session-1h-revert-after-uat already carry the first two.
   ============================================================================ */
