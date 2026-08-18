-- ============================================================
-- Budget Management Web — Azure SQL Schema
-- ============================================================

-- 1. USER DIVISION MAP
-- Maps each user to their division, role, and approver chain
CREATE TABLE user_division_map (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    email           NVARCHAR(255)   NOT NULL UNIQUE,
    full_name       NVARCHAR(255)   NOT NULL,
    division        NVARCHAR(255)   NOT NULL,
    department      NVARCHAR(255)   NOT NULL,
    role            NVARCHAR(50)    NOT NULL,  -- 'user', 'vp', 'budget_staff', 'budget_manager', 'admin'
    vp_email        NVARCHAR(255)   NULL,       -- VP/AVP of this user's division
    cost_center     NVARCHAR(50)    NULL,
    is_active       BIT             NOT NULL DEFAULT 1,
    created_at      DATETIME2       NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME2       NOT NULL DEFAULT GETDATE()
);

-- 2. BUDGET SUBMISSIONS
-- Stores monthly budget input per GL Account per division per fiscal year
CREATE TABLE budget_submissions (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    fiscal_year     INT             NOT NULL,
    division        NVARCHAR(255)   NOT NULL,
    department      NVARCHAR(255)   NOT NULL,
    cost_center     NVARCHAR(50)    NOT NULL,
    gl_account      NVARCHAR(20)    NOT NULL,
    gl_account_name NVARCHAR(255)   NOT NULL,
    gl_group        NVARCHAR(255)   NOT NULL,
    template_type   NVARCHAR(50)    NOT NULL,  -- 'opex', 'budget_dept'
    m01             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m02             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m03             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m04             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m05             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m06             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m07             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m08             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m09             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m10             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m11             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    m12             DECIMAL(18,2)   NOT NULL DEFAULT 0,
    total_year      AS (m01+m02+m03+m04+m05+m06+m07+m08+m09+m10+m11+m12),  -- computed
    remark          NVARCHAR(500)   NULL,
    status          NVARCHAR(50)    NOT NULL DEFAULT 'DRAFT',
    submitted_by    NVARCHAR(255)   NOT NULL,
    created_at      DATETIME2       NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME2       NOT NULL DEFAULT GETDATE(),
    updated_by      NVARCHAR(255)   NOT NULL
);

-- 3. APPROVAL STATUS
-- One row per division + fiscal_year — tracks current approval state
CREATE TABLE approval_status (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    fiscal_year     INT             NOT NULL,
    division        NVARCHAR(255)   NOT NULL,
    status          NVARCHAR(50)    NOT NULL DEFAULT 'DRAFT',
    -- DRAFT → PENDING_VP → PENDING_BUDGET_STAFF → PENDING_MANAGER → APPROVED
    -- or → REJECTED_BY_VP / REJECTED_BY_STAFF / REJECTED_BY_MANAGER
    submitted_by    NVARCHAR(255)   NULL,
    submitted_at    DATETIME2       NULL,
    vp_email        NVARCHAR(255)   NULL,
    vp_actioned_at  DATETIME2       NULL,
    staff_actioned_at   DATETIME2   NULL,
    manager_actioned_at DATETIME2   NULL,
    reject_reason   NVARCHAR(1000)  NULL,
    created_at      DATETIME2       NOT NULL DEFAULT GETDATE(),
    updated_at      DATETIME2       NOT NULL DEFAULT GETDATE(),
    CONSTRAINT uq_approval_status UNIQUE (fiscal_year, division)
);

-- 4. APPROVAL LOG
-- Full history of every action taken (approve / reject / submit / upload / download)
CREATE TABLE approval_log (
    id              INT IDENTITY(1,1) PRIMARY KEY,
    fiscal_year     INT             NOT NULL,
    division        NVARCHAR(255)   NOT NULL,
    action          NVARCHAR(50)    NOT NULL,
    -- 'SUBMIT', 'APPROVE_VP', 'REJECT_VP', 'APPROVE_STAFF', 'REJECT_STAFF',
    -- 'APPROVE_MANAGER', 'REJECT_MANAGER', 'UPLOAD_ACTUALS', 'DOWNLOAD'
    action_by       NVARCHAR(255)   NOT NULL,
    action_at       DATETIME2       NOT NULL DEFAULT GETDATE(),
    comment         NVARCHAR(1000)  NULL,
    previous_status NVARCHAR(50)    NULL,
    new_status      NVARCHAR(50)    NULL
);

-- 5. SUBMISSION DEADLINE
-- Admin sets deadline per fiscal year — system locks form when reached.
-- Live shape verified 2026-07-31 (dbo.submission_deadline on Fabric SQL):
-- the closing DAY/MONTH/YEAR + reminder_day are INT inputs; the REAL dates
-- are the precomputed `deadline_date` / `reminder_date` columns — always
-- read those two. ⚠ `closing_date` here is an INT day-of-month (31), NOT a
-- date — reading it as one already caused one caught-before-deploy bug in
-- jobs/send_reminders.py (2026-07-31).
CREATE TABLE submission_deadline (
    fiscal_year     INT             NOT NULL,
    closing_date    INT             NULL,   -- day-of-month INPUT (e.g. 31), not a date
    closing_month   INT             NULL,
    closing_year    INT             NULL,
    reminder_day    INT             NULL,   -- COUNT OF DAYS BEFORE the deadline
                                            -- (corrected 2026-08-18: was read as a
                                            -- day-of-month; DW commit 7f51775)
    deadline_date   DATE            NULL,   -- real closing date (precomputed) — read THIS
    reminder_date   DATE            NULL,   -- real first-reminder date (precomputed)
    _load_dt        DATE            NULL,
    _load_dttm      DATETIME2       NULL
);

-- 6. REMINDER LOG (live: budget.reminder_log — db/ddl/budget_reminder_log.sql)
-- 7-day reminder cadence bookkeeping for jobs/send_reminders.py
-- (2026-07-31 email-notification revamp + §7 grouping rework). One row per
-- reminder stream, updated in place after each successful send; dry-runs
-- never write. department = sentinel '*' for both types (§7.2): reminder
-- mails are grouped PER PERSON, so cadence is per-person-per-year — a ฝ่าย
-- newly pending mid-week rides the person's next 7-day round (accepted
-- trade-off; event mails still fire instantly).
CREATE TABLE budget.reminder_log (
    reminder_type   VARCHAR(20)     NOT NULL,  -- 'turn' | 'deadline'
    department      NVARCHAR(200)   NOT NULL,  -- sentinel '*' (§7.2 per-person grouping)
    fiscal_year     INT             NOT NULL,
    recipient       NVARCHAR(320)   NOT NULL,  -- empcode (turn) / email (deadline)
    sent_at         DATETIME2       NOT NULL,
    CONSTRAINT pk_reminder_log PRIMARY KEY (reminder_type, department, fiscal_year, recipient)
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX ix_budget_submissions_division_year
    ON budget_submissions (fiscal_year, division);

CREATE INDEX ix_approval_status_division_year
    ON approval_status (fiscal_year, division);

CREATE INDEX ix_approval_log_division_year
    ON approval_log (fiscal_year, division);
