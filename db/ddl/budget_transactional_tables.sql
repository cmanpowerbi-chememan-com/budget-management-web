/* ============================================================================
   budget_transactional_tables.sql
   ----------------------------------------------------------------------------
   Target DB : fabric_sql_database  (Microsoft Fabric SQL Database in the DW
               workspace cman-dw-ws, db id a42ef9f3) — the consolidated app DB.
               env FABRIC_SQL_SERVER / FABRIC_SQL_DATABASE re-point here (was
               DB1 "budget_management_web" 036a3270, now RETIRED); transactional, R/W.
   Schema    : budget (transactional; synced masters live in dbo in the SAME database)
   Scope     : the 5 TRANSACTIONAL tables the app WRITES (submission + approval).
               board_budget + submission_deadline are NOT here — they live in the
               dbo schema of THIS SAME database (read-only, pipeline-synced) — still
               not created by this file, and no FK (validated at the app layer).
   Source    : docs/specs/budget-transactional-data-model.md  §2 (grain),
               §3a (DBML), §4 (DQ rules), §4a (trip side).
   ADRs      : 0008 (approval_status PK = department/ฝ่าย × fiscal_year),
               0006 (frozen approver1 + log actions), 0013 (editing ≠ status),
               0005 (detail/trip), 0015 (per-diem is_auto_calc derived-on-read).

   HOW TO RUN: paste into the Fabric SQL query editor (or SSMS / Azure Data
               Studio) and execute. GO = batch separator.
   APPROVAL  : jakkaritw MUST review + approve before running on prod.
               This artifact is NOT executed by the agent.

   Notes on Fabric SQL Database T-SQL choices:
     - IDENTITY, clustered PK, and non-clustered indexes ARE supported here
       (this is the Azure-SQL engine, NOT the Fabric Warehouse).
     - NO persisted-computed columns: total_year is a plain STORED DECIMAL the
       app keeps in sync (Fabric SQL DB persisted-computed support is limited).
     - NO cross-schema FK to dbo (masters, employee — same DB) nor cross-store FK
       to the DW gold warehouse (fact_gl_trans) — validated at the app layer only.
     - timestamps default to SYSDATETIME().
   ============================================================================ */


/* -- 0. schema --------------------------------------------------------
   Create the budget schema if absent. The 5 transactional tables below
   live in budget.*; the synced read-only masters live in dbo.* in the
   SAME database (fabric_sql_database).                                   */
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE [name] = N'budget')
    EXEC (N'CREATE SCHEMA budget');
GO


/* -- 1. budget.pending_budget ----------------------------------------------
   Wide 12-month pending budget, user-entered. Grain = (cost_center, gl_account,
   fiscal_year). NO status column (status lives on approval_status, spec §5 Q4).
   total_year = STORED snapshot of SUM(m01..m12) (spec §4; not a computed col).
   Dimension cols (gl_name..department) are re-derived snapshots (spec §4).      */
CREATE TABLE budget.pending_budget (
    [cost_center]  NVARCHAR(20)   NOT NULL,
    [gl_account]   NVARCHAR(20)   NOT NULL,
    [fiscal_year]  INT            NOT NULL,
    [m01]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m02]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m03]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m04]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m05]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m06]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m07]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m08]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m09]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m10]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m11]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m12]          DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [total_year]   DECIMAL(18,2)  NOT NULL DEFAULT 0,   -- STORED snapshot = SUM(m01..m12)
    [template]     NVARCHAR(10)   NOT NULL DEFAULT N'USER',  -- USER (Template 1.1) | ADMIN (Template 2)
    [remark]       NVARCHAR(500)  NULL,
    [gl_name]      NVARCHAR(200)  NULL,   -- re-derived snapshot
    [gl_group]     NVARCHAR(200)  NULL,   -- re-derived; decides normal vs special (subform)
    [c_level]      NVARCHAR(150)  NULL,   -- re-derived snapshot
    [division]     NVARCHAR(150)  NULL,   -- re-derived snapshot
    [department]   NVARCHAR(150)  NULL,   -- re-derived snapshot
    [_user]        NVARCHAR(150)  NOT NULL,
    [_updated_at]  DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_pending_budget PRIMARY KEY ([cost_center], [gl_account], [fiscal_year]),
    CONSTRAINT ck_pending_budget_template CHECK ([template] IN (N'USER', N'ADMIN'))
);
GO
CREATE INDEX ix_pb_cc_year_gl ON budget.pending_budget ([cost_center], [fiscal_year], [gl_account]);
CREATE INDEX ix_pb_gl_year    ON budget.pending_budget ([gl_account], [fiscal_year]);
GO


/* -- 2. budget.pending_budget_detail ---------------------------------------
   Special-GL subform lines (many per GL cell). The parent cell = SUM of these
   lines. trip_id set only for Travelling lines. is_auto_calc=1 → per-diem line
   whose m01..m12 are DERIVED ON READ (spec §4 / ADR-0015); the stored months
   are non-authoritative for those lines.                                        */
CREATE TABLE budget.pending_budget_detail (
    [detail_id]     BIGINT         NOT NULL IDENTITY(1,1),
    [cost_center]   NVARCHAR(20)   NOT NULL,
    [gl_account]    NVARCHAR(20)   NOT NULL,
    [fiscal_year]   INT            NOT NULL,
    [trip_id]       BIGINT         NULL,   -- FK to budget_trip (app-validated); NULL for non-Travelling
    [gl_group]      NVARCHAR(200)  NOT NULL,
    [line_label]    NVARCHAR(300)  NULL,
    [m01]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m02]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m03]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m04]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m05]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m06]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m07]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m08]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m09]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m10]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m11]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [m12]           DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [total_year]    DECIMAL(18,2)  NOT NULL DEFAULT 0,
    [meta_json]     NVARCHAR(MAX)  NULL,   -- group-specific fields as JSON (spec §4/§4a)
    [is_auto_calc]  BIT            NOT NULL DEFAULT 0,  -- 1 = per-diem auto (derived-on-read)
    [_user]         NVARCHAR(150)  NOT NULL,
    [_updated_at]   DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_pending_budget_detail PRIMARY KEY ([detail_id])
);
GO
CREATE INDEX ix_pbd_parent ON budget.pending_budget_detail ([cost_center], [gl_account], [fiscal_year]);
CREATE INDEX ix_pbd_trip   ON budget.pending_budget_detail ([trip_id]);
GO


/* -- 3. budget.budget_trip -------------------------------------------------
   Travelling trip header, shared across the (up to 4) travel-GL detail lines
   of one trip. side = COST | SGA — ONE side per trip (spec §4a); all detail
   lines of a trip_id must post to that side's GLs (enforced at app layer).       */
CREATE TABLE budget.budget_trip (
    [trip_id]           BIGINT         NOT NULL IDENTITY(1,1),
    [cost_center]       NVARCHAR(20)   NOT NULL,
    [fiscal_year]       INT            NOT NULL,
    [traveler_empcode]  NVARCHAR(20)   NULL,   -- FK to dbo.v_employee_primary.employee_code (app-validated; VIEW, full 612-row roster)
    [traveler_name]     NVARCHAR(200)  NOT NULL,   -- fullnameth snapshot
    [position]          NVARCHAR(150)  NULL,   -- joblevel snapshot; drives per-diem rate
    [destination]       NVARCHAR(200)  NULL,
    [country_group]     TINYINT        NOT NULL,   -- 1 domestic (no FX) / 2 asian / 3 other
    [days]              INT            NOT NULL DEFAULT 0,
    [travel_months]     NVARCHAR(40)   NOT NULL,   -- comma list of months e.g. 03,09
    [purpose]           NVARCHAR(500)  NULL,
    [project]           NVARCHAR(200)  NULL,   -- free-text project name (template col F); added to a live table via setup/migrate_budget_trip_project.py
    [side]              NVARCHAR(4)    NOT NULL,   -- COST | SGA (one side per trip, spec §4a)
    [client_token]      NVARCHAR(64)   NULL,   -- idempotency token for POST create (one per new-trip intent, client-generated); NULL = legacy/token-less create, unconstrained
    [_user]             NVARCHAR(150)  NOT NULL,
    [_updated_at]       DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_budget_trip PRIMARY KEY ([trip_id]),
    CONSTRAINT ck_budget_trip_country_group CHECK ([country_group] IN (1, 2, 3)),
    CONSTRAINT ck_budget_trip_side          CHECK ([side] IN (N'COST', N'SGA'))
);
GO
CREATE INDEX ix_trip_cc_year ON budget.budget_trip ([cost_center], [fiscal_year]);
GO
/* Idempotent create (network retry / double-click): a repeated POST with the
   same token from the same user returns the existing trip instead of a
   duplicate. Dedup key = (client_token, _user) ONLY — NEVER trip content
   (two genuinely-identical trips are legitimate). Filtered so legacy
   NULL-token rows stay unconstrained.
   Added to a live table via setup/migrate_budget_trip_client_token.py.     */
CREATE UNIQUE INDEX ux_trip_client_token_user
    ON budget.budget_trip ([client_token], [_user])
    WHERE [client_token] IS NOT NULL;
GO


/* -- 4. budget.approval_status ---------------------------------------------
   Current approval state per approval unit = ฝ่าย × fiscal_year (ADR-0008).
   ALL CCs of one ฝ่าย are approved as one record. Replaced on re-submit
   (last-submitter-wins). approver2/3 are fixed people (Nipaporn/Waraporn) so
   only their actioned_at is stored; approver1 empcode is frozen at submit.       */
CREATE TABLE budget.approval_status (
    [department]             NVARCHAR(150)  NOT NULL,   -- ฝ่าย — approval unit key (ADR-0008)
    [fiscal_year]            INT            NOT NULL,
    [status]                 NVARCHAR(40)   NOT NULL DEFAULT N'DRAFT',
    -- status enum: DRAFT, PENDING_APPROVER1, PENDING_APPROVER2, PENDING_APPROVER3, APPROVED, REJECTED
    [submitter_empcode]      NVARCHAR(20)   NULL,   -- owner of record; last submitter wins
    [submitter_email]        NVARCHAR(255)  NULL,
    [submitted_at]           DATETIME2      NULL,
    [approver1_empcode]      NVARCHAR(20)   NULL,   -- managerempcode frozen at submit (ADR-0006)
    [approver1_actioned_at]  DATETIME2      NULL,
    [approver2_actioned_at]  DATETIME2      NULL,   -- Nipaporn (Budget Staff)
    [approver3_actioned_at]  DATETIME2      NULL,   -- Waraporn (Budget Manager, final)
    [reject_reason]          NVARCHAR(1000) NULL,
    [rejected_by_empcode]    NVARCHAR(20)   NULL,
    [_updated_at]            DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
    CONSTRAINT pk_approval_status PRIMARY KEY ([department], [fiscal_year])
);
GO
CREATE INDEX ix_as_year_status ON budget.approval_status ([fiscal_year], [status]);
CREATE INDEX ix_as_approver1   ON budget.approval_status ([approver1_empcode], [fiscal_year]);
GO


/* -- 5. budget.approval_log ------------------------------------------------
   Append-only history of every approval action (ADR-0006). INSERT only;
   never UPDATE/DELETE. action covers SUBMIT/APPROVE/REJECT/RESUBMIT plus the
   automated/admin actions AUTO_SUBMIT/AUTO_ESCALATE/ADMIN_SUBMIT/ADMIN_OVERRIDE. */
CREATE TABLE budget.approval_log (
    [log_id]             BIGINT         NOT NULL IDENTITY(1,1),
    [department]         NVARCHAR(150)  NOT NULL,   -- ฝ่าย — matches the approval unit (ADR-0008)
    [fiscal_year]        INT            NOT NULL,
    [action]             NVARCHAR(40)   NOT NULL,
    [action_by_empcode]  NVARCHAR(20)   NULL,
    [action_by_email]    NVARCHAR(255)  NOT NULL,
    [action_at]          DATETIME2      NOT NULL DEFAULT SYSDATETIME(),
    [previous_status]    NVARCHAR(40)   NULL,
    [new_status]         NVARCHAR(40)   NULL,
    [comment]            NVARCHAR(1000) NULL,
    CONSTRAINT pk_approval_log PRIMARY KEY ([log_id])
);
GO
CREATE INDEX ix_log_dept_year ON budget.approval_log ([department], [fiscal_year]);
CREATE INDEX ix_log_at        ON budget.approval_log ([action_at]);
GO

/* ============================================================================
   END — 5 tables, schema budget (in fabric_sql_database; dbo holds synced masters).
         Index count (non-clustered, excl. PKs) = 9.
   Do NOT run on prod without jakkaritw approval.
   ============================================================================ */
