-- ═══════════════════════════════════════════════════════════
-- ⚠️  AUDIT DISABLED BY DESIGN
-- ═══════════════════════════════════════════════════════════
-- Decision date: 2026-05-25
-- Rationale: 3 eligible admins, 1 active in practice
--
-- Known limitations:
-- - Cannot determine WHO changed a row
-- - Cannot determine WHEN a row was changed
-- - Cannot rollback to previous values via this schema
--
-- Mitigation: Delta Lake Time Travel (default 7-day retention)
--   SELECT * FROM table TIMESTAMP AS OF '2026-05-20'
--
-- To enable audit later (additive migration):
-- 1. ALTER TABLE ADD COLUMNS (updated_by STRING, updated_at TIMESTAMP)
-- 2. Update MERGE statement to set these fields
-- 3. Backfill is impossible — historical changes are lost
-- ═══════════════════════════════════════════════════════════

-- Ensure schema exists
CREATE SCHEMA IF NOT EXISTS cfg_master;

-- ───────────────────────────────────────────────────────────
-- Exclusion rule table: Hide Document Number per fiscal period
--
-- Composite PRIMARY KEY on (doc_num, fiscal_year, fiscal_month).
-- One Document Number can be hidden in many fiscal periods.
-- The triple is the unique identity.
--
-- Year/month stored as separate INT columns (not "YYYY-MM"
-- string) so filters like WHERE fiscal_year = 2026 work natively
-- without substring extraction.
--
-- Range CHECK constraints mirror the frontend input limits:
--   - Year input: min=2020 max=2099
--   - Month dropdown: 1 to 12
-- ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cfg_master.hide_document_number (
    doc_num       STRING  NOT NULL,
    fiscal_year   INT     NOT NULL,
    fiscal_month  INT     NOT NULL,
    CONSTRAINT pk_hide_document_number 
        PRIMARY KEY (doc_num, fiscal_year, fiscal_month),
    CONSTRAINT chk_fiscal_year  CHECK (fiscal_year  BETWEEN 2020 AND 2099),
    CONSTRAINT chk_fiscal_month CHECK (fiscal_month BETWEEN 1 AND 12)
) USING DELTA
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact'   = 'true'
);

-- ───────────────────────────────────────────────────────────
-- Reference table: NOT created here
-- cfg_master.sap_document_number_ref is populated by the
-- nightly SAP sync pipeline. This skill consumes it read-only.
-- ───────────────────────────────────────────────────────────
