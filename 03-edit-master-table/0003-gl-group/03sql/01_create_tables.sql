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
-- Mitigation: Fabric SQL Database point-in-time restore
--
-- To enable audit later (additive migration):
-- 1. ALTER TABLE ADD COLUMN updated_by NVARCHAR(100), updated_at DATETIME2
-- 2. Update MERGE statement to set these fields
-- 3. Backfill is impossible — historical changes are lost
-- ═══════════════════════════════════════════════════════════

-- Target: Fabric SQL Database (T-SQL)
-- Safe to re-run — IF NOT EXISTS guards on all objects

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'cfg_master')
    EXEC('CREATE SCHEMA cfg_master');
GO

-- ───────────────────────────────────────────────────────────
-- Dimension table: GL Group
-- Stable group_id (UUID) so renaming a group is UPDATE 1 row,
-- not UPDATE many rows in the mapping table.
-- ───────────────────────────────────────────────────────────
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = 'cfg_master' AND t.name = 'gl_group_dim'
)
CREATE TABLE cfg_master.gl_group_dim (
    group_id    NVARCHAR(50)  NOT NULL,
    group_name  NVARCHAR(200) NOT NULL,
    CONSTRAINT pk_gl_group_dim PRIMARY KEY (group_id)
);
GO

-- ───────────────────────────────────────────────────────────
-- Mapping table: GL Code → GL Group
-- Single PK on gl_code. Each GL code maps to exactly one group.
-- group_id is FK to gl_group_dim (enforced at app layer).
-- ───────────────────────────────────────────────────────────
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = 'cfg_master' AND t.name = 'gl_group_mapping'
)
CREATE TABLE cfg_master.gl_group_mapping (
    gl_code   NVARCHAR(20) NOT NULL,
    group_id  NVARCHAR(50) NOT NULL,
    CONSTRAINT pk_gl_group_mapping PRIMARY KEY (gl_code),
    CONSTRAINT chk_gl_code_format CHECK (gl_code NOT LIKE '%[^0-9]%')
);
GO

-- ───────────────────────────────────────────────────────────
-- Reference table: GL Code master
-- Seeded from docs/04gl code & gl group & gl thai name (master).xlsx
-- (137 rows). Until a nightly SAP sync is built, this is static.
-- ───────────────────────────────────────────────────────────
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = 'cfg_master' AND t.name = 'sap_gl_code_ref'
)
CREATE TABLE cfg_master.sap_gl_code_ref (
    code  NVARCHAR(20)  NOT NULL,
    name  NVARCHAR(200) NOT NULL,
    CONSTRAINT pk_sap_gl_code_ref PRIMARY KEY (code)
);
GO
