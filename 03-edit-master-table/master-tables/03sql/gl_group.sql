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
-- ═══════════════════════════════════════════════════════════
-- 02_seed_reference.sql — reference table seed data
-- Source: docs/04gl code & gl group & gl thai name (master).xlsx
-- Seeded: 2026-05-25 — 18 groups, 137 GL codes
-- Safe to re-run (INSERT only if table is empty)
-- ═══════════════════════════════════════════════════════════

INSERT INTO cfg_master.gl_group_dim (group_id, group_name) VALUES
    ('6bb0620e-21f8-4b7b-a2e1-55130db8c702', 'Bank Charge'),
    ('c9937804-141f-483b-b0a5-7a134c7941d8', 'Communication Expense'),
    ('0f879748-1b5d-416d-b9ca-960a9528418d', 'Electricity & Water'),
    ('2b99c080-34dd-41b6-9061-dcfff4687270', 'Employee benefits'),
    ('0d935c42-2722-4ce9-8c0a-f2aa8e353a05', 'Entertainment'),
    ('4a2d19a5-90f1-4114-92f1-4ae2e325781d', 'Insurance Premium'),
    ('176d5f59-bf00-4f89-8d0c-80f4777a8f93', 'Lease & Rental'),
    ('dd44508c-c6d1-45b3-9861-38c6a40c9b84', 'Maintenance - License for software'),
    ('afc09935-39df-4b02-a679-b02dc2127996', 'Office expenses'),
    ('0cbdd0e4-51fb-4bde-9ca0-031891f8f685', 'Other admin. Expenses'),
    ('9c62d57c-f7bf-40b1-b032-6e49f0e0ff18', 'Other manpower exp (Per diem,Health check,Uniform…etc)'),
    ('bc4109ac-5062-47a5-a664-c5ca2606029e', 'Personal expenses'),
    ('18ed8d80-a050-4ff5-9c25-ce2da319f4b4', 'Professional & Legal Fee'),
    ('76c73dd0-aaab-493b-b0fd-13cdc8df37b0', 'Public Relation & Donation'),
    ('393b2bf7-6d68-4310-baff-dde5c480e90e', 'Remuneration of director'),
    ('704d9090-4e41-4a80-931c-db76644af1ec', 'Repair & Maintenance'),
    ('8eb7e169-4454-41eb-a47f-61217f6e81ae', 'Training & Seminar'),
    ('4df65d86-feaf-4f34-aaa6-40fe3652c1d5', 'Travelling Expense');

-- ── GL Code master (137 rows) ────────────────────────────────
IF NOT EXISTS (SELECT 1 FROM cfg_master.sap_gl_code_ref)
INSERT INTO cfg_master.sap_gl_code_ref (code, name) VALUES
    ('5211900030', 'Entertainment Expenses'),
    ('6211900031', 'Entertainment Exter.'),
    ('6211900030', 'Entertainment Expenses (External)'),
    ('5211200020', 'Lease & Rental - Building'),
    ('6211200020', 'Lease & Rental - Building'),
    ('5211200050', 'Lease & Rental - Computer Equipment'),
    ('6211200050', 'Lease & Rental - Computer Equipment'),
    ('5211200010', 'Lease & Rental - Land'),
    ('5211200030', 'Lease & Rental - Machinery & Equipment'),
    ('6211200030', 'Lease & Rental - Machinery & Equipment'),
    ('5211200040', 'Lease & Rental - Office Equipment'),
    ('5211200999', 'Lease & Rental - Other'),
    ('6211200999', 'Lease & Rental - Other'),
    ('5211200060', 'Lease & Rental - Vehicles'),
    ('6211200060', 'Lease & Rental - Vehicles'),
    ('6211200010', 'Lease&Rental-Land'),
    ('6211200040', 'Lease&Rental-Office'),
    ('6210700050', 'Audit Fee'),
    ('6210700030', 'Consulting fee-Legal'),
    ('6210700999', 'Consulting fee-Other'),
    ('6210700040', 'Consulting fee - Finance'),
    ('5210700030', 'Consulting fee - Legal'),
    ('5210700999', 'Consulting fee - Others'),
    ('5210700010', 'Consulting fee - Research and development'),
    ('6210700010', 'Consulting fee - Research and development'),
    ('5210700020', 'Consulting fee - Technical'),
    ('6210700020', 'Consulting fee - Technical'),
    ('5211900020', 'ISO Expense'),
    ('6210800020', 'Management fee - Related'),
    ('6210800010', 'Management fee - Subsidiaries'),
    ('6211700020', 'Community Relations Expenses'),
    ('6211700030', 'Donation'),
    ('6211700010', 'PR Production expenses'),
    ('6211400040', 'Bank Charge'),
    ('5211400040', 'Bank Charge'),
    ('6510200010', 'Front end fee'),
    ('5210600020', 'Communication Circuit - Rent/Service'),
    ('6210600020', 'Communication Circuit - Rent/Service'),
    ('5210600999', 'Other communication expenses'),
    ('6210600999', 'Other communication expenses'),
    ('5210900060', 'Service fee - Postage and Courier'),
    ('6210900060', 'Service fee - Postage and Courier'),
    ('6210600010', 'Telephone / Mobile'),
    ('5210600010', 'Telephone / Mobile'),
    ('6210500010', 'Electricity'),
    ('6210500020', 'Water'),
    ('5210500020', 'Water'),
    ('6210100070', 'Employee Benefit'),
    ('5210100070', 'Employee Benefit Expenses'),
    ('6211300999', 'Insurance Premium - Others'),
    ('5211300999', 'Insurance Premium - Others'),
    ('5211100110', 'Maintenance - License for software'),
    ('6211100110', 'Maintence- software'),
    ('5211800030', 'Expense Office Equipment, F&F (< 5,000 Baht)'),
    ('6211800030', 'Expense Office Equipment, F&F (< 5,000 Baht)'),
    ('5211800070', 'Gardening supplies'),
    ('6211800070', 'Gardening supplies'),
    ('5211800020', 'Janitorial Supplies'),
    ('6211800020', 'Janitorial Supplies'),
    ('5211800040', 'Office & Plant Supplies used'),
    ('6211800040', 'Office & Plant Supplies used'),
    ('5210900010', 'Service fee - Messenger'),
    ('6210900010', 'Service fee - Messenger'),
    ('5210900999', 'Service fee - Others'),
    ('6210900999', 'Service fee - Others'),
    ('5211800010', 'Stationery and printing supplies'),
    ('6211800010', 'Stationery and printing supplies'),
    ('6120300010', 'Diesel Usage'),
    ('6211400050', 'Fees for Listed Company'),
    ('5211800060', 'Laboratory & QC Supplies'),
    ('6211800060', 'Laboratory & QC Supplies'),
    ('6211400010', 'Membership fee'),
    ('5211400010', 'Membership fee'),
    ('6211900050', 'Miscelleneous Exp.'),
    ('5211900050', 'Miscelleneous Exp.'),
    ('5120300020', 'Oil Expenses'),
    ('6211400999', 'Other Fee'),
    ('5211400999', 'Other Fee - Cost Operation'),
    ('5211900040', 'Other Meeting'),
    ('6211900040', 'Other Meeting'),
    ('5211400020', 'Other Penalty & Claim'),
    ('6211400020', 'Other Penalty & Claim'),
    ('5210500999', 'Other Utility Expense'),
    ('6210500999', 'Other Utility Expense'),
    ('5120300030', 'Packaging Used'),
    ('6212000010', 'Property&Other Tax'),
    ('5212000010', 'Property, Sign - board & Other Tax'),
    ('5211800050', 'Safety Supplies'),
    ('6211800050', 'Safety Supplies'),
    ('6119900010', 'Sample Exp-Inven Cos'),
    ('5210900050', 'Service fee - Driver Services'),
    ('5210900040', 'Service fee - Packing Service'),
    ('5210900020', 'Service fee - Security Guard'),
    ('6210900020', 'Service fee - Security Guard'),
    ('5210900030', 'Service fee - Waste Treatment'),
    ('6211900070', 'Stockholder Meeting'),
    ('5211400030', 'Tax Penalty, Adjust, Non - refundable'),
    ('6211400030', 'Tax Penalty, Adjust, Non - refundable'),
    ('6211900060', 'Vehicle Expense'),
    ('5211900060', 'Vehicle Expense'),
    ('5210500030', 'Water plant supply'),
    ('6210300020', 'Compensation Fund'),
    ('6210300040', 'Fund for Empowerment of Persons with Disabilities'),
    ('5210100100', 'Health & Accidental Insurance'),
    ('6210100100', 'Health & Accidental Insurance'),
    ('5210100110', 'Health Check'),
    ('6210100110', 'Health Check'),
    ('6210100080', 'Other welfare'),
    ('5210100080', 'Other welfare'),
    ('5210400010', 'Per Diem'),
    ('6210400010', 'Per Diem'),
    ('5210100130', 'Recruiting Expenses'),
    ('5210100090', 'Uniform'),
    ('6210100090', 'Uniform'),
    ('5210100140', 'Personal Activity & Function'),
    ('6210100140', 'Personal Activity & Function'),
    ('6210100130', 'Recruiting Expenses'),
    ('6210200010', 'Remuneration of directors'),
    ('6211100030', 'Repair & Maintenance - Building Improvement'),
    ('5211100080', 'Repair & Maintenance - Computer Equipment'),
    ('6211100080', 'Repair & Maintenance - Computer Equipment'),
    ('5211100060', 'Repair & Maintenance - Furniture & Fixture'),
    ('6211100060', 'Repair & Maintenance - Furniture & Fixture'),
    ('6211100010', 'Repair & Maintenance - Land Improvement'),
    ('6211100040', 'Repair & Maintenance - Machinery & Equipment'),
    ('5211100070', 'Repair & Maintenance - Office Equipment'),
    ('6211100070', 'Repair & Maintenance - Office Equipment'),
    ('6211100090', 'RM-Vehicle'),
    ('6120500010', 'Spare parts & Consumables Usage'),
    ('6210100150', 'Training & Seminars Fee'),
    ('5210100150', 'Training & Seminars Fee'),
    ('5210400030', 'Accommodation'),
    ('6210400030', 'Accommodation'),
    ('6210400999', 'Other Travel Exp.'),
    ('5210400999', 'Other Travelling Expenses'),
    ('5210400020', 'Transportation'),
    ('6210400020', 'Transportation');
