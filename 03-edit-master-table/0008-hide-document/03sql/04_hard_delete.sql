-- ═══════════════════════════════════════════════════════════
-- Hard DELETE template (parameterized)
-- Locked decision #22: hard delete + simple confirm modal
--
-- ⚠️ CRITICAL: WHERE clause MUST include all 3 PK columns.
--
-- If only doc_num were used → would delete the exclusion rule
-- across EVERY fiscal period for that document. Catastrophic.
--
-- If only (doc_num, fiscal_year) → would delete all 12 months
-- of that year's exclusions. Still very bad.
-- ═══════════════════════════════════════════════════════════

DELETE FROM cfg_master.hide_document_number
WHERE doc_num      = :doc_num
  AND fiscal_year  = :fiscal_year
  AND fiscal_month = :fiscal_month;
