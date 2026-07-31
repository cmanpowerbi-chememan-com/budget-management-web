/* ============================================================================
   budget_reminder_log.sql
   ----------------------------------------------------------------------------
   Target DB : fabric_sql_database  (Microsoft Fabric SQL Database in the DW
               workspace cman-dw-ws) — the SAME consolidated app DB as
               budget_transactional_tables.sql; transactional, R/W.
   Schema    : budget
   Scope     : ONE table — budget.reminder_log, the cadence bookkeeping for
               the 2026-07-31 email-notification revamp
               (plan/email-notify-revamp.md §3.3). Written ONLY by
               backend/jobs/send_reminders.py (7-day turn reminders +
               7-day per-department deadline reminders).

   HOW TO RUN: paste into the Fabric SQL query editor (or SSMS / Azure Data
               Studio) and execute. GO = batch separator.
   APPROVAL  : jakkaritw MUST review + approve before running on the shared
               staging/prod DB. This artifact is NOT executed by the agent.

   Design notes:
     - PK = (reminder_type, department, fiscal_year, recipient): one row per
       reminder stream, UPDATEd in place on every repeat send — the job only
       ever needs MAX(sent_at) per stream, so history is deliberately NOT
       kept here (the send itself is the audit; approval_log stays the
       business-action audit).
     - recipient is NVARCHAR(320) to hold EITHER an empcode (turn reminders:
       the current approver, so an approver change naturally starts a fresh
       cadence) OR an email (deadline reminders: the filler).
     - No FK to budget.approval_status / dbo masters — same app-layer
       validation posture as the other transactional tables.
   ============================================================================ */


/* -- 0. schema --------------------------------------------------------
   The budget schema already exists (budget_transactional_tables.sql);
   guard kept so this file is runnable standalone.                       */
IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE [name] = N'budget')
    EXEC (N'CREATE SCHEMA budget');
GO

/* -- 1. budget.reminder_log ------------------------------------------- */
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON s.schema_id = t.schema_id
    WHERE s.[name] = N'budget' AND t.[name] = N'reminder_log'
)
BEGIN
    CREATE TABLE budget.reminder_log (
        reminder_type  varchar(20)   NOT NULL,  -- 'turn' | 'deadline'
        department     nvarchar(200) NOT NULL,
        fiscal_year    int           NOT NULL,
        recipient      nvarchar(320) NOT NULL,  -- empcode (turn) / email (deadline)
        sent_at        datetime2     NOT NULL,
        CONSTRAINT pk_reminder_log PRIMARY KEY (reminder_type, department, fiscal_year, recipient)
    );
END
GO
