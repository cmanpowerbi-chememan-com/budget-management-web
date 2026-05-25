-- ═══════════════════════════════════════════════════════════
-- MERGE upsert template (parameterized)
-- ═══════════════════════════════════════════════════════════
-- Composite PK on (doc_num, fiscal_year, fiscal_month).
--
-- ⚠️ ALL THREE PK columns MUST appear in the ON clause.
-- Using only 1 or 2 columns would throw
-- DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE
-- whenever the same doc_num is hidden across multiple periods.
--
-- Source is deduplicated with SELECT DISTINCT to guard against
-- duplicate rows in the same batch.
--
-- No WHEN MATCHED clause: pure exclusion table, all columns
-- are PK, nothing to update. If the triple already exists,
-- the MERGE is a no-op.
-- ═══════════════════════════════════════════════════════════

MERGE INTO cfg_master.hide_document_number t
USING (
    SELECT DISTINCT
        :doc_num      AS doc_num,
        :fiscal_year  AS fiscal_year,
        :fiscal_month AS fiscal_month
) s
ON  t.doc_num      = s.doc_num
AND t.fiscal_year  = s.fiscal_year
AND t.fiscal_month = s.fiscal_month
WHEN NOT MATCHED THEN INSERT (doc_num, fiscal_year, fiscal_month)
VALUES (s.doc_num, s.fiscal_year, s.fiscal_month);
