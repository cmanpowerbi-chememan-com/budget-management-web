-- ═══════════════════════════════════════════════════════════════════
-- cfg_master.hide_document_number — T-SQL for Fabric SQL Database
--
-- Composite PK 3 cols: (doc_num, fiscal_year, fiscal_month)
-- doc_num: SAP accounting_doc_number (10 digits expected; checked at API layer)
-- fiscal_year: 2020-2099 (CHECK constraint backstop)
-- fiscal_month: 1-12 (CHECK constraint backstop)
--
-- No audit columns — admin team is 2 people, traceability not required at this scale.
-- ═══════════════════════════════════════════════════════════════════

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'cfg_master')
    EXEC('CREATE SCHEMA cfg_master');
GO

IF OBJECT_ID('cfg_master.hide_document_number', 'U') IS NULL
BEGIN
    CREATE TABLE cfg_master.hide_document_number (
        doc_num       NVARCHAR(30) NOT NULL,
        fiscal_year   INT          NOT NULL,
        fiscal_month  INT          NOT NULL,
        CONSTRAINT pk_hide_document_number PRIMARY KEY (doc_num, fiscal_year, fiscal_month),
        CONSTRAINT chk_hide_document_number_fiscal_year  CHECK (fiscal_year  BETWEEN 2020 AND 2099),
        CONSTRAINT chk_hide_document_number_fiscal_month CHECK (fiscal_month BETWEEN 1 AND 12)
    );
END
GO

-- Verify
SELECT name, type_desc
FROM sys.objects
WHERE schema_id = SCHEMA_ID('cfg_master')
  AND name = 'hide_document_number';

SELECT name, type_desc
FROM sys.objects
WHERE parent_object_id = OBJECT_ID('cfg_master.hide_document_number');
