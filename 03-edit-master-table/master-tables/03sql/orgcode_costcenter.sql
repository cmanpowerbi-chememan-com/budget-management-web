-- ═══════════════════════════════════════════════════════════
-- cfg_master.orgcode_costcenter_map — T-SQL for Fabric SQL Database
--
-- Junction table mapping SAP Orgcode <-> Cost Center (many-to-many).
-- Reflects production schema verified 2026-05-30.
--
-- No audit columns — 2-admin policy (project-context.md).
-- ═══════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'cfg_master')
    EXEC('CREATE SCHEMA cfg_master');
GO

IF OBJECT_ID('cfg_master.orgcode_costcenter_map', 'U') IS NULL
BEGIN
    CREATE TABLE cfg_master.orgcode_costcenter_map (
        id           INT          IDENTITY(1,1) NOT NULL,
        orgcode      NVARCHAR(20) NOT NULL,
        cost_center  NVARCHAR(20) NOT NULL,
        CONSTRAINT pk_orgcode_costcenter_map PRIMARY KEY (id),
        CONSTRAINT uq_orgcode_costcenter UNIQUE (orgcode, cost_center)
    );
END
GO

-- Verify
SELECT name, type_desc
FROM sys.objects
WHERE parent_object_id = OBJECT_ID('cfg_master.orgcode_costcenter_map');
