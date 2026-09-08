/* ============================================================================
   00_capture_baseline.sql   —   READ-ONLY.  Run BEFORE the AI UAT round.
   ----------------------------------------------------------------------------
   Target DB : the PRODUCTION Fabric SQL Database behind cman-budget-web-prd
               (FABRIC_SQL_DATABASE = fabric_sql_database-a42ef9f3-f190-464a-
               8d5e-c0d41ef9ce42, server v5o4qez3u4cupase7cogkwvyke-
               bby6xlm3ncqexly4ozejod2vqe.database.fabric.microsoft.com).
               staging and production share THIS ONE database.

   WHAT THIS IS: a snapshot of everything the 54-case UAT round can write,
   plus a generator that emits the exact T-SQL needed to put those rows back.
   It contains NOT ONE mutating statement — every batch is a SELECT.

   WHY IT MATTERS: 10_reset_after_ai_run.sql cannot restore what was never
   captured.  Incident 2026-08-18: a cleanup on this system assumed an empty
   baseline and deleted a trip a real user had created.  Nothing below ever
   assumes an empty baseline — it records what IS there, whatever that is.

   ---------------------------------------------------------------------------
   HOW TO RUN
   ---------------------------------------------------------------------------
   1. Open the Fabric SQL query editor (or SSMS / Azure Data Studio) against
      the database above, as jakkaritw or the cman-fabric-write SP.
   2. Run SECTION 0 FIRST and leave the session open.  It creates #params,
      which every later section reads.  #params is session-scoped: if the
      connection drops, start again from section 0.
   3. Run the remaining sections one at a time and SAVE each result grid to
      the file named in its "SAVE AS" comment, under
      .scratch\uat-prep\reset\out\ .  CSV with headers, UTF-8 — except
      sections 7b and 8, which are T-SQL text and are saved as .sql, one
      result row per line, with nothing added or quoted.
   4. Section 0 prints the run-start timestamp.  WRITE IT DOWN.

   ---------------------------------------------------------------------------
   THE ONE THING PEOPLE GET WRONG HERE: TIME ZONE
   ---------------------------------------------------------------------------
   The application writes UTC.  backend/app/write_model.py:300 and
   backend/app/approval.py:276 are both `datetime.now(timezone.utc)`, and the
   values land in DATETIME2 columns, which carry no offset.  So every
   _updated_at / action_at / submitted_at in these tables is a UTC wall clock,
   SEVEN HOURS BEHIND Bangkok.
   (Only the DEADLINE comparison is Bangkok-anchored — app/deadline.py
   `bangkok_today()` — and that compares dates against dbo.submission_deadline,
   not any column here.)
   Paste the UTC value into the reset script.  A Bangkok timestamp selects the
   wrong seven-hour band and looks entirely plausible while being wrong.

   ---------------------------------------------------------------------------
   A NOTE ON GRID TRUNCATION (sections 7b and 8)
   ---------------------------------------------------------------------------
   Those sections emit T-SQL as nvarchar(max) text.  Some query editors clip
   long values in the results grid.  In SSMS use Results To Text with
   "Maximum characters displayed" raised to 8192+; in the Fabric editor, copy
   from the grid cell itself, not from a CSV export.  If any generated
   statement looks cut off mid-word, re-run that generator filtered to the one
   row rather than trusting the clipped text.
   ============================================================================ */


/* ===========================================================================
   SECTION 0 — parameters, identity, clock.  RUN THIS FIRST.
   SAVE AS: out\00_section0_identity.csv
   ---------------------------------------------------------------------------
   #params holds the three values every later section needs, in ONE place, so
   no section can drift from another.  It survives GO but not a reconnect.
   =========================================================================== */
DROP TABLE IF EXISTS #params;
CREATE TABLE #params (
    fy      INT           NOT NULL,
    dept_a  NVARCHAR(150) NOT NULL,
    dept_b  NVARCHAR(150) NOT NULL
);
INSERT INTO #params (fy, dept_a, dept_b) VALUES
    (2027,                       -- planning fiscal year.  The on-screen year
                                 -- picker says "Year 2026"; the DB, the Submit
                                 -- confirm dialog and the attachments folder
                                 -- name all say 2027.
                                 -- frontend/src/filters/deepLink.ts:48 = label + 1.
     N'Data & Analytic',
     N'Solution Delivery');

SELECT N'RUN START (UTC) — copy this into @run_start_utc in the reset script' AS [what],
       CONVERT(varchar(33), SYSUTCDATETIME(), 126) AS [value]
UNION ALL SELECT N'the same instant in Bangkok (for humans only — NEVER paste this into the reset)',
       CONVERT(varchar(33), DATEADD(HOUR, 7, SYSUTCDATETIME()), 126)
UNION ALL SELECT N'database', DB_NAME()
UNION ALL SELECT N'server',   CONVERT(nvarchar(200), SERVERPROPERTY('ServerName'))
UNION ALL SELECT N'login',    SUSER_SNAME()
UNION ALL SELECT N'fiscal_year under test', CONVERT(nvarchar(10), (SELECT fy FROM #params));
GO


/* ===========================================================================
   SECTION 0b — which fiscal years are OPEN for web writing
   ---------------------------------------------------------------------------
   This is the containment fact the whole plan leans on.  write_model
   `_ensure_year_open_for_write` (line 362) refuses EVERY write path
   (/budget/rows, /budget/detail, /budget/trip and their deletes) for a year
   with no dbo.submission_deadline row — admin included, no bypass.  So the
   round physically cannot touch a fiscal_year absent from this list.
   If more than FY2027 comes back, either widen the reset's scope to match or
   ask the admin to close the extra year for the duration of the round.
   SAVE AS: out\00_section0b_open_years.csv
   =========================================================================== */
SELECT fiscal_year,
       deadline_date,
       CASE WHEN CAST(DATEADD(HOUR, 7, SYSUTCDATETIME()) AS date) > deadline_date
            THEN N'PAST_DEADLINE (only admin may write)'
            ELSE N'OPEN (anyone with Fill scope may write)' END AS state_bangkok_anchored
FROM dbo.submission_deadline
ORDER BY fiscal_year;
GO


/* ===========================================================================
   SECTION 0c — live column reality check
   ---------------------------------------------------------------------------
   Do NOT trust db/schema.sql: that file is the RETIRED Azure-SQL-era schema
   (ADR-0017) and does not describe these tables at all.  The live shape is
   db/ddl/budget_transactional_tables.sql plus three columns added to
   budget.budget_trip afterwards by setup/migrate_budget_trip_project.py,
   _remark.py and _client_token.py.  Confirm project, remark and client_token
   are present before trusting section 8b — "live columns != spec DBML" has
   produced showstoppers on this project before.
   SAVE AS: out\00_section0c_columns.csv
   =========================================================================== */
SELECT TABLE_SCHEMA, TABLE_NAME, ORDINAL_POSITION, COLUMN_NAME, DATA_TYPE,
       CHARACTER_MAXIMUM_LENGTH, NUMERIC_PRECISION, NUMERIC_SCALE, IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'budget'
  AND TABLE_NAME IN ('pending_budget','pending_budget_detail','budget_trip',
                     'approval_status','approval_log','reminder_log')
ORDER BY TABLE_NAME, ORDINAL_POSITION;
GO


/* ===========================================================================
   SECTION 1 — resolve the two departments to their cost centers
   ---------------------------------------------------------------------------
   budget.pending_budget.department is a SNAPSHOT column, re-derived at write
   time from dbo.cc_filler_map (write_model `_lookup_cc_dims`, line 458).
   cc_filler_map changes — it was purged on 2026-08-31, 117 fillers down to 79
   — so an old row's snapshot can disagree with today's mapping.  Every
   predicate downstream therefore matches on BOTH the snapshot department AND
   the cost-center list built here.

   ASSERTION: both departments MUST return cost centers.  A typo in a
   department name returns zero rows everywhere downstream, and the whole
   reset then looks reassuringly "safe" while doing nothing.  If either count
   is 0, STOP and fix the name in #params.
   SAVE AS: out\01_scope_cost_centers.csv
   =========================================================================== */
DROP TABLE IF EXISTS #cc;
CREATE TABLE #cc (cost_center NVARCHAR(20) NOT NULL PRIMARY KEY);
INSERT INTO #cc (cost_center)
SELECT DISTINCT m.cost_center
FROM dbo.cc_filler_map m
CROSS JOIN #params p
WHERE m.department IN (p.dept_a, p.dept_b);

SELECT m.department,
       COUNT(DISTINCT m.cost_center) AS cost_center_count,
       STRING_AGG(CONVERT(nvarchar(max), m.cost_center), N', ')
           WITHIN GROUP (ORDER BY m.cost_center) AS cost_centers
FROM (SELECT DISTINCT m2.department, m2.cost_center
      FROM dbo.cc_filler_map m2 CROSS JOIN #params p2
      WHERE m2.department IN (p2.dept_a, p2.dept_b)) m
GROUP BY m.department;

SELECT DISTINCT m.department, m.cost_center, m.filler_email
FROM dbo.cc_filler_map m CROSS JOIN #params p
WHERE m.department IN (p.dept_a, p.dept_b)
ORDER BY m.department, m.cost_center, m.filler_email;
GO


/* ===========================================================================
   SECTION 2 — budget.pending_budget  (PK: cost_center, gl_account, fiscal_year)
   Every column, every in-scope row.  This is where the money lives.
   SAVE AS: out\02_pending_budget_rows.csv
   =========================================================================== */
SELECT pb.*
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b)
       OR pb.cost_center IN (SELECT cost_center FROM #cc))
ORDER BY pb.department, pb.cost_center, pb.gl_account;
GO


/* ===========================================================================
   SECTION 3 — budget.pending_budget_detail  (PK: detail_id, IDENTITY)
   ---------------------------------------------------------------------------
   Special-GL subform lines.  Scoped through the cost-center list, since this
   table carries no department column of its own.  is_auto_calc = 1 marks a
   per-diem line whose months the server re-derives on read (ADR-0015) — it is
   still a real stored row and still needs restoring.
   SAVE AS: out\03_pending_budget_detail_rows.csv
   =========================================================================== */
SELECT d.*
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
ORDER BY d.cost_center, d.gl_account, d.detail_id;
GO


/* ===========================================================================
   SECTION 4 — budget.budget_trip  (PK: trip_id, IDENTITY)
   SAVE AS: out\04_budget_trip_rows.csv
   =========================================================================== */
SELECT t.*
FROM budget.budget_trip t CROSS JOIN #params p
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
ORDER BY t.cost_center, t.trip_id;
GO


/* ===========================================================================
   SECTION 5 — budget.approval_status and budget.approval_log
   ---------------------------------------------------------------------------
   approval_status PK = (department, fiscal_year) — the approval unit, ADR-0008.

   ZERO ROWS FOR A DEPARTMENT IS A REAL, MEANINGFUL BASELINE.  It means "never
   submitted", and the app synthesizes DRAFT from the absence of a row
   (approval.get_approval_status).  If Solution Delivery FY2027 returns
   nothing here, the reset must DELETE the row the round creates — not update
   it back to DRAFT.  Those are different end states.
   SAVE AS: out\05a_approval_status_rows.csv, out\05b_approval_log_rows.csv
   =========================================================================== */
SELECT s.*
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
ORDER BY s.department;

-- approval_log is append-only (ADR-0006) and NOTHING in the application ever
-- reads it back — verified: no SELECT against budget.approval_log exists
-- anywhere in backend/ or frontend/.  Deleting the round's log rows therefore
-- has zero functional effect; it is purely a question of whether the audit
-- trail should keep saying an AI acted under colleagues' names on this date.
SELECT l.*
FROM budget.approval_log l CROSS JOIN #params p
WHERE l.fiscal_year = p.fy AND l.department IN (p.dept_a, p.dept_b)
ORDER BY l.log_id;

SELECT N'MAX(log_id) BEFORE the round — copy into @max_log_id_before' AS [what],
       CONVERT(varchar(20), ISNULL(MAX(log_id), 0)) AS [value]
FROM budget.approval_log;
GO


/* ===========================================================================
   SECTION 5c — budget.reminder_log
   ---------------------------------------------------------------------------
   Written ONLY by backend/jobs/send_reminders.py, driven by
   .github/workflows/budget-automations.yml.  The nightly schedule passes no
   --execute and sets DRY_RUN='true', so it writes nothing.  Captured anyway:
   if somebody triggers that workflow manually with execute=true during the
   round, this is the only way to see it afterwards.
   SAVE AS: out\05c_reminder_log_rows.csv
   =========================================================================== */
SELECT r.*
FROM budget.reminder_log r CROSS JOIN #params p
WHERE r.fiscal_year = p.fy
ORDER BY r.reminder_type, r.recipient;
GO


/* ===========================================================================
   SECTION 6 — counts, money totals, fingerprints
   ---------------------------------------------------------------------------
   Two rings:
     IN SCOPE   — the two departments, FY2027.  The reset restores these to
                  exactly these numbers.
     BLAST RING — all of FY2027 and both neighbouring years, every department.
                  The reset must leave these IDENTICAL.  Re-run this section
                  after the reset and diff it; a moved blast-ring number means
                  the reset reached outside the two departments.
   The fingerprint is CHECKSUM_AGG over a per-row CHECKSUM: two runs returning
   the same number almost certainly hold the same rows.  Treat it as a smoke
   alarm, not a proof — the counts and money totals are the real evidence.
   SAVE AS: out\06_counts_totals_fingerprints_BEFORE.csv
   =========================================================================== */
SELECT N'IN SCOPE' AS ring, N'pending_budget' AS [table],
       COUNT(*) AS row_count,
       CONVERT(DECIMAL(38,2), ISNULL(SUM(pb.total_year), 0)) AS total_thb,
       CHECKSUM_AGG(CHECKSUM(pb.cost_center, pb.gl_account, pb.fiscal_year,
                             pb.total_year, pb.remark, pb._user, pb._updated_at)) AS fingerprint
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))

UNION ALL
SELECT N'IN SCOPE', N'pending_budget_detail',
       COUNT(*), CONVERT(DECIMAL(38,2), ISNULL(SUM(d.total_year), 0)),
       CHECKSUM_AGG(CHECKSUM(d.detail_id, d.cost_center, d.gl_account, d.fiscal_year,
                             d.trip_id, d.total_year, d._user, d._updated_at))
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)

UNION ALL
SELECT N'IN SCOPE', N'budget_trip',
       COUNT(*), NULL,
       CHECKSUM_AGG(CHECKSUM(t.trip_id, t.cost_center, t.fiscal_year, t.traveler_empcode,
                             t.days, t.travel_months, t.side, t._updated_at))
FROM budget.budget_trip t CROSS JOIN #params p
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)

UNION ALL
SELECT N'IN SCOPE', N'approval_status',
       COUNT(*), NULL,
       CHECKSUM_AGG(CHECKSUM(s.department, s.fiscal_year, s.status, s.submitter_email, s._updated_at))
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)

UNION ALL
SELECT N'IN SCOPE', N'approval_log',
       COUNT(*), NULL, CHECKSUM_AGG(CHECKSUM(l.log_id))
FROM budget.approval_log l CROSS JOIN #params p
WHERE l.fiscal_year = p.fy AND l.department IN (p.dept_a, p.dept_b)

/* ---- BLAST RING: must be identical before and after the reset ---------- */
UNION ALL
SELECT N'BLAST RING', N'pending_budget FY-1..FY+1, ALL departments',
       COUNT(*), CONVERT(DECIMAL(38,2), ISNULL(SUM(pb.total_year), 0)),
       CHECKSUM_AGG(CHECKSUM(pb.cost_center, pb.gl_account, pb.fiscal_year, pb.total_year, pb._updated_at))
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year BETWEEN p.fy - 1 AND p.fy + 1

UNION ALL
SELECT N'BLAST RING', N'pending_budget_detail FY-1..FY+1, ALL departments',
       COUNT(*), CONVERT(DECIMAL(38,2), ISNULL(SUM(d.total_year), 0)),
       CHECKSUM_AGG(CHECKSUM(d.detail_id, d.total_year, d._updated_at))
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year BETWEEN p.fy - 1 AND p.fy + 1

UNION ALL
SELECT N'BLAST RING', N'budget_trip FY-1..FY+1, ALL departments',
       COUNT(*), NULL, CHECKSUM_AGG(CHECKSUM(t.trip_id, t._updated_at))
FROM budget.budget_trip t CROSS JOIN #params p
WHERE t.fiscal_year BETWEEN p.fy - 1 AND p.fy + 1

UNION ALL
SELECT N'BLAST RING', N'approval_status FY-1..FY+1, ALL departments',
       COUNT(*), NULL, CHECKSUM_AGG(CHECKSUM(s.department, s.fiscal_year, s.status, s._updated_at))
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year BETWEEN p.fy - 1 AND p.fy + 1

UNION ALL
SELECT N'BLAST RING', N'pending_budget WHOLE TABLE',
       COUNT(*), CONVERT(DECIMAL(38,2), ISNULL(SUM(total_year), 0)), NULL
FROM budget.pending_budget;
GO


/* ===========================================================================
   SECTION 6b — per-department money totals for the planning year
   ---------------------------------------------------------------------------
   The single most useful "did we harm anyone else's data" check.  Every
   department except the two under test must show an identical row count and
   THB total after the reset.
   SAVE AS: out\06b_department_totals_BEFORE.csv
   =========================================================================== */
SELECT ISNULL(pb.department, N'(null department)') AS department,
       COUNT(*)                                    AS row_count,
       CONVERT(DECIMAL(38,2), SUM(pb.total_year))  AS total_thb
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
GROUP BY pb.department
ORDER BY department;
GO


/* ===========================================================================
   SECTION 7 — THE PRE-ROUND PRIMARY KEY MANIFEST (human-readable)
   ---------------------------------------------------------------------------
   Exactly which rows existed BEFORE the round.  The reset uses this to answer
   the only question that matters about any row it finds afterwards: "was this
   already here, or did the round create it?"
   SAVE AS: out\07_baseline_pk_manifest.csv
   =========================================================================== */
SELECT N'pending_budget' AS [table],
       pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year) AS pk,
       CONVERT(nvarchar(40), pb.total_year) AS amount_or_status,
       pb._user AS who, CONVERT(varchar(33), pb._updated_at, 126) AS updated_at_utc
FROM budget.pending_budget pb CROSS JOIN #params p
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
UNION ALL
SELECT N'pending_budget_detail', CONVERT(nvarchar(40), d.detail_id),
       CONVERT(nvarchar(40), d.total_year), d._user, CONVERT(varchar(33), d._updated_at, 126)
FROM budget.pending_budget_detail d CROSS JOIN #params p
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
UNION ALL
SELECT N'budget_trip', CONVERT(nvarchar(40), t.trip_id),
       NULL, t._user, CONVERT(varchar(33), t._updated_at, 126)
FROM budget.budget_trip t CROSS JOIN #params p
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
UNION ALL
SELECT N'approval_status', s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year),
       s.status, s.submitter_email, CONVERT(varchar(33), s._updated_at, 126)
FROM budget.approval_status s CROSS JOIN #params p
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
ORDER BY 1, 2;
GO


/* ===========================================================================
   SECTION 7b — THE SAME MANIFEST, AS PASTE-READY INSERT ROWS
   ---------------------------------------------------------------------------
   Copy this whole result column into the #baseline_pk block of the reset
   script.  It saves converting a CSV by hand, which is where transcription
   errors come from.  Each row is one VALUES tuple; the last one ends in a
   comma, so delete that final comma and add a semicolon after pasting.
   IF THIS RETURNS NO ROWS, the two departments genuinely had nothing at
   FY2027 — record that fact explicitly rather than assuming you mis-ran it.
   SAVE AS: out\07b_baseline_pk_inserts.sql
   =========================================================================== */
SELECT CONVERT(nvarchar(max), N'  (N''') + x.tbl + N''', N''' + REPLACE(x.pk, '''', '''''') + N'''),'
       AS values_row
FROM (
    SELECT N'pending_budget' AS tbl,
           pb.cost_center + N'|' + pb.gl_account + N'|' + CONVERT(nvarchar(10), pb.fiscal_year) AS pk
    FROM budget.pending_budget pb CROSS JOIN #params p
    WHERE pb.fiscal_year = p.fy
      AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
    UNION ALL
    SELECT N'pending_budget_detail', CONVERT(nvarchar(40), d.detail_id)
    FROM budget.pending_budget_detail d CROSS JOIN #params p
    WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
    UNION ALL
    SELECT N'budget_trip', CONVERT(nvarchar(40), t.trip_id)
    FROM budget.budget_trip t CROSS JOIN #params p
    WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
    UNION ALL
    SELECT N'approval_status', s.department + N'|' + CONVERT(nvarchar(10), s.fiscal_year)
    FROM budget.approval_status s CROSS JOIN #params p
    WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
) x
ORDER BY x.tbl, x.pk;
GO


/* ===========================================================================
   SECTION 8 — RESTORE-SCRIPT GENERATOR
   ---------------------------------------------------------------------------
   Each generator emits T-SQL text, ONE STATEMENT PER RESULT ROW, in the order
   they must be run.  Between them they rebuild every in-scope baseline row
   exactly: same values, same identity ids, same _updated_at.

   WHY _updated_at MUST COME BACK UNCHANGED: the application uses it as an
   optimistic-lock token — write_model sends it as expected_updated_at and
   refuses the write when it does not match.  A restore that stamped "now"
   would leave every open browser tab holding a token that no longer exists,
   and the next real save would 409 against a value the user never saw.

   Each key gets a DELETE followed by an INSERT.  That is what makes the
   restore correct whether the round MODIFIED the row, DELETED it, or never
   touched it at all.

   Every generated statement is built as nvarchar(max) deliberately: meta_json
   on pending_budget_detail is NVARCHAR(MAX), and an nvarchar(4000)
   concatenation would truncate a long JSON payload SILENTLY, producing a
   statement that still parses and restores the wrong data.

   SAVE AS: out\08a_restore_pending_budget.sql
            out\08b_restore_budget_trip.sql
            out\08c_restore_pending_budget_detail.sql
            out\08d_restore_approval_status.sql
   RUN ORDER inside the reset: 08a, then 08b, then 08c, then 08d —
   trips before detail lines, because detail rows carry trip_id.
   =========================================================================== */

/* ---- 8a. budget.pending_budget --------------------------------------- */
SELECT v.stmt
FROM budget.pending_budget pb
CROSS JOIN #params p
CROSS APPLY (VALUES
  (1, CONVERT(nvarchar(max),
        N'DELETE FROM budget.pending_budget WHERE cost_center = N''' + REPLACE(pb.cost_center, '''', '''''')
      + N''' AND gl_account = N''' + REPLACE(pb.gl_account, '''', '''''')
      + N''' AND fiscal_year = ' + CONVERT(nvarchar(10), pb.fiscal_year) + N';')),
  (2, CONVERT(nvarchar(max),
        N'INSERT INTO budget.pending_budget (cost_center,gl_account,fiscal_year,m01,m02,m03,m04,m05,m06,m07,m08,m09,m10,m11,m12,total_year,template,remark,gl_name,gl_group,c_level,division,department,_user,_updated_at) VALUES (')
      + N'N''' + REPLACE(pb.cost_center, '''', '''''') + N''','
      + N'N''' + REPLACE(pb.gl_account,  '''', '''''') + N''','
      + CONVERT(nvarchar(10), pb.fiscal_year) + N','
      + CONVERT(nvarchar(40), pb.m01) + N',' + CONVERT(nvarchar(40), pb.m02) + N',' + CONVERT(nvarchar(40), pb.m03) + N','
      + CONVERT(nvarchar(40), pb.m04) + N',' + CONVERT(nvarchar(40), pb.m05) + N',' + CONVERT(nvarchar(40), pb.m06) + N','
      + CONVERT(nvarchar(40), pb.m07) + N',' + CONVERT(nvarchar(40), pb.m08) + N',' + CONVERT(nvarchar(40), pb.m09) + N','
      + CONVERT(nvarchar(40), pb.m10) + N',' + CONVERT(nvarchar(40), pb.m11) + N',' + CONVERT(nvarchar(40), pb.m12) + N','
      + CONVERT(nvarchar(40), pb.total_year) + N','
      + N'N''' + REPLACE(pb.template, '''', '''''') + N''','
      + ISNULL(N'N''' + REPLACE(pb.remark,     '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(pb.gl_name,    '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(pb.gl_group,   '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(pb.c_level,    '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(pb.division,   '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(pb.department, '''', '''''') + N'''', N'NULL') + N','
      + N'N''' + REPLACE(pb._user, '''', '''''') + N''','
      + N'''' + CONVERT(varchar(33), pb._updated_at, 126) + N''');')
) v(ord, stmt)
WHERE pb.fiscal_year = p.fy
  AND (pb.department IN (p.dept_a, p.dept_b) OR pb.cost_center IN (SELECT cost_center FROM #cc))
ORDER BY pb.cost_center, pb.gl_account, v.ord;
GO


/* ---- 8b. budget.budget_trip (IDENTITY: trip_id) -----------------------
   Wrap the pasted block by hand:
       SET IDENTITY_INSERT budget.budget_trip ON;
       ...
       SET IDENTITY_INSERT budget.budget_trip OFF;
   project / remark / client_token were added to the live table by
   setup/migrate_budget_trip_*.py.  Section 0c proves they exist; if any is
   missing, remove it from BOTH the column list and the VALUES list below
   before generating.
   ---------------------------------------------------------------------- */
SELECT v.stmt
FROM budget.budget_trip t
CROSS JOIN #params p
CROSS APPLY (VALUES
  (1, CONVERT(nvarchar(max),
        N'DELETE FROM budget.budget_trip WHERE trip_id = ' + CONVERT(nvarchar(40), t.trip_id) + N';')),
  (2, CONVERT(nvarchar(max),
        N'INSERT INTO budget.budget_trip (trip_id,cost_center,fiscal_year,traveler_empcode,traveler_name,position,destination,country_group,days,travel_months,purpose,project,remark,side,client_token,_user,_updated_at) VALUES (')
      + CONVERT(nvarchar(40), t.trip_id) + N','
      + N'N''' + REPLACE(t.cost_center, '''', '''''') + N''','
      + CONVERT(nvarchar(10), t.fiscal_year) + N','
      + ISNULL(N'N''' + REPLACE(t.traveler_empcode, '''', '''''') + N'''', N'NULL') + N','
      + N'N''' + REPLACE(t.traveler_name, '''', '''''') + N''','
      + ISNULL(N'N''' + REPLACE(t.position,    '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(t.destination, '''', '''''') + N'''', N'NULL') + N','
      + CONVERT(nvarchar(10), t.country_group) + N','
      + CONVERT(nvarchar(10), t.days) + N','
      + N'N''' + REPLACE(t.travel_months, '''', '''''') + N''','
      + ISNULL(N'N''' + REPLACE(t.purpose,      '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(t.project,      '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(t.remark,       '''', '''''') + N'''', N'NULL') + N','
      + N'N''' + REPLACE(t.side, '''', '''''') + N''','
      + ISNULL(N'N''' + REPLACE(t.client_token, '''', '''''') + N'''', N'NULL') + N','
      + N'N''' + REPLACE(t._user, '''', '''''') + N''','
      + N'''' + CONVERT(varchar(33), t._updated_at, 126) + N''');')
) v(ord, stmt)
WHERE t.fiscal_year = p.fy AND t.cost_center IN (SELECT cost_center FROM #cc)
ORDER BY t.trip_id, v.ord;
GO


/* ---- 8c. budget.pending_budget_detail (IDENTITY: detail_id) -----------
   Wrap the pasted block by hand:
       SET IDENTITY_INSERT budget.pending_budget_detail ON;
       ...
       SET IDENTITY_INSERT budget.pending_budget_detail OFF;
   ---------------------------------------------------------------------- */
SELECT v.stmt
FROM budget.pending_budget_detail d
CROSS JOIN #params p
CROSS APPLY (VALUES
  (1, CONVERT(nvarchar(max),
        N'DELETE FROM budget.pending_budget_detail WHERE detail_id = ' + CONVERT(nvarchar(40), d.detail_id) + N';')),
  (2, CONVERT(nvarchar(max),
        N'INSERT INTO budget.pending_budget_detail (detail_id,cost_center,gl_account,fiscal_year,trip_id,gl_group,line_label,m01,m02,m03,m04,m05,m06,m07,m08,m09,m10,m11,m12,total_year,meta_json,is_auto_calc,_user,_updated_at) VALUES (')
      + CONVERT(nvarchar(40), d.detail_id) + N','
      + N'N''' + REPLACE(d.cost_center, '''', '''''') + N''','
      + N'N''' + REPLACE(d.gl_account,  '''', '''''') + N''','
      + CONVERT(nvarchar(10), d.fiscal_year) + N','
      + ISNULL(CONVERT(nvarchar(40), d.trip_id), N'NULL') + N','
      + N'N''' + REPLACE(d.gl_group, '''', '''''') + N''','
      + ISNULL(N'N''' + REPLACE(d.line_label, '''', '''''') + N'''', N'NULL') + N','
      + CONVERT(nvarchar(40), d.m01) + N',' + CONVERT(nvarchar(40), d.m02) + N',' + CONVERT(nvarchar(40), d.m03) + N','
      + CONVERT(nvarchar(40), d.m04) + N',' + CONVERT(nvarchar(40), d.m05) + N',' + CONVERT(nvarchar(40), d.m06) + N','
      + CONVERT(nvarchar(40), d.m07) + N',' + CONVERT(nvarchar(40), d.m08) + N',' + CONVERT(nvarchar(40), d.m09) + N','
      + CONVERT(nvarchar(40), d.m10) + N',' + CONVERT(nvarchar(40), d.m11) + N',' + CONVERT(nvarchar(40), d.m12) + N','
      + CONVERT(nvarchar(40), d.total_year) + N','
      + ISNULL(N'N''' + REPLACE(d.meta_json, '''', '''''') + N'''', N'NULL') + N','
      + CONVERT(nvarchar(1), d.is_auto_calc) + N','
      + N'N''' + REPLACE(d._user, '''', '''''') + N''','
      + N'''' + CONVERT(varchar(33), d._updated_at, 126) + N''');')
) v(ord, stmt)
WHERE d.fiscal_year = p.fy AND d.cost_center IN (SELECT cost_center FROM #cc)
ORDER BY d.detail_id, v.ord;
GO


/* ---- 8d. budget.approval_status ---------------------------------------
   A department that produced NO row in section 5 produces none here either.
   That is the correct baseline: the reset DELETEs the round's row for it
   rather than restoring one.  See section 5.
   ---------------------------------------------------------------------- */
SELECT v.stmt
FROM budget.approval_status s
CROSS JOIN #params p
CROSS APPLY (VALUES
  (1, CONVERT(nvarchar(max),
        N'DELETE FROM budget.approval_status WHERE department = N''' + REPLACE(s.department, '''', '''''')
      + N''' AND fiscal_year = ' + CONVERT(nvarchar(10), s.fiscal_year) + N';')),
  (2, CONVERT(nvarchar(max),
        N'INSERT INTO budget.approval_status (department,fiscal_year,status,submitter_empcode,submitter_email,submitted_at,approver1_empcode,approver1_actioned_at,approver2_actioned_at,approver3_actioned_at,reject_reason,rejected_by_empcode,_updated_at) VALUES (')
      + N'N''' + REPLACE(s.department, '''', '''''') + N''','
      + CONVERT(nvarchar(10), s.fiscal_year) + N','
      + N'N''' + REPLACE(s.status, '''', '''''') + N''','
      + ISNULL(N'N''' + REPLACE(s.submitter_empcode, '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(s.submitter_email,   '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'''' + CONVERT(varchar(33), s.submitted_at, 126) + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(s.approver1_empcode, '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'''' + CONVERT(varchar(33), s.approver1_actioned_at, 126) + N'''', N'NULL') + N','
      + ISNULL(N'''' + CONVERT(varchar(33), s.approver2_actioned_at, 126) + N'''', N'NULL') + N','
      + ISNULL(N'''' + CONVERT(varchar(33), s.approver3_actioned_at, 126) + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(s.reject_reason,       '''', '''''') + N'''', N'NULL') + N','
      + ISNULL(N'N''' + REPLACE(s.rejected_by_empcode, '''', '''''') + N'''', N'NULL') + N','
      + N'''' + CONVERT(varchar(33), s._updated_at, 126) + N''');')
) v(ord, stmt)
WHERE s.fiscal_year = p.fy AND s.department IN (p.dept_a, p.dept_b)
ORDER BY s.department, v.ord;
GO


/* ===========================================================================
   SECTION 9 — what this file CANNOT capture
   ---------------------------------------------------------------------------
   Read this before starting the round.  Everything below is outside SQL, and
   outside any reset.

   1. SENT EMAILS.  NOTIFICATIONS_DRY_RUN is 'false' on cman-budget-web-prd,
      and neither NOTIFICATIONS_REDIRECT_ALL_TO nor
      NOTIFICATIONS_ENVIRONMENT_LABEL is set, so every submit / approve /
      reject / step-override sends a real, unlabelled Thai email to the real
      colleague, from the shared cmanpowerbi mailbox, cc'd to the audit
      mailbox.  There is no recall.  About thirteen of these, several signed
      as the impersonated person.  PREVENTABLE — see the end of this file.

   2. SHAREPOINT ATTACHMENTS.  Uploads go to the real library CMANDWPRD >
      "Budgeting and Management" > "เอกสาร ฝ่าย/<department>/2027/".  There is
      NO database table for attachments at all — the folder IS the index
      (backend/app/attachments.py module docstring).  Nothing in these scripts
      can see them, list them, or put them back.  UAT-27 uploads two files and
      UAT-30 permanently deletes one; leftovers must be removed by hand, and a
      wrongly-deleted file comes back only from the SharePoint recycle bin, by
      a SharePoint admin.

   3. dbo.master_currency_rate (UAT-54).  That case asks an admin to change
      the USD/THB rate in the SharePoint master workbook and change it back.
      It is a GLOBAL master feeding every department's per-diem, synced daily
      — not scoped to the two test departments, and not restorable here.
      UAT-54's own note offers a documented way out: skip its steps 2 to 6 and
      do only step 7.  Take it.

   4. Anything a REAL colleague writes while the round is running.  staging and
      production share this one database, and the round runs during working
      hours under real people's identities.  That is why section 7 exists, and
      why the reset refuses to delete a row absent from the AI's own journal.

   ---------------------------------------------------------------------------
   THE ONE SIDE EFFECT THAT IS ACTUALLY PREVENTABLE
   ---------------------------------------------------------------------------
   Setting these two env vars on the cman-budget-web-prd Container App for the
   duration of the AI round turns every notification into a loud, labelled mail
   delivered ONLY to jakkaritw, with the real intended To/cc printed in the body
   (backend/app/notifications.py `_apply_redirect`, `_mark_test_environment`):

       NOTIFICATIONS_REDIRECT_ALL_TO=jakkaritw@chememan.com
       NOTIFICATIONS_ENVIRONMENT_LABEL=UAT - AI DRY RUN

   Cost: UAT-46 to UAT-50 check email delivery to the real approvers, and with
   the redirect on, the AI checks delivery to jakkaritw's inbox instead.  The
   AI cannot read a colleague's inbox anyway, so it was never going to verify
   real delivery — the human round, run with these vars removed, is what proves
   it.  Both must be REMOVED before the human round starts; put them on the
   same revert list as APP_ENV and SIT_IMPERSONATE.
   ============================================================================ */
