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
-- Junction table: Orgcode × Cost Center (many-to-many)
-- 
-- Composite PRIMARY KEY on (cost_center, orgcode).
-- One Cost Center can map to many Orgcodes; one Orgcode can
-- map to many Cost Centers. The pair is the unique identity.
--
-- No non-PK columns — this is a pure relationship table.
-- ───────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS cfg_master.orgcode_costcenter (
    cost_center  STRING  NOT NULL,
    orgcode      STRING  NOT NULL,
    CONSTRAINT pk_orgcode_costcenter PRIMARY KEY (cost_center, orgcode),
    CONSTRAINT chk_cost_center_format CHECK (cost_center RLIKE '^[0-9A-Z]+$')
) USING DELTA
TBLPROPERTIES (
    'delta.autoOptimize.optimizeWrite' = 'true',
    'delta.autoOptimize.autoCompact'   = 'true'
);

-- ───────────────────────────────────────────────────────────
-- Reference table: NOT created here
-- cfg_master.sap_orgcode_ref is populated by the nightly SAP
-- sync pipeline. This skill consumes it read-only.
-- ───────────────────────────────────────────────────────────
